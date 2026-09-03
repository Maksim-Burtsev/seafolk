#!/usr/bin/env bash
# Start the whole night's work on the VM, detached, and get out of the way.
#
#   ssh root@IP 'cd /root/seafolk && scripts/vm/night.sh'
#
# The three queues run in sequence inside one tmux session called `queue`, each
# as its own scripts/run_queue.sh (the runner takes exactly one queue file and
# holds data/.queue.lock for its whole run, so they cannot overlap). Chained
# with && so a failure stops the night where it broke rather than rolling on.
set -euo pipefail
cd "$(dirname "$0")/../.."

if tmux has-session -t =queue 2>/dev/null; then
  echo "tmux session 'queue' is already running — leaving it alone"
else
  mkdir -p data
  # AHEAD=8 for the dailies (0.7 GB each, ~6 GB in flight). AHEAD=4 for the
  # monthlies: the biggest zip is ~19 GB, eight in flight would be ~150 GB and
  # on a 300 GB disk that is a coin toss against the FREE_FLOOR_GB=40 gate,
  # which STOPS the run rather than waiting. Four is ~75 GB and still saturates
  # the archive's per-stream throttle.
  tmux new-session -d -s queue -c "$PWD" "FREE_FLOOR_GB=40 bash -c '
    AHEAD=8 scripts/run_queue.sh queues/daily-2024-2026.txt &&
    AHEAD=4 scripts/run_queue.sh queues/ref-years.txt &&
    AHEAD=4 scripts/run_queue.sh queues/storms.txt
  ' >> data/night.log 2>&1; echo \"chain exited \$?\" >> data/night.log"
  echo "started tmux session 'queue'"
fi

cat <<'EOF'

watch it:
  tail -f data/progress.tsv        one line per loaded file, with an ETA
  tail -f data/night.log           everything the runner printed
  tmux attach -t queue             live (detach again with ctrl-b d)
  tmux has-session -t =queue       exit 0 while it is still going

when the session is gone, pull the store home from the laptop:
  scripts/vm/pull.sh <this VM's IP>
EOF
