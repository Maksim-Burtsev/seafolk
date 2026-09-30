"""The chart sheets and the hero animation of site/index.html.

    uv run --project notes scripts/charts_index.py        (CH_PATH=<clone> to read a store clone)

Writes site/media/charts/<id>.webp, site/media/charts/index.js (the manifest)
and site/media/charts/hero-ferries.js (one Saturday of ferries, for the canvas).

Two sources, two privacy stories:
  * Small boats come ONLY from dist/dataset/leisure_daily.parquet — the export
    that is floored at k >= 5 and tested by scripts/test_export.py. They are
    drawn as stipple scattered at random inside their ~9 km cell, and the
    minimum per cell is re-asserted here on the rows read.
  * Cargo, fishing and ferries are public. Cargo and fishing come from the
    open dataset's class_a_hourly files; the ferries' actual tracks come from
    the store's public_track (Class A passenger ships only, by its schema), and
    every radio ID in them is checked against vessel_day before anything is
    drawn: Class A, never leisure. Radio IDs never reach a written file.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck  # noqa: E402

ROOT = ck.ROOT
DS = ROOT / "dist" / "dataset"
PIN = ["--geotoh3_argument_order=lat_lon", "--h3togeo_lon_lat_result_order=0"]
K_FLOOR = 5
BOATS_PER_DOT = 30          # one dot = 30 boat-days, the same on every small-boat sheet
FERRY_DAY = "2025-07-12"    # a summer Saturday, the day scripts/fetch.sh's README names


def ch(sql, store=False):
    args = ["clickhouse", "local", *PIN, "--max_bytes_before_external_group_by=6000000000"]
    if store:
        args += ["--path", os.environ.get("CH_PATH", str(ROOT / "data" / "ch"))]
    out = subprocess.run([*args, "-q", sql + " FORMAT TSV"], cwd=ROOT, capture_output=True,
                         text=True, stdin=subprocess.DEVNULL)
    if out.returncode:
        sys.exit(out.stderr[:2000])
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def small_boats(month):
    """(lon, lat, boat-days) per res-5 cell for one month, from the floored export."""
    rows = ch(f"""SELECT h3ToGeo(h3).2, h3ToGeo(h3).1, sum(vessels), min(vessels)
                  FROM file('{DS}/leisure_daily.parquet')
                  WHERE toStartOfMonth(day) = '{month}-01' GROUP BY h3""")
    assert rows, month
    assert min(int(r[3]) for r in rows) >= K_FLOOR, f"{month}: a small-boat row under the floor"
    return [(float(a), float(b), int(c)) for a, b, c, _ in rows]


def public(year, groups, month=None):
    """(lon, lat, ship-hours under way) per res-7 cell. Ship-hours: the ships heard
    in every hour the fleet moved through the cell — immune to duplicated messages."""
    where = f"ship_group IN ({','.join(repr(g) for g in groups)})"
    if month:
        where += f" AND toMonth(hour) = {month}"
    rows = ch(f"""SELECT h3ToGeo(h3).2, h3ToGeo(h3).1, sumIf(vessels, moving_msgs > 0) v
                  FROM file('{DS}/class_a_hourly_{year}.parquet') WHERE {where}
                  GROUP BY h3 HAVING v > 0""")
    return [float(r[0]) for r in rows], [float(r[1]) for r in rows], [int(r[2]) for r in rows]


def ferry_tracks(day_from, day_to, step_min):
    """Segments of every passenger ship's track, radio IDs checked and then dropped."""
    bad = ch(f"""SELECT count() FROM (SELECT DISTINCT mmsi FROM public_track
                 WHERE toDate(ts) BETWEEN '{day_from}' AND '{day_to}') t
                 WHERE mmsi NOT IN (SELECT mmsi FROM vessel_day
                   WHERE day BETWEEN '{day_from}' AND '{day_to}'
                   AND mobile = 'Class A' AND ship_group != 'leisure')""", store=True)
    assert bad[0][0] == "0", f"{bad[0][0]} radio IDs in public_track are not public ships"
    rows = ch(f"""SELECT mmsi, toUnixTimestamp(ts), round(lon, 4), round(lat, 4), sog
                  FROM public_track WHERE toDate(ts) BETWEEN '{day_from}' AND '{day_to}'
                  AND toMinute(ts) % {step_min} = 0 ORDER BY mmsi, ts""", store=True)
    tracks = {}
    for m, t, lon, lat, sog in rows:
        tracks.setdefault(m, []).append((int(t), float(lon), float(lat), float(sog)))
    return list(tracks.values())       # the radio IDs end here


