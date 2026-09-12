#!/usr/bin/env python3
"""S11 — the one runnable check on dist/dataset/. Fails loudly.

    uv run --project notes scripts/test_export.py
    CH_PATH=data/ch_a uv run --project notes scripts/test_export.py

scripts/export.sh runs it as its last step and exits with its status. It reads
the WRITTEN Parquet files with pyarrow (never the query that made them) and
recounts against the store through scripts/ch.sh, which honours CH_PATH.

Two independent oracles on every count and every sum: a live recount on the
store AND a hard-coded literal measured on 2026-09-12. The recount catches an
export that drops rows; the literal catches a STORE that silently changed under
an export that still agrees with it.

The privacy checks are the reason this file exists:
  * THE SCHEMA IS THE CONTRACT. Each product has an exact allow-list of
    (column, arrow type) below; a column that is not on it, or one whose type
    changed, is a FAIL. That is a stronger statement than a deny-list of
    identity names, which passes anything not thought of, and it also covers
    the AggregateFunction state (`vessels` must be uint64, and clickhouse
    cannot write a state to Parquet except as a string/binary column, which
    fails the type).
  * leisure_daily (the only private-fleet product) must have min(vessels) >= 5
    and every cell at H3 resolution 5 — a res-7 private cell is never
    published at any k (docs/DECISIONS.md 2026-08-30). Resolution is read out
    of the H3 index itself, bits 52-55, so no library and no round trip
    through the thing being tested.
  * the class_a files must carry NO 'leisure' row: the private fleet is every
    Class B transponder AND every ship_group = 'leisure' whatever its class
    (docs/DECISIONS.md 2026-09-12).
  * this script's own stdout is grepped for a 9-digit integer, like
    notes/plot_honesty.py's guard (z). H3 ids are 18-digit and do not match.
    Sums are printed with thousands separators so a legitimate 9-digit total
    does not trip the guard; nothing here prints a raw per-vessel value.
  * dist/dataset/README.md (the published card) is grepped for the same shape.
"""
import io
import re
import subprocess
import sys
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "dataset"

# Measured 2026-09-12 on the store: grouped (h3, hour, ship_group) rows of
# h3_hourly WHERE mobile = 'Class A' AND ship_group != 'leisure', per year.
CLASS_A = {2015: 45268396, 2018: 46676185, 2021: 44527813, 2022: 5983224,
           2023: 6156200, 2024: 36833820, 2025: 43112480, 2026: 28001968}
LEISURE_ROWS = 341092          # res-5 cell-days of the private fleet that
LEISURE_SHARE = 23.60          # clear vessels >= 5, and their % of all, +-0.5 pp
GROUPS = {"cargo", "passenger", "fishing", "leisure", "other"}

# THE SCHEMA CONTRACT, one entry per product. Exact list, exact order, exact
# arrow type. Anything else is a FAIL.
H3_COLS = [("msgs", "uint64"), ("vessels", "uint64"), ("moving_msgs", "uint64"),
           ("mean_sog", "double")]
SCHEMAS = {
    "class_a_hourly": [("h3", "uint64"), ("hour", "timestamp[ms, tz=UTC]"),
                       ("ship_group", "string")] + H3_COLS,
    "leisure_daily": [("h3", "uint64"), ("day", "date32[day]"),
                      ("ship_group", "string")] + H3_COLS,
    "ferry_daily": [("line", "string"), ("kind", "string"), ("island", "string"),
                    ("day", "date32[day]"), ("year", "uint16"),
                    ("season", "string"), ("daytype", "string"), ("dow", "uint8"),
                    ("crossings", "uint64"), ("vessels", "uint64"),
                    ("routes", "uint64"), ("baseline", "uint32"),
                    ("missed", "int64"), ("is_storm_day", "uint8"),
                    ("fleet_positions", "uint64"), ("fleet_sog_known", "uint64"),
                    ("fleet_moving", "uint64"), ("fleet_vessels_reporting", "uint64")],
}

log = io.StringIO()
fail = 0


def check(name, cond, detail=""):
    global fail
    line = f"{'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else "")
    if not cond:
        fail = 1
    print(line, file=log)
    print(line)


