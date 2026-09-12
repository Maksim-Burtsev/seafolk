#!/usr/bin/env bash
# S11 — build dist/dataset/ from the store and verify it. The whole export:
#   scripts/export.sh                  against data/ch
#   CH_PATH=data/ch_a scripts/export.sh   against an APFS clone
# dist/dataset is rebuilt from scratch every run, so a product that sql/70 no
# longer writes cannot survive as a stale file that the tests then bless.
# Exits with scripts/test_export.py's status: a failed privacy check fails the
# export.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf dist/dataset
mkdir -p dist/dataset

/usr/bin/time -p scripts/ch.sh sql/70_export.sql

# The data card is docs/dataset-card.md in the repo and README.md in the
# published dataset, which is where Hugging Face and a GitHub Release look.
# A published product without its card is not publishable, so this is a FAIL,
# not a warning: test_export.py also greps the copy for an MMSI-shaped number.
if [ ! -f docs/dataset-card.md ]; then
  echo "export: docs/dataset-card.md does not exist — no card, no dataset" >&2
  exit 1
fi
cp docs/dataset-card.md dist/dataset/README.md

ls -lh dist/dataset
du -sh dist/dataset

uv run --project notes scripts/test_export.py
# scripts/publish.sh refuses to run without this marker; rm -rf above clears it.
touch dist/dataset/.tests-passed
