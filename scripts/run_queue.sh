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

while read -r d _; do
  case "$d" in ''|\#*) continue ;; esac
  f="aisdk-$d.zip"
  if grep -qxF "$f" <<<"$loaded"; then echo "skip    $f (already in load_log)"; continue; fi
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
  scripts/fetch.sh "$d"
  scripts/load.sh "$DEST/$f"            # never --limit: a capped load keeps the zip
  # A complete load deletes its own archive. A surviving zip therefore means the
  # day is only partly loaded — stop, rather than roll on and fill the disk with
  # 92 of them.
  [ ! -e "$DEST/$f" ] || { echo "ERROR   $f survived the load — stopping" >&2; exit 1; }
done < "$q"

echo "queue done: $q"
