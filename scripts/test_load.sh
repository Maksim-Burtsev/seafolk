#!/usr/bin/env bash
# The one runnable check for the S2 loader. Runs scripts/load.sh itself — the
# real thing, not a copy of its logic — against a throwaway store in
# data/ch_test and a 2 M-row sample of whatever archive files are on disk.
#
# The samples are HARD LINKS to the real zips: load.sh deletes the file it
# loads, and a hard link makes that free and harmless (nothing is copied, the
# original name survives). Prints PASS/FAIL per assert, exits non-zero on any
# FAIL, and SKIPs cleanly once data/raw is empty — which it will be after S3.
set -euo pipefail
cd "$(dirname "$0")/.."

export CH_PATH=data/ch_test
LIMIT=2000000                      # ~2 h 43 min of a daily file; ~2 s to stage
LINKS=data/raw/.test_links

# Samples come from their own directory, never from data/raw: a bulk run is
# downloading into data/raw and deleting from it, so a sample taken there is
# both a race and, half the time, a half-downloaded file.
#   scripts/fetch.sh 2025-08-01   with AIS_RAW=data/sample
SAMPLES="${SAMPLES:-data/sample}"
complete=$(ls "$SAMPLES"/aisdk-*.zip 2>/dev/null || true)
z1=$(printf '%s\n' "$complete" | sed -n 1p)
z2=$(printf '%s\n' "$complete" | sed -n 2p)
if [ -z "$z1" ]; then
  echo "SKIP  no archive in $SAMPLES — nothing to sample."
  echo "      Fetch one first:  AIS_RAW=$SAMPLES scripts/fetch.sh 2025-08-01"
  exit 0
fi

cleanup() { rm -rf "$LINKS" data/ch_test; }
trap cleanup EXIT
cleanup
mkdir -p "$LINKS/1" "$LINKS/2" "$LINKS/3" "$LINKS/4" "$LINKS/5"

fail=0
assert() {  # assert <name> <expected> <actual>
  if [ "$2" = "$3" ]; then printf 'PASS  %s\n' "$1"
  else printf 'FAIL  %s — expected %s, got %s\n' "$1" "$2" "$3"; fail=1; fi
}
q() { scripts/ch.sh -q "$1"; }

echo "sample: $(basename "$z1") (first $LIMIT rows)"
echo

ln "$z1" "$LINKS/1/$(basename "$z1")"
scripts/load.sh --limit "$LIMIT" "$LINKS/1/$(basename "$z1")" > /dev/null

kept=$(q "SELECT rows_kept FROM load_log")
msgs=$(q "SELECT sum(msgs) FROM h3_hourly")

# 1. Every kept row landed in exactly one cell-hour. Ties the public table to
#    the number load_log publishes as "rows we counted".
assert "h3_hourly sum(msgs) == load_log rows_kept" "$kept" "$msgs"

# 2. The uniqExact state and an independent GROUP BY day, mmsi agree. One is a
#    probabilistic-looking aggregate, the other is a plain row count; if they
#    ever diverge the vessel counts in every chapter are wrong.
assert "uniqExactMerge(vessels) == count(vessel_day)" \
  "$(q "SELECT count() FROM vessel_day")" \
  "$(q "SELECT uniqExactMerge(vessels) FROM h3_hourly")"

# 3. The privacy rule. Both halves matter: no Class B vessel may appear in
#    public_track, AND Class B vessels calling themselves 'Passenger' must
#    actually exist in this sample, or the first half proves nothing.
assert "no Class B vessel in public_track" 0 \
  "$(q "SELECT count() FROM public_track
        WHERE mmsi IN (SELECT mmsi FROM vessel_day WHERE mobile = 'Class B')")"
assert "…and Class B 'Passenger' vessels do exist here (assert 3 is not vacuous)" 1 \
  "$(q "SELECT count() > 0 FROM vessel_day WHERE mobile = 'Class B' AND ship_group = 'passenger'")"
assert "public_track is populated" 1 "$(q "SELECT count() > 0 FROM public_track")"

