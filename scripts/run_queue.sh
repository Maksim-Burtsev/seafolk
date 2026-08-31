#!/usr/bin/env bash
# Fetch and load every date in a queue file, one file at a time.
#   scripts/run_queue.sh queues/phase0.txt
#   caffeinate -i scripts/run_queue.sh queues/phase0.txt   # leave it running
#
# Safe to re-run: a date already in load_log is skipped BEFORE it is downloaded.
# (load.sh skips it too, but only after the 0.9 GB is on disk and it would then
# leave the zip behind — see the assert below.)
#
# Stops on the first failure with the zip still in place, so the re-run resumes
# where it stopped. Everything is appended to data/queue.log.
#
# S4 owns the unattended guards: free-disk floor, flock, --dry-run, ETA.
set -euo pipefail
cd "$(dirname "$0")/.."
q="${1:?usage: scripts/run_queue.sh <dates-file>}"
# Where the archive lands is fetch.sh's rule, not this script's — read the same
# variable it reads, or setting AIS_RAW sends the download one place and the
# load another. QUEUE_LOG follows CH_PATH's precedent so the test can redirect it.
DEST="${AIS_RAW:-data/raw}"
log="${QUEUE_LOG:-data/queue.log}"
mkdir -p "$(dirname "$log")" "$DEST"
exec > >(tee -a "$log") 2>&1

scripts/ch.sh sql/01_schema.sql            # load_log has to exist before it is read
loaded="$(scripts/ch.sh -q 'SELECT file FROM load_log')"

# The dates still to do, resolved once here because this is the only process
# that may read the store — the prefetcher cannot, the loader holds the lock.
work=data/queue.work
: > "$work"
while read -r d _; do
  case "$d" in ''|\#*) continue ;; esac
  if grep -qxF "aisdk-$d.zip" <<<"$loaded"; then echo "skip    aisdk-$d.zip (already in load_log)"
  else echo "$d" >> "$work"; fi
done < "$q"
echo "queue    $(grep -c . "$work" | tr -d ' ') dates to load"

# Download ahead, several at a time: one connection gets a third of the link.
# PREFETCH=0 falls back to fetching each file inline, one at a time.
pf=""
if [ "${PREFETCH:-1}" != 0 ]; then
  scripts/prefetch.sh "$work" "${AHEAD:-3}" &
  pf=$!
  # `:` last, or the trap's own failing pkill becomes the script's exit status.
  trap 'kill "$pf" 2>/dev/null; :' EXIT
fi

while read -r d _; do
  f="aisdk-$d.zip"
  # The one guard that matters for an unattended run: a full disk fails the
  # load, and a failed load keeps its zip, so the next file starts with less
  # room than the last. Stop while stopping is still cheap. The rest of S4's
  # guards (flock, --dry-run, progress/ETA) are S4's.
  free_gb=$(df -k . | awk 'NR==2 {print int($4/1048576)}')
  if [ "$free_gb" -lt "${FREE_FLOOR_GB:-30}" ]; then
    echo "STOP    free disk ${free_gb} GB is under the ${FREE_FLOOR_GB:-30} GB floor" >&2
    exit 1
  fi
  echo "===     $(date -u '+%F %T')  $d  (free ${free_gb} GB)"

  # Wait for the prefetcher to finish this date. Fall back to fetching it here
  # if the prefetcher is gone or has fallen too far behind — in the foreground,
  # so a genuine failure is visible and stops the run instead of hanging it.
  waited=0
  while [ ! -f "$DEST/$f.ok" ]; do
    if [ -z "$pf" ] || ! kill -0 "$pf" 2>/dev/null || [ "$waited" -ge 1200 ]; then
      scripts/fetch.sh "$d"
      break
    fi
    sleep 5
    waited=$((waited + 5))
  done
  scripts/load.sh "$DEST/$f"            # never --limit: a capped load keeps the zip
  # A complete load deletes its own archive. A surviving zip therefore means the
  # day is only partly loaded — stop, rather than roll on and fill the disk with
  # 92 of them.
  [ ! -e "$DEST/$f" ] || { echo "ERROR   $f survived the load — stopping" >&2; exit 1; }
done < "$work"

echo "queue done: $q"
