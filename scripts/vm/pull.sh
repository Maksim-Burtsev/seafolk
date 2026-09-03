#!/usr/bin/env bash
# Bring the finished store home from the VM and verify it. Runs on the LAPTOP.
#
#   scripts/vm/pull.sh 203.0.113.7
#
# tar over ssh, not scp/cp/rsync: data/ch is full of hardlinked parts and only
# tar reproduces them. zstd on both ends because the store is ~15 GB of very
# compressible columnar data over somebody else's uplink.
#
# The store lands in data/ch.incoming and becomes data/ch only after every
# check below passes. A failed check exits non-zero and says DO NOT DESTROY: the
# VM then holds the only intact copy, and there is no way to ship a store back
# up to a fresh machine — it would start over from an empty load_log.
set -euo pipefail
cd "$(dirname "$0")/../.."

ip="${1:?usage: scripts/vm/pull.sh <vm-ip>}"
r="root@$ip"
remote=/root/seafolk
incoming=data/ch.incoming
# The key made for the night (docs/PLAN.md § S4-redo). accept-new because the
# VM is fresh; BatchMode because this runs unattended — a host-key or password
# prompt would hang it instead of failing.
key="${SEAFOLK_KEY:-$HOME/.ssh/seafolk_vm}"
ssh() { command ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$@"; }
scp() { command scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$@"; }

# A store has tables; a data/ch with no metadata/ is the empty scaffold any
# scripts/ch.sh call leaves behind (it mkdir -p's its --path) and holds nothing.
# Refuse a real store — deleting it is a decision with a person's name on it —
# and clear the scaffold, or the plan's own Validate lines would block the pull.
if [ -e data/ch/metadata ]; then
  echo "data/ch already holds a store — refusing to overwrite it." >&2
  echo "Delete it deliberately (rm -rf data/ch) and re-run." >&2
  exit 1
fi
[ -e data/ch ] && rm -rf data/ch
if [ -e "$incoming" ]; then
  echo "$incoming exists — a previous pull did not finish. It is rubble, not a store:" >&2
  echo "rm -rf $incoming and re-run." >&2
  exit 1
fi

# One round trip for the whole remote state. exit 9 distinguishes "no repo
# there" from "checks printed nothing". The chain's exit status is the only
# record that the night finished: a runner that STOPs (disk floor, a stalled
# download) drops its lock in its EXIT trap and the tmux session ends with it,
# so tmux and the lock alone cannot tell a finished night from a broken one.
state=$(ssh "$r" "cd $remote 2>/dev/null || exit 9
  tmux has-session -t =queue 2>/dev/null && echo tmux
  [ -e data/.queue.lock ] && echo lock
  tail -1 data/night.log 2>/dev/null
  :") || { echo "cannot reach $remote on $r (ssh exit $?)" >&2; exit 1; }

case "$state" in
  *tmux*) echo "the remote tmux session 'queue' is still running — the night is not over." >&2; exit 1 ;;
esac
case "$state" in
  *lock*) echo "$remote/data/.queue.lock still exists — a runner is going, or one died mid-load." >&2
          echo "Check 'ssh $r tail -20 $remote/data/night.log' before removing it." >&2; exit 1 ;;
esac
case "$state" in
  *"chain exited 0"*) ;;
  *) echo "the night did not finish: last line of $remote/data/night.log is" >&2
     echo "    ${state##*$'\n'}" >&2
     echo "Fix the cause on the VM and re-run scripts/vm/night.sh (it resumes from load_log). DO NOT destroy the instance." >&2
     exit 1 ;;
esac

mkdir -p data "$incoming"
echo "pulling $remote/data/ch …"
ssh "$r" "tar -C $remote/data -cf - ch | zstd -T0" | zstd -d | tar -xf - -C "$incoming" --strip-components=1   # ch/… → $incoming/…

# Gitignored, but they are the night's only record of what happened when.
scp -q "$r:$remote/data/progress.tsv" "$r:$remote/data/night.log" data/ \
  || echo "WARN  could not copy progress.tsv / night.log" >&2

echo
echo "=== verify ==="
# Every queued archive, counted the way run_queue.sh reads the files.
expected=$(grep -hv '^[[:space:]]*#' queues/daily-2024-2026.txt queues/ref-years.txt queues/storms.txt | grep -c .)
# invariant: sum(msgs) == rows_kept, exact — the honesty layer's spine.
# files:     one load_log row per queued archive.
# copenhagen: the cell the h3 reference library gives for 55.676N 12.568E, or
#            one of its six neighbours, holds rows — the grid is not mirrored
#            (docs/DECISIONS.md 2026-09-03). The ring, not the one cell: a
#            2 M-row sample of one night had traffic in the ring and none in
#            the cell itself.
# mirrored:  no cell centre sits in the swapped hemisphere.
read -r invariant files copenhagen mirrored <<<"$(CH_PATH=$incoming scripts/ch.sh -q "SELECT
    (SELECT sum(msgs) FROM h3_hourly) = (SELECT sum(rows_kept) FROM load_log),
    (SELECT count() FROM load_log),
    (SELECT count() FROM h3_hourly WHERE h3 IN h3kRing(608531686258376703, 1)),
    (SELECT count() FROM (SELECT DISTINCT h3 FROM h3_hourly)
      WHERE h3ToGeo(h3).1 BETWEEN 2.9 AND 17.1 AND h3ToGeo(h3).2 BETWEEN 52.9 AND 59.1)
FORMAT TSV")"
CH_PATH=$incoming scripts/ch.sh -q "SELECT
    (SELECT sum(msgs) FROM h3_hourly) AS h3_msgs,
    (SELECT sum(rows_kept) FROM load_log) AS log_rows_kept,
    (SELECT min(day) FROM vessel_day) AS first_day,
    (SELECT max(day) FROM vessel_day) AS last_day,
    (SELECT count(DISTINCT day) FROM vessel_day) AS days
FORMAT Vertical"
printf 'invariant_ok: %s\nfiles: %s (expected %s)\ncopenhagen_rows: %s\nmirrored_cells: %s\n' \
  "$invariant" "$files" "$expected" "$copenhagen" "$mirrored"
du -sh "$incoming"

bad=""
[ "$invariant" = 1 ]         || bad="$bad invariant"
[ "$files" = "$expected" ]   || bad="$bad files"
[ "${copenhagen:-0}" -gt 0 ] || bad="$bad copenhagen"
[ "$mirrored" = 0 ]          || bad="$bad mirrored"
if [ -n "$bad" ]; then
  echo >&2
  echo "FAILED:$bad — the store in $incoming is not the one to keep." >&2
  echo "The VM holds the only intact copy. DO NOT destroy the instance until this is understood." >&2
  exit 1
fi

mv "$incoming" data/ch
[ -f data/progress.tsv ] && { echo "--- last 3 lines of the VM's progress.tsv ---"; tail -3 data/progress.tsv; }

cat <<EOF

The store is home in data/ch: all $files archives, invariant exact, grid not mirrored.
It contains MMSI of private vessels — it must not leave this machine, and the
VM must not keep a copy.

DESTROY THE INSTANCE through the provider API/console now. This script does not
do it: deleting somebody's server on the strength of a passing checksum is not a
call a script gets to make.
EOF
