#!/usr/bin/env bash
# Download ahead of the loader, several archives at a time.
#
#   scripts/prefetch.sh data/queue.work [ahead]
#
# Why this exists: the archive gives a single connection ~3.5 MB/s while the
# link carries ~11 MB/s — measured by running extra streams alongside a live
# queue (1 stream 3.78 MB/s, 3 streams 7.81 MB/s aggregate, on top of the
# queue's own). Downloading serially therefore wastes two thirds of the
# bandwidth and was costing ~183 s of the ~214 s each file took.
#
# Loading stays strictly serial — `clickhouse local` locks the store — so this
# parallelises the fetch and nothing else.
#
# Disk is bounded by counting the archives on disk, partial ones included:
# never more than `ahead` at a time, so at most ~ahead x 1 GB. run_queue.sh
# deletes each zip as it loads it, which frees a slot.
#
# A failed fetch is not fatal here: it leaves no .ok sidecar, and run_queue.sh
# falls back to fetching that date itself, in the foreground, where the error
# is visible and stops the run.
set -uo pipefail
cd "$(dirname "$0")/.."

work="${1:?usage: scripts/prefetch.sh <dates-file> [ahead]}"
ahead="${2:-3}"
DEST="${AIS_RAW:-data/raw}"
mkdir -p "$DEST"

# The runner needs to be able to stop this process, and $! is not a reliable
# handle for it: run_queue's own stdout is a process substitution, and the pid
# it read back from $! was not this script's — killing it terminated the
# caller instead, which killed the whole test suite with SIGTERM. So the
# prefetcher publishes its own pid and the runner kills exactly that.
[ -n "${PREFETCH_PID_FILE:-}" ] && echo $$ > "$PREFETCH_PID_FILE"

# Killing this script must take its downloads with it. Without this they are
# orphaned and keep writing into data/raw after the runner has stopped.
trap 'kids=$(jobs -p); [ -n "$kids" ] && kill $kids 2>/dev/null; exit 130' TERM INT

# Slots are counted as READY archives (a .ok sidecar, waiting to be loaded)
# plus this script's own live downloads — never as "zip files on disk".
# Counting files deadlocked the runner: a restart with half-downloaded archives
# left over saw three zips, refused to start anything, and the runner then sat
# waiting for a .ok that nobody was fetching.
ready()    { ls "$DEST"/aisdk-*.zip.ok 2>/dev/null | wc -l | tr -d ' '; }
inflight() { jobs -rp | wc -l | tr -d ' '; }

while read -r d _; do
  case "$d" in ''|\#*) continue ;; esac
  [ -f "$DEST/aisdk-$d.zip.ok" ] && continue

  while [ $(( $(ready) + $(inflight) )) -ge "$ahead" ]; do sleep 5; done

  free_gb=$(df -k . | awk 'NR==2 {print int($4/1048576)}')
  if [ "$free_gb" -lt "${FREE_FLOOR_GB:-30}" ]; then
    echo "prefetch stopping: free disk ${free_gb} GB is under the ${FREE_FLOOR_GB:-30} GB floor" >&2
    break
  fi

  scripts/fetch.sh "$d" &
  sleep 1          # let curl create the file, so the next slot count sees it
done < "$work"
wait