# 4. H3 argument order. geoToH3(lat, lon) does not error — it silently moves
#    the whole fleet to Kazakhstan. Every cell centre must land back inside the
#    Danish bbox (+0.1 deg, since a res-7 cell straddles the edge).
assert "every h3 cell maps back into the Danish bbox" 0 \
  "$(q "SELECT count() FROM h3_hourly
        WHERE NOT (h3ToGeo(h3).2 BETWEEN 52.9 AND 59.1
               AND h3ToGeo(h3).1 BETWEEN  2.9 AND 17.1)")"

# 5. The drop counters partition the file exactly. If they drift, S10 reports a
#    dropped share that does not add up.
assert "rows_read == non_vessel + sentinel + out_of_bbox + kept" 0 \
  "$(q "SELECT countIf(rows_read != rows_non_vessel + rows_sentinel
                                  + rows_out_of_bbox + rows_kept) FROM load_log")"

# 6. dist_nm is in the physical range: something moved, nothing did 1500 nm in
#    a day. Catches a lost first-row guard (which banks phantom thousands).
assert "dist_nm: something moved" 1 "$(q "SELECT sum(dist_nm) > 0 FROM vessel_day")"
assert "dist_nm: nothing did 1500 nm in a day" 1 "$(q "SELECT max(dist_nm) < 1500 FROM vessel_day")"

# 7. Re-loading the same file replaces its contribution instead of doubling it.
ln "$z1" "$LINKS/2/$(basename "$z1")"
scripts/load.sh --force --limit "$LIMIT" "$LINKS/2/$(basename "$z1")" > /dev/null
assert "--force reload does not double sum(msgs)" "$msgs" "$(q "SELECT sum(msgs) FROM h3_hourly")"
assert "--force reload leaves one load_log row" 1 "$(q "SELECT count() FROM load_log")"

