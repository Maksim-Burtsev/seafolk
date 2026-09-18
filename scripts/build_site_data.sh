#!/usr/bin/env bash
# Refresh the numbers embedded in the pages under site/.
#
# A thin wrapper around scripts/build_site_data.py, kept because every document
# in this repo tells the reader to run this name. The work, the guards and the
# ledger are all in the Python; see its docstring.
#
#   scripts/build_site_data.sh                        # read data/ch
#   CH_PATH=data/ch_s12a scripts/build_site_data.sh   # read an APFS clone
#   scripts/build_site_data.sh index                  # one page
#
# CH_PATH is not read here: it is exported through to scripts/ch.sh, which is
# the only thing in the chain that opens the store.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run scripts/build_site_data.py "$@"
