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

The chart underneath (depths, land) is site/explore/data/sheet.js, drawn by
scripts/charts_explore.py.

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
import math
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "dataset"
OUT = ROOT / "site" / "explore" / "data"

# The project bounding box (docs/DATA.md, dataset card § Coverage). The counts
# stop here; the map shows the part of it the bathymetry covers.
LON0, LAT0, LON1, LAT1 = 3.0, 53.0, 17.0, 59.0

BUDGET_MB = 40
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
    check_geography()


def dump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))


# Two places a cargo ship is always found, and a box around each. Drogden is
# the deep-water gate of the Sound south of Copenhagen; the Great Belt carries
# everything that does not fit through it. Both are named in docs/DATA.md and
# neither is anywhere near the other, which is what makes them an oracle: a
# mirrored or transposed grid puts the busiest cells in the Arabian Sea, and a
# map drawn from it looks perfectly plausible until somebody knows the water.
DROGDEN = (55.536, 12.712)
GREAT_BELT = (55.0, 10.7, 55.9, 11.3)   # lat0, lon0, lat1, lon1


def check_geography(out=OUT, top=60):
    """The oracle, on the files that were WRITTEN.

    There was none at all: the whole pipeline could emit a mirrored world and
    every assert in this script would pass, because nothing here ever asked
    where anything is. This reads the committed cell index and the committed
    months back, takes the busiest cargo cells, and puts them on the Earth
    through `h3ToGeo` with BOTH argument-order settings pinned exactly as
    scripts/ch.sh pins them — the project states which convention it means
    rather than depending on which clickhouse is installed.
    """
    index = json.loads(read_js(out / "index.js", "window.SEAFOLK_INDEX="))
    cells6 = index["cells6"]
    total = {}
    for f in sorted(out.glob("*.js")):
        if not f.stem[:4].isdigit():
            continue
        month = json.loads(read_js(f, None))
        idx, vals = month.get("cargo") or [[], []]
        for i, v in zip(idx, vals):
            total[int(i)] = total.get(int(i), 0) + v
    if not total:
        sys.exit("no cargo cells in the written months — nothing to check")

    busiest = sorted(total, key=total.get, reverse=True)[:top]
    ids = "','".join(cells6[i] for i in busiest)
    out_tsv = subprocess.run(
        ["clickhouse", "local",
         "--geotoh3_argument_order=lat_lon",
         "--h3togeo_lon_lat_result_order=0",
         "-q", f"""SELECT round(tupleElement(g, 1), 4),
                          round(tupleElement(g, 2), 4)
                   FROM (SELECT h3ToGeo(stringToH3(h)) AS g
                         FROM (SELECT arrayJoin(['{ids}']) AS h))"""],
        capture_output=True, text=True, check=True).stdout
    places = [tuple(float(v) for v in ln.split("\t"))
              for ln in out_tsv.splitlines() if ln.strip()]

    near = min(_km(DROGDEN, p) for p in places)
    belt = [p for p in places if GREAT_BELT[0] <= p[0] <= GREAT_BELT[2]
            and GREAT_BELT[1] <= p[1] <= GREAT_BELT[3]]
    if near > 10:
        sys.exit(f"geography: the busiest {top} cargo cells come no closer "
                 f"than {near:.0f} km to the Drogden channel {DROGDEN} — the "
                 f"grid is mirrored or the h3 argument order is not pinned")
    if not belt:
        sys.exit(f"geography: none of the busiest {top} cargo cells is in the "
                 f"Great Belt {GREAT_BELT} — the grid is mirrored")
    print(f"geography      busiest cargo cells: {near:.1f} km from Drogden, "
          f"{len(belt)} in the Great Belt")


def _km(a, b):
    """Kilometres between two (lat, lon) points; flat earth is plenty here."""
    return math.dist((a[0], a[1] * math.cos(math.radians(a[0]))),
                     (b[0], b[1] * math.cos(math.radians(b[0])))) * 111.19


def read_js(path: Path, prefix):
    """The JSON out of one of the files this script writes."""
    body = path.read_text().strip().rstrip(";")
    if prefix:
        assert body.startswith(prefix), f"{path}: not {prefix}…"
        return body[len(prefix):]
    return body[body.index("]=") + 2:]


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
