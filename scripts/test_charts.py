"""The geography oracle for the chart sheets (round 3).

    uv run --project notes scripts/test_charts.py

This project has shipped a mirrored map once (DECISIONS, S4-redo): a flip does
not error, it draws a plausible sea in the wrong place. Every map on the site
goes through two lines of projection — `project()` in scripts/chartkit.py for
the images and `chart.project` in site/js/chart.js for everything drawn over
them — and a depth grid that says where the sea is. This holds all three to
places whose position is a fact about Denmark, not a rerun of the code:

 (1) the bathymetry says sea in the Great Belt and the Kattegat, land at Viborg
 (2) chartkit draws a known point where it is: Drogden east of and south of
     Skagen on the image, and the ink peak of a one-point wash lands on the
     pixel project() names
 (3) chart.js puts the same places on the same pixels as chartkit, to a
     fraction of a pixel, run by node on the real file

Needs data/context/bathy_emodnet_0005.npz (uv run scripts/fetch_bathymetry.py)
and node. Reads no store.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck  # noqa: E402

PLACES = {                                   # lon, lat
    "Drogden":   (12.712, 55.536),
    "Skagen":    (10.59, 57.72),
    "Kiel":      (10.14, 54.32),
    "Rønne":     (14.69, 55.10),
}
SEA = {"Storebælt": (10.90, 55.30), "Kattegat": (11.50, 56.50)}
LAND = {"Viborg": (9.40, 56.45), "Odense": (10.39, 55.40)}


def main():
    fails = []
    box, w, h = ck.BOXES["denmark"], 400, 205

    # (1) sea and land
    for name, (lon, lat) in SEA.items():
        if not ck.is_sea(np.array([lon]), np.array([lat]))[0]:
            fails.append(f"bathymetry: {name} is not sea")
    for name, (lon, lat) in LAND.items():
        if ck.is_sea(np.array([lon]), np.array([lat]))[0]:
            fails.append(f"bathymetry: {name} is sea")

    # (2) the image: north is up, east is right, and the ink lands where project() says
    px = {k: ck.project(box, w, h, *v) for k, v in PLACES.items()}
    if not px["Drogden"][0] > px["Skagen"][0] > px["Kiel"][0]:
        fails.append(f"project: east is not to the right {px}")
    if not px["Skagen"][1] < px["Drogden"][1] < px["Kiel"][1]:
        fails.append(f"project: north is not up {px}")
    s = ck.Sheet(box, w)
    lon, lat = PLACES["Drogden"]
    s.wash([lon], [lat], [1], "cargo", pct=100, sigma_km=3)   # no plateau: one peak
    iy, ix = np.unravel_index(np.argmax(s._wash), s._wash.shape)
    ex, ey = ck.project(box, s.w, s.h, lon, lat)
    if abs(ix - ex) > 2 or abs(iy - ey) > 2:
        fails.append(f"wash: Drogden's ink is at pixel {ix},{iy}, project() says {ex:.1f},{ey:.1f}")

    # (3) the overlay: the same pixels from site/js/chart.js, run as it ships
    js = ("global.window = {}; require(process.argv[1]); const c = window.chart;"
          "const box = JSON.parse(process.argv[2]), p = JSON.parse(process.argv[3]);"
          "console.log(JSON.stringify(Object.fromEntries(Object.entries(p).map("
          f"([k, v]) => [k, c.project(box, {w}, {h}, v[0], v[1])]))))")
    out = subprocess.run(["node", "-e", js, str(ck.ROOT / "site/js/chart.js"),
                          json.dumps(list(box)), json.dumps(PLACES)],
                         capture_output=True, text=True)
    if out.returncode:
        fails.append(f"node: {out.stderr.strip()[:300]}")
    else:
        for k, (x, y) in json.loads(out.stdout).items():
            if abs(x - px[k][0]) > .01 or abs(y - px[k][1]) > .01:
                fails.append(f"chart.js puts {k} at {x:.2f},{y:.2f}; chartkit at {px[k][0]:.2f},{px[k][1]:.2f}")

    if fails:
        print("FAIL")
        for f in fails:
            print(f"  {f}")
        sys.exit(1)
    print(f"PASS  scripts/test_charts.py  (Drogden ink at {ix},{iy}; chart.js agrees on {len(PLACES)} places)")


if __name__ == "__main__":
    main()
