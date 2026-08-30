#!/usr/bin/env bash
# Load one archive file into the aggregates, then delete it.
#   scripts/load.sh data/raw/aisdk-2025-07-16.zip
#   scripts/load.sh --force data/raw/aisdk-2025-07-16.zip   reload a logged file
#   scripts/load.sh --limit 2000000 <zip>                   load a sample only
#
# Idempotent two ways. A file already in load_log is skipped (scripts/run_queue.sh
# in S3 relies on that). And the file's own date range is deleted from all three
# tables before the aggregates are written, unconditionally: on a fresh day that
# is a no-op, on a day left half-loaded by a crash it is the cleanup. Recovery
# therefore needs no human to remember a flag.
#
# The range comes from min(ts)/max(ts) of the staged data, never from the file
# name — a name can lie, the rows cannot.
#
# Any failure exits non-zero and KEEPS the zip. Raw data is deleted only after
# the load is logged.
set -euo pipefail
cd "$(dirname "$0")/.."

force=0
# UInt64 max, because ClickHouse reads LIMIT 0 as "zero rows".
limit=18446744073709551615
while :; do
  case "${1:-}" in
    --force) force=1; shift ;;
    # A cap is a flag, never ambient state. A truncated load that still deleted
    # its archive would silently lose most of a day with no way to notice: the
    # log row looks complete, and S3's run_queue.sh would skip the file forever.
    # So a capped run keeps the zip, and says so.
    --limit) limit="${2:?--limit needs a row count}"; shift 2 ;;
    *) break ;;
  esac
done
zip="${1:?usage: scripts/load.sh [--force] <archive.zip>}"
[ -f "$zip" ] || { echo "no such file: $zip" >&2; exit 1; }
base="$(basename "$zip")"

trap 'echo "FAILED  $base — zip kept. Re-run: the date range is deleted and rewritten." >&2' ERR

ch() { scripts/ch.sh "$@"; }

ch sql/01_schema.sql

if [ "$force" = 0 ] && \
   [ "$(ch -q "SELECT count() FROM load_log WHERE file = {f:String}" --param_f "$base")" != 0 ]; then
  echo "skip    $base (already in load_log)"
  exit 0
fi

t_start=$(date +%s)

ch sql/02_stage.sql --param_src "$zip :: *.csv" --param_lim "$limit"

# One pass over the stage for every number load_log records. The four row
# counters partition rows_read exactly; test_load.sh asserts that they do.
read -r rows_read non_vessel sentinel oob kept ts0 ts1 <<<"$(ch -q "
SELECT count(),
       countIf(mobile NOT IN ('Class A', 'Class B')),
       countIf(mobile IN ('Class A', 'Class B') AND abs(lat) > 90),
       countIf(mobile IN ('Class A', 'Class B') AND abs(lat) <= 90
               AND NOT (lat BETWEEN 53 AND 59 AND lon BETWEEN 3 AND 17)),
       countIf(mobile IN ('Class A', 'Class B')
               AND lat BETWEEN 53 AND 59 AND lon BETWEEN 3 AND 17),
       toUnixTimestamp(min(ts)), toUnixTimestamp(max(ts))
FROM ais_raw_stage")"

[ "$rows_read" -gt 0 ] || { echo "empty archive: $base — staged 0 rows, zip kept" >&2; exit 1; }

# Delete this file's range first, so a re-run replaces rather than doubles.
# Monthly partitioning prunes these to the months actually touched.
ch -q "
DELETE FROM h3_hourly    WHERE hour BETWEEN toStartOfHour(toDateTime({t0:UInt32}, 'UTC'))
                                        AND toDateTime({t1:UInt32}, 'UTC');
DELETE FROM vessel_day   WHERE day  BETWEEN toDate(toDateTime({t0:UInt32}, 'UTC'))
                                        AND toDate(toDateTime({t1:UInt32}, 'UTC'));
DELETE FROM public_track WHERE ts   BETWEEN toStartOfMinute(toDateTime({t0:UInt32}, 'UTC'))
                                        AND toDateTime({t1:UInt32}, 'UTC');
DELETE FROM load_log     WHERE file = {f:String};
" --param_t0 "$ts0" --param_t1 "$ts1" --param_f "$base"

ch sql/03_aggregate.sql

secs=$(( $(date +%s) - t_start ))

# The range was deleted immediately above and written by a single grouped
# INSERT, so a plain count() over it is this file's own contribution.
ch -q "
INSERT INTO load_log SELECT
    {f:String}, now('UTC'), {sec:Float32},
    toDateTime({t0:UInt32}, 'UTC'), toDateTime({t1:UInt32}, 'UTC'),
    {read:UInt64}, {nonv:UInt64}, {sent:UInt64}, {oob:UInt64}, {kept:UInt64},
    (SELECT count() FROM h3_hourly    WHERE hour BETWEEN toStartOfHour(toDateTime({t0:UInt32}, 'UTC'))
                                                     AND toDateTime({t1:UInt32}, 'UTC')),
    (SELECT count() FROM vessel_day   WHERE day  BETWEEN toDate(toDateTime({t0:UInt32}, 'UTC'))
                                                     AND toDate(toDateTime({t1:UInt32}, 'UTC'))),
    (SELECT count() FROM public_track WHERE ts   BETWEEN toStartOfMinute(toDateTime({t0:UInt32}, 'UTC'))
                                                     AND toDateTime({t1:UInt32}, 'UTC'))
" --param_f "$base" --param_sec "$secs" --param_t0 "$ts0" --param_t1 "$ts1" \
  --param_read "$rows_read" --param_nonv "$non_vessel" --param_sent "$sentinel" \
  --param_oob "$oob" --param_kept "$kept"

# DROP ... SYNC, not TRUNCATE. TRUNCATE leaves the old parts inactive, and
# `clickhouse local` exits before the background cleaner runs, so they are never
# collected: one daily file leaves ~58 MB of dead stage behind, which over the
# 900 files of S4 is ~52 GB against a 70 GB budget. sql/01_schema.sql recreates
# the table at the top of the next load.
ch -q "DROP TABLE IF EXISTS ais_raw_stage SYNC; DROP TABLE IF EXISTS ais_vessel_stage SYNC"

# Only a complete load makes the raw file expendable.
if [ "$limit" = 18446744073709551615 ]; then
  rm -f "$zip" "$zip.ok"
  disposition="zip removed"
else
  disposition="CAPPED at $limit rows — zip KEPT, this day is incomplete"
fi
trap - ERR

printf 'loaded  %s: %s rows read, %s kept in %ss (%s rows/s), %s\n' \
  "$base" "$rows_read" "$kept" "$secs" "$(( rows_read / (secs > 0 ? secs : 1) ))" "$disposition"
