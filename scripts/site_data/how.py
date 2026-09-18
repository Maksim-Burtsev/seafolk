"""site/how.html — how it was made: the pipeline, the privacy rule, the bugs.

This page is the one place on the site that is allowed to name the real terms,
once each, in brackets — its readers are the people who will run the queries.
It is not allowed to name a radio ID even so: `scripts/test_site.py` refuses
the word anywhere under site/, in any file, on any page.

    figure  what it says                        where the numbers come from
    H1      the >= 5 rule, drawn                nothing — it is an illustration
    H2      what that rule costs                h3_hourly, sql/70_export.sql's
                                                own grouping, recomputed here
    H3      the pipeline                        load_log, vessel_day, du
    prose   the mirrored grid                   geoToH3 under scripts/ch.sh's pin
    prose   the double-stored messages          sql/60_coverage_index.sql block 6
    prose   the ferries filed as something else sql/44_hidden_fleet.sql
    prose   a radio is not a boat               sql/61_adoption.sql block 1
    prose   the box is not Denmark              sql/61_adoption.sql block 4
    prose   somebody else's map                 sql/62_emodnet_compare.sql

PRIVACY. Nothing here reads a position, a name or an identifier. The private
fleet appears as two shares (what the floor keeps) and as three head counts
that are store-wide sums over thousands of boats. The Laeso cell quoted in the
prose is one res-7 cell with 353 distinct boats in a month — an aggregate well
over the floor, and its cell id is deliberately not carried into the page.
"""
import os

from . import ROOT, blocks, typed

# The floor itself (CLAUDE.md, docs/dataset-card.md § Privacy rule).
FLOOR = 5

# ITU-R M.1371: a Class A transponder sends at most one position report every
# 2 s, so this many in a day is a property of the radio. sql/60 block 6 counts
# the vessel-days above it.
REPORT_SECONDS = 2
CAP_A = 86_400 // REPORT_SECONDS

# THE HAND-TYPED NUMBERS ON THIS PAGE. Every one is a wall clock or a byte
# count in a log, not a column in any table, and each carries its source.
#
# docs/STATUS.md § S4-redo: 2026-09-06 14:56:59 -> 2026-09-08 01:50:30 UTC
# = 34 h 54 min, 1 233 GB pulled over 949 archives.
RELOAD_HOURS = 35
PULLED_TB = 1.2
# CLAUDE.md § Data facts: the archive's 2014 -> 2026 stretch, zipped.
ARCHIVE_TB = 2.3
# docs/STATUS.md § S4 "The measurement that shaped the session": one connection
# to the archive gets 3.78 MB/s of an ~11 MB/s link, so the runner downloads
# AHEAD files while loading stays serial — 214 s/file -> 60 s/file. AHEAD ran
# at 8 for the daily files of the S4-redo reload (§ S4-redo, "How it ran").
ONE_STREAM_MBS, LINK_MBS = 3.78, 11.0
AHEAD = 8
PREFETCH_SPEEDUP = 3.6
# docs/STATUS.md § S4-tails, defect 1: aisdk-2015-09.zip blew the 21.6 GiB
# memory cap inside the aggregation; scripts/ch.sh now spills past 6 GB.
OOM_MILLION = 806
SPILL_GB = 6

# The six years the store holds whole or nearly so; 2022 and 2023 are two storm
# months each and a head count over 59 days is not a year's head count.
YEARS = [2015, 2018, 2021, 2024, 2025, 2026]

# Copenhagen, as scripts/test_load.sh hard-codes it after S4-redo.
CPH = (55.6761, 12.5683)

# Column names, as index.py spells them: these query files emit several result
# sets on one stdout and `blocks` tells them apart by width.
A1 = ("year window coverage loaded_days class_b_vessels class_b_leisure_vessels "
      "class_a_vessels class_a_vessels_5d leisure_per_class_a "
      "leisure_per_class_a_5d class_b_5d class_b_1d class_a_1d").split()
A1_INT = ("year loaded_days class_b_vessels class_b_leisure_vessels "
          "class_a_vessels class_a_vessels_5d class_b_5d class_b_1d "
          "class_a_1d").split()
A4 = ("year vessel_days median_msgs_per_vessel_day vessel_hours msgs "
      "msgs_per_vessel_hour vessel_days_moving median_dist_nm_moving "
      "danish_share german_share").split()
B6 = ("mon loaded_days vessel_days median_msgs mean_msgs p90_msgs p99_msgs "
      "max_msgs vd_over_cap share_over_cap max_over_cap_x dup_month").split()
B6_INT = "loaded_days vessel_days max_msgs vd_over_cap dup_month".split()
H1 = "year fleet visible_days hidden_days hidden_share vessels_with_hidden".split()
H3 = "name year line kind island hidden_days ship_type".split()
E3 = ("res n_both n_emodnet_only n_ours_only rank_both rank_union pearson "
      "top10 top25 floored_out emo_in_our_zero our_in_emo_zero n_union").split()
