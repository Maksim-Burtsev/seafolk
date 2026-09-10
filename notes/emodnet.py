# S10 — build the EMODnet cross-check context file for July 2021.
#
#   EMODNET_SCRATCH=/some/scratch uv run --project notes --group emodnet \
#       notes/emodnet.py
#
# THE --group IS NOT OPTIONAL. rasterio is a 69 MB wheel and this is the only
# file that imports it, so notes/pyproject.toml keeps it in the `emodnet`
# dependency group instead of in `dependencies`, where every other
# `uv run --project notes` caller would pay for it.
#
# Writes ONE file into the repo: data/context/emodnet_2021-07_leisure.tsv
# (un-ignored by name in .gitignore, read by sql/62_emodnet_compare.sql).
# Everything else it touches lives in the scratch directory and is deleted
# before the script returns — the two source zips are ~720 MB together and
# CLAUDE.md's disk budget has no room for them under data/.
#
# WHY A SCRATCH DIRECTORY AND NOT data/. The rule is "raw archive files are
# deleted right after they are aggregated"; these are the same kind of thing.
# EMODNET_SCRATCH defaults to the OS temp dir so the script is runnable
# anywhere; point it somewhere with ~1 GB free.
#
# IDEMPOTENT. The TSV is rewritten from scratch every run and carries no build
# date, so two runs produce the same file byte for byte — which is what makes a
# diff of this 5.7 MB blob mean something. A SUCCESSFUL RUN RE-DOWNLOADS BOTH
# ZIPS: main() deletes them at the end, so the "already here" branch in fetch()
# only helps after an INTERRUPTED run, when the ~720 MB are still on disk.
# It FAILS LOUDLY — an assert, not a warning — if a July-2021 member is
# missing, if the two rasters do not share a grid, or if the kept pixels fall
# outside the Danish bbox.
#
# NO PRIVACY SURFACE. This file reads nothing from data/ch. Its output is a
# third party's published aggregate.
import os
import re
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import rasterio.windows
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data/context/emodnet_2021-07_leisure.tsv"
SCRATCH = Path(os.environ.get("EMODNET_SCRATCH", tempfile.gettempdir())) / "emodnet"

RECORD = ("https://ows.emodnet-humanactivities.eu/geonetwork/srv/api/records/"
          "0f2f3ff1-30ef-49e1-96e7-8ca78d58a07c")
# ship-type codes as EMODnet numbers them: 04 = Sailing, 05 = Pleasure Craft
TYPES = {"04": "sailing", "05": "pleasure"}
MONTH = "2021-07"
# The member naming convention is vesseldensity_<code>_<YYYYMM01>.tif — one
# GeoTIFF per month, 96 of them per zip (2017-01 .. 2024-12) next to one
# ISO-19139 metadata XML. It is matched by regex, not built by format string,
# so a convention change is an assert instead of a silent miss.
MEMBER_RE = re.compile(r"vesseldensity_(\d\d)_(\d{6})01\.tif$", re.I)

# The project bbox (sql/01_schema.sql's ais_rows). Everything outside it is
# not in our store either, so a pixel there has nothing to be compared with.
LAT0, LAT1, LON0, LON1 = 53.0, 59.0, 3.0, 17.0
# EPSG:3035 is LAEA: a lat/lon box maps to a curved quadrilateral, so the
# read window is taken from the densified bounds and then widened. The exact
# filter is done in lon/lat afterwards; this margin only has to be generous.
MARGIN_M = 50_000


def fetch(code: str) -> Path:
    """Download one ship-type zip into the scratch dir. Skips an existing file."""
    name = f"EMODnet_HA_Vessel_Density_{code}.zip"
    path = SCRATCH / name
    if path.exists() and path.stat().st_size > 0:
        print(f"  {name}: already here, {path.stat().st_size / 1e6:.1f} MB")
        return path
    url = f"{RECORD}/attachments/{name}"
    t = time.time()
    # to a .part first: a half-written zip left by an interrupted run would
    # otherwise be "already here" on the next one.
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(path)
    mb = path.stat().st_size / 1e6
    print(f"  {name}: {mb:.1f} MB in {time.time() - t:.0f} s ({mb / (time.time() - t):.0f} MB/s)")
    return path


