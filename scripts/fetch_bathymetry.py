#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=2", "rasterio>=1.4"]
# ///
"""Depths for the chart basemap: EMODnet Bathymetry mean depth, 0.005 deg grid.

    uv run scripts/fetch_bathymetry.py

Writes data/context/bathy_emodnet_0005.npz (z in metres, negative = below sea
level; west, north, step). Machine output, gitignored; re-running is free once
the file exists. The WCS refuses one request over ~100 MB of native pixels, so
the box is fetched as six 3 x 2.5 degree tiles and mosaicked here; the tiles
live in a temp dir and are gone when this returns.
"""
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "context" / "bathy_emodnet_0005.npz"
WEST, EAST, SOUTH, NORTH, STEP = 7.0, 16.0, 53.5, 58.5, 0.005
URL = ("https://ows.emodnet-bathymetry.eu/wcs?service=wcs&version=1.0.0&request=getcoverage"
       "&coverage=emodnet:mean&crs=EPSG:4326&BBOX={},{},{},{}&format=image/tiff"
       "&interpolation=nearest&resx={s}&resy={s}")


def main():
    if OUT.exists():
        print(f"{OUT.relative_to(ROOT)} already here")
        return
    z = np.full((round((NORTH - SOUTH) / STEP), round((EAST - WEST) / STEP)), np.nan, np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        for x in (7, 10, 13):
            for y in (53.5, 56.0):
                f = Path(tmp) / f"{x}_{y}.tif"
                urllib.request.urlretrieve(URL.format(x, y, x + 3, y + 2.5, s=STEP), f)
                assert f.read_bytes()[:2] in (b"II", b"MM"), f"WCS error for tile {x},{y}: {f.read_text()[:300]}"
                with rasterio.open(f) as r:
                    a, b = r.read(1).astype(np.float32), r.bounds
                    if r.nodata is not None:
                        a[a == r.nodata] = np.nan
                r0, c0 = round((NORTH - b.top) / STEP), round((b.left - WEST) / STEP)
                z[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
    assert not np.isnan(z).any(), "a tile did not land in the mosaic"
    # The Skagerrak trench is the deepest water in the box (~700 m); the Great
    # Belt must read as sea. A mosaic with a swapped axis fails both.
    assert -750 < np.nanmin(z) < -500, np.nanmin(z)
    i, j = round((NORTH - 55.3) / STEP), round((10.9 - WEST) / STEP)   # Storebælt
    assert z[i, j] < -5, ("Storebælt is not sea", z[i, j])
    np.savez_compressed(OUT, z=z, west=WEST, north=NORTH, step=STEP)
    print(f"{OUT.relative_to(ROOT)}  {z.shape}  min {np.nanmin(z):.0f} m")


if __name__ == "__main__":
    main()
