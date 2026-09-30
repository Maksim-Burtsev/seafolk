"""The chart sheet at the head of site/pulse.html.

    uv run --project notes scripts/charts_pulse.py

Writes site/media/charts/pulse-hero.webp and site/media/charts/pulse.js (the
manifest). No store is opened: the one data layer is the small boats of July
2025, read ONLY from dist/dataset/leisure_daily.parquet — the export floored at
k >= 5 and tested by scripts/test_export.py — through the same reader as
scripts/charts_index.py, which re-asserts the floor on the rows it read. They
are drawn as stipple scattered at random inside their ~9 km cell, so no dot is
a boat.

The sheet is the South Funen waters: Als and the marina at Sønderborg that the
page's harbour chart is about, and the archipelago where the sailing fleet
spends its summer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck                                        # noqa: E402
from charts_index import BOATS_PER_DOT, small_boats         # noqa: E402

BOX = (8.95, 12.35, 54.45, 55.62)
PER_DOT = BOATS_PER_DOT // 3     # a closer sheet, so finer dots than the country maps


def main():
    s = ck.Sheet(BOX, 1800).base()
    x0, x1, y0, y1 = BOX
    lon, lat, v = zip(*[r for r in small_boats("2025-07")
                        if x0 - .2 < r[0] < x1 + .2 and y0 - .1 < r[1] < y1 + .1])
    n = s.stipple(lon, lat, [round(x / PER_DOT) for x in v], 9, "small", size=3.2, alpha=.7)
    ck.write_manifest({"pulse-hero": {**s.save("pulse-hero"), "dots": n, "per_dot": PER_DOT}}, "pulse")
    print(f"pulse-hero: {n} dots, one per {PER_DOT} boat-days")


if __name__ == "__main__":
    main()
