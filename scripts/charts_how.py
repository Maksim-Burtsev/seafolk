"""The chart sheet under figure H1 of site/how.html: the >= 5 rule, drawn.

    uv run --project notes scripts/charts_how.py

Writes site/media/charts/how-h1.webp and the manifest site/media/charts/how.js.

H1 IS A DRAWING, NOT DATA. The sheet is a real chart of the South Funen
archipelago (depths, coast, soundings), but the patches of sea and the boats in
them are invented: seven patch centres typed below, and for each a seeded
random scatter of candidate positions over water. site/js/how.js takes the
first n of them, n being the illustrative counts in scripts/site_data/how.py.
Nothing here reads the store or the dataset, so no boat on this sheet is a boat.
"""
import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck  # noqa: E402

BOX = (9.62, 11.22, 54.62, 55.36)       # Lillebælt, the South Funen islands, Langeland
PATCH_KM = 7.5                           # drawn radius of a patch; a real one is ~9 km across a side
CANDIDATES = 16                          # more than the largest illustrative count
# lon, lat of each patch, in the order of the illustrative counts in how.py
PATCHES = [(9.83, 55.17), (10.55, 54.98), (10.08, 55.02), (10.25, 54.72),
           (11.0, 55.1), (10.52, 54.70), (10.93, 54.74)]
DOTS = 60                                # the published side's stipple, drawn apart from the boats


def scatter(lon, lat, rnd, n=CANDIDATES, apart=.28):
    """n positions over water within the patch, at least `apart` of its radius apart."""
    pts, dlat = [], PATCH_KM / ck.KM_PER_DEG_LAT
    for _ in range(8000):
        a, r = rnd.uniform(0, 2 * math.pi), .85 * math.sqrt(rnd.random())
        x, y = lon + math.cos(a) * r * dlat * ck.ASPECT, lat + math.sin(a) * r * dlat
        if not ck.is_sea(np.array([x]), np.array([y]))[0]:
            continue
        if all(math.hypot((x - p[0]) / ck.ASPECT, y - p[1]) > apart * dlat for p in pts):
            pts.append((round(x, 4), round(y, 4)))
        if len(pts) == n:
            return pts
    sys.exit(f"patch at {lon}, {lat}: only {len(pts)} spots over water — move it")


def soundings(s, per_px=7000):
    """Chartkit samples soundings over its whole bathymetry grid, so a sheet this
    small gets a handful; this samples inside the box instead, in its style."""
    d, lons, lats, _ = ck.bathy()
    x0, x1, y0, y1 = s.box
    j = np.flatnonzero((lons > x0 + .03) & (lons < x1 - .03))
    i = np.flatnonzero((lats > y0 + .03) & (lats < y1 - .03))
    rng = np.random.default_rng(3)
    for _ in range(int(s.w * s.h / per_px)):
        a, b = rng.choice(i), rng.choice(j)
        if not np.isnan(d[a, b]) and d[a, b] >= 2:
            s.ax.text(lons[b], lats[a], f"{d[a, b]:.0f}", fontsize=5.2, color=ck.C["sounding"],
                      style="italic", family="serif", ha="center", va="center", zorder=3, alpha=.8)


def main():
    s = ck.Sheet(BOX, 1100).base(soundings=False)
    soundings(s)
    rnd = random.Random(11)
    patches = [{"lon": lon, "lat": lat, "pts": scatter(lon, lat, rnd),
                "dots": scatter(lon, lat, rnd, DOTS, .06)} for lon, lat in PATCHES]
    entry = {**s.save("how-h1"), "patch_km": PATCH_KM, "patches": patches}
    ck.write_manifest({"how-h1": entry}, "how")
    print(f"how-h1: {len(patches)} illustrative patches, {CANDIDATES} spots each")


if __name__ == "__main__":
    main()
