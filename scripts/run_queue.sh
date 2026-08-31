#!/usr/bin/env bash
# Fetch and load every date in a queue file. Safe to leave running for nights.
#
#   scripts/run_queue.sh queues/phase0.txt
#   scripts/run_queue.sh --dry-run queues/2024-2026.txt
#   caffeinate -i scripts/run_queue.sh queues/daily-2024-2026.txt
#
# Downloads run several at a time through scripts/prefetch.sh; loading is
# strictly serial because `clickhouse local` locks the store. A date already in
# load_log is skipped BEFORE it is downloaded — load.sh skips it too, but only
# after the file is on disk, and then leaves it there.
#
# Stops on the first failure with the zip still in place, so the re-run resumes
# where it stopped. Everything is appended to data/queue.log, and one row per
# loaded file goes to data/progress.tsv.
#
# Environment: AIS_RAW, QUEUE_LOG, PROGRESS, FREE_FLOOR_GB, AHEAD, PREFETCH=0.
set -euo pipefail
cd "$(dirname "$0")/.."

dry=0
while :; do
  case "${1:-}" in
    --dry-run) dry=1; shift ;;
    *) break ;;
  esac
done
q="${1:?usage: scripts/run_queue.sh [--dry-run] <dates-file>}"

# Where the archive lands is fetch.sh's rule, not this script's — read the same
# variable it reads, or setting AIS_RAW sends the download one place and the
# load another. QUEUE_LOG follows CH_PATH's precedent so the test can redirect it.
DEST="${AIS_RAW:-data/raw}"
log="${QUEUE_LOG:-data/queue.log}"
prog="${PROGRESS:-data/progress.tsv}"
lock="${QUEUE_LOCK:-data/.queue.lock}"
mkdir -p "$(dirname "$log")" "$DEST"

pf=""
held=0
work=""
cleanup() {
  # Read the pid the prefetcher published; see the note in prefetch.sh for why
  # $! is not usable here. Redirected, or job control prints "Terminated: 15"
  # into the log the human reads.
  if [ -n "$pf" ] && [ -f "$pf" ]; then
    { kill "$(cat "$pf")" && wait; } 2>/dev/null
  fi
  [ "$held" = 1 ] && rm -rf "$lock"          # takes the work list with it
  [ "$dry" = 1 ] && rm -f "$work"
  :                       # last, or a failing kill/rm becomes the exit status
}
trap cleanup EXIT

# Two runners would not corrupt the store — clickhouse local refuses the second
# writer — but they would download every file twice and interleave the log into
# nonsense. mkdir is the atomic primitive that is actually present on macOS;
# there is no flock(1) here.
if [ "$dry" = 0 ]; then
  if ! mkdir "$lock" 2>/dev/null; then
    other="$(cat "$lock/pid" 2>/dev/null || true)"
    if [ -n "$other" ] && kill -0 "$other" 2>/dev/null; then
      echo "another runner is already going (pid $other) — refusing to start a second" >&2
      exit 1
    fi
    echo "taking a stale lock left by pid ${other:-unknown}"
    rm -rf "$lock"
    mkdir "$lock" || { echo "cannot take $lock" >&2; exit 1; }
  fi
  held=1
  echo $$ > "$lock/pid"
fi

exec > >(tee -a "$log") 2>&1

scripts/ch.sh sql/01_schema.sql            # load_log has to exist before it is read
loaded="$(scripts/ch.sh -q 'SELECT file FROM load_log')"

# The dates still to do, resolved once here because this is the only process
# that may read the store — the prefetcher cannot, the loader holds the lock.
#
# The list lives INSIDE the lock directory, so it has exactly one owner. It was
# a fixed data/queue.work, which --dry-run truncated out from under a running
# queue — measured, 620 lines to 1 — and the running prefetcher then hit EOF and
# silently stopped reading ahead. --dry-run takes no lock, so it gets a scratch
# file of its own instead.
if [ "$dry" = 1 ]; then work="$(mktemp -t seafolk-queue)"; else work="$lock/work"; fi
: > "$work"
skipped=0
while read -r d _; do
  case "$d" in ''|\#*) continue ;; esac
  if grep -qxF "aisdk-$d.zip" <<<"$loaded"; then skipped=$((skipped + 1))
  else echo "$d" >> "$work"; fi