def q(sql):
    """One query through scripts/ch.sh (CH_PATH is inherited from the env)."""
    p = subprocess.run([str(ROOT / "scripts" / "ch.sh"), "-q", sql + " FORMAT TSV"],
                       capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"recount failed (exit {p.returncode}):\n{p.stderr.strip()}\n"
                 "  'Cannot lock file .../status' means another clickhouse "
                 "local holds the store (docs/DECISIONS.md).")
    return [l.split("\t") for l in p.stdout.splitlines() if l]


def product(fname):
    """dist/dataset file name -> key in SCHEMAS."""
    return "class_a_hourly" if fname.startswith("class_a_hourly_") \
        else fname[:-len(".parquet")]


def n(x):
    """A number in a detail string, with separators so the (z) guard, which
    looks for a bare 9-digit integer, does not fire on a legitimate total."""
    return f"{x:,}"


# ---------------------------------------------------------------- the files
expected = [f"class_a_hourly_{y}.parquet" for y in CLASS_A] + \
           ["leisure_daily.parquet", "ferry_daily.parquet"]
present = sorted(p.name for p in DIST.glob("*.parquet"))
for f in expected:
    check(f"{f} exists", (DIST / f).is_file())
check("no unexpected parquet in dist/dataset", set(present) <= set(expected),
      f"extra: {sorted(set(present) - set(expected))}")

# ------------------------------------------------- per-file generic checks
rows, sums = {}, {}
for f in present:
    pf = pq.ParquetFile(DIST / f)
    schema = pf.schema_arrow
    cols = schema.names
    rows[f] = pf.metadata.num_rows
    got = [(c, str(schema.field(c).type)) for c in cols]
    check(f"{f}: schema is exactly the published contract",
          got == SCHEMAS[product(f)], str(got))
    # One streaming pass per file: min/max of every integer column, the sums
    # the store is recounted against, the mean_sog range, msgs >= moving_msgs,
    # the H3 resolution bits, the `hour` range and the ship_group vocabulary.
    lo, hi, tot = {}, {}, {}
    sog_lo = sog_hi = ts_lo = ts_hi = None
    bad_moving = 0
    seen_groups = set()
    for b in pf.iter_batches(batch_size=1 << 20):
        for c in cols:
            a = b.column(c)
            if a.type in ("uint64", "int64", "uint32", "int32", "uint16", "uint8"):
                mm = pc.min_max(a).as_py()
                lo[c] = min(lo.get(c, mm["min"]), mm["min"])
                hi[c] = max(hi.get(c, mm["max"]), mm["max"])
                tot[c] = tot.get(c, 0) + (pc.sum(a).as_py() or 0)
        if "mean_sog" in cols:
            mm = pc.min_max(b.column("mean_sog")).as_py()
            if mm["min"] is not None:
                sog_lo = mm["min"] if sog_lo is None else min(sog_lo, mm["min"])
                sog_hi = mm["max"] if sog_hi is None else max(sog_hi, mm["max"])
        if "moving_msgs" in cols:
            bad_moving += pc.sum(pc.less(b.column("msgs"),
                                         b.column("moving_msgs"))).as_py() or 0
        if "h3" in cols:
            r = pc.min_max(pc.bit_wise_and(pc.shift_right(b.column("h3"), 52), 15)).as_py()
            lo["_res"] = min(lo.get("_res", r["min"]), r["min"])
            hi["_res"] = max(hi.get("_res", r["max"]), r["max"])
        if "hour" in cols:
            mm = pc.min_max(b.column("hour")).as_py()
            ts_lo = mm["min"] if ts_lo is None else min(ts_lo, mm["min"])
            ts_hi = mm["max"] if ts_hi is None else max(ts_hi, mm["max"])
        if "ship_group" in cols:
            seen_groups |= set(pc.unique(b.column("ship_group")).to_pylist())
    sums[f] = tot

    if "mean_sog" in cols:
        check(f"{f}: mean_sog is NULL or in (0, 100)",
              sog_lo is None or (sog_lo > 0 and sog_hi < 100),
              f"range {sog_lo} .. {sog_hi}")
    if "moving_msgs" in cols:
        check(f"{f}: msgs >= moving_msgs", bad_moving == 0, f"{bad_moving} rows")
    if "ship_group" in cols:
        check(f"{f}: ship_group vocabulary", seen_groups <= GROUPS,
              f"unknown: {sorted(seen_groups - GROUPS)}")
    # ferry_daily is a ZERO-FILLED panel: a line-day its fleet was not heard on
    # is a real row with crossings = vessels = 0 (sql/41's coverage columns say
    # why). The >= 1 floor is on the h3 products, where a row exists only
    # because a vessel was seen in the cell.
    if "vessels" in cols:
        floor = 1 if "h3" in cols else 0
        check(f"{f}: vessels >= {floor}", lo["vessels"] >= floor,
              f"min {lo['vessels']}")
    if f.startswith("class_a_hourly_"):
        year = int(f[len("class_a_hourly_"):-len(".parquet")])
        check(f"{f}: every h3 is resolution 7", lo["_res"] == hi["_res"] == 7,
              f"resolutions seen: {lo['_res']} .. {hi['_res']}")
        check(f"{f}: hour stays inside {year}",
              ts_lo is not None and ts_lo.year == ts_hi.year == year,
              f"{ts_lo} .. {ts_hi}")
        # The private fleet is Class B OR leisure, whatever the transponder:
        # a leisure row in a class_a file would be an unfloored private boat.
        check(f"{f}: no 'leisure' row (it belongs to the private fleet)",
              "leisure" not in seen_groups)
    if f == "leisure_daily.parquet":
        check("leisure_daily: min(vessels) >= 5 (THE PRIVACY FLOOR)",
              lo["vessels"] >= 5, f"min {lo['vessels']}")
        check("leisure_daily: every h3 is resolution 5, no res-7 cell",
              lo["_res"] == hi["_res"] == 5,
              f"resolutions seen: {lo['_res']} .. {hi['_res']}")

