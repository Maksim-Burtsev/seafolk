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
# stdin is closed, never inherited. `clickhouse local -q "INSERT INTO t SELECT
# <constants>"` binds whatever is on stdin as its implicit input table and
# writes ONE ROW PER LINE OF IT. scripts/run_queue.sh runs its loop with stdin
# on the queue file, so every load.sh under it wrote 98 identical load_log rows
# — one per line of queues/phase0.txt. The aggregates were untouched (they are
# written through the file branch below, whose stdin is the SQL file), but S10
# reads load_log by sum(), and 98x is not a number anyone would question.
# To feed data in, call clickhouse local directly and mean it.
case "${1:-}" in
  -*|"") exec clickhouse local --path "$p" "$@" < /dev/null ;;
  *)     f="$1"; shift; exec clickhouse local --path "$p" "$@" < "$f" ;;
esac
