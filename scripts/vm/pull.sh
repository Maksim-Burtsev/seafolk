#!/usr/bin/env bash
# Bring the finished store home from the VM and verify it. Runs on the LAPTOP.
#
#   scripts/vm/pull.sh 203.0.113.7
#
# tar over ssh, not scp/cp/rsync: data/ch is full of hardlinked parts and only
# tar reproduces them. zstd on both ends because the store is ~15 GB of very
# compressible columnar data over somebody else's uplink.
set -euo pipefail
cd "$(dirname "$0")/../.."

ip="${1:?usage: scripts/vm/pull.sh <vm-ip>}"
r="root@$ip"
remote=/root/seafolk
# The key made for the night (docs/PLAN.md § S4-redo); accept-new because the
# VM is fresh and this runs unattended — a host-key prompt would hang it.
key="${SEAFOLK_KEY:-$HOME/.ssh/seafolk_vm}"
ssh() { command ssh -i "$key" -o StrictHostKeyChecking=accept-new "$@"; }
scp() { command scp -i "$key" -o StrictHostKeyChecking=accept-new "$@"; }

# Refuse rather than merge into an existing store: a half-overwritten MergeTree
# is worse than either version, and deleting the old data/ch is a decision with
# a person's name on it.
if [ -e data/ch ]; then
  echo "data/ch already exists here — refusing to overwrite it." >&2
  echo "Delete it deliberately (rm -rf data/ch) and re-run." >&2
  exit 1
fi

# One round trip for both liveness checks. exit 9 distinguishes "no repo there"
# from "checks passed and printed nothing".
state=$(ssh "$r" "cd $remote 2>/dev/null || exit 9
  tmux has-session -t queue 2>/dev/null && echo tmux
  [ -e data/.queue.lock ] && echo lock
  :") || { echo "cannot reach $remote on $r (ssh exit $?)" >&2; exit 1; }

case "$state" in
  *tmux*) echo "the remote tmux session 'queue' is still running — the night is not over." >&2; exit 1 ;;
esac
case "$state" in
  *lock*) echo "$remote/data/.queue.lock still exists — a runner is going, or one died mid-load." >&2
          echo "Check 'ssh $r tail -20 $remote/data/night.log' before removing it." >&2; exit 1 ;;
esac

mkdir -p data
echo "pulling $remote/data/ch …"
ssh "$r" "tar -C $remote/data -cf - ch | zstd -T0" | zstd -d | tar -xf - -C data

# Gitignored, but they are the night's only record of what happened when.
scp -q "$r:$remote/data/progress.tsv" "$r:$remote/data/night.log" data/ \
  || echo "WARN  could not copy progress.tsv / night.log" >&2

echo
echo "=== verify ==="
scripts/ch.sh -q "SELECT
    (SELECT sum(msgs) FROM h3_hourly) = (SELECT sum(rows_kept) FROM load_log) AS invariant_ok,
    (SELECT sum(msgs) FROM h3_hourly) AS h3_msgs,
    (SELECT sum(rows_kept) FROM load_log) AS log_rows_kept,
    (SELECT count() FROM load_log) AS files
FORMAT Vertical"
scripts/ch.sh -q "SELECT min(day) AS first_day, max(day) AS last_day, count(DISTINCT day) AS days
                  FROM vessel_day FORMAT Vertical"
du -sh data/ch
echo "--- last 3 lines of the VM's progress.tsv ---"
tail -3 data/progress.tsv

cat <<EOF

The store is home. It contains MMSI of private vessels — it must not leave this
machine, and the VM must not keep a copy.

DESTROY THE INSTANCE through the provider API/console now. This script does not
do it: deleting somebody's server on the strength of a passing checksum is not a
call a script gets to make.
EOF