E4 = ("res side h3 lat lon our_hours our_vessels emo_hours rank_ours "
      "rank_emo").split()
E5 = "zone emo_hours emo_missed missed_share cells".split()

# The fractions a reader hears as a quantity. Sixths and sevenths are not on
# the list on purpose: "five sixths" is read as arithmetic, "four fifths" as an
# amount, and the exact percentage is always in the same figure.
FRACTIONS = {0.1: "a tenth", 0.2: "a fifth", 0.25: "a quarter",
             1 / 3: "a third", 0.5: "half", 2 / 3: "two thirds",
             0.75: "three quarters", 0.8: "four fifths", 0.9: "nine tenths"}


def sp(x):
    """12345.6 -> '12 346', the separator the rest of the site prints."""
    return f"{round(x):,}".replace(",", " ")


def frac(x):
    """0.764 -> 'three quarters'. The closest fraction on the list above."""
    return min(FRACTIONS.items(), key=lambda kv: abs(x - kv[0]))[1]


# ------------------------------------------------------------- H1, H2 ----
def floor_cost(ch):
    """What the >= 5 floor keeps, at both grains, recomputed here.

    The published grain first: sql/70_export.sql's own GROUP BY, so this is
    the cost of the actual export and not of something near it. Then the grain
    that was rejected — res 7 x hour — because the page claims it does not
    survive the floor and a claim gets a number.

    Only counts and shares come back. The message totals behind the shares run
    to nine digits, which is the shape of a radio ID and the driver's guard (a)
    refuses them on sight; they are divided inside the query instead.
    """
    private = "mobile = 'Class B' OR ship_group = 'leisure'"
    day = ch("-q", f"""
        WITH d AS (
            SELECT h3ToParent(h3, 5) AS c, toDate(hour) AS dy, ship_group AS g,
                   uniqExactMerge(vessels) AS v, sum(moving_msgs) AS mm
            FROM h3_hourly WHERE {private} GROUP BY c, dy, g)
        SELECT count(), countIf(v >= {FLOOR}),
               round(countIf(v >= {FLOOR}) / count(), 4),
               round(sumIf(mm, v >= {FLOOR}) / sum(mm), 4) FROM d""")[0]
    hour = ch("-q", f"""
        WITH d AS (
            SELECT h3, hour, ship_group AS g,
                   uniqExactMerge(vessels) AS v, sum(moving_msgs) AS mm
            FROM h3_hourly WHERE {private} GROUP BY h3, hour, g)
        SELECT round(countIf(v >= {FLOOR}) / count(), 4),
               round(sumIf(mm, v >= {FLOOR}) / sum(mm), 4) FROM d""")[0]
    return {"cells_total": int(day[0]), "cells_kept": int(day[1]),
            "cells_share": float(day[2]), "moving_share": float(day[3]),
            "hourly_cells_share": float(hour[0]),
            "hourly_moving_share": float(hour[1])}


def pleasure_with_a_big_radio(ch):
    """How many pleasure craft carry a Class A transponder each year.

    This is the reason the private fleet is not simply "Class B": these boats
    are private and their transponder says otherwise, so the floor is keyed on
    the boat, not the radio (docs/DECISIONS.md 2026-09-12). Only the whole
    years are read — a 59-day storm month has a 59-day head count.
    """
    rows = ch("-q", "SELECT toYear(day), uniqExact(mmsi) FROM vessel_day "
                    "WHERE mobile = 'Class A' AND ship_group = 'leisure' "
                    "GROUP BY 1 ORDER BY 1")
    counts = [int(v) for y, v in rows if int(y) in YEARS]
    return min(counts), max(counts)


# ----------------------------------------------------------------- H3 ----
def pipeline(ch):
    """The size and the speed of the thing, off `load_log` and the store.

    `rows_read` sums past nine digits, so the query divides before it prints.
    The rate is a median over the 949 files rather than total rows over total
    seconds: one 19 GB monthly file would otherwise decide the number for all
    of them.
    """
    files, read, kept, hours, rate = ch("-q", """
        SELECT count(), round(sum(rows_read) / 1e9, 1),
               round(sum(rows_kept) / 1e9, 1), round(sum(seconds) / 3600, 1),
               round(median(rows_read / seconds) / 1e6, 1) FROM load_log""")[0]
    days, years = ch("-q", "SELECT count(DISTINCT day), uniqExact(toYear(day)) "
                           "FROM vessel_day")[0]
    cells = ch("-q", "SELECT uniqExact(h3) FROM h3_hourly")[0][0]
    store = ROOT / os.environ.get("CH_PATH", "data/ch")
    return {"files": int(files), "read_billion": float(read),
            "kept_billion": float(kept), "load_hours": float(hours),
            "rate_million": float(rate), "days": int(days), "cells": int(cells),
            "years": int(years),
            "store_gb": round(sum(f.stat().st_size for f in store.rglob("*")
                                  if f.is_file()) / 2 ** 30)}


