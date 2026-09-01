#!/usr/bin/env bash
# Load one archive file into the aggregates, then delete it.
#   scripts/load.sh data/raw/aisdk-2025-07-16.zip
#   scripts/load.sh --force data/raw/aisdk-2025-07-16.zip   reload a logged file
#   scripts/load.sh --limit 2000000 <zip>                   load a sample only
#
# Idempotent two ways. A file already in load_log is skipped (scripts/run_queue.sh
# in S3 relies on that). And the file's own date range is deleted from all three
# tables before the aggregates are written whenever anything is there: on a fresh
# day that costs nothing, on a day left half-loaded by a crash it is the cleanup.
# Recovery therefore needs no human to remember a flag.
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

# `**`, not `*`. A daily zip holds one CSV at the root; a monthly zip holds 31
# under FtpRoot/ais_data/ — and which of the two it is varies month to month
# (2015-01 root, 2015-07 subdirectory, 2017-01 subdirectory, 2017-07 root), so
# no rule on the file name can predict it. ClickHouse's `*` does not cross a
# `/`, and a glob that matches nothing is not an error: the first attempt at a
# monthly file staged 0 rows in silence. `**` matches both layouts.
src="$zip :: **/*.csv"

# Two CSV dialects live in this archive. From 2016-10 on: header row, ','
# delimiter, decimal point. Before it: none of the three (see
# sql/02_stage_legacy.sql). The era is read from the archive's own first line
# rather than from its date, because the date rule is only as good as the months
# somebody probed and this costs 0.05 s even on a 17 GB zip. An unreadable or
# unrecognised first line stops the load here, before a wrong parser turns a
# header into a data row or a `;`-delimited line into one 22-field column.
first_line=$(ch -q "SELECT line FROM file({src:String}, LineAsString) LIMIT 1" --param_src "$src")
case "$first_line" in
  '# Timestamp'*) stage=sql/02_stage.sql;        dialect=modern ;;
  *\;*)           stage=sql/02_stage_legacy.sql; dialect=pre-2016-10 ;;
  # An empty first line is not a dialect problem and must not be reported as
  # one: it means the glob matched no member at all, which ClickHouse returns as
  # zero rows and exit 0. That is the failure the `**` above fixes, and naming
  # it correctly is what points the next person at the glob.
  '') echo "no member matched: $src — zip kept" >&2; exit 1 ;;
  *)  echo "unrecognised CSV dialect in $base — first line: ${first_line:0:80}" >&2; exit 1 ;;
esac

ch "$stage" --param_src "$src" --param_lim "$limit"

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

# rows_read > 0 says the CSV parsed. kept > 0 says it parsed into the RIGHT
# columns, and only the second one is worth anything to a positional parser:
# sql/02_stage_legacy.sql binds by index, so a column order that is wrong for
# some era stages every row with `mobile` reading something that is not a class,
# keeps none of them, and looks from here like a file of nothing but base
# stations. Without this guard that writes a complete-looking load_log row with
# a 100 % non-vessel drop, deletes the archive at the end of this script, and
# leaves run_queue.sh with no reason to ever fetch the month again.
# No real file is empty this way: the 2015-07 sample keeps 92 % of its rows.
[ "$kept" -gt 0 ] || { echo "no vessel rows kept from $base — wrong column order for this era? zip kept" >&2; exit 1; }

# Delete this file's range first, so a re-run replaces rather than doubles —
# but only when there is something to replace. A DELETE writes a new version of
# every part it touches even when it matches no row, and running these four on
# every load is what grew the store to 116 161 part directories mid-way through
# the S4 daily queue and took the median load from 40 s to 67 s. A fresh range
# must cost zero mutations.
#
# The guard counts exactly what the four DELETEs would remove, and asks the
# tables rather than load_log alone: a load killed between the INSERTs of
# sql/03_aggregate.sql leaves rows behind with NO log row, and that half-loaded
# day is the case the re-run exists to clean up. --force needs no special case
# either — its own rows and its own log row are inside the range. These are the
# same three range counts load_log is filled from below, so the cost is known:
# 0.5 s over the 6.2 GB store, against the 27 s the skipped mutations cost.
# Monthly partitioning prunes both the counts and the DELETEs to the months
# actually touched.
stale=$(ch -q "
SELECT (SELECT count() FROM h3_hourly    WHERE hour BETWEEN toStartOfHour(toDateTime({t0:UInt32}, 'UTC'))
                                                        AND toDateTime({t1:UInt32}, 'UTC'))
     + (SELECT count() FROM vessel_day   WHERE day  BETWEEN toDate(toDateTime({t0:UInt32}, 'UTC'))
                                                        AND toDate(toDateTime({t1:UInt32}, 'UTC')))
     + (SELECT count() FROM public_track WHERE ts   BETWEEN toStartOfMinute(toDateTime({t0:UInt32}, 'UTC'))
                                                        AND toDateTime({t1:UInt32}, 'UTC'))
     + (SELECT count() FROM load_log     WHERE file = {f:String})
" --param_t0 "$ts0" --param_t1 "$ts1" --param_f "$base")

if [ "$stale" != 0 ]; then
  ch -q "
DELETE FROM h3_hourly    WHERE hour BETWEEN toStartOfHour(toDateTime({t0:UInt32}, 'UTC'))
                                        AND toDateTime({t1:UInt32}, 'UTC');
DELETE FROM vessel_day   WHERE day  BETWEEN toDate(toDateTime({t0:UInt32}, 'UTC'))
                                        AND toDate(toDateTime({t1:UInt32}, 'UTC'));
DELETE FROM public_track WHERE ts   BETWEEN toStartOfMinute(toDateTime({t0:UInt32}, 'UTC'))
                                        AND toDateTime({t1:UInt32}, 'UTC');
DELETE FROM load_log     WHERE file = {f:String};
" --param_t0 "$ts0" --param_t1 "$ts1" --param_f "$base"
fi

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
  # "the staged range", not "this day": a monthly archive holds 31 members and
  # ClickHouse decides how many of them a capped read reaches, so ts_min..ts_max
  # can span several days — all of which were DELETEd above and only partly
  # rewritten. --limit is a sampling tool; never point it at the real store.
  disposition="CAPPED at $limit rows — zip KEPT, the staged range is incomplete"
fi
trap - ERR

# The dialect is in the line so a queue log says which parser ran without
# anyone deriving it. It is not the record of last resort — load_log.ts_min
# is: everything before 2016-10 is the legacy dialect by definition.
printf 'loaded  %s: %s rows read, %s kept in %ss (%s rows/s), %s dialect, %s\n' \
  "$base" "$rows_read" "$kept" "$secs" "$(( rows_read / (secs > 0 ? secs : 1) ))" \
  "$dialect" "$disposition"