# ------------------------------------------------- one row per key, per file
# A duplicated key would double a cell's counts for every consumer and, on
# leisure_daily, could split one cell-day into two sub-floor halves. GROUP BY
# and not uniqExact: it spills to disk on the 45 M-row files.
for f in present:
    if not f.startswith(("class_a_hourly_", "leisure_daily")):
        continue
    t = "hour" if f.startswith("class_a_hourly_") else "day"
    distinct = int(q(f"SELECT count() FROM (SELECT h3, {t}, ship_group FROM "
                     f"file('dist/dataset/{f}') GROUP BY h3, {t}, ship_group)")[0][0])
    check(f"{f}: one row per (h3, {t}, ship_group)", rows[f] == distinct,
          f"{n(rows[f])} rows, {n(distinct)} keys")

# --------------------------------------------------- row counts and the sums
recount = {int(r[0]): [int(x) for x in r[1:]] for r in q(
    "SELECT y, count(), sum(m), sum(mm), sum(v) FROM ("
    "SELECT toYear(hour) AS y, h3, hour, ship_group, sum(msgs) AS m, "
    "sum(moving_msgs) AS mm, uniqExactMerge(vessels) AS v FROM h3_hourly "
    "WHERE mobile = 'Class A' AND ship_group != 'leisure' "
    "GROUP BY y, h3, hour, ship_group) GROUP BY y ORDER BY y")}
# A year loaded into the store but not exported by sql/70 is a FAIL, not a
# silent omission: the export must be extended when the store grows.
check("the store's Class A years are exactly the exported ones",
      set(recount) == set(CLASS_A),
      f"store {sorted(recount)} vs export {sorted(CLASS_A)}")
for y, lit in CLASS_A.items():
    f = f"class_a_hourly_{y}.parquet"
    r = recount.get(y, [None, None, None, None])
    check(f"{f}: rows == store recount", rows.get(f) == r[0],
          f"file {n(rows.get(f) or 0)} vs store {n(r[0] or 0)}")
    check(f"{f}: rows == the literal measured on 2026-09-12",
          rows.get(f) == lit, f"file {n(rows.get(f) or 0)} vs literal {n(lit)}")
    for i, c in enumerate(("msgs", "moving_msgs", "vessels"), start=1):
        check(f"{f}: sum({c}) == store recount",
              sums.get(f, {}).get(c) == r[i],
              f"file {n(sums.get(f, {}).get(c) or 0)} vs store {n(r[i] or 0)}")