# -------------------------------------------------------------- bug 1 ----
def copenhagen(ch):
    """The cell scripts/test_load.sh hard-codes, and the cell the bug made.

    Handing the pinned geoToH3 its two arguments the wrong way round IS the
    bug, so the mirrored cell is produced by doing exactly that. The store
    should hold rows in the first and nothing at all in the second; the assert
    is here because a page that says so should fail the build if it stops
    being true.
    """
    lat, lon = CPH
    rows = int(ch("-q", f"SELECT count() FROM h3_hourly "
                        f"WHERE h3 = geoToH3({lat}, {lon}, 7)")[0][0])
    mirrored = int(ch("-q", f"SELECT count() FROM h3_hourly "
                            f"WHERE h3 = geoToH3({lon}, {lat}, 7)")[0][0])
    assert rows > 0 and mirrored == 0, \
        f"the grid moved: Copenhagen {rows} rows, its mirror {mirrored}"
    return rows


# -------------------------------------------------------------- bug 2 ----
def impossible(ch):
    """sql/60 block 6 — the share of big-ship days above the physical ceiling,
    before 2023 and since. Recomputed from the two counts rather than read out
    of `share_over_cap`, which the query rounds to five places.

    `dup_month` flags 2015-08 and 2015-09, the duplication event this same
    ceiling test finds unaided; those two months are not part of "before",
    because they are the thing the test is being validated against.
    """
    rows = [typed(B6, r, B6_INT) for r in blocks(ch("60_coverage_index.sql"))[12]]
    clean = [r for r in rows if r["mon"] < "2023-01-01" and not r["dup_month"]]
    recent = [r for r in rows if r["mon"] >= "2023-12-01"]
    worst = max(rows, key=lambda r: r["max_msgs"])
    share = lambda rs: 100 * max(r["vd_over_cap"] / r["vessel_days"] for r in rs)
    return share(clean), share(recent), worst["max_msgs"] / CAP_A


# -------------------------------------------------------------- bug 3 ----
def hidden(ch):
    """sql/44 — the ferry fleet the archive filed as something else, in the
    last year the store holds whole, plus the worst single case: the longest
    run of hidden days any one Fano vessel has in a single year."""
    rows = [typed(H1, r, ("year", "fleet", "visible_days", "hidden_days",
                          "vessels_with_hidden"))
            for r in blocks(ch("44_hidden_fleet.sql"))[6]]
    ships = [typed(H3, r, ("year", "hidden_days"))
             for r in blocks(ch("44_hidden_fleet.sql"))[7]]
    fano = max((s for s in ships if s["island"] == "Fanø"),
               key=lambda s: s["hidden_days"])
    return next(r for r in rows if r["year"] == 2025), fano


# ------------------------------------------------ what it cannot say ----
def adoption(ch):
    """sql/61 block 1 — the private fleet and the instrument it is heard by,
    over the window all six years share, and block 4's flag split."""
    a1 = [typed(A1, r, A1_INT) for r in blocks(ch("61_adoption.sql"))[13]]
    win = {r["year"]: r for r in a1 if r["window"] == "mar_aug"}
    a4 = {int(r["year"]): r for r in
          (typed(A4, r) for r in blocks(ch("61_adoption.sql"))[10])}
    raw = win[2026]["class_b_leisure_vessels"] / win[2015]["class_b_leisure_vessels"]
    divided = (win[2026]["leisure_per_class_a_5d"]
               / win[2015]["leisure_per_class_a_5d"])
    return {"boats_2015": win[2015]["class_b_leisure_vessels"],
            "boats_2026": win[2026]["class_b_leisure_vessels"],
            "raw": raw, "divided": divided, "cost": 100 * (raw - divided) / raw,
            "german": 100 * a4[2026]["german_share"],
            "danish": 100 * a4[2026]["danish_share"]}


def emodnet(ch):
    """sql/62 blocks 3, 4 and 5 — the independent source.

    Block 3 res 7 gives the rank agreement and the share of EMODnet's leisure
    hours that falls where we hold nothing; block 5 splits that share by zone;
    block 4's worst-ranked cell of ours is the marina the other method cannot
    see. The cell id stays in the query output and out of the page.
    """
    out = ch("62_emodnet_compare.sql")
    s = next(typed(E3, r) for r in blocks(out)[13] if r[0] == "7")
    core = next(typed(E5, r) for r in blocks(out)[5] if r[0] == "Danish core")
    mine = [typed(E4, r, ("our_hours", "our_vessels", "rank_ours", "rank_emo"))
            for r in blocks(out)[10] if r[0] == "7" and r[1] == "ours"]
    marina = max(mine, key=lambda r: r["rank_emo"])
    return {"agreement": s["rank_both"], "missing": 100 * s["emo_in_our_zero"],
            "core_missing": 100 * core["missed_share"],
            "rank_ours": marina["rank_ours"], "rank_emo": marina["rank_emo"],
            "boats": marina["our_vessels"], "emo_hours": marina["emo_hours"]}