def segments(tracks, max_gap_s):
    out = []
    for pts in tracks:
        for a, b in zip(pts, pts[1:]):
            # a gap in the radio is not a straight line across the sea
            if b[0] - a[0] <= max_gap_s and abs(a[1] - b[1]) + abs(a[2] - b[2]) < .15:
                out.append([(a[1], a[2]), (b[1], b[2])])
    return out


def main():
    charts = {}

    # Small boats: July against January, and July 2015 against July 2025, all at one dot scale.
    for cid, month in [("i1-jul", "2025-07"), ("i1-jan", "2025-01"),
                       ("i2-2015", "2015-07"), ("i2-2025", "2025-07")]:
        s = ck.Sheet("denmark", 1200).base()
        lon, lat, v = zip(*small_boats(month))
        n = s.stipple(lon, lat, [round(x / BOATS_PER_DOT) for x in v], 9, "small", size=2.2, alpha=.75)
        charts[cid] = {**s.save(cid), "dots": n, "per_dot": BOATS_PER_DOT}
        print(f"{cid}: {n} dots from {len(v)} cells")

    # Cargo lanes, July 2025.
    s = ck.Sheet("denmark", 1600).base()
    s.wash(*public(2025, ["cargo"], 7), "cargo", pct=99.3, sigma_km=1.8)
    charts["i3-cargo"] = s.save("i3-cargo")

    # Fishing, all of 2025, as stipple: one dot per 40 ship-hours in a cell.
    s = ck.Sheet("denmark", 1600).base()
    lon, lat, v = public(2025, ["fishing"])
    n = s.stipple(lon, lat, [min(round(x / 40), 12) for x in v], 1.3, "fishing", size=1.1, alpha=.7)
    charts["i3-fishing"] = {**s.save("i3-fishing"), "dots": n}

    # The ferry web: every passenger ship's track through July 2025.
    s = ck.Sheet("denmark", 1600).base()
    segs = segments(ferry_tracks("2025-07-01", "2025-07-31", 2), 600)
    s.tracks(segs, "ferry", lw=.35, alpha=.18)
    charts["i3-ferries"] = s.save("i3-ferries")

    # The hero: a quiet chart with July's small boats as a faint stipple, and the
    # Saturday's ferries as data the canvas draws hour by hour. No cargo wash:
    # magenta under red ink reads as one colour, and the ferries are the subject.
    s = ck.Sheet("denmark", 1800).base()
    lon, lat, v = zip(*small_boats("2025-07"))
    s.stipple(lon, lat, [round(x / BOATS_PER_DOT) for x in v], 9, "small", size=1.5, alpha=.35)
    charts["hero"] = s.save("hero")

    x0, x1, y0, y1 = charts["hero"]["box"]
    day = ferry_tracks(FERRY_DAY, FERRY_DAY, 3)
    t0 = min(p[0] for tr in day for p in tr) // 86400 * 86400
    ships = []
    for tr in day:
        if max(p[3] for p in tr) < 3:          # a ship that never left the quay draws nothing
            continue
        # minutes since midnight UTC, and the position as a fraction of the sheet
        ships.append([[round((p[0] - t0) / 60), round((p[1] - x0) / (x1 - x0), 4),
                       round((y1 - p[2]) / (y1 - y0), 4)] for p in tr])
    (ck.OUT / "hero-ferries.js").write_text(
        f"// Written by scripts/charts_index.py: every ferry under way on {FERRY_DAY}, "
        "minutes since midnight UTC and position as a fraction of the hero sheet.\n"
        f"window.SEAFOLK_FERRY_DAY={json.dumps({'day': FERRY_DAY, 'ships': ships}, separators=(',', ':'))};\n")
    print(f"hero: {len(ships)} ferries under way on {FERRY_DAY}")

    ck.write_manifest(charts, "index")


if __name__ == "__main__":
    main()
