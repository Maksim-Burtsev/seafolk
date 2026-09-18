#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""S13 — the data behind site/explore/index.html. Stdlib only, no new dependency.

    uv run scripts/build_explore_data.py        (or: python3 scripts/build_explore_data.py)

Reads ONLY dist/dataset/*.parquet through `clickhouse local` with no --path, so
it never touches data/ch and never takes the store's exclusive lock. The export
is already privacy-tested by scripts/test_export.py; this script re-asserts the
one rule that matters here (every leisure row it reads has >= 5 boats) and
fails loudly if it ever stops being true.

Writes, all as `.js` files loaded by a <script> tag, because the page must open
from file:// by double-click and fetch() of a sibling file is blocked there:

    site/explore/data/index.js      months, cell dictionaries, colour-scale tops
    site/explore/data/YYYY-MM.js    one month, all fleets, loaded on demand
    site/explore/data/land.js       Natural Earth land clipped to the bbox

THE MEASURE, and why this one.

  Public fleets ("ship-hours"): for every hour in which anything of that fleet
  MOVED through the cell (moving_msgs > 0), add the number of distinct ships
  the archive heard in that cell-hour; sum over the month, over the res-7 cells
  that make up one res-6 cell.

  The obvious measure — sum(moving_msgs) — is unusable across years. The
  archive stores messages twice from 2023 on and again in 2015-09 (dataset card
  § Known biases 1 and 2: the Class A message tail doubles, p99 goes 14-17k ->
  32-44k, while the median stands still). A map coloured by message counts
  would show "more ships since 2023" that are the same ships counted twice.

  Head counts are structurally immune to that (card § Known biases 3): a
  duplicated message does not invent a vessel. So is the moving_msgs > 0 test —
  duplication can double a count, never lift it off zero. Both halves of this
  measure are therefore comparable across 2015..2026, which is the whole point
  of a month slider.

  It is an approximation in one direction: in a cell-hour where some ships moved
  and others lay still, the still ones are counted too. At res 6 / 1 hour that
  is what "ships were working here" means anyway, and the alternative (drop the
  cell-hour's whole head count unless every ship moved) is not available from
  the published columns.

  Small boats ("boat-days"): sum of the daily distinct-boat counts from
  leisure_daily, at res 5 x month, exactly as published. Nothing finer is
  derived: res 5 / day IS the private-fleet product, and every row of it already
  clears the >= 5 floor (asserted below).

SIZE. ~2.0 M (cell, fleet, month) rows do not fit in 40 MB as hex ids repeated
every month, so the res-6 and res-5 ids are written once into index.js and the
months carry indices into those arrays. Nothing is dropped or thresholded.
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "dataset"
OUT = ROOT / "site" / "explore" / "data"
LAND_SRC = ROOT / "data" / "context" / "ne_10m_land.geojson"

# The project bounding box (docs/DATA.md, dataset card § Coverage). The counts
# stop here, and so does the map's "All of it" view.
LON0, LAT0, LON1, LAT1 = 3.0, 53.0, 17.0, 59.0

# Land is clipped to a bigger box than the data. Clipped to the data box, the
# coast of Sweden and Germany ended in a straight grey edge floating inside the
# frame, which reads as a bug rather than as a map: land has to run off the
# edge of the frame at every preset.
MLON0, MLAT0, MLON1, MLAT1 = -2.0, 50.0, 22.0, 62.0

# Douglas-Peucker tolerance, in degrees. The coast people actually look at is
# kept near the source's own detail; the far coast, which is only there so the
# frame is full, is simplified hard to stay inside the file budget.
TOL_NEAR, TOL_FAR = 0.0015, 0.02

BUDGET_MB = 40
LAND_KB = 400
RES6, RES5 = 6, 5

# ship_group in the files -> the name a reader sees. `passenger` and `other`
# are renamed here and nowhere else; the page never says "ship_group".
PUBLIC_FLEETS = {"cargo": "cargo", "passenger": "ferries", "fishing": "fishing",
                 "other": "work_boats"}
LABELS = {"cargo": "Cargo ships", "ferries": "Ferries & passenger ships",
          "fishing": "Fishing boats", "work_boats": "Work boats",
          "small_boats": "Small boats"}


def ch(sql: str):
    """One clickhouse-local run over the exported Parquet, streamed row by row
    (the big query is 2 M rows; materialising it costs half a gigabyte for
    nothing). No --path: the store in data/ch has an exclusive lock and other
    sessions are using it."""
    p = subprocess.Popen(
        ["clickhouse", "local",
         "--max_bytes_before_external_group_by=6000000000",
         "--max_bytes_before_external_sort=6000000000",
         "-q", sql],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        if line.strip():
            yield line.rstrip("\n").split("\t")
    if p.wait() != 0:
        sys.exit(f"clickhouse failed:\n{p.stderr.read().strip()[:2000]}")


def clip_ring(ring):
    """Sutherland-Hodgman against the map rectangle. Convex clip window, so it
    is the right algorithm; on a concave ring it can leave a zero-area sliver
    along the boundary, which is invisible in a filled land layer.
    ponytail: stdlib clip instead of shapely — shapely would be a new dependency
    for one background polygon; swap it in if the map ever needs real geometry."""
    edges = ((0, MLON0, 1), (0, MLON1, -1), (1, MLAT0, 1), (1, MLAT1, -1))
    out = ring
    for axis, bound, sign in edges:
        inside = lambda pt: (pt[axis] - bound) * sign >= 0
        src, out = out, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur, axis, bound))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur, axis, bound))
        if not out:
            return []
    return out


def cross(a, b, axis, bound):
    t = (bound - a[axis]) / (b[axis] - a[axis])
    other = 1 - axis
    pt = [0.0, 0.0]
    pt[axis] = bound
    pt[other] = a[other] + t * (b[other] - a[other])
    return pt


def simplify(pts, tol):
    """Douglas-Peucker, iterative so a 3 500-point coastline cannot blow the
    recursion limit. Distances are in degrees, which is fine for a backdrop."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack, t2 = [(0, len(pts) - 1)], tol * tol
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        ax, ay = pts[a]
        dx, dy = pts[b][0] - ax, pts[b][1] - ay
        d2 = dx * dx + dy * dy
        best, at = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if d2 == 0:
                far = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / d2
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                far = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if far > best:
                best, at = far, i
        if best > t2:
            keep[at] = True
            stack += [(a, at), (at, b)]
    return [p for p, k in zip(pts, keep) if k]


def build_land() -> str:
    if not LAND_SRC.exists():
        sys.exit(f"missing {LAND_SRC} — see scripts/fetch_context.sh")
    # The two runnable checks on the geometry: a square straddling the west edge
    # comes back as a square cut off at the edge, a square entirely outside
    # comes back empty, and a straight line simplifies to its two ends.
    probe = clip_ring([[MLON0 - 1, 54], [MLON0 + 1, 54], [MLON0 + 1, 55], [MLON0 - 1, 55]])
    assert len(probe) == 4 and min(p[0] for p in probe) == MLON0, probe
    assert clip_ring([[MLON0 - 2, 54], [MLON0 - 1, 54], [MLON0 - 1, 55]]) == []
    assert simplify([[0, 0], [1, 1], [2, 2], [3, 3]], 0.01) == [[0, 0], [3, 3]]

    geo = json.loads(LAND_SRC.read_text())
    polys, kept_near = [], 0
    for feat in geo["features"]:
        g = feat["geometry"]
        raw = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in raw:
            xs = [p[0] for p in poly[0]]
            ys = [p[1] for p in poly[0]]
            if max(xs) < MLON0 or min(xs) > MLON1 or max(ys) < MLAT0 or min(ys) > MLAT1:
                continue
            near = not (max(xs) < LON0 or min(xs) > LON1 or max(ys) < LAT0 or min(ys) > LAT1)
            rings = []
            for ring in poly:
                c = simplify(clip_ring([list(p[:2]) for p in ring]),
                             TOL_NEAR if near else TOL_FAR)
                if len(c) >= 4:
                    # 4 decimals ~ 11 m: finer than a pixel at the deepest zoom
                    # the map allows, and no 9-digit run can appear in the file.
                    rings.append([[round(x, 4), round(y, 4)] for x, y in c])
            if rings:
                polys.append(rings)
                kept_near += near
    if not polys:
        sys.exit("land clip produced nothing — check the map box")
    fc = {"type": "Feature", "properties": {},
          "geometry": {"type": "MultiPolygon", "coordinates": polys}}
    print(f"land            {len(polys)} polygons ({kept_near} in the data box), "
          f"{sum(len(r) for p in polys for r in p)} points")
    return "window.SEAFOLK_LAND=" + json.dumps(fc, separators=(",", ":")) + ";\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # --- privacy assert, before anything is read for real ------------------
    floor = int(next(ch("SELECT min(vessels) FROM file('dist/dataset/leisure_daily.parquet')"))[0])
    if floor < 5:
        sys.exit(f"REFUSING TO BUILD: leisure_daily has a row with {floor} boats, "
                 "the k >= 5 floor is broken (CLAUDE.md, dataset card § Privacy rule)")
    print(f"leisure floor   min(vessels) = {floor}  (>= 5, ok)")

    months: dict[str, dict[str, dict[int, int]]] = {}
    cells: dict[int, dict[str, int]] = {RES6: {}, RES5: {}}
    counts: dict[str, int] = {}

    def add(res, month, fleet, hexid, value):
        idx = cells[res].setdefault(hexid, len(cells[res]))
        months.setdefault(month, {}).setdefault(fleet, {})[idx] = value
        counts[fleet] = counts.get(fleet, 0) + 1

    years = "20{15,18,21,22,23,24,25,26}"
    for month, group, hexid, value in ch(f"""
        SELECT formatDateTime(hour, '%Y-%m'), ship_group,
               h3ToString(h3ToParent(h3, {RES6})), toUInt64(sum(vessels))
        FROM file('dist/dataset/class_a_hourly_{years}.parquet')
        WHERE moving_msgs > 0
        GROUP BY 1, 2, 3"""):
        add(RES6, month, PUBLIC_FLEETS[group], hexid, int(value))

    for month, hexid, value in ch(f"""
        SELECT formatDateTime(day, '%Y-%m'), h3ToString(h3), toUInt64(sum(vessels))
        FROM file('dist/dataset/leisure_daily.parquet')
        WHERE ship_group = 'leisure'
        GROUP BY 1, 2"""):
        add(RES5, month, "small_boats", hexid, int(value))

    # --- per-fleet colour tops --------------------------------------------
    # The top of the scale is the 99th percentile of a fleet's cell values, not
    # its maximum: one shipping lane is 30x a busy bay, and scaling to it paints
    # the whole sea one flat colour. Values above the top clamp to the darkest.
    fleets = {}
    for fleet in list(PUBLIC_FLEETS.values()) + ["small_boats"]:
        vals = sorted(v for m in months.values() for v in m.get(fleet, {}).values())
        if not vals:
            sys.exit(f"no rows for fleet {fleet}")
        fleets[fleet] = {
            "label": LABELS[fleet],
            "res": RES5 if fleet == "small_boats" else RES6,
            "unit": "boat-days" if fleet == "small_boats" else "ship-hours",
            "top": vals[int(len(vals) * 0.99)],
            "max": vals[-1],
        }

    # --- write -------------------------------------------------------------
    order = sorted(months)
    inv = {res: [h for h, _ in sorted(d.items(), key=lambda kv: kv[1])]
           for res, d in cells.items()}
    index = {"built": date.today().isoformat(), "months": order,
             "cells6": inv[RES6], "cells5": inv[RES5], "fleets": fleets,
             "bbox": [LON0, LAT0, LON1, LAT1]}
    write(OUT / "index.js", "window.SEAFOLK_INDEX=" + dump(index) + ";\n")
    write(OUT / "land.js", build_land())
    land_kb = (OUT / "land.js").stat().st_size / 1024
    print(f"land.js         {land_kb:.0f} KB of {LAND_KB} KB")
    if land_kb > LAND_KB:
        sys.exit(f"land.js is {land_kb:.0f} KB — raise TOL_FAR or shrink the map box")

    for month in order:
        # [indices, values] per fleet — half the bytes of [[i,v],...].
        payload = {f: [list(d), list(d.values())] for f, d in months[month].items()}
        write(OUT / f"{month}.js",
              "window.SEAFOLK_MONTH=window.SEAFOLK_MONTH||{};"
              f'window.SEAFOLK_MONTH["{month}"]=' + dump(payload) + ";\n")

    total = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"months          {len(order)}  ({order[0]} .. {order[-1]})")
    print(f"cells           {len(inv[RES6])} at the town size, {len(inv[RES5])} at the island size")
    for fleet, meta in fleets.items():
        print(f"  {fleet:<12} {counts[fleet]:>9} rows   top {meta['top']:>6} "
              f"max {meta['max']:>6}  {meta['unit']}")
    print(f"size            {total / 1e6:.1f} MB of {BUDGET_MB} MB")
    if total > BUDGET_MB * 1e6:
        sys.exit(f"OVER BUDGET: {total / 1e6:.1f} MB > {BUDGET_MB} MB")


def dump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))


# Same shape as the project's own guard (`grep -rEn '\b[0-9]{9}\b' site/`): a
# 9-digit run that stands alone. An h3 id like 861964157ffffff can hold nine
# decimal digits by chance, but never as a standalone token — it always ends in
# f's — and a float's fraction is not a radio ID either.
NINE_DIGITS = re.compile(r"(?<![\w.])\d{9,}(?![\w.])")


def write(path: Path, text: str):
    """Every file goes through here so the MMSI-shaped guard cannot be skipped."""
    bad = NINE_DIGITS.search(text)
    if bad:
        sys.exit(f"{path.name}: 9-digit integer {bad.group()!r} — "
                 "that is the shape of a radio ID, refusing to write")
    path.write_text(text)


if __name__ == "__main__":
    main()
