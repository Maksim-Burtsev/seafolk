"""The chart sheets of site/season.html — "A year under sail".

    uv run --project notes scripts/charts_season.py

Writes site/media/charts/season-*.webp and site/media/charts/season.js (the
manifest). Reads nothing but dist/dataset/leisure_daily.parquet — the export
that is floored at k >= 5 and tested by scripts/test_export.py — so no store
and no store clone is needed.

Small boats only, and only as the open dataset publishes them: a count of boats
per patch of sea (~250 km²) per day, drawn as dots scattered at random over the
water inside the patch. No dot is a boat's position. The floor is re-asserted
here on every row read.

  season-jul / season-jan    July and January 2025 over the Belts and the Sound
  season-2015                July 2015 on the same sheet (its 2025 twin is season-jul)
  season-usual / season-race the South Funen archipelago on a usual September
                             Friday and on Silverrudder's race day, one dot a boat
"""
import datetime
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck  # noqa: E402

DS = ck.ROOT / "dist" / "dataset" / "leisure_daily.parquet"
PIN = ["--geotoh3_argument_order=lat_lon", "--h3togeo_lon_lat_result_order=0"]
K_FLOOR = 5
INNER = (9.6, 12.8, 54.35, 56.25)      # the Belts, the Sound, the South Funen islands
FUNEN = (9.95, 11.1, 54.7, 55.25)      # the South Funen archipelago, Svendborg in the middle
BOATS_PER_DOT = 25                     # the four monthly sheets share this scale
RACE = "2025-09-19"                    # Silverrudder 2025 (sql/22_regatta_spikes.sql)


def ch(sql):
    out = subprocess.run(["clickhouse", "local", *PIN, "-q", sql + " FORMAT TSV"], cwd=ck.ROOT,
                         capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if out.returncode:
        sys.exit(out.stderr[:2000])
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def cells(where, box):
    """(lon, lat, boat-days, days) per res-5 cell inside `box`, summed over the rows
    `where` picks. The floor is checked on the ROWS, before anything is summed."""
    x0, x1, y0, y1 = box
    rows = ch(f"""SELECT h3ToGeo(h3).2 lon, h3ToGeo(h3).1 lat, sum(vessels), min(vessels), count()
                  FROM file('{DS}') WHERE ({where}) AND ship_group = 'leisure'
                  GROUP BY h3 HAVING lon BETWEEN {x0 - .2} AND {x1 + .2}
                                 AND lat BETWEEN {y0 - .15} AND {y1 + .15}""")
    assert rows, where
    assert min(int(r[3]) for r in rows) >= K_FLOOR, f"{where}: a small-boat row under the floor"
    return [(float(a), float(b), int(c), int(e)) for a, b, c, _, e in rows]


def fine_land(sheet):
    """Natural Earth's 1:10 m land is too coarse for a sheet this close in: it has
    no Tåsinge and draws Langeland with a ruler. Here the coast is EMODnet's own
    (land is where the bathymetry has no water), so land and depths agree.
    ponytail: page-local; belongs in chartkit.Sheet.base(land=...) if a second
    zoomed sheet appears."""
    import numpy as np
    d, lons, lats, _ = ck.bathy()
    for c in list(sheet.ax.collections):
        if c.get_zorder() == 20:            # base()'s Natural Earth land
            c.remove()
    land = ck._gauss(np.isnan(d).astype(float), .8)
    sheet.ax.contourf(lons, lats, land, levels=[.5, 2], colors=[ck.C["land"]], zorder=20)
    sheet.ax.contour(lons, lats, land, levels=[.5], colors=[ck.C["coast"]], linewidths=.7, zorder=21)
    return sheet


def month(m, box):
    return cells(f"toStartOfMonth(day) = '{m}-01'", box)


def main():
    charts = {}

    # The season, as water: July against January 2025, and July 2015 on the same scale.
    for cid, m in [("season-jul", "2025-07"), ("season-jan", "2025-01"), ("season-2015", "2015-07")]:
        s = ck.Sheet(INNER, 1200).base()
        lon, lat, v, _ = zip(*month(m, INNER))
        n = s.stipple(lon, lat, [round(x / BOATS_PER_DOT) for x in v], 9, "small", size=4.2, alpha=.8)
        charts[cid] = {**s.save(cid), "dots": n, "per_dot": BOATS_PER_DOT}
        print(f"{cid}: {n} dots from {len(v)} patches, {sum(v)} boat-days")

    # Race day in the archipelago against a usual day: the same weekday one and
    # two weeks either side, as sql/22 defines it. A usual patch is the mean of
    # the four days' published counts (a day the patch was under the floor
    # counts as none), and a patch whose mean rounds under five is left out.
    race = datetime.date.fromisoformat(RACE)
    usual = [str(race + datetime.timedelta(weeks=k)) for k in (-2, -1, 1, 2)]
    days = ",".join(f"'{d}'" for d in usual)
    base = [(a, b, round(v / len(usual))) for a, b, v, _ in cells(f"day IN ({days})", FUNEN)]
    base = [c for c in base if c[2] >= K_FLOOR]
    today = [(a, b, v) for a, b, v, _ in cells(f"day = '{RACE}'", FUNEN)]
    for cid, cs in [("season-usual", base), ("season-race", today)]:
        s = fine_land(ck.Sheet(FUNEN, 1200).base())
        lon, lat, v = zip(*cs)
        n = s.stipple(lon, lat, v, 7.5, "small", size=16, alpha=.85, seed=5)
        # the patch Svendborg sits in, for the figure's own tally
        svend = min(cs, key=lambda c: (c[0] - 10.61) ** 2 + (c[1] - 55.06) ** 2)[2]
        assert svend >= K_FLOOR
        charts[cid] = {**s.save(cid), "dots": n, "per_dot": 1}
        print(f"{cid}: {n} dots from {len(v)} patches; Svendborg's patch {svend}")
    charts["season-race"]["day"] = RACE

    ck.write_manifest(charts, "season")


if __name__ == "__main__":
    main()