# 8. Without --force a logged file is skipped, and nothing changes.
ln "$z1" "$LINKS/3/$(basename "$z1")"
skip_out=$(scripts/load.sh --limit "$LIMIT" "$LINKS/3/$(basename "$z1")")
case "$skip_out" in skip*) said_skip=1;; *) said_skip=0;; esac
assert "second load without --force says skip" 1 "$said_skip"
assert "…and sum(msgs) is unchanged" "$msgs" "$(q "SELECT sum(msgs) FROM h3_hourly")"
rm -f "$LINKS/3"/*

# 9. The two grains agree. A vessel reports several Ship type values in a day,
#    so resolving the group per MESSAGE puts one boat in two ship_groups at
#    once and makes "how many leisure vessels" non-additive. Summing distinct
#    vessels over h3_hourly's groups must land exactly on the vessel-day count.
assert "vessels summed over h3_hourly groups == vessel_day rows" \
  "$(q "SELECT count() FROM vessel_day")" \
  "$(q "SELECT sum(v) FROM
          (SELECT uniqExactMerge(vessels) AS v FROM h3_hourly
           GROUP BY toDate(hour), mobile, ship_group)")"

# 10. imo actually parses. It arrives as the string 'Unknown' or digits, so a
#     column shift or a silently-zeroing cast would leave the whole thing 0 and
#     take chapter 03's only link to the ship registries with it.
assert "imo is populated for passenger vessels" 1 \
  "$(q "SELECT count() > 0 FROM vessel_day WHERE ship_group = 'passenger' AND imo > 0")"

# 11. The stage leaves nothing behind. TRUNCATE would leave ~58 MB of inactive
#    parts per daily file that `clickhouse local` never collects — invisible in
#    a query, fatal to the disk budget over the 900 files of S4.
assert "no stage parts survive a load" 0 \
  "$(q "SELECT count() FROM system.parts
        WHERE table IN ('ais_raw_stage', 'ais_vessel_stage')")"

# 12. A second file adds to the aggregates rather than replacing them.
if [ -n "$z2" ]; then
  ln "$z2" "$LINKS/4/$(basename "$z2")"
  scripts/load.sh --limit "$LIMIT" "$LINKS/4/$(basename "$z2")" > /dev/null
  assert "two files merge: sum(msgs) == sum(rows_kept)" \
    "$(q "SELECT sum(rows_kept) FROM load_log")" "$(q "SELECT sum(msgs) FROM h3_hourly")"
  assert "…and load_log has two rows" 2 "$(q "SELECT count() FROM load_log")"
else
  echo "SKIP  cross-file merge — only one archive file on disk"
fi

# 13. scripts/ch.sh must not inherit its caller's stdin. `clickhouse local -q
#     "INSERT INTO t SELECT <constants>"` binds whatever is on stdin as its
#     implicit input table and writes ONE ROW PER LINE of it. run_queue.sh runs
#     its loop with stdin on the queue file, so every load under it wrote one
#     load_log row per line of the queue — found in S3 with 8 919 rows for 92
#     archives. A --force reload replaces its own row, so the count must not move.
ln "$z1" "$LINKS/5/$(basename "$z1")"
printf 'one\ntwo\nthree\n' > "$LINKS/multiline.txt"
before=$(q "SELECT count() FROM load_log")
scripts/load.sh --force --limit "$LIMIT" "$LINKS/5/$(basename "$z1")" \
  < "$LINKS/multiline.txt" > /dev/null
assert "a load with a multi-line file on stdin writes one load_log row" \
  "$before" "$(q "SELECT count() FROM load_log")"

# 14. scripts/run_queue.sh skips a date already in load_log — WITHOUT fetching
#     it. This is the branch that decides whether a resumed queue re-downloads
#     72 GB it already has, and load.sh's own skip cannot cover it: that one
#     fires after the file is on disk, and leaves it there. AIS_RAW and
#     QUEUE_LOG, QUEUE_LOCK and PROGRESS point the runner at throwaway paths —
#     every file it writes, or a test run corrupts the real one. A broken skip
#     lands in
#     the scratch directory instead of data/raw.
d1=$(basename "$z1" .zip); d1=${d1#aisdk-}
printf '%s\n' "$d1" > "$LINKS/queue.txt"
rq_out=$(AIS_RAW="$LINKS/raw" QUEUE_LOG="$LINKS/queue.log" QUEUE_LOCK="$LINKS/lock" \
         PROGRESS="$LINKS/progress.tsv" scripts/run_queue.sh "$LINKS/queue.txt")
case "$rq_out" in *"0 dates to load, 1 already in load_log"*) said_skip=1;; *) said_skip=0;; esac
assert "run_queue skips a date already in load_log" 1 "$said_skip"
assert "…and downloads nothing while doing it" 0 \
  "$(ls "$LINKS/raw" 2>/dev/null | wc -l | tr -d ' ')"

# 15. scripts/prefetch.sh is where the whole 3.6x download speedup lives, and
#     it runs unattended for days. Two things it must never do: re-download a
#     file it already has, and keep downloading past the free-disk floor.
mkdir -p "$LINKS/pf"
printf '2024-01-01\n2024-01-02\n' > "$LINKS/pfq1.txt"
: > "$LINKS/pf/aisdk-2024-01-01.zip.ok"
: > "$LINKS/pf/aisdk-2024-01-02.zip.ok"
AIS_RAW="$LINKS/pf" scripts/prefetch.sh "$LINKS/pfq1.txt" 3
assert "prefetch fetches nothing when every date is already complete" 2 \
  "$(ls "$LINKS/pf" | wc -l | tr -d ' ')"

printf '2024-01-03\n' > "$LINKS/pfq2.txt"
pf_out=$(FREE_FLOOR_GB=99999999 AIS_RAW="$LINKS/pf" scripts/prefetch.sh "$LINKS/pfq2.txt" 3 2>&1)
case "$pf_out" in *"under the"*) floored=1;; *) floored=0;; esac
assert "prefetch stops at the free-disk floor" 1 "$floored"
assert "…and downloaded nothing on the way out" 2 "$(ls "$LINKS/pf" | wc -l | tr -d ' ')"

echo
[ "$fail" = 0 ] && echo "ALL PASS" || echo "FAILURES ABOVE"
exit "$fail"