# ------------------------------------------------------------------ page ----
def build(ch):
    fl, pipe = floor_cost(ch), pipeline(ch)
    small, big = pleasure_with_a_big_radio(ch)
    before, now, times = impossible(ch)
    ferries, fano = hidden(ch)
    ad, emo = adoption(ch), emodnet(ch)

    charts = {
        # H1 is a DRAWING. These are the boats in the seven hexagons of the
        # illustration, two rows, four then three — not a measurement, and the
        # caption says so. They live here so that the ledger shows every number
        # that reaches the page, including the invented ones.
        "picture": {"floor": FLOOR, "rows": [[2, 9, 1, 4], [5, 12, 3]]},
        "floor": {"cells_pct": round(100 * fl["cells_share"], 1),
                  "moving_pct": round(100 * fl["moving_share"], 1)},
        "pipe": pipe,
    }
    charts["n"] = {
        # --- the >= 5 rule
        "floor_k": str(FLOOR),
        "pleasure_a_lo": sp(small),
        "pleasure_a_hi": sp(big),
        "cells_total": sp(fl["cells_total"]),
        "cells_kept": sp(fl["cells_kept"]),
        "floor_cells_pct": f"{100 * fl['cells_share']:.0f}",
        "floor_moving_pct": f"{100 * fl['moving_share']:.0f}",
        "floor_hidden_words": frac(1 - fl["cells_share"]),
        "floor_kept_words": frac(fl["moving_share"]),
        "hourly_cells_pct": f"{100 * fl['hourly_cells_share']:.0f}",
        "hourly_moving_pct": f"{100 * fl['hourly_moving_share']:.0f}",
        # --- the pipeline
        "archive_tb": str(ARCHIVE_TB),
        "pulled_tb": str(PULLED_TB),
        "files": sp(pipe["files"]),
        "rows_billion": f"{pipe['read_billion']:.0f}",
        "kept_billion": f"{pipe['kept_billion']:.0f}",
        "days": sp(pipe["days"]),
        "store_gb": str(pipe["store_gb"]),
        "rate_million": f"{pipe['rate_million']:.1f}",
        "load_hours": f"{pipe['load_hours']:.1f}",
        "reload_hours": str(RELOAD_HOURS),
        "link_share_words": frac(ONE_STREAM_MBS / LINK_MBS),
        "ahead": str(AHEAD),
        "prefetch_speedup": str(PREFETCH_SPEEDUP),
        "oom_million": str(OOM_MILLION),
        "spill_gb": str(SPILL_GB),
        # --- bug 1, the mirrored grid
        "cph_rows": sp(copenhagen(ch)),
        "cells": sp(pipe["cells"]),
        # --- bug 2, the messages stored twice
        "cap": sp(CAP_A),
        "cap_seconds": str(REPORT_SECONDS),
        "over_cap_before": f"{before:.2f}",
        "over_cap_now": f"{now:.1f}",
        "worst_times": f"{times:.1f}",
        # --- bug 3, the ferries filed as something else
        "hidden_share": f"{100 * ferries['hidden_share']:.0f}",
        "hidden_fleet": sp(ferries["fleet"]),
        "fano_ship": fano["name"],
        "fano_year": str(int(fano["year"])),
        "fano_days": sp(fano["hidden_days"]),
        # --- what this data cannot say
        "boats_2015": sp(ad["boats_2015"]),
        "boats_2026": sp(ad["boats_2026"]),
        "boats_growth": f"{ad['raw']:.1f}",
        "instrument_growth": f"{ad['divided']:.1f}",
        "instrument_cost": f"{ad['cost']:.1f}",
        "german_2026": f"{ad['german']:.0f}",
        "danish_2026": f"{ad['danish']:.0f}",
        "emodnet_agreement": f"{emo['agreement']:.2f}",
        "emodnet_missing": f"{emo['missing']:.0f}",
        "emodnet_core_missing": f"{emo['core_missing']:.0f}",
        "marina_rank_ours": sp(emo["rank_ours"]),
        "marina_rank_emo": sp(emo["rank_emo"]),
        "marina_boats": sp(emo["boats"]),
        "marina_emo_hours": f"{emo['emo_hours']:.1f}",
        # --- reproduce it
        "licence": "CC BY 4.0",
        "dataset_years": str(pipe["years"]),
    }
    return charts
