#!/usr/bin/env bash
# Download Danish AIS archive files by date.
#   scripts/fetch.sh 2025-07-12 2025-07-16      # daily files (2024-03 →)
#   scripts/fetch.sh 2016-06 2018-06            # monthly files (→ 2024-02)
# Files land in $AIS_RAW (default data/raw). A file is complete when a
# sidecar "<name>.ok" exists; re-running skips those. Downloads resume.
set -euo pipefail

BASE=http://aisdata.ais.dk
DEST="${AIS_RAW:-data/raw}"
mkdir -p "$DEST"

for d in "$@"; do
  f="aisdk-$d.zip"
  y="${d:0:4}"
  out="$DEST/$f"
  if [ -f "$out.ok" ]; then echo "skip  $f"; continue; fi

  found=""
  for url in "$BASE/$f" "$BASE/$y/$f"; do          # some days sit at the root, some under YYYY/
    if curl -sfIL --max-time 30 "$url" -o /dev/null; then found="$url"; break; fi
  done
  [ -n "$found" ] || { echo "not found: $f" >&2; exit 1; }

  echo "get   $found"
  curl -fL --retry 5 --retry-delay 15 -C - --progress-bar -o "$out" "$found"
  if unzip -tq "$out" >/dev/null; then
    touch "$out.ok"; echo "ok    $f ($(du -h "$out" | cut -f1))"
  else
    echo "corrupt $f — removed, rerun to retry" >&2; rm -f "$out"; exit 1
  fi
done