done < "$q"
total=$(grep -c . "$work" | tr -d ' ' || true)
echo "queue    $total dates to load, $skipped already in load_log"

if [ "$dry" = 1 ]; then
  echo "--dry-run: would fetch and load these, in order:"
  head -20 "$work" | sed 's/^/         /'
  [ "$total" -gt 20 ] && echo "         … and $((total - 20)) more"
  free_gb=$(df -k . | awk 'NR==2 {print int($4/1048576)}')
  echo "         free disk ${free_gb} GB, floor ${FREE_FLOOR_GB:-30} GB, prefetching ${AHEAD:-3} ahead"
  exit 0
fi

# Download ahead, several at a time: one connection gets a third of the link.
# PREFETCH=0 falls back to fetching each file inline, one at a time.
if [ "${PREFETCH:-1}" != 0 ] && [ "$total" -gt 0 ]; then
  pf="$lock/prefetch.pid"
  PREFETCH_PID_FILE="$pf" scripts/prefetch.sh "$work" "${AHEAD:-3}" &
fi

[ -f "$prog" ] || printf 'finished_utc\tdate\tseconds\tdone\tremaining\teta_hours\n' > "$prog"

run_start=$(date +%s)
done_n=0
while read -r d _; do
  f="aisdk-$d.zip"
  # The guard that matters for an unattended run: a full disk fails the load,
  # and a failed load keeps its zip, so the next file starts with less room than
  # the last. Stop while stopping is still cheap.
  free_gb=$(df -k . | awk 'NR==2 {print int($4/1048576)}')
  if [ "$free_gb" -lt "${FREE_FLOOR_GB:-30}" ]; then
    echo "STOP    free disk ${free_gb} GB is under the ${FREE_FLOOR_GB:-30} GB floor" >&2
    exit 1
  fi
  echo "===     $(date -u '+%F %T')  $d  (free ${free_gb} GB)"
  t0=$(date +%s)

  # Wait for the prefetcher to finish this date. Fall back to fetching it here
  # if the prefetcher is gone or has fallen too far behind — in the foreground,
  # so a genuine failure is visible and stops the run instead of hanging it.
  waited=0
  while [ ! -f "$DEST/$f.ok" ]; do
    pfpid=""; [ -n "$pf" ] && [ -f "$pf" ] && pfpid="$(cat "$pf")"
    if [ -z "$pfpid" ] || ! kill -0 "$pfpid" 2>/dev/null || [ "$waited" -ge 1200 ]; then
      scripts/fetch.sh "$d"
      break
    fi
    sleep 5
    waited=$((waited + 5))
  done

  scripts/load.sh "$DEST/$f"            # never --limit: a capped load keeps the zip
  # A complete load deletes its own archive. A surviving zip therefore means the
  # day is only partly loaded — stop, rather than roll on and fill the disk.
  [ ! -e "$DEST/$f" ] || { echo "ERROR   $f survived the load — stopping" >&2; exit 1; }

  done_n=$((done_n + 1))
  now=$(date +%s)
  eta=$(awk -v e=$((now - run_start)) -v n="$done_n" -v l="$((total - done_n))" \
        'BEGIN { printf "%.1f", (n > 0 ? e / n * l / 3600 : 0) }')
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u '+%F %T')" "$d" "$((now - t0))" "$done_n" "$((total - done_n))" "$eta" >> "$prog"
  if [ $((done_n % 10)) = 0 ]; then
    echo "PROGRESS $done_n/$total done, $((total - done_n)) left, eta ${eta} h"
  fi
done < "$work"

echo "queue done: $q"
