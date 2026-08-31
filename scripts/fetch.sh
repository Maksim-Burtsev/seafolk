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
  # A progress bar is for a human. Piped into a log (scripts/run_queue.sh) it is
  # 90 KB of carriage returns per file — see data/fetch.log.
  if [ -t 2 ]; then prog=--progress-bar; else prog=--no-progress-meter; fi
  # --retry alone covers timeouts and 5xx, NOT curl 18 "transfer closed with N
  # bytes remaining" — a mid-download disconnect. That killed an unattended run
  # after 173 files: curl exited 18, fetch.sh exited non-zero, and the queue
  # stopped for the rest of the morning. --retry-all-errors covers it, and -C -
  # resumes from what is already on disk rather than starting the file over.
  curl -fL --retry 10 --retry-delay 15 --retry-all-errors -C - "$prog" -o "$out" "$found"
  if unzip -tq "$out" >/dev/null; then
    touch "$out.ok"; echo "ok    $f ($(du -h "$out" | cut -f1))"
  else
    echo "corrupt $f — removed, rerun to retry" >&2; rm -f "$out"; exit 1
  fi
done