# The private fleet: Class B OR leisure, res-5 parent cell x UTC day x group,
# spelled out here and not through sql/70's aliases, so a GROUP BY key that
# drifts in sql/70 shows up as a mismatch instead of matching by construction.
lr = q("SELECT count(), countIf(v >= 5), round(countIf(v >= 5) / count() * 100, 2), "
       "sumIf(m, v >= 5), sumIf(mm, v >= 5), sumIf(v, v >= 5) FROM ("
       "SELECT sum(msgs) AS m, sum(moving_msgs) AS mm, uniqExactMerge(vessels) AS v "
       "FROM h3_hourly WHERE mobile = 'Class B' OR ship_group = 'leisure' "
       "GROUP BY h3ToParent(h3, 5), toDate(hour), ship_group)")[0]
all_cd, floored, share = int(lr[0]), int(lr[1]), float(lr[2])
lf = "leisure_daily.parquet"
check("leisure_daily: rows == store recount with the floor",
      rows.get(lf) == floored, f"file {n(rows.get(lf) or 0)} vs store {n(floored)}")
check("leisure_daily: rows == the literal", rows.get(lf) == LEISURE_ROWS,
      f"file {n(rows.get(lf) or 0)} vs literal {n(LEISURE_ROWS)}")
check(f"leisure_daily: surviving share within 0.5 pp of {LEISURE_SHARE} %",
      abs(share - LEISURE_SHARE) <= 0.5, f"{share} % of {n(all_cd)} cell-days")
for i, c in enumerate(("msgs", "moving_msgs", "vessels"), start=3):
    check(f"leisure_daily: sum({c}) == store recount",
          sums.get(lf, {}).get(c) == int(lr[i]),
          f"file {n(sums.get(lf, {}).get(c) or 0)} vs store {n(int(lr[i]))}")

# The ferry recount runs sql/41's OWN block 1, not sql/70's copy of it, so a
# copy that drifts shows up here as a mismatch. The block is located by its
# markers, not by line numbers: `WITH` to the separator that follows it.
lines = (ROOT / "sql" / "41_ferry_daily.sql").read_text().splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("WITH"))
end = next(i for i, l in enumerate(lines[start:], start) if l.startswith("-- ===="))
blk = lines[start:end]
while blk and not blk[-1].strip():
    blk.pop()
if blk and blk[-1].startswith("SETTINGS"):
    blk.pop()
blk = "\n".join(blk)
fq = q(f"SELECT count(), sum(crossings), sum(vessels), sum(missed) FROM (\n{blk}\n) "
       "SETTINGS join_use_nulls = 0")[0]
ff = "ferry_daily.parquet"
check("ferry_daily: rows == a recount of sql/41 block 1",
      rows.get(ff) == int(fq[0]), f"file {n(rows.get(ff) or 0)} vs sql/41 {n(int(fq[0]))}")
for i, c in enumerate(("crossings", "vessels", "missed"), start=1):
    check(f"ferry_daily: sum({c}) == a recount of sql/41 block 1",
          sums.get(ff, {}).get(c) == int(fq[i]),
          f"file {n(sums.get(ff, {}).get(c) or 0)} vs sql/41 {n(int(fq[i]))}")

# ------------------------------------------------------------- the guard (z)
card = DIST / "README.md"
hit = re.search(r"\b\d{9}\b", card.read_text()) if card.is_file() else None
check("dist/dataset/README.md exists", card.is_file())
check("no 9-digit integer in the published card (the MMSI guard)",
      hit is None, hit.group(0) if hit else "")
hit = re.search(r"\b\d{9}\b", log.getvalue())
check("no 9-digit integer in this script's own output (the MMSI guard)",
      hit is None, hit.group(0) if hit else "")
print(f"\n{'FAIL' if fail else 'PASS'} — {len(log.getvalue().splitlines())} checks, "
      f"{sum(rows.values()) / 1e6:.1f} M rows in {len(rows)} files")
sys.exit(fail)
