#!/usr/bin/env bash
# clickhouse local against the persistent store in data/ch.
#   scripts/ch.sh sql/00_peek.sql          run a SQL file
#   scripts/ch.sh -q "SELECT 1"            run one query
#   CH_PATH=data/ch_test scripts/ch.sh …   run against a throwaway store
# Extra clickhouse args after the first one are passed through. Paths inside
# the SQL are resolved from the repo root, not from the caller's cwd.
set -euo pipefail
cd "$(dirname "$0")/.."
p="${CH_PATH:-data/ch}"
mkdir -p "$p"
# Spill to disk instead of dying. The machine has 24 GB of RAM and clickhouse
# local caps itself at 90 % of it; loading aisdk-2015-09.zip (19 GB zip, the
# largest monthly file) hit that cap inside sql/03_aggregate.sql's join and
# killed the queue with MEMORY_LIMIT_EXCEEDED. Past these thresholds a GROUP BY
# or sort continues on disk — slower, but a monthly load is minutes either way
# and disk is the resource this project actually has.
#
# The H3 argument order is pinned, not inherited. ClickHouse changed both
# defaults out from under callers: h3ToGeo returns (lat, lon) since 25.1
# (#74719) and geoToH3 takes (lat, lon, res) since 25.5 (#78852), both flagged
# Backward Incompatible. A swap does not error — it mirrors the whole fleet
# into the Arabian Sea — so the project states which convention it means and
# stops depending on which clickhouse is installed. test_load.sh checks the pin
# against a hard-coded cell id computed by the h3 reference library.
opts=(--max_bytes_before_external_group_by=6000000000
      --max_bytes_before_external_sort=6000000000
      --geotoh3_argument_order=lat_lon
      --h3togeo_lon_lat_result_order=0)
# stdin is closed, never inherited. `clickhouse local -q "INSERT INTO t SELECT
# <constants>"` binds whatever is on stdin as its implicit input table and
# writes ONE ROW PER LINE OF IT. scripts/run_queue.sh runs its loop with stdin
# on the queue file, so every load.sh under it wrote 98 identical load_log rows
# — one per line of queues/phase0.txt. The aggregates were untouched (they are
# written through the file branch below, whose stdin is the SQL file), but S10
# reads load_log by sum(), and 98x is not a number anyone would question.
# To feed data in, call clickhouse local directly and mean it.
case "${1:-}" in
  -*|"") exec clickhouse local --path "$p" "${opts[@]}" "$@" < /dev/null ;;
  *)     f="$1"; shift; exec clickhouse local --path "$p" "${opts[@]}" "$@" < "$f" ;;
esac
