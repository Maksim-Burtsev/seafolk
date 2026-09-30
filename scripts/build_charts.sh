#!/usr/bin/env bash
# Draw every map sheet under site/media/charts (and the explorer's base sheet)
# with scripts/chartkit.py. Run it after scripts/build_site_data.sh: the ferry
# race reads its two crossing times back out of the built ferries page.
#   scripts/build_charts.sh              all pages
#   CH_PATH=data/ch_x scripts/build_charts.sh   against a store clone
# Needs data/context/bathy_emodnet_0005.npz (uv run scripts/fetch_bathymetry.py).
set -euo pipefail
cd "$(dirname "$0")/.."
for page in index season pulse ferries storms how explore; do
  echo "== charts_$page"
  uv run --project notes "scripts/charts_$page.py"
done
