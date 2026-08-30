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
case "${1:-}" in
  -*|"") exec clickhouse local --path "$p" "$@" ;;
  *)     f="$1"; shift; exec clickhouse local --path "$p" "$@" < "$f" ;;
esac
