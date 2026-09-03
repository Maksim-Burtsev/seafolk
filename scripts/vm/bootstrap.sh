#!/usr/bin/env bash
# Prepare a throwaway Linux VM to run the whole archive load.
#
#   ssh root@IP 'bash -s' < scripts/vm/bootstrap.sh
#
# Idempotent: re-running only re-pulls the repo — and refuses while the night is
# running, because `git pull` rewrites scripts bash is reading by byte offset
# (that has killed two queue runs already, docs/STATUS.md) and the schema step
# opens the store under the loader's exclusive lock. It does NOT start the
# queue — scripts/vm/night.sh does that, explicitly, once you have looked at
# the disk numbers this prints.
#
# SEAFOLK_REPO overrides the clone source (used by the Docker test to clone from
# a local mount instead of GitHub).
set -euo pipefail

CH_VERSION=26.7.5.10
REPO="${SEAFOLK_REPO:-https://github.com/Maksim-Burtsev/seafolk.git}"
DIR=/root/seafolk

if command -v tmux >/dev/null && tmux has-session -t =queue 2>/dev/null; then
  echo "tmux session 'queue' is running — not touching the repo or the store under it" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
# This script arrives on stdin (`bash -s`); a child that reads stdin would eat
# the rest of it, so apt-get gets /dev/null.
apt-get update -qq </dev/null
# procps is for pgrep: run_queue.sh's "is anybody still downloading this zip"
# guard is a pgrep, and a minimal cloud image does not always ship it.
apt-get install -y -qq unzip curl tmux git zstd procps ca-certificates </dev/null

if clickhouse --version 2>/dev/null | grep -qF "$CH_VERSION"; then
  echo "clickhouse $CH_VERSION already installed"
else
  case "$(uname -m)" in
    x86_64|amd64)  arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
  esac
  # Pinned to an exact version, never "latest", for two reasons:
  #   * the store this VM builds is read back on the laptop by the same binary,
  #     and a MergeTree written by a newer server is not guaranteed readable by
  #     an older one;
  #   * ClickHouse flipped geoToH3's argument order to (lat, lon, res) in 25.5
  #     (#78852, Backward Incompatible) and h3ToGeo's result order in 25.1.
  #     Neither swap errors — it silently mirrors the whole fleet into the
  #     Arabian Sea. scripts/ch.sh pins the setting; this pins the binary the
  #     setting exists on.
  tmp=$(mktemp -d)
  curl -fL --retry 5 --retry-delay 5 --retry-all-errors --no-progress-meter \
    -o "$tmp/ch.tgz" \
    "https://packages.clickhouse.com/tgz/stable/clickhouse-common-static-$CH_VERSION-$arch.tgz"
  # The tarball is clickhouse-common-static-<ver>/usr/bin/clickhouse (+ much
  # else we do not need); strip the three leading components and take the one.
  tar -xf "$tmp/ch.tgz" -C "$tmp" --strip-components=3 --wildcards '*/usr/bin/clickhouse'
  install -m 755 "$tmp/clickhouse" /usr/local/bin/clickhouse
  rm -rf "$tmp"
fi

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  # A clone from a bind-mounted checkout (the Docker test) trips git's
  # dubious-ownership check; a clone from a URL never reaches this.
  if [ -d "$REPO" ] && ! git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$REPO"; then
    git config --global --add safe.directory "$REPO"
  fi
  git clone "$REPO" "$DIR"
fi

cd "$DIR"
scripts/ch.sh sql/01_schema.sql

echo
echo "=== ready ==="
df -h /
echo "cpus: $(nproc)"
free -h | head -2
clickhouse --version
echo "repo: $DIR   next: scripts/vm/night.sh"
