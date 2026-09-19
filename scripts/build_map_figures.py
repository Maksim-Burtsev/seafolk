#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""S12 round 2 — the data behind the static map figures (site/js/minimap.js).

    uv run scripts/build_map_figures.py     (or: python3 scripts/build_map_figures.py)

Reads ONLY dist/dataset/*.parquet through `clickhouse local` with NO --path, so
it never touches data/ch and never waits on the store's exclusive lock. Writes
one file, site/media/maps.js, as `window.SEAFOLK_MAPS = {...}` loaded by a
<script> tag, because the site must open from file:// by double-click.

THE MEASURE, same as scripts/build_explore_data.py and for the same reason.

  Public fleets, "ship-hours": for every hour in which that fleet MOVED through
  the cell (moving_msgs > 0), add the ships the archive heard there; sum over
  the period. Head counts and the moving_msgs > 0 test are both immune to the
  archive's message duplication (dataset card § Known biases 2 and 3), so a
  2015 map and a 2025 map are the same instrument. sum(msgs) is not.

  Small boats, "boat-days": the daily distinct-boat counts from
  leisure_daily.parquet summed per resolution-5 cell over the month, exactly as
  published. Nothing finer is derived — res 5 x day IS the private-fleet
  product, and every row of it already clears the k >= 5 floor, which this
  script re-asserts twice: on the rows it reads and on the file it wrote.

HEXAGONS WITHOUT AN H3 LIBRARY. The browser gets a centre per cell plus, per
resolution, one radius in kilometres and one rotation in degrees, both measured
here from a real H3 cell boundary. Over a box 14 degrees wide the shape of a
cell barely moves, so a constant hexagon tiles to the eye and the page carries
no h3-js. Both H3 argument-order settings are pinned exactly as scripts/ch.sh
pins them: a swap does not error, it mirrors the fleet into the Arabian Sea.
"""
import json
import math
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "media" / "maps.js"
STORMS_CSV = ROOT / "data" / "context" / "storms.csv"
MEDIA = ROOT / "site" / "media"

LON0, LAT0, LON1, LAT1 = 3.0, 53.0, 17.0, 59.0     # dataset card § Coverage
BUDGET_MB = 2.5
RES6, RES5 = 6, 5

# The pin, character for character out of scripts/ch.sh.
PIN = ["--geotoh3_argument_order=lat_lon", "--h3togeo_lon_lat_result_order=0"]

# Daylight, as one fixed window in UTC for every storm day. Fishing boats work
# by the sun; a fixed window is not the true sunrise, but it is the SAME window
# on all three days of a triptych, which is what makes the three comparable.
DAY_H0, DAY_H1 = 6, 17

STORM_KEYS = ("amy", "malik", "pia")


def ch(sql, *extra):
    """One clickhouse-local run over the exported Parquet, streamed."""
    p = subprocess.Popen(
        ["clickhouse", "local", *PIN, *extra,
         "--max_bytes_before_external_group_by=6000000000", "-q", sql],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        if line.strip():
            yield line.rstrip("\n").split("\t")
    if p.wait() != 0:
        sys.exit(f"clickhouse failed:\n{p.stderr.read().strip()[:2000]}")


def one(sql):
    return next(ch(sql))


def hex_shape(res):
    """Radius in km and rotation in degrees of an H3 cell at this resolution,
    measured from real boundaries in the middle of the box. Rotation is the
    bearing of the first vertex in equal-aspect projected space, folded into
    one 60-degree sector; the spread over the box is printed so a future reader
    can see how good the constant is."""
    pts = [(lat, lon) for lat in (54.0, 55.5, 57.0) for lon in (5.0, 10.0, 15.0)]
    sel = " UNION ALL ".join(
        f"SELECT h3ToGeo(geoToH3({la},{lo},{res})) c, "
        f"h3ToGeoBoundary(geoToH3({la},{lo},{res})) b" for la, lo in pts)
    rs, angs = [], []
    for c, b in ch(f"SELECT c, b FROM ({sel})"):
        (clat, clon), verts = _tup(c), _arr(b)
        k = math.cos(math.radians(clat))
        for i, (vlat, vlon) in enumerate(verts):
            dx, dy = (vlon - clon) * k, vlat - clat
            rs.append(math.hypot(dx, dy) * 111.19)
            angs.append((math.degrees(math.atan2(dy, dx)) - 60 * i) % 60)
    rot = sorted(angs)[len(angs) // 2]
    spread = max(angs) - min(angs)
    # Measured 2026-09-19: ~16 deg out of a 60 deg sector, and most of it is
    # inside a single cell — an H3 cell is not a regular hexagon once it is
    # flattened onto lon/lat. So the constant is an approximation of a shape
    # that is itself irregular, and the ceiling here only catches a grid that
    # has come loose from the Earth. minimap.js draws 5 % over the radius so
    # the residual misalignment does not open seams between neighbours.
    assert spread < 20, f"res {res}: hexagon rotation varies by {spread:.0f} deg"
    print(f"hexagon res {res}   r = {sum(rs)/len(rs):.2f} km, "
          f"rotation {rot:.1f} deg (spread {spread:.1f})")
    return round(sum(rs) / len(rs), 2), round(rot, 1)


def _tup(s):
    return tuple(float(v) for v in s.strip("()").split(","))


def _arr(s):
    return [_tup(t) for t in re.findall(r"\(([^)]*)\)", s)]


def cells(sql, unit, title, note, res):
    """Run a (lon_milli, lat_milli, value) query into one layer."""
    flat, vals = [], []
    for lon, lat, v in ch(sql):
        lon, lat, v = int(lon), int(lat), int(v)
        # Half a degree of slack: a cell whose points are all inside the box
        # can have its centre just outside it, and a res-5 cell is ~0.16 deg
        # across. Mirroring misses by degrees, so the check still bites.
        if not (LON0 * 1000 - 500 <= lon <= LON1 * 1000 + 500
                and LAT0 * 1000 - 500 <= lat <= LAT1 * 1000 + 500):
            sys.exit(f"{title}: cell centre {lon/1000},{lat/1000} is outside the "
                     "dataset box — the grid is mirrored or the H3 pin is gone")
        flat += [lon, lat, v]
        vals.append(v)
    if not vals:
        sys.exit(f"{title}: no cells")
    vals.sort()
    return {"title": title, "unit": unit, "note": note, "res": res,
            "top": vals[int(len(vals) * 0.99)], "max": vals[-1],
            "min": vals[0], "n": len(vals), "cells": flat}


def public_layer(year, group, where, title, note):
    return cells(f"""
        SELECT toInt32(round(tupleElement(g, 2) * 1000)),
               toInt32(round(tupleElement(g, 1) * 1000)), v
        FROM (SELECT h3ToGeo(cell) AS g, v FROM (
              SELECT h3ToParent(h3, {RES6}) AS cell, toUInt64(sum(vessels)) AS v
              FROM file('dist/dataset/class_a_hourly_{year}.parquet')
              WHERE ship_group = '{group}' AND moving_msgs > 0 AND {where}
              GROUP BY cell))""",
        "ship-hours", title, note, RES6)


def small_layer(yyyymm, title, note):
    layer = cells(f"""
        SELECT toInt32(round(tupleElement(g, 2) * 1000)),
               toInt32(round(tupleElement(g, 1) * 1000)), v
        FROM (SELECT h3ToGeo(cell) AS g, v FROM (
              SELECT h3 AS cell, toUInt64(sum(vessels)) AS v
              FROM file('dist/dataset/leisure_daily.parquet')
              WHERE ship_group = 'leisure' AND toYYYYMM(day) = {yyyymm}
              GROUP BY cell))""",
        "boat-days", title, note, RES5)
    if layer["min"] < 5:
        sys.exit(f"REFUSING TO BUILD: {title} has a cell with {layer['min']} "
                 "boats — the k >= 5 floor is broken (CLAUDE.md)")
    return layer


def storm_days():
    """key -> (day before, first storm day, two days after the last), from
    data/context/storms.csv. Only the storms that have a clip in site/media."""
    rows = {}
    for line in STORMS_CSV.read_text().splitlines()[1:]:
        name, start, end = line.split(",")[:3]
        rows[name.lower()] = (date.fromisoformat(start[:10]),
                              date.fromisoformat(end[:10]))
    out = {}
    for key in STORM_KEYS:
        if not (MEDIA / f"storm-{key}.js").exists():
            sys.exit(f"no site/media/storm-{key}.js — the triptychs must match "
                     "the clips the page shows")
        first, last = rows[key]
        out[key] = (first - timedelta(days=1), first, last + timedelta(days=2))
    return out


def main():
    maps = {"built": date.today().isoformat(), "bbox": [LON0, LAT0, LON1, LAT1],
            "hex": {}, "layers": {}}
    for res in (RES5, RES6):
        r, rot = hex_shape(res)
        maps["hex"][str(res)] = [r, rot]

    floor = int(one("SELECT min(vessels) FROM file('dist/dataset/leisure_daily.parquet')")[0])
    if floor < 5:
        sys.exit(f"REFUSING TO BUILD: leisure_daily has a row with {floor} boats")
    print(f"leisure floor   min(vessels) = {floor}  (>= 5, ok)")

    L = maps["layers"]
    src = "Danish Maritime Authority AIS archive"
    L["small_july_2025"] = small_layer(202507, "July 2025",
        "Small boats heard in each patch of sea, added up over the month. " + src)
    L["small_january_2025"] = small_layer(202501, "January 2025",
        "The same count for January. " + src)
    L["small_july_2015"] = small_layer(201507, "July 2015",
        "The same count ten years earlier. " + src)

    L["fishing_2025"] = public_layer(2025, "fishing", "1", "Fishing boats, 2025",
        "Hours in which a fishing boat was under way in each patch of sea, "
        "all of 2025. " + src)
    L["ferries_2025"] = public_layer(2025, "passenger", "toYYYYMM(hour) = 202507",
        "Ferries, July 2025",
        "Hours in which a ferry or passenger ship was under way, July 2025. " + src)
    L["cargo_2025"] = public_layer(2025, "cargo", "toYYYYMM(hour) = 202507",
        "Cargo ships, July 2025",
        "Hours in which a cargo ship or tanker was under way, July 2025. " + src)

    labels = ("the day before", "the storm", "two days after")
    for key, days in storm_days().items():
        for label, day in zip(labels, days):
            L[f"storm_triptych_{key}_{day.isoformat()}"] = public_layer(
                day.year, "fishing",
                f"toDate(hour) = '{day}' AND toHour(hour) BETWEEN {DAY_H0} AND {DAY_H1}",
                f"{label} ({day.strftime('%-d %b')})",
                "Daylight hours in which a fishing boat was under way. " + src)
        maps.setdefault("triptychs", {})[key] = [
            f"storm_triptych_{key}_{d.isoformat()}" for d in days]

    write(OUT, "window.SEAFOLK_MAPS=" + json.dumps(maps, separators=(",", ":")) + ";\n")

    kb = OUT.stat().st_size / 1024
    for name, l in L.items():
        print(f"  {name:<34} {l['n']:>6} cells  min {l['min']:>5}  "
              f"top {l['top']:>6}  max {l['max']:>6}  {l['unit']}")
    print(f"maps.js         {kb:.0f} KB of {BUDGET_MB * 1024:.0f} KB")
    if kb > BUDGET_MB * 1024:
        sys.exit(f"OVER BUDGET: {kb:.0f} KB")
    check_written()


# Two places a cargo ship is always found, far apart, both named in
# docs/DATA.md. A mirrored or transposed grid puts the busiest cells in the
# Arabian Sea and every other assert in this file still passes.
DROGDEN = (55.536, 12.712)
GREAT_BELT = (55.0, 10.7, 55.9, 11.3)      # lat0, lon0, lat1, lon1
NORTH_SEA = (7.5, 9.0)                     # lon window west of Jutland


def check_written(path=OUT, top=60):
    """The oracle, on the file that was WRITTEN — centres included, so it needs
    no h3 call: if the pin had been wrong the coordinates in the file would be."""
    body = path.read_text().strip().rstrip(";")
    maps = json.loads(body[body.index("=") + 1:])
    c = maps["layers"]["cargo_2025"]["cells"]
    pts = sorted(((c[i + 2], c[i + 1] / 1000, c[i] / 1000)
                  for i in range(0, len(c), 3)), reverse=True)[:top]
    near = min(_km(DROGDEN, (lat, lon)) for _, lat, lon in pts)
    belt = [1 for _, lat, lon in pts if GREAT_BELT[0] <= lat <= GREAT_BELT[2]
            and GREAT_BELT[1] <= lon <= GREAT_BELT[3]]
    if near > 10:
        sys.exit(f"geography: the busiest {top} cargo cells come no closer than "
                 f"{near:.0f} km to Drogden {DROGDEN} — the grid is mirrored")
    if not belt:
        sys.exit(f"geography: none of the busiest {top} cargo cells is in the "
                 f"Great Belt {GREAT_BELT} — the grid is mirrored")

    # The second half of the oracle: the fishing map is the one the demo makes
    # a claim about, so it gets its own check. The North Sea grounds west of
    # Jutland must carry real weight, not a rounding error.
    f = maps["layers"]["fishing_2025"]["cells"]
    west = sum(f[i + 2] for i in range(0, len(f), 3)
               if NORTH_SEA[0] <= f[i] / 1000 <= NORTH_SEA[1] and f[i + 1] / 1000 > 55.0)
    whole = sum(f[i + 2] for i in range(0, len(f), 3))
    if west / whole < 0.05:
        sys.exit(f"geography: only {west/whole:.1%} of the fishing is west of "
                 "Jutland — that is not the North Sea fishery")
    print(f"geography      busiest cargo cells: {near:.1f} km from Drogden, "
          f"{len(belt)} in the Great Belt; {west/whole:.0%} of the fishing is "
          "west of Jutland")


def _km(a, b):
    return math.dist((a[0], a[1] * math.cos(math.radians(a[0]))),
                     (b[0], b[1] * math.cos(math.radians(b[0])))) * 111.19


# Same guard as scripts/build_explore_data.py: a standalone 9-digit run is the
# shape of a radio ID and nothing here has any business writing one.
NINE_DIGITS = re.compile(r"(?<![\w.])\d{9,}(?![\w.])")


def write(path: Path, text: str):
    bad = NINE_DIGITS.search(text)
    if bad:
        sys.exit(f"{path.name}: 9-digit integer {bad.group()!r} — that is the "
                 "shape of a radio ID, refusing to write")
    path.write_text(text)


if __name__ == "__main__":
    main()