def extract_month(zip_path: Path, code: str) -> Path:
    """Pull the one July-2021 GeoTIFF out of the zip. Throws if it is not there."""
    want = MONTH.replace("-", "")
    with zipfile.ZipFile(zip_path) as z:
        members = z.namelist()
        print(f"  {zip_path.name}: {len(members)} members, first 10:")
        for m in members[:10]:
            print(f"      {m}")
        hits = [m for m in members
                if (g := MEMBER_RE.search(m)) and g.group(1) == code and g.group(2) == want]
        assert len(hits) == 1, (
            f"expected exactly one {MONTH} member for type {code} in {zip_path.name}, "
            f"found {hits}; members look like {members[2:4]}")
        print(f"  -> {MONTH} member: {hits[0]}")
        z.extract(hits[0], SCRATCH)
        return SCRATCH / hits[0]


def read_window(tif: Path):
    """Read the Danish part of one raster. Returns (values, window_transform, meta)."""
    with rasterio.open(tif) as src:
        x0, y0, x1, y1 = transform_bounds("EPSG:4326", src.crs,
                                          LON0, LAT0, LON1, LAT1, densify_pts=101)
        win = from_bounds(x0 - MARGIN_M, y0 - MARGIN_M, x1 + MARGIN_M, y1 + MARGIN_M,
                          src.transform).round_offsets().round_lengths()
        # clip to the raster: a boundless window would make the window
        # transform below disagree with the array read() actually returns.
        win = win.intersection(Window(0, 0, src.width, src.height))
        arr = src.read(1, window=win, masked=True).filled(0.0).astype(np.float64)
        # a nodata fill that is not flagged as nodata still has to go
        arr[~np.isfinite(arr)] = 0.0
        arr[arr < 0] = 0.0
        meta = dict(crs=str(src.crs), nodata=src.nodata,
                    px=abs(src.transform.a), py=abs(src.transform.e),
                    shape=src.shape)
        return arr, rasterio.windows.transform(win, src.transform), meta


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    print(f"scratch: {SCRATCH}")

    grids, metas, tifs, zips = {}, {}, [], []
    for code, label in TYPES.items():
        zp = fetch(code)
        zips.append(zp)
        tif = extract_month(zp, code)
        tifs.append(tif)
        arr, tr, meta = read_window(tif)
        grids[label], metas[label] = (arr, tr), meta
        print(f"  {label}: window {arr.shape}, full raster {meta['shape']}, "
              f"crs {meta['crs']}, pixel {meta['px']:.0f}x{meta['py']:.0f} m, "
              f"nodata {meta['nodata']}")

    (a_sail, tr_sail), (a_plea, tr_plea) = grids["sailing"], grids["pleasure"]
    # The two ship types must be on the same grid or summing them is nonsense.
    assert a_sail.shape == a_plea.shape, (a_sail.shape, a_plea.shape)
    assert tuple(tr_sail)[:6] == tuple(tr_plea)[:6], (tr_sail, tr_plea)
    assert metas["sailing"]["crs"] == metas["pleasure"]["crs"] == "EPSG:3035", metas
    assert round(metas["sailing"]["px"]) == 1000, metas["sailing"]

    # ROUND BEFORE SELECTING, not after. The TSV carries 4 decimals, and a
    # pixel holding 0.00003 h is written as 0.0000 — kept by a `> 0` test on
    # the raw array and then read back as an empty cell. Two res-7 cells came
    # out that way, with an EMODnet total of exactly 0.0, which made "cells
    # EMODnet has hours in" disagree with itself by two. Rounding first makes
    # the mask, the printed sums and the file agree by construction.
    a_sail, a_plea = np.round(a_sail, 4), np.round(a_plea, 4)
    rows, cols = np.nonzero((a_sail > 0) | (a_plea > 0))
    print(f"  pixels with any leisure hours in the read window: {len(rows)}")
    # pixel CENTRES, not corners: rasterio's xy() offsets by half a pixel.
    xs, ys = rasterio.transform.xy(tr_sail, rows, cols, offset="center")
    lons, lats = warp_transform("EPSG:3035", "EPSG:4326", list(xs), list(ys))
    lons, lats = np.array(lons), np.array(lats)

    keep = (lats >= LAT0) & (lats <= LAT1) & (lons >= LON0) & (lons <= LON1)
    lons, lats = lons[keep], lats[keep]
    v_sail = a_sail[rows, cols][keep]
    v_plea = a_plea[rows, cols][keep]
    assert len(lons) > 1000, f"only {len(lons)} pixels kept — the bbox filter is wrong"

    order = np.lexsort((lons, lats))          # stable output, so a diff is a diff
    lons, lats, v_sail, v_plea = lons[order], lats[order], v_sail[order], v_plea[order]

    # NO BUILD DATE AND NO PROVENANCE LINE THAT CHANGES BETWEEN RUNS. A
    # "# built: <today>" line used to sit above the column line; it made every
    # rebuild a diff of the whole 5.7 MB file and contradicted the docstring's
    # "two runs produce the same file". The COUNT of these lines is what
    # sql/62_emodnet_compare.sql skips and asserts (17), so adding one here
    # means changing it there — the query throws either way, loudly.
    header = [
        f"# EMODnet Human Activities — vessel density, {MONTH}, leisure ship types.",
        f"# source:  {RECORD}",
        f"# zips:    {RECORD}/attachments/EMODnet_HA_Vessel_Density_0[45].zip",
        "# members: vesseldensity_04_20210701.tif (04 = Sailing),",
        "#          vesseldensity_05_20210701.tif (05 = Pleasure Craft)",
        "# licence: Creative Commons CC-BY 4.0 (as stated in the dataset's",
        "#          ISO-19139 metadata inside each zip) — attribution required.",
        "# crs:     EPSG:3035 (ETRS89 / LAEA Europe), 1000 x 1000 m pixels,",
        "#          equal-area, so one pixel is exactly 1 km2.",
        "# unit:    hours per square kilometre per month. EMODnet builds it by",
        "#          drawing a line between consecutive positions of one ship and",
        "#          intersecting it with the 1 km grid, so it is TRACK time, not",
        "#          message count. Per 1 km2 pixel, hours/km2 = hours.",
        "# rows:    pixel CENTRES reprojected to WGS84, kept where the centre is",
        f"#          inside lat {LAT0}-{LAT1}, lon {LON0}-{LON1} (the project bbox)",
        "#          AND at least one of the two types is > 0. Sorted by lat, lon.",
        "# lon\tlat\thours_sailing\thours_pleasure",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        f.write("\n".join(header) + "\n")
        for lo, la, s, p in zip(lons, lats, v_sail, v_plea):
            f.write(f"{lo:.6f}\t{la:.6f}\t{s:.4f}\t{p:.4f}\n")

    print(f"\nwrote {OUT.relative_to(REPO)}")
    print(f"  header lines: {len(header)}  <- sql/62's input_format_tsv_skip_first_lines")
    print(f"  pixels:       {len(lons)}   "
          f"(sailing > 0: {(v_sail > 0).sum()}, pleasure > 0: {(v_plea > 0).sum()}, "
          f"both > 0: {((v_sail > 0) & (v_plea > 0)).sum()})")
    print(f"  hours sailing:  {v_sail.sum():,.1f}")
    print(f"  hours pleasure: {v_plea.sum():,.1f}")
    print(f"  hours total:    {(v_sail + v_plea).sum():,.1f}")
    print(f"  bbox kept:    lat {lats.min():.4f} .. {lats.max():.4f}, "
          f"lon {lons.min():.4f} .. {lons.max():.4f}")
    print(f"  file size:    {OUT.stat().st_size / 1e6:.2f} MB")

    for p in tifs + zips:
        p.unlink(missing_ok=True)
    for d in sorted(SCRATCH.glob("EMODnet_HA_Vessel_Density_*"), reverse=True):
        if d.is_dir():
            for leftover in d.iterdir():
                leftover.unlink()
            d.rmdir()
    print(f"  deleted {len(tifs)} tif(s) and {len(zips)} zip(s); "
          f"scratch now holds {sorted(p.name for p in SCRATCH.iterdir())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
