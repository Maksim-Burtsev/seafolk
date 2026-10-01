"""The chart sheets of site/storms.html (and the storm figure I6 on the story page).

    uv run --project notes scripts/charts_storms.py

Writes site/media/charts/storms-*.webp and the manifest site/media/charts/storms.js:

    storms-sea               the bare chart the storm animation plays on
                             (site/js/storm-player.js draws the fleets over it)
    storms-fishing           T2-fishing: where the fishing is, 2025, green stipple
    storms-anchorages        T3: the five Danish anchorages, marked with an anchor
    storms-<key>-0|1|2       T4 triptychs: the day before, the storm, two days after

Only the open dataset is read (dist/dataset/class_a_hourly_*.parquet: cargo,
ferries and fishing — public fleets). There is no small-boat layer on any of
these sheets, so no floor to assert here; the store is not opened at all.
"""
import csv
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck                                   # noqa: E402
from site_data._storms import ANCHORAGES, ANCHOR_SHORT   # noqa: E402

ROOT = ck.ROOT
DS = ROOT / "dist" / "dataset"
PIN = ["--geotoh3_argument_order=lat_lon", "--h3togeo_lon_lat_result_order=0"]

# The storms that have a triptych, the same keys scripts/render_storm.py files
# its clips under. Dates come from data/context/storms.csv, never from here.
TRIPTYCH = ("amy",)          # round 4: the one storm on the page
# Daylight, one fixed UTC window on every day of a triptych (the same window
# the old map figures used): fishing boats work by the sun, and a
# fixed window keeps the three days comparable.
DAY_H0, DAY_H1 = 6, 17
ANCHOR_BOX = (9.9, 14.5, 55.35, 57.95)      # Skagen down to the Sound, with Skåne to letter on
# The triptychs' box: the North Sea coast, the Skagerrak and the Kattegat, where
# the fishing is (see storms-fishing). The Baltic has almost none to lose.
FISH_BOX = (7.6, 12.9, 55.2, 58.0)


def ch(sql):
    out = subprocess.run(["clickhouse", "local", *PIN, "-q", sql + " FORMAT TSV"], cwd=ROOT,
                         capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if out.returncode:
        sys.exit(out.stderr[:2000])
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def fishing_hours(year, where):
    """(lon, lat, hours) per res-7 cell: the hours in which a fishing boat was
    under way there. Hours, not boats — one boat crossing two cells is in both."""
    rows = ch(f"""SELECT h3ToGeo(h3).2, h3ToGeo(h3).1, uniqExact(hour)
                  FROM file('{DS}/class_a_hourly_{year}.parquet')
                  WHERE ship_group = 'fishing' AND moving_msgs > 0 AND {where}
                  GROUP BY h3""")
    return [float(r[0]) for r in rows], [float(r[1]) for r in rows], [int(r[2]) for r in rows]


def storm_dates():
    with (ck.CONTEXT / "storms.csv").open() as f:
        return {r["name"].lower(): (date.fromisoformat(r["start_utc"][:10]),
                                    date.fromisoformat(r["end_utc"][:10]))
                for r in csv.DictReader(f)}


def anchors():
    """The five anchorages T3 measures, each as the middle of its cells."""
    cells = {}
    with (ck.CONTEXT / "anchorages.csv").open() as f:
        for r in csv.DictReader(f):
            if r["name"] in ANCHORAGES:
                cells.setdefault(r["name"], []).append(r["h3"])
    out = []
    for name in ANCHORAGES:
        assert cells.get(name), f"{name} has no cell in anchorages.csv"
        arr = ",".join(cells[name])
        lon, lat = ch(f"SELECT avg(h3ToGeo(c).2), avg(h3ToGeo(c).1) FROM "
                      f"(SELECT arrayJoin([{arr}]) AS c)")[0]
        lon, lat = float(lon), float(lat)
        x0, x1, y0, y1 = ANCHOR_BOX
        # a mirrored grid lands in the Arabian Sea, not a few km off
        assert x0 < lon < x1 and y0 < lat < y1, f"{name} at {lon},{lat} is off the sheet"
        out.append({"name": ANCHOR_SHORT[name], "lon": round(lon, 3), "lat": round(lat, 3)})
    return out


def main():
    charts = {}

    # T4 triptychs: one dot per daylight hour with a fishing boat under way in a
    # cell, the same scale on all three days of a storm.
    dates = storm_dates()
    for key in TRIPTYCH:
        first, last = dates[key]
        days = [first - timedelta(days=1), first, last + timedelta(days=2)]
        for i, d in enumerate(days):
            s = ck.Sheet(FISH_BOX, 900).base(soundings=False)
            lon, lat, v = fishing_hours(d.year, f"toDate(hour) = '{d}' AND toHour(hour) "
                                               f"BETWEEN {DAY_H0} AND {DAY_H1}")
            n = s.stipple(lon, lat, v, 1.8, "greenpen", size=15, alpha=.8, seed=11) if v else 0
            cid = f"storms-{key}-{i}"
            charts[cid] = {**s.save(cid), "day": d.isoformat(), "dots": n}
            print(f"{cid}: {d} {n} dots from {len(v)} cells")

    ck.write_manifest(charts, "storms")


if __name__ == "__main__":
    main()
