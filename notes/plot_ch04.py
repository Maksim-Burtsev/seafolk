#!/usr/bin/env python3
"""S9 chapter-04 charts: three PNGs into notes/img/, and the numbers behind them.

    uv run --project notes notes/plot_ch04.py

Same contract as notes/plot.py and plot_ch01/02/03.py, whose helpers this file
imports: every query runs through scripts/ch.sh against the
`clickhouse local --path data/ch` store, ONE AT A TIME (the store lock is
exclusive — two clickhouse processes on data/ch is an error, not a slowdown),
there is no client library, matplotlib is the one dependency, and every number
notes/ch04-findings.md quotes is printed by numbers() below.

Four query files, each read exactly once:
    sql/50_storm_window.sql   one row per (storm, hour, mobile, ship_group),
                              15 columns: heard, moving_msgs, the reference
                              hour a fortnight away, ratio_moving, and the
                              DANISH-end ferry departures of that hour (the
                              island, domestic and international lines)
    sql/51_anchorage_fill.sql three blocks: the rule's candidate cell-years
                              (9 cols), the labelling guard (1 col), and the
                              per-hour occupancy of each labelled anchorage
                              around each storm (8 cols)
    sql/52_who_stays.sql      block 1 (12 cols): vessels heard and vessels
                              that moved >= 1 nm per day; block 2 (11 cols):
                              every fleet on the storm's DERIVED peak hour,
                              with is_dip; block 3 (6 cols): the fleet that
                              ever runs a ferry crossing, by the ship type it
                              was filed under that day
    sql/53_storm_oracle.sql   the two recounts, 8 + 5 columns

THE FIFTEEN STORMS are every row of data/context/storms.csv whose window
touches a loaded day, with Dagmar and Egon merged into one event exactly as S8
treats them. ALFRIDA IS A RUN-UP, NOT A STORM: 2019 is unloaded, so only its
three pre-days survive and it has no storm hour, no peak hour and no storm-day
row anywhere. It is drawn and printed as what it is rather than dropped.

THE THREE INSTRUMENTS, and why there are three. `docs/PLAN.md` § S9 asked for
"hourly moving vessels by group"; that number does not exist. `h3_hourly`'s
`vessels` is a uniqExact state over every vessel PRESENT in the cell-hour, and
no state of the moving subset was ever stored (sql/11, 12, 24, 30 and 50 all
say so). So:
    hour, exact      `heard` — the head count of the fleet in the bbox
    hour, shape only `ratio_moving` — a fleet's moving MESSAGES against its own
                     messages a fortnight away. Never compare the level across
                     fleets: a Class A ship reports every few seconds, a Class B
                     one every 30 s at best, and the rate rises with speed.
    day, exact       `share_moved` — vessels with dist_nm >= 1 over vessels
                     heard, from `vessel_day` (sql/52)
Chart 1 is the second, chart 3 the third, and `heard` stands beside both.

PRIVACY. `vessel_day` carries MMSI and never leaves data/ch; sql/50-53 emit
counts only, and this file asserts that its own stdout holds no 9-digit integer
(guard (g) in main). No Class B vessel is named, positioned or tracked here.
Ferries and commercial vessels are public: the Ærø line is named in the oracle.
"""
import collections
import datetime
import io
import re
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot import GRID, GROUPS, IMG, INK, MUTED, ROOT, label_ends, rows, tidy

# Colour follows the entity across all four chapters: plot.GROUPS is the
# source. `other` has no slot there (chapters 01-03 never plot it) and gets
# ch03's contrast grey, because it is the catch-all — tugs, offshore support
# and, since S8, every high-speed craft in the archive.
COLOUR = {(mobile, grp): colour for grp, mobile, _, colour in GROUPS}
COLOUR[("Class A", "other")] = "#5b6b73"
LABEL = {("Class A", "cargo"): "cargo", ("Class A", "fishing"): "fishing",
         ("Class A", "passenger"): "ferries", ("Class A", "other"): "other",
         ("Class B", "leisure"): "leisure"}
# The order is the reading order of the chapter: the fleet that never stops
# first, the fleets that stop last.
PLOTTED = [("Class A", "cargo"), ("Class A", "passenger"), ("Class A", "other"),
           ("Class A", "fishing"), ("Class B", "leisure")]

# THE LEISURE FLOOR, AND IT IS ON THE DAY INSTRUMENT, NOT ON `heard`. Class B
# is a seasonal fleet and a winter transponder reports from the cradle: the
# winter storms of 2022-2025 have a MEDIAN HOUR of 234 to 328 leisure vessels
# heard in the bbox while sql/52 counts ten to twenty of them covering a mile
# in a WHOLE DAY (measured over the December-February days of these windows:
# quartiles
# 9.8 / 14 / 22 vessels that moved, max 61). A floor on `heard` therefore
# admits a ratio built on ten boats, and those lines dominated chart 1's
# winter panels.
# So the floor is read off sql/52's REFERENCE day instead: the number of Class
# B leisure vessels that covered >= 1 nm a fortnight away, median over the
# storm's own dates. MEASURED, per storm: 15.5, 17, 18, 26, 26.5, 27, 35,
# 43.5, 79, 107, 203 | 506, 2056, 2096. The literal sits in the widest gap of
# that list (203 Dave -> 506 Knud) and leaves solid exactly the three storms
# that fall in a sailing season. Below it chart 1 draws leisure dashed, grey
# and out of the legend; numbers() prints every value.
LEISURE_FLOOR = 250

# The Danish anchorages of chart 2, in the order the essay walks them: the two
# Skagerrak roadsteads where the North Sea traffic waits out a westerly, the
# two Øresund berths, and the one sheltered fjord. `Øresund anchorage off
# Helsingør` was here and is NOT: it holds one ship at a time and is empty a
# fortnight away, so only 6 of its 192 pooled hours have all four storms
# reporting on both sides and the panel was a blank square with a label. It is
# a berth, not an anchorage the fleet could pile into; chart 2's caption says
# so rather than showing six dots. Every name is a label from
# data/context/anchorages.csv; the numbers behind them are all from the store.
DANISH_ANCHORAGES = [
    "Skagen Red",
    "Ålbæk Bugt",
    "Copenhagen roads – Øresund",
    "Øresund anchorage off Landskrona",
    "Isefjord entrance anchorage",
]
# Chart 2 pools storms, so it can only pool storms of the same LENGTH — a
# two-day storm's hour +36 is inside the weather and a one-day storm's is a day
# after it. These are the four deepest two-day storms by sql/52's derived peak
# ratio (0.45 Sif, 0.52 Otto, 0.63 Malik, 0.65 Pia), so their windows share the
# same offsets -72 .. +119 and the same storm band 0 .. +47.
ANCHOR_STORMS = ["Sif", "Otto", "Malik", "Pia"]

W = ("storm start_day hour offset_h mobile ship_group heard moving_msgs msgs "
     "ref_hour ref_heard ref_moving_msgs ratio_moving ferry_crossings "
     "ref_ferry_crossings").split()
A1 = "h3 lat lon year vessels msgs still_share name note".split()
A3 = "storm name hour offset_h present still_share ref_hour ref_present".split()
D1 = ("storm mobile ship_group day offset_d heard moved share_moved ref_day "
      "ref_heard ref_moved ref_share_moved").split()
D2 = ("storm peak_hour peak_offset_h peak_ratio mobile ship_group heard "
      "moving_share ref_heard ref_moving_share is_dip").split()
D3 = "storm day day_kind ship_group vessels share".split()


def num(s, cast=int):
    """A ClickHouse TSV field: \\N is a real NULL and must not become 0."""
    return None if s == "\\N" else cast(s)


# ------------------------------------------------------------- sql/50 ----
def window():
    """sql/50 -> (rows, {storm: start_day}, {storm: storm-day count}).

    The storm-day count is read off the WINDOW rather than out of storms.csv:
    the window runs [start_day 00:00 - 72 h, end_day 24:00 + 72 h), so
    n = (max offset + 1 - 72) / 24. Every window in the store is contiguous
    from -72 to its end, which is asserted here — a hole would make that
    arithmetic a guess.
    """
    out = []
    for r in rows("50_storm_window.sql"):
        assert len(r) == 15, f"sql/50: {len(r)} columns, not 15: {r[:4]}"
        row = dict(zip(W, r))
        for k in ("offset_h", "heard", "moving_msgs", "msgs", "ferry_crossings"):
            # A NULL here would mean the INNER JOIN onto `agg` stopped being
            # inner, or join_use_nulls flipped to 1 — either way a count that
            # reads as "nothing was heard" when it means "the join lost it".
            assert re.fullmatch(r"-?\d+", row[k]), \
                f"sql/50 {row['storm']} {row['hour']}: {k} = {row[k]!r}"
            row[k] = int(row[k])
        for k in ("ref_heard", "ref_moving_msgs", "ref_ferry_crossings"):
            row[k] = num(row[k])
        row["ratio_moving"] = num(row["ratio_moving"], float)
        # THE RATIO ROUND-TRIP. sql/50 rounds moving_msgs / ref_moving_msgs to
        # four places; recomputing it here from the two counts on the same row
        # is the one check that the division is over the numbers it claims —
        # a reference joined on the wrong hour, or on another fleet, lands
        # here. And a NULL ratio must have a reason: no reference hour, or a
        # reference hour in which nothing of that fleet moved.
        if row["ratio_moving"] is not None:
            assert abs(row["ratio_moving"]
                       - row["moving_msgs"] / row["ref_moving_msgs"]) < 5e-4, \
                (f"sql/50 {row['storm']} {row['hour']} {row['ship_group']}: "
                 f"ratio_moving {row['ratio_moving']} is not "
                 f"{row['moving_msgs']}/{row['ref_moving_msgs']}")
        else:
            assert row["ref_hour"] == "\\N" or row["ref_moving_msgs"] == 0, \
                (f"sql/50 {row['storm']} {row['hour']} {row['ship_group']}: "
                 f"ratio_moving is NULL with ref_moving_msgs "
                 f"{row['ref_moving_msgs']}")
        # ferry_crossings is a property of the HOUR and is emitted on the
        # (Class A, passenger) row only, so that nobody sums it across five
        # groups and quintuples the Danish ferry timetable. If that ever
        # changes, this file's ferry figures are five times too large.
        if not (row["mobile"] == "Class A" and row["ship_group"] == "passenger"):
            assert row["ferry_crossings"] == 0 and row["ref_ferry_crossings"] is None, \
                (f"sql/50 {row['storm']} {row['hour']} {row['mobile']} "
                 f"{row['ship_group']} carries ferry crossings")
        out.append(row)

    offsets = collections.defaultdict(set)
    start = {}
    for row in out:
        offsets[row["storm"]].add(row["offset_h"])
        start[row["storm"]] = row["start_day"]
    ndays = {}
    for storm, off in offsets.items():
        lo, hi = min(off), max(off)
        assert lo == -72, f"{storm}: window starts at {lo}, not -72"
        assert len(off) == hi - lo + 1, \
            (f"{storm}: the window has holes ({len(off)} hours over "
             f"{hi - lo + 1} offsets) — the storm-day count cannot be read off it")
        ndays[storm] = max((hi + 1 - 72) // 24, 0)
    return out, start, ndays


def series(win, storm, mobile, group, key="ratio_moving"):
    """{offset hour: value} for one fleet in one storm's window."""
    return {r["offset_h"]: r[key] for r in win
            if r["storm"] == storm and r["mobile"] == mobile
            and r["ship_group"] == group}


def smooth(s, lo, hi, k=5):
    """Centred k-hour mean over a dense offset range; None where incomplete.

    The hourly ratio of one fleet's messages against the same hour a fortnight
    away is a noisy quantity — a fortnight is a different day of weather, and
    the denominator is one hour of one afternoon. At k = 3 the leisure line of
    a winter storm is a picket fence of a few dozen boats; k = 5, the default
    and what every chart and every table in this file uses, is the smallest
    window that leaves fifteen panels readable. It is applied to every series
    and to no quoted number: numbers() prints the raw hourly minima and the
    pooled ratios.
    """
    xs, ys = [], []
    half = k // 2
    for o in range(lo, hi + 1):
        vals = [s.get(o + d) for d in range(-half, half + 1)]
        vals = [v for v in vals if v is not None]
        if len(vals) == k:
            xs.append(o)
            ys.append(sum(vals) / k)
    return xs, ys


def storm_mean(win, storm, mobile, group, ndays):
    """Σ moving_msgs ÷ Σ reference moving_msgs over the storm's OWN days.

    A pooled ratio, not a mean of ratios: an hour with four messages must not
    weigh as much as an hour with forty thousand.
    """
    rs = [r for r in win if r["storm"] == storm and r["mobile"] == mobile
          and r["ship_group"] == group and 0 <= r["offset_h"] < 24 * ndays[storm]
          and r["ratio_moving"] is not None]
    if not rs:
        return None
    ref = sum(r["ref_moving_msgs"] for r in rs)
    deep = min(rs, key=lambda r: r["ratio_moving"])
    return dict(
        mean=sum(r["moving_msgs"] for r in rs) / ref if ref else None,
        low=deep["ratio_moving"], low_at=deep["offset_h"],
        ref_heard=statistics.median(r["ref_heard"] for r in rs),
        heard=statistics.median(r["heard"] for r in rs))


def stops_at(win, storm, mobile, group, ndays):
    """The hour a fleet STOPS, relative to the storm's first calendar day.

    Defined as the first offset at which the 5-hour mean ratio falls below HALF
    the fleet's own pre-window median (offsets -72 .. -25), searched from -24 to
    the end of the storm's own days. The normalisation is the point: a fleet
    whose ratio sits at 0.4 all week — leisure in a mild February — has not
    stopped, and an absolute threshold would say it had three days early.
    None means the fleet never halved. Ties to no single hour: it is a crossing
    time, deliberately coarse, and the note quotes it as such.
    """
    s = series(win, storm, mobile, group)
    base = [v for o, v in s.items() if -72 <= o <= -25 and v is not None]
    if not base:
        return None, None
    base = statistics.median(base)
    if base <= 0:
        return None, base
    xs, ys = smooth(s, -24, 24 * ndays[storm] - 1)
    for x, y in zip(xs, ys):
        if y < 0.5 * base:
            return x, base
    return None, base


def ferry_hours(win, storm, ndays):
    """Ferry departures per hour in the window: (storm hours, reference, pre).

    The column rides on the (Class A, passenger) row and counts departures on
    the lines with at least one DANISH end — island, domestic and
    international. sql/50's header carries what that excludes and how much of
    it: 36.5 % foreign (Goteborg, the Kiel canal, Ruegen, the Baltic
    long-haul), 0.66 % intra-harbour and 7.48 % unmatched. It is the Danish
    ferry timetable, not a line's and not the bbox's.
    """
    rs = [r for r in win if r["storm"] == storm and r["mobile"] == "Class A"
          and r["ship_group"] == "passenger"]
    sto = [r for r in rs if 0 <= r["offset_h"] < 24 * ndays[storm]]
    pre = [r for r in rs if r["offset_h"] < 0]
    return (sum(r["ferry_crossings"] for r in sto),
            sum(r["ref_ferry_crossings"] or 0 for r in sto),
            sum(r["ferry_crossings"] for r in pre))


# ------------------------------------------------------------- sql/51 ----
def anchorage():
    """sql/51 -> (candidate cell-years, the per-hour storm profile).

    Three blocks on one stdout, separated by width: 9 columns per candidate
    cell-year, 1 for the labelling guard, 8 per (storm, anchorage, hour).
    """
    cells, guard, prof = [], None, []
    for r in rows("51_anchorage_fill.sql"):
        if len(r) == 1:
            # sql/51 block 2 is `throwIf(...) + ... = 0 AS
            # anchorages_csv_is_sound`: each throwIf returns 0 when it does not
            # throw, so the sum is 0 and the column is 1. A 0 here means the
            # guard has been rewritten into something that REPORTS instead of
            # failing, and an unlabelled anchorage would ride along unnoticed
            # into chart 2.
            guard = int(r[0])
            continue
        if len(r) == 9:
            row = dict(zip(A1, r))
            for k in ("year", "vessels", "msgs"):
                row[k] = int(row[k])
            for k in ("lat", "lon", "still_share"):
                row[k] = float(row[k])
            cells.append(row)
            continue
        assert len(r) == 8, f"sql/51: {len(r)} columns, not 9 / 1 / 8"
        row = dict(zip(A3, r))
        for k in ("offset_h", "present"):
            row[k] = int(row[k])
        row["ref_present"] = num(row["ref_present"])
        row["still_share"] = num(row["still_share"], float)
        prof.append(row)
    assert guard == 1, \
        (f"sql/51's labelling guard returned {guard}, not 1 — the column is "
         "`sum of throwIf = 0`, so 1 is the only value that means "
         "'nothing to report'")
    assert cells and prof, "sql/51 lost one of its three blocks"
    return cells, prof


def anchor_profile(prof, storm, name):
    """{offset: (present, ref_present)} for one anchorage in one storm."""
    return {r["offset_h"]: (r["present"], r["ref_present"])
            for r in prof if r["storm"] == storm and r["name"] == name}


def anchor_pool(prof, name, lo, hi):
    """Chart 2's series: the mean of ANCHOR_STORMS, hour by hour.

    Returns (offsets, storm mean, reference mean, hours pooled). An offset is
    emitted only where every pooled storm has both numbers, so the two curves
    are always drawn over the same population.
    """
    xs, sto, ref = [], [], []
    for o in range(lo, hi + 1):
        pairs = [anchor_profile(prof, s, name).get(o) for s in ANCHOR_STORMS]
        if any(p is None or p[1] is None for p in pairs):
            continue
        xs.append(o)
        sto.append(statistics.mean(p[0] for p in pairs))
        ref.append(statistics.mean(p[1] for p in pairs))
    return xs, sto, ref


def labelled_names(cells):
    """The anchorage names sql/51 block 3 is allowed to profile.

    `note == ''` alone is not the test: a rule cell-year under 100 vessels may
    go unlabelled, and 266 of the 758 do — they arrive with name '' and note ''
    from the LEFT JOIN, and counting them made this file say 38 anchorages
    where the CSV has 37.
    """
    return {c["name"] for c in cells if c["note"] == "" and c["name"]}


def anchor_cells(prof, ndays):
    """Per (storm, Danish anchorage): mean vessels present before / during /
    after the storm's own dates, and at the reference hours, with the two
    ratios. Chart 2's table and the medians finding 48 and 49 quote.

    A cell is emitted only where all three of pre, storm and reference have
    hours; the ratios are None where a side is empty, which is a real state —
    an anchorage can hold ships during a storm and none a fortnight away.
    """
    out = []
    for storm in ndays:
        if not ndays[storm]:
            continue
        n = ndays[storm]
        for name in DANISH_ANCHORAGES:
            p = anchor_profile(prof, storm, name)
            if not p:
                continue
            f = lambda sel: [v[0] for o, v in p.items() if sel(o)]
            pre, sto, post = (f(lambda o: o < 0), f(lambda o: 0 <= o < 24 * n),
                              f(lambda o: o >= 24 * n))
            ref = [v[1] for o, v in p.items()
                   if 0 <= o < 24 * n and v[1] is not None]
            if not (pre and sto and ref):
                continue
            m = statistics.mean
            out.append(dict(
                storm=storm, name=name, pre=m(pre), sto=m(sto), ref=m(ref),
                post=m(post) if post else None,
                r_ref=m(sto) / m(ref) if m(ref) else None,
                r_pre=m(sto) / m(pre) if m(pre) else None))
    return out


# ------------------------------------------------------------- sql/52 ----
def who_stays():
    """sql/52 -> (the day panel, the peak-hour rows, the ferry-fleet rows).

    Three blocks on one stdout, separated by width, the way anchorage() splits
    sql/51: 12 columns per (storm, fleet, day), 11 per fleet on the derived
    peak hour, and 6 per (storm, day, day_kind, ship_group) of the fleet that
    has ever run a ferry crossing.
    """
    day, peak, fleet = [], [], []
    for r in rows("52_who_stays.sql"):
        if len(r) == 12:
            row = dict(zip(D1, r))
            for k in ("offset_d", "heard", "moved"):
                row[k] = int(row[k])
            for k in ("ref_heard", "ref_moved"):
                row[k] = num(row[k])
            for k in ("share_moved", "ref_share_moved"):
                row[k] = num(row[k], float)
            # The round-trip, not `moved <= heard`: the latter holds by
            # construction (one uniqExactIf over the other's MMSI set) and
            # cannot fail. This one catches a share computed over a different
            # day's head count.
            assert abs(row["share_moved"] - row["moved"] / row["heard"]) < 5e-4, \
                (f"sql/52 {row['storm']} {row['day']} {row['ship_group']}: "
                 f"share_moved {row['share_moved']} is not "
                 f"{row['moved']}/{row['heard']}")
            day.append(row)
            continue
        if len(r) == 11:
            row = dict(zip(D2, r))
            for k in ("peak_offset_h", "heard", "ref_heard", "is_dip"):
                row[k] = int(row[k])
            for k in ("peak_ratio", "moving_share", "ref_moving_share"):
                row[k] = num(row[k], float)
            peak.append(row)
            continue
        assert len(r) == 6, f"sql/52: {len(r)} columns, not 12 / 11 / 6"
        row = dict(zip(D3, r))
        row["vessels"] = int(row["vessels"])
        row["share"] = float(row["share"])
        fleet.append(row)
    assert day and peak and fleet, "sql/52 lost one of its three blocks"
    return day, peak, fleet


def leisure_ref_moved(panel, storm, ndays):
    """Chart 1's leisure floor: the median number of Class B leisure vessels
    that covered a mile on the REFERENCE day, over the storm's own dates.

    None for a storm with no observed date (Alfrida). See LEISURE_FLOOR for
    why the floor is on this number and not on `heard`.
    """
    rs = [r["ref_moved"] for r in panel
          if r["storm"] == storm and r["mobile"] == "Class B"
          and r["ship_group"] == "leisure" and 0 <= r["offset_d"] < ndays[storm]
          and r["ref_moved"] is not None]
    return statistics.median(rs) if rs else None


def ferry_fleet_days(fleet):
    """sql/52 block 3 -> {(storm, day, day_kind): (vessels, outside passenger)}.

    The population is fixed — every Class A MMSI that has ever run a crossing —
    and the LABEL is not: a ferry that broadcast something else that day is
    filed somewhere else that day. What comes out is the size of the hole in
    the `passenger` group, and of the bulge in `other`, on each side of the
    comparison.
    """
    agg = collections.defaultdict(lambda: [0, 0])
    for r in fleet:
        k = (r["storm"], r["day"], r["day_kind"])
        agg[k][0] += r["vessels"]
        if r["ship_group"] != "passenger":
            agg[k][1] += r["vessels"]
    return {k: tuple(v) for k, v in agg.items()}


def moved_pool(panel, storm, mobile, group, ndays):
    """Vessels heard / vessels that moved, pooled over the storm's own days."""
    rs = [r for r in panel if r["storm"] == storm and r["mobile"] == mobile
          and r["ship_group"] == group and 0 <= r["offset_d"] < ndays[storm]]
    if not rs or any(r["ref_heard"] is None for r in rs):
        return None
    heard = sum(r["heard"] for r in rs)
    ref_heard = sum(r["ref_heard"] for r in rs)
    if not heard or not ref_heard:
        return None
    return dict(heard=heard, moved=sum(r["moved"] for r in rs),
                share=sum(r["moved"] for r in rs) / heard,
                ref_heard=ref_heard,
                ref_share=sum(r["ref_moved"] for r in rs) / ref_heard)


# ------------------------------------------------------------- sql/53 ----
def oracle():
    """sql/53 -> (Pia's fishing week, the Ærø week), both blocks parsed."""
    fish, aero = [], []
    for r in rows("53_storm_oracle.sql"):
        if len(r) == 8:
            fish.append(dict(day=r[0], heard=int(r[1]), moved_msgs=int(r[2]),
                             moved_dist=int(r[3]), moved_gap=int(r[4]),
                             vd_moving_msgs=int(r[5]),
                             h3_moving_msgs=int(r[6]), msgs_gap=int(r[7])))
            continue
        assert len(r) == 5, f"sql/53: {len(r)} columns, not 8 / 5"
        aero.append(dict(day=r[0], oracle=int(r[1]), table=int(r[2]),
                         gap=int(r[3]), vessels=int(r[4])))
    assert len(fish) == 8 and len(aero) == 8, \
        f"sql/53 returned {len(fish)} + {len(aero)} days, not 8 + 8"
    return fish, aero


# ------------------------------------------------------------- charts ----
def chart_window(win, start, ndays, peak, panel):
    """Chart 1 — one panel per storm, every fleet's moving messages against the
    same hour a fortnight away.

    Fifteen panels and five series: direct labels would be seventy-five pieces
    of text, so this is the one chart in the chapter with a legend, and the
    series are ordered in it the way they order themselves on the page. The
    grey band is the storm's own calendar dates; the triangle on the axis is
    the DERIVED peak hour from sql/52 block 2 (DMI publishes dates, not hours),
    drawn HOLLOW where is_dip = 0 — the peak hour is an argMin and always
    exists, and for Floriane it is the least bad hour of a storm with no dip.
    A dashed grey leisure line means the storm's reference days had fewer than
    LEISURE_FLOOR leisure vessels covering a mile: the ratio above it is ten
    boats' afternoon, and it stays out of the legend so the eye reads the four
    fleets that are fleets.
    """
    peak_at = {r["storm"]: r for r in peak}
    order = sorted(ndays, key=lambda s: start[s])
    cols, rowsn = 4, 4
    fig, axes = plt.subplots(rowsn, cols, figsize=(13, 8.6), sharey=True)
    flat = axes.flatten()
    thin, solid, seen = [], [], set()
    for ax, storm in zip(flat, order):
        n = ndays[storm]
        hi = max(r["offset_h"] for r in win if r["storm"] == storm)
        if n:
            ax.axvspan(0, 24 * n, color=GRID, alpha=0.55, linewidth=0)
        ax.axhline(1.0, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
        for mobile, group in PLOTTED:
            xs, ys = smooth(series(win, storm, mobile, group), -72, hi)
            if not xs:
                continue
            colour, style, width, alpha = COLOUR[(mobile, group)], "-", 1.6, 1.0
            if group == "leisure":
                moved = leisure_ref_moved(panel, storm, ndays)
                if moved is None or moved < LEISURE_FLOOR:
                    colour, style, width, alpha = MUTED, (0, (3, 2)), 0.9, 0.32
                    thin.append((storm, moved or 0))
                else:
                    solid.append(storm)
            # The legend label is attached to the first panel that draws the
            # series as DATA. Taking them all off panel 1 put "leisure" in the
            # legend in its own colour while every winter panel drew it grey.
            lab = None
            if (mobile, group) not in seen and colour != MUTED:
                lab = LABEL[(mobile, group)]
                seen.add((mobile, group))
            # No clamping: a series that leaves the top of the panel is drawn
            # leaving it. Clipping the VALUE to the axis maximum would draw a
            # flat plateau at 1.6, which reads as a fleet holding steady when
            # it is a fleet at three times its fortnight-away level.
            ax.plot(xs, ys, color=colour, linestyle=style, linewidth=width,
                    alpha=alpha, label=lab)
        if storm in peak_at:
            # In axes fraction on y, so the marker sits on the floor of the
            # panel whatever the (log) y-limits are. Hollow = sql/52's
            # is_dip = 0, i.e. the "peak" hour is above the fortnight-away
            # level and this storm has no dip on its own date at all.
            ax.plot([peak_at[storm]["peak_offset_h"]], [0.02], marker="^",
                    markersize=5, color=INK,
                    markerfacecolor=INK if peak_at[storm]["is_dip"] else "white",
                    transform=ax.get_xaxis_transform(), clip_on=False)
        ax.set_xticks(range(-72, hi + 1, 24))
        ax.set_xlim(-72, hi)
        # A LOG AXIS, because this is a ratio. On a linear scale "half as much
        # movement" and "twice as much" are 0.5 and 2.0 — one of them a
        # centimetre from the reference line and the other off the top of the
        # panel — and the leisure line of a winter storm, whose denominator is
        # a few dozen boats, spends its life off the top. On a log scale the
        # two are the same distance from 1.0 in opposite directions, which is
        # what the eye should be comparing. Nothing is clamped: a series beyond
        # 20x or under 1/20 leaves the panel rather than drawing a false
        # plateau at the limit.
        ax.set_yscale("log")
        ax.set_ylim(0.05, 4)
        ax.set_yticks([0.1, 0.25, 0.5, 1, 2, 4])
        ax.set_yticklabels(["0.1", "0.25", "0.5", "1", "2", "4"])
        ax.minorticks_off()
        ax.set_title(f"{storm}  ·  {start[storm]}"
                     + ("  (run-up only)" if not n else ""),
                     color=INK, fontsize=9, loc="left")
        tidy(ax)
    for ax in flat[len(order):]:
        ax.set_visible(False)
    for col in range(cols):
        column = [axes[r][col] for r in range(rowsn) if axes[r][col].get_visible()]
        column[-1].set_xlabel("hours from the storm's first date, UTC",
                              color=MUTED, fontsize=8)
    fig.supylabel("moving messages ÷ the same hour a fortnight away",
                  color=MUTED, fontsize=9)
    handles, labels = [], []
    for ax in flat:
        h, l = ax.get_legend_handles_labels()
        handles += h
        labels += l
    fig.legend(handles, labels, frameon=False, fontsize=9,
               labelcolor=MUTED, ncol=5, loc="upper right",
               bbox_to_anchor=(0.995, 0.995))
    fig.suptitle("Who stops when the storm comes\n"
                 "5-hour mean on a LOG axis — a line that leaves the panel is "
                 "past 4× or under 1/20 · shaded = the storm's calendar dates\n"
                 "▲ = the derived peak hour, hollow where the storm has no dip "
                 f"· dashed grey = under {LEISURE_FLOOR} leisure boats moved a "
                 "mile on the reference day",
                 color=INK, fontsize=11, x=0.006, ha="left", va="top")
    fig.tight_layout(rect=(0.012, 0, 1, 0.955))
    fig.savefig(IMG / "ch04-window.png", dpi=160, facecolor="white")
    return sorted(set(thin)), sorted(set(solid))


def chart_anchorage(prof):
    """Chart 2 — do the ships that stop go and sit somewhere?

    One panel per Danish anchorage; the two curves are the mean of the four
    deepest two-day storms, hour by hour: how many Class A cargo and `other`
    vessels are present, against the same hours a fortnight away. The chart's
    job is to make a NEGATIVE result legible, so both curves are drawn over the
    identical set of hours and the storm band is marked exactly as in chart 1.
    Read the vertical gap, not the wiggle: where the dark curve sits above the
    grey one it does so for the whole 8 days, storm hours and all.
    """
    lo, hi = -72, 119
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.6))
    flat = axes.flatten()
    for ax in flat[len(DANISH_ANCHORAGES):]:
        ax.set_visible(False)
    for ax, name in zip(flat, DANISH_ANCHORAGES):
        xs, sto, ref = anchor_pool(prof, name, lo, hi)
        ax.axvspan(0, 48, color=GRID, alpha=0.55, linewidth=0)
        ax.plot(xs, ref, color=MUTED, linewidth=1.2, linestyle=(0, (3, 2)))
        ax.plot(xs, sto, color="#7d2c10", linewidth=1.8)
        ax.set_xticks(range(lo, hi + 1, 48))
        ax.set_xlim(lo, hi)
        top = max(max(sto), max(ref)) if xs else 1
        ax.set_ylim(0, top * 1.45)
        # An anchorage with no hour where all four storms report on both sides
        # draws an empty panel, and the end labels have nothing to hang off.
        # That is not hypothetical: it is what the Helsingør berth did before
        # it was dropped from DANISH_ANCHORAGES, and `sto[-1]` on an empty list
        # took the whole chapter down with an IndexError.
        if xs:
            label_ends(ax, xs[-1],
                       [(sto[-1], "storm", "#7d2c10"),
                        (ref[-1], "fortnight away", MUTED)], gap_frac=0.12)
        band = [(s, r) for x, s, r in zip(xs, sto, ref) if 0 <= x < 48]
        # An hour is drawn only where all four storms report the anchorage on
        # BOTH sides, so a thin anchorage yields a thin panel. The pooled-hour
        # count is in the title rather than left for the reader to guess at.
        note = f"\n{len(xs)} of {hi - lo + 1} hours pooled" if len(xs) < hi - lo + 1 else ""
        if band:
            bs = statistics.mean(s for s, _ in band)
            br = statistics.mean(r for _, r in band)
            note = f"\nstorm hours {bs:.1f} vs {br:.1f} a fortnight away" + note
        ax.set_title(f"{name}{note}", color=INK, fontsize=8.5, loc="left")
        ax.set_xlabel("hours from the storm's first date", color=MUTED, fontsize=8)
        tidy(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel("Class A cargo + other present", color=MUTED, fontsize=8.5)
    fig.suptitle("Nobody piles into the anchorages: vessels present per hour, "
                 "mean of Sif, Otto, Malik and Pia, against the same hours a "
                 "fortnight away · shaded = the storm's two dates\n"
                 "The sixth labelled Danish anchorage, the Øresund berth off "
                 "Helsingør, is absent: it holds one ship at a time and is "
                 "empty a fortnight away, so only 6 of its 192 hours pool",
                 color=INK, fontsize=11, x=0.006, ha="left")
    fig.tight_layout(rect=(0, 0, 0.97, 0.93))
    fig.savefig(IMG / "ch04-anchorage.png", dpi=160, facecolor="white")


def chart_who_stays(panel, peak, ndays):
    """Chart 3 — the exact count: who was out, storm against reference.

    Two scatter panels sharing one 45° line, one mark per (storm, fleet). Left,
    the DAY grain and the exact instrument: vessels that covered at least a
    nautical mile ÷ vessels heard, storm dates against the fortnight-away
    dates. Right, the derived peak HOUR and a message share, which is a
    different and weaker quantity — the two panels are separate because they
    must never be read as one series.
    A scatter, not fifteen small multiples: the claim of this chapter is an
    ORDER between fleets that holds across storms, and a diagonal turns that
    into one glance — cargo on the line, fishing and leisure under it. Every
    mark is labelled with its storm only where it would otherwise be anonymous
    (the six deepest); the clusters are labelled by fleet.
    HOLLOW MARKS in the right-hand panel are sql/52's is_dip = 0: Floriane's
    "peak" hour is the least bad hour of a storm that has no dip at all on its
    own date, so its five marks are not a storm hour in the sense the other
    thirteen storms' are.
    """
    nodip = {r["storm"] for r in peak if not r["is_dip"]}
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.6))
    points = collections.defaultdict(list)
    for storm in ndays:
        for mobile, group in PLOTTED:
            p = moved_pool(panel, storm, mobile, group, ndays)
            if p:
                points[(mobile, group)].append((storm, p["ref_share"], p["share"]))
    for ax, (data, xlab, ylab, title) in zip(axes, [
            (points, "share that moved ≥ 1 nm, a fortnight away",
             "share that moved ≥ 1 nm, the storm's dates",
             "Vessels, whole days — exact"),
            (None, "moving messages ÷ all messages, a fortnight away",
             "moving messages ÷ all messages, the peak hour",
             "Messages, the derived peak hour — shape only")]):
        hollow = set()
        if data is None:
            # The right-hand panel only: the left one is a DAY number and has
            # no peak hour to be a dip or not.
            hollow = nodip
            data = collections.defaultdict(list)
            for r in peak:
                key = (r["mobile"], r["ship_group"])
                if key in COLOUR and r["ref_moving_share"] is not None:
                    data[key].append((r["storm"], r["ref_moving_share"],
                                      r["moving_share"]))
        ax.plot([0, 1], [0, 1], color=MUTED, linewidth=0.9, linestyle=(0, (4, 3)))
        for key, pts in data.items():
            colour = COLOUR[key]
            full = [q for q in pts if q[0] not in hollow]
            open_ = [q for q in pts if q[0] in hollow]
            ax.scatter([x for _, x, _ in full], [y for _, _, y in full],
                       s=26, color=colour, linewidth=0, alpha=0.85, zorder=3)
            ax.scatter([x for _, x, _ in open_], [y for _, _, y in open_],
                       s=30, facecolors="none", edgecolors=colour,
                       linewidth=1.1, alpha=0.9, zorder=3)
            # The cluster label hangs off the RIGHTMOST mark of its fleet, not
            # off the centroid: fishing and leisure share a centroid in the
            # right-hand panel and two bold words landed on top of each other.
            rx, ry = max(((x, y) for _, x, y in pts))
            ax.annotate(LABEL[key], (rx, ry), xytext=(9, 0),
                        textcoords="offset points", color=colour, fontsize=9,
                        fontweight="bold", va="center", annotation_clip=False)
            # One storm named per fleet: the mark furthest below the diagonal,
            # i.e. the storm that cost that fleet the most. Naming six storms
            # in five colours was 30 pieces of text on top of the marks.
            storm, x, y = min(pts, key=lambda t: t[2] - t[1])
            ax.annotate(storm, (x, y), xytext=(3, -9), textcoords="offset points",
                        color=colour, fontsize=7)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.set_xlabel(xlab, color=MUTED, fontsize=8.5)
        ax.set_ylabel(ylab, color=MUTED, fontsize=8.5)
        ax.set_title(title, color=INK, fontsize=10, loc="left")
        tidy(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.suptitle("On the diagonal = the storm changed nothing · below it = the "
                 "fleet stayed in · one mark per storm and fleet\n"
                 "hollow, right-hand panel only = the storm has no dip on its "
                 "own date (sql/52's is_dip = 0): Floriane",
                 color=INK, fontsize=11, x=0.006, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(IMG / "ch04-who-stays.png", dpi=160, facecolor="white")


# ------------------------------------------------------------ numbers ----
def numbers(win, start, ndays, cells, prof, panel, peak, fleet, fish, aero,
            thin, solid):
    """Every figure notes/ch04-findings.md quotes. Printed, never hand-typed."""
    order = sorted(ndays, key=lambda s: start[s])
    peak_at = {r["storm"]: r for r in peak}

    print("\n== the fifteen storms, as sql/50 emits them ==")
    print(f"{'storm':14s} {'first date':11s} {'dates':>5} {'window':>12} "
          f"{'reference':>10} {'peak hour':>17} {'pooled ratio':>12} {'dip?':>5}")
    for storm in order:
        w = [r for r in win if r["storm"] == storm]
        hi = max(r["offset_h"] for r in w)
        deltas = sorted({(datetime.date.fromisoformat(r["ref_hour"][:10])
                          - datetime.date.fromisoformat(r["hour"][:10])).days
                         for r in w if r["ref_hour"] != "\\N"})
        pk = peak_at.get(storm)
        print(f"{storm:14s} {start[storm]:11s} {ndays[storm]:5d} "
              f"{'-72..%+d' % hi:>12} "
              f"{'/'.join('%+d d' % d for d in deltas):>10} "
              f"{(pk['peak_hour'] if pk else '— none —'):>17} "
              f"{(('%.4f' % pk['peak_ratio']) if pk else '-'):>12} "
              f"{('yes' if pk['is_dip'] else 'NO') if pk else '-':>5}")
    print("Alfrida has no storm hour in the store: 2019 is unloaded and only "
          "its three run-up days (2018-12-29/30/31) survive. It is charted and "
          "printed as a run-up.")
    print("The peak hour is DERIVED (sql/52 block 2): the hour of the storm's "
          "own dates at which the POOLED Class A moving-message ratio is "
          "lowest. DMI publishes dates, not hours.")

    print("\n== chart 1's numbers: each fleet over the storm's own dates ==")
    print("mean = Σ moving messages ÷ Σ the same fleet's messages a fortnight "
          "away; low = the deepest single hour; heard = median distinct "
          "vessels of that fleet in the bbox in a storm hour")
    print(f"{'storm':14s} {'fleet':16s} {'heard':>6} {'ref heard':>9} "
          f"{'mean':>6} {'low':>6} {'at h':>5}")
    for storm in order:
        for mobile, group in PLOTTED:
            st = storm_mean(win, storm, mobile, group, ndays)
            if not st:
                continue
            print(f"{storm:14s} {LABEL[(mobile, group)]:16s} {st['heard']:6.0f} "
                  f"{st['ref_heard']:9.0f} {st['mean']:6.3f} {st['low']:6.3f} "
                  f"{st['low_at']:+5d}")
        print()
    print("\n== the leisure floor: Class B vessels that covered a mile on the "
          "REFERENCE day ==")
    print("median over the storm's own dates (sql/52 block 1, ref_moved). The "
          f"floor is {LEISURE_FLOOR}: above it chart 1 draws leisure as data, "
          "below it dashed grey and out of the legend.")
    for storm in sorted(ndays, key=lambda s: leisure_ref_moved(panel, s, ndays)
                        if ndays[s] else -1):
        if not ndays[storm]:
            continue
        m = leisure_ref_moved(panel, storm, ndays)
        print(f"  {storm:14s} {m:8.1f}  {'DATA' if m >= LEISURE_FLOOR else 'noise'}")
    print(f"drawn as data: {', '.join(solid)}; dashed grey: "
          + ", ".join(s for s, _ in thin))
    winter = sorted(r["moved"] for r in panel
                    if r["mobile"] == "Class B" and r["ship_group"] == "leisure"
                    and r["day"][5:7] in ("12", "01", "02"))
    q = statistics.quantiles(winter, n=4, method="inclusive")
    print(f"and what the winter fleet actually does: over the {len(winter)} "
          "December-February days of these windows, the number of leisure "
          f"vessels that covered a mile runs min {winter[0]}, p25 {q[0]:.1f}, "
          f"median {q[1]:.0f}, p75 {q[2]:.0f}, max {winter[-1]} — while "
          "hundreds of transponders are heard.")

    print("\n== Pia's daily moving-message totals, Class A (sql/50, summed "
          "over the hours of each date) ==")
    print("2023-12-20 is the ordinary Wednesday before the storm; 2023-12-22 "
          "is Pia's second date.")
    pia = collections.Counter()
    for r in win:
        if r["storm"] == "Pia" and r["mobile"] == "Class A":
            pia[(r["ship_group"], r["hour"][:10])] += r["moving_msgs"]
    for group in ("cargo", "fishing", "passenger", "other"):
        quiet = pia[(group, "2023-12-20")]
        storm_day = pia[(group, "2023-12-22")]
        print(f"  {group:10s} {storm_day:10d} on 12-22 against {quiet:10d} on "
              f"12-20 = {storm_day / quiet:.3f} ({100 * storm_day / quiet:.1f} %)")
    print("\n== who stops FIRST: the hour the 5-h ratio halves against the "
          "fleet's own pre-window median ==")
    print("'-' = the fleet never halved. Relative to the storm's first date at "
          "00:00 UTC; the pooled peak is printed for scale.")
    print(f"{'storm':14s} {'peak':>5} " + " ".join(f"{LABEL[k]:>10}" for k in PLOTTED))
    crossed = collections.Counter()
    when = collections.defaultdict(list)
    for storm in order:
        if not ndays[storm]:
            continue
        line = f"{storm:14s} {peak_at[storm]['peak_offset_h']:+5d} "
        for key in PLOTTED:
            at, _ = stops_at(win, storm, *key, ndays)
            line += f"{('%+d' % at) if at is not None else '-':>10} "
            if at is not None:
                crossed[key] += 1
                when[key].append(at)
        print(line)
    print("fleets that halved, of the 14 storms with observed storm hours, and "
          "the median hour when they did:")
    for key in PLOTTED:
        med = f"{statistics.median(when[key]):+.0f} h" if when[key] else "-"
        print(f"  {LABEL[key]:10s} {crossed[key]:2d} / 14   median {med}")

    print("\n== chart 3's numbers: vessels that moved ≥ 1 nm (sql/52 block 1) ==")
    print("pooled over the storm's own dates against the same number of days a "
          "fortnight away. EXACT vessel counts, not messages.")
    print(f"{'storm':14s} {'fleet':10s} {'heard':>6} {'moved':>6} {'share':>6} "
          f"{'ref':>6} {'delta':>7}")
    deltas = collections.defaultdict(list)
    for storm in order:
        for key in PLOTTED:
            p = moved_pool(panel, storm, *key, ndays)
            if not p:
                continue
            deltas[key].append((p["share"] - p["ref_share"], storm))
            print(f"{storm:14s} {LABEL[key]:10s} {p['heard']:6d} {p['moved']:6d} "
                  f"{p['share']:6.3f} {p['ref_share']:6.3f} "
                  f"{p['share'] - p['ref_share']:+7.3f}")
        print()
    print("by fleet, across the 14 storms with storm dates:")
    for key in PLOTTED:
        d = sorted(deltas[key])
        print(f"  {LABEL[key]:10s} worst {d[0][0]:+.3f} ({d[0][1]}), median "
              f"{statistics.median(x for x, _ in d):+.3f}, best {d[-1][0]:+.3f} "
              f"({d[-1][1]})")

    print("\n== the Alfrida run-up (sql/50 and sql/52), the three loaded days ==")
    print("2019 is unloaded, so 2018-12-29/30/31 are all there is: the days "
          "BEFORE the storm, against 2018-12-15/16/17. New Year's Eve is in "
          "them and the reference days are ordinary ones — read this as a "
          "holiday week with weather in it, not as a storm profile.")
    print("pooled moving-message ratio over the three run-up days:")
    for key in PLOTTED:
        rs = [r for r in win if r["storm"] == "Alfrida" and r["mobile"] == key[0]
              and r["ship_group"] == key[1] and r["ratio_moving"] is not None]
        ref = sum(r["ref_moving_msgs"] for r in rs)
        print(f"  {LABEL[key]:10s} {sum(r['moving_msgs'] for r in rs) / ref:.3f}")
    print("and the exact vessel counts, day by day:")
    for r in sorted((r for r in panel if r["storm"] == "Alfrida"),
                    key=lambda r: (r["ship_group"], r["day"])):
        key = (r["mobile"], r["ship_group"])
        if key not in LABEL:
            continue
        print(f"  {LABEL[key]:10s} {r['day']}  heard {r['heard']:4d}  moved "
              f"{r['moved']:4d}  share {r['share_moved']:.3f}  against "
              f"{r['ref_day']} {r['ref_share_moved']:.3f}")

    print("\n== the peak hour, every fleet on it (sql/52 block 2) ==")
    print("moving_share is a MESSAGE share and compares to its own reference "
          "hour only.")
    print(f"{'storm':14s} {'fleet':10s} {'heard':>6} {'ref heard':>9} "
          f"{'share':>6} {'ref':>6}")
    for r in sorted(peak, key=lambda r: (start[r["storm"]], r["mobile"], r["ship_group"])):
        key = (r["mobile"], r["ship_group"])
        if key not in LABEL or r["moving_share"] is None:
            continue
        print(f"{r['storm']:14s} {LABEL[key]:10s} {r['heard']:6d} "
              f"{r['ref_heard']:9d} {r['moving_share']:6.3f} "
              f"{(r['ref_moving_share'] if r['ref_moving_share'] is not None else float('nan')):6.3f}")

    print("\n== ferry departures per hour under the storm (sql/50's "
          "ferry_crossings) ==")
    print("The lines with at least one DANISH end — island, domestic and "
          "international. sql/50 excludes 36.5 % foreign, 0.66 % "
          "intra-harbour and 7.48 % unmatched crossings from this column and "
          "from its reference alike.")
    print(f"{'storm':14s} {'storm/day':>9} {'ref/day':>8} {'storm÷ref':>10} "
          f"{'pre/day':>8} {'storm÷pre':>10}")
    for storm in order:
        if not ndays[storm]:
            continue
        sto, ref, pre = ferry_hours(win, storm, ndays)
        n = ndays[storm]
        print(f"{storm:14s} {sto / n:9.0f} {ref / n:8.0f} "
              f"{sto / ref if ref else 0:10.3f} {pre / 3:8.0f} "
              f"{sto / n / (pre / 3):10.3f}")
    pia_ferry = collections.Counter()
    for r in win:
        if (r["storm"] == "Pia" and r["mobile"] == "Class A"
                and r["ship_group"] == "passenger" and 0 <= r["offset_h"] < 48):
            pia_ferry[r["hour"][:10]] += r["ferry_crossings"]
    print("Pia, date by date: "
          + " + ".join(f"{d} {n}" for d, n in sorted(pia_ferry.items()))
          + f" = {sum(pia_ferry.values())} Danish-end departures over the two "
          "storm dates.")

    print("\n== the hidden ferry fleet (sql/52 block 3) ==")
    print("Every Class A vessel that has ever run a crossing, counted by the "
          "ship type `vessel_day` resolved for it THAT DAY. The share filed "
          "outside `passenger` is the size of the hole in the passenger group "
          "— and of the bulge in `other` — on each side of the comparison.")
    print(f"{'storm':14s} {'day':12s} {'kind':10s} {'fleet':>6} "
          f"{'outside passenger':>18}")
    ff = ferry_fleet_days(fleet)
    for k in sorted(ff, key=lambda k: (start[k[0]], k[1])):
        total, outside = ff[k]
        print(f"{k[0]:14s} {k[1]:12s} {k[2]:10s} {total:6d} "
              f"{outside:8d} = {outside / total:6.1%}")

    print("\n== the anchorages (sql/51) ==")
    labelled = labelled_names(cells)
    unlabelled = {c["name"] for c in cells if c["note"] == "not an anchorage"}
    print(f"the rule returns {len(cells)} cell-years over "
          f"{len({c['h3'] for c in cells})} distinct cells; "
          f"{len(labelled)} names are anchorages with a source and "
          f"{len(unlabelled)} are labelled 'not an anchorage' and excluded; "
          f"{sum(1 for c in cells if not c['name'])} cell-years are under the "
          "100-vessel bar and carry no label at all")
    print(f"the {len(DANISH_ANCHORAGES)} Danish anchorages of chart 2, mean "
          "Class A cargo + other present per hour: the 72 hours before, the "
          "storm's own dates, the 72 after, and the same hours a fortnight "
          "away. The sixth labelled one, the Øresund berth off Helsingør, is "
          "not charted and not counted here: 6 of its 192 hours pool.")
    print(f"{'storm':14s} {'anchorage':32s} {'pre':>6} {'storm':>6} {'post':>6} "
          f"{'ref':>6} {'storm÷ref':>10} {'storm÷pre':>10}")
    cellsr = anchor_cells(prof, ndays)
    by_storm = collections.defaultdict(list)
    for c in cellsr:
        by_storm[c["storm"]].append(c)
    for storm in sorted(by_storm, key=lambda s: peak_at[s]["peak_ratio"]
                        if s in peak_at else 9):
        for c in by_storm[storm]:
            # An anchorage can be EMPTY at the reference hours and not at the
            # storm's, so the two ratios print as '-' rather than dividing by
            # zero, and such a cell is left out of the medians below.
            print(f"{c['storm']:14s} {c['name']:32s} {c['pre']:6.1f} "
                  f"{c['sto']:6.1f} "
                  f"{c['post'] if c['post'] is not None else float('nan'):6.1f} "
                  f"{c['ref']:6.1f} "
                  f"{('%.2f' % c['r_ref']) if c['r_ref'] else '-':>10} "
                  f"{('%.2f' % c['r_pre']) if c['r_pre'] else '-':>10}")
        print()
    ratios = [c for c in cellsr if c["r_ref"] and c["r_pre"]]
    print(f"over the {len(ratios)} storm × anchorage cells above: median "
          f"storm ÷ the 72 hours before it "
          f"{statistics.median(c['r_pre'] for c in ratios):.2f}, median storm ÷ "
          f"the fortnight-away hours "
          f"{statistics.median(c['r_ref'] for c in ratios):.2f}")

    print("\n== Floriane's whole-window pooled Class A ratio (sql/50) ==")
    pool = collections.defaultdict(lambda: [0, 0])
    for r in win:
        if (r["storm"] == "Floriane" and r["mobile"] == "Class A"
                and r["ref_moving_msgs"]):
            pool[r["offset_h"]][0] += r["moving_msgs"]
            pool[r["offset_h"]][1] += r["ref_moving_msgs"]
    deepest = sorted((a / b, o) for o, (a, b) in pool.items() if b)[:3]
    last = max(pool)
    print("sql/52 restricts the peak search to the storm's own dates and finds "
          f"no dip ({peak_at['Floriane']['peak_ratio']:.4f}). Over the WHOLE "
          "window the three deepest hours are "
          + ", ".join(f"{v:.4f} at {o:+d} h" for v, o in deepest)
          + f" — and the window ends at {last:+d} h, so the minimum is the "
          "LAST hour in it. It is an edge, not a trough: nothing after it was "
          "measured, and it is three days past the date DMI published.")

    print("\n== the oracle, block 1: Pia's fishing week recounted (sql/53) ==")
    print("moved_msgs = vessels with ANY moving message; moved_dist = vessels "
          "with dist_nm ≥ 1 (sql/52's rule); msgs_gap = vessel_day's moving "
          "messages minus h3_hourly's, two tables written by two INSERTs")
    print(f"{'day':12s} {'heard':>6} {'moved(msgs)':>12} {'moved(≥1nm)':>12} "
          f"{'gap':>5} {'vd moving':>10} {'h3 moving':>10} {'msgs gap':>9}")
    for r in fish:
        print(f"{r['day']:12s} {r['heard']:6d} {r['moved_msgs']:12d} "
              f"{r['moved_dist']:12d} {r['moved_gap']:5d} "
              f"{r['vd_moving_msgs']:10d} {r['h3_moving_msgs']:10d} "
              f"{r['msgs_gap']:9d}")

    print("\n== the oracle, block 2: Svendborg – Ærøskøbing under Pia (sql/53) ==")
    print("oracle = raw public_track positions in two hard-coded res-7 cells, "
          "no ferry_crossing and no line label; table = what sql/40 wrote for "
          "this line. Two counting routes that share nothing but the day.")
    for r in aero:
        print(f"{r['day']:12s} oracle {r['oracle']:3d}  table "
              f"{r['table']:3d}  gap {r['gap']:+d}  vessels {r['vessels']}")


class Tee(io.StringIO):
    """stdout, recorded, so guard (g) can be run against the real output."""

    def write(self, s):
        sys.__stdout__.write(s)
        return super().write(s)


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    # One query at a time: the store lock is exclusive (docs/DECISIONS.md).
    win, start, ndays = window()
    cells, prof = anchorage()
    panel, peak, fleet = who_stays()
    fish, aero = oracle()

    # ---- asserts. Every literal below was measured by the supervising
    # ---- session with its own queries against h3_hourly / vessel_day, or is
    # ---- stated in a query file's header. None of them is read back out of
    # ---- the same rows they check.
    # (a) THE STORM LIST AND EVERY WINDOW'S LENGTH. Fifteen events, Dagmar and
    # Egon merged, and the eight DMI storms with no loaded day absent. The
    # counts are end - start + 1 read off data/context/storms.csv BY HAND, not
    # off these rows: `ndays` is arithmetic on sql/50's largest offset, so a
    # window built one day too long or too short is invisible to the file that
    # builds it and lands here. A sixteenth name, or a different length, means
    # storms.csv or the loaded-day set moved and every "of the fifteen" below
    # is stale.
    assert ndays == {
        "Dagmar·Egon": 3, "Freja": 2, "Gorm": 1, "Helga": 1, "Johanne": 1,
        "Knud": 1, "Alfrida": 0, "Malik": 2, "Nora": 2, "Otto": 2, "Pia": 2,
        "Sif": 2, "Floriane": 1, "Amy": 1, "Dave": 1}, \
        f"sql/50 emits {len(ndays)} storms: {sorted(ndays.items())}"
    # (b) ALFRIDA IS THE ONLY RUN-UP. If a second storm ever loses its own
    # dates, every per-storm mean below silently becomes a mean over 13.
    runups = [s for s, n in ndays.items() if n == 0]
    assert runups == ["Alfrida"], f"storms with no observed storm hour: {runups}"
    assert max(r["offset_h"] for r in win if r["storm"] == "Alfrida") == -1, \
        "Alfrida's window now reaches its own dates — 2019 has been loaded?"
    # (c) PIA'S DAILY TOTALS, THE CHAPTER'S ANCHOR. Measured on h3_hourly by
    # the supervising session before this file existed: Class A moving messages
    # on 2023-12-20 (an ordinary Wednesday) and on 2023-12-22 (Pia's second
    # date). Summed here out of sql/50's HOURLY rows, so a window built on the
    # wrong dates, a timezone conversion sneaking in, or a group remapped at
    # load time all land on this assert.
    pia = collections.Counter()
    for r in win:
        if r["storm"] == "Pia" and r["mobile"] == "Class A":
            pia[(r["ship_group"], r["hour"][:10])] += r["moving_msgs"]
    for group, quiet, storm_day in (("fishing", 461_314, 58_921),
                                    ("cargo", 4_544_874, 4_683_637),
                                    ("passenger", 1_112_095, 736_203)):
        assert pia[(group, "2023-12-20")] == quiet, \
            (f"Class A {group} moving messages on 2023-12-20: "
             f"{pia[(group, '2023-12-20')]}, measured {quiet}")
        assert pia[(group, "2023-12-22")] == storm_day, \
            (f"Class A {group} moving messages on 2023-12-22: "
             f"{pia[(group, '2023-12-22')]}, measured {storm_day}")
    # (d) THE REFERENCE RULE, on the two storms that exercise its branches.
    # Dagmar·Egon is the +14 d case — 2014-12-26..31 is not in the store at all
    # — and Pia the ordinary -14 d one. A rule that quietly fell back to "-14 d
    # or nothing" would leave Dagmar·Egon with no ratios and its panel empty,
    # which is exactly the failure a reader cannot see.
    # The comparison is on the whole DATETIME, not on the dates: the rule is
    # "the same UTC hour a fortnight away", and a reference joined an hour off
    # — a timezone conversion, an off-by-one in the INTERVAL — keeps the date
    # delta at exactly 14 days and changes the hour under it.
    deltas = collections.defaultdict(set)
    for r in win:
        if r["ref_hour"] != "\\N":
            deltas[r["storm"]].add(
                datetime.datetime.fromisoformat(r["ref_hour"])
                - datetime.datetime.fromisoformat(r["hour"]))
    DAY = datetime.timedelta(days=1)
    for storm, expect in (("Dagmar·Egon", {14 * DAY}), ("Pia", {-14 * DAY}),
                          ("Otto", {-14 * DAY, 14 * DAY})):
        assert deltas[storm] == expect, \
            f"{storm}: reference offsets {sorted(deltas[storm])}"
    assert set().union(*deltas.values()) == {-14 * DAY, 14 * DAY}, \
        f"some reference hour is not a whole fortnight away: "\
        f"{sorted(set().union(*deltas.values()))}"
    assert not [r for r in win if r["ref_hour"] == "\\N"], \
        "some window hour has no reference — sql/50's header says every one has"
    # (e) THE ORACLE, block 1. Three things at once: sql/53's own header states
    # the measured collapse of vessels that covered a mile (72 → 24 → 11 over
    # 12-20/21/22) and this file checks sql/52 against it across two files;
    # `moved_gap` must never be negative (dist_nm >= 1 implies a moving
    # message); and `msgs_gap` must be 0 on every day, which is the real check
    # — `vessel_day` and `h3_hourly` are two separate INSERTs in
    # sql/03_aggregate.sql and this is the only place they are compared.
    for r in fish:
        assert r["msgs_gap"] == 0, \
            (f"sql/53 {r['day']}: vessel_day and h3_hourly disagree by "
             f"{r['msgs_gap']} moving messages")
        assert r["moved_gap"] >= 0, \
            f"sql/53 {r['day']}: moved_gap {r['moved_gap']} is negative"
    fish_by_day = {r["day"]: r for r in fish}
    for day, dist, msgs, heard in (("2023-12-20", 72, 99, 320),
                                   ("2023-12-21", 24, 63, 313),
                                   ("2023-12-22", 11, 41, 298)):
        got = fish_by_day[day]
        assert (got["moved_dist"], got["moved_msgs"], got["heard"]) \
            == (dist, msgs, heard), \
            (f"sql/53 {day}: {got['moved_dist']} / {got['moved_msgs']} fishing "
             f"vessels moved out of {got['heard']} heard, sql/53's header "
             f"measured {dist} / {msgs} out of {heard}")
        same = [r for r in panel if r["storm"] == "Pia" and r["mobile"] == "Class A"
                and r["ship_group"] == "fishing" and r["day"] == day]
        assert len(same) == 1 and same[0]["moved"] == dist, \
            f"sql/52 and sql/53 disagree about {day}: {same}"
    # THE h3_hourly SIDE, pinned to its own literal. `moved_dist` and
    # `moved_msgs` above are both `vessel_day`; this is the other table, and
    # sql/50's whole chart 1 is built on it — sql/53's header emits the daily
    # sum here so it can be pinned once instead of re-summing 24 hourly rows.
    assert fish_by_day["2023-12-20"]["h3_moving_msgs"] == 461_314, \
        (f"sql/53: h3_hourly holds {fish_by_day['2023-12-20']['h3_moving_msgs']} "
         "Class A fishing moving messages on 2023-12-20, measured 461 314")
    # (f) THE ORACLE, block 2, and it is a real one: the oracle side counts
    # crossings from raw `public_track` positions in two hard-coded cells and
    # reads nothing sql/40 wrote, the table side is `ferry_crossing` on the
    # line label. BOTH SIDES are pinned to the same eight literals from
    # sql/53's header, so a change that moved both together — a lost day, a
    # re-folded line — cannot pass by making the gap zero.
    WEEK = [20, 20, 20, 16, 18, 18, 14, 16]
    assert [r["oracle"] for r in aero] == WEEK, \
        f"the raw-position oracle counts {[r['oracle'] for r in aero]}, not {WEEK}"
    assert [r["table"] for r in aero] == WEEK, \
        f"ferry_crossing holds {[r['table'] for r in aero]}, not {WEEK}"
    for r in aero:
        assert r["gap"] == 0, \
            f"sql/53 {r['day']}: oracle {r['oracle']} vs table {r['table']}"
        assert r["vessels"] == 2, \
            f"sql/53 {r['day']}: {r['vessels']} vessels on the Ærø line, not 2"
    # The storm-day count read off the WINDOW (sql/50) against the one read off
    # the DAY panel (sql/52, max offset_d = n + 2). Two files, two window
    # constructions, one number.
    for storm, n in ndays.items():
        if not n:
            continue
        got = max(r["offset_d"] for r in panel if r["storm"] == storm) - 2
        assert got == n, f"{storm}: sql/50 says {n} storm dates, sql/52 says {got}"
    # (g) CARGO DOES NOT STOP — the chapter's headline negative, asserted so it
    # cannot rot into a sentence nobody rechecks. Across all 14 storms with
    # storm dates, the exact share of cargo vessels that covered a mile moves by
    # at most a tenth against the fortnight-away days, in either direction.
    # Fishing, on the same instrument, falls by up to 0.45.
    cargo = [moved_pool(panel, s, "Class A", "cargo", ndays) for s in ndays
             if ndays[s]]
    worst = max(abs(p["share"] - p["ref_share"]) for p in cargo)
    assert worst <= 0.10, \
        f"cargo's share_moved moves by {worst:.3f} on some storm — the bound is 0.10"
    fishing = [moved_pool(panel, s, "Class A", "fishing", ndays) for s in ndays
               if ndays[s]]
    assert min(p["share"] - p["ref_share"] for p in fishing) < -0.4, \
        "no storm costs the fishing fleet 40 points of share_moved any more"
    # (h) FLORIANE HAS NO DIP ON ITS OWN DATE, and that is a finding, not a
    # bug: its derived peak ratio is ABOVE 1. It is the one storm whose window
    # minimum (0.76, three days later) sits outside its DMI date, which is what
    # sql/52's header means by "a quiet storm must be allowed to read as quiet".
    floriane = next(r for r in peak if r["storm"] == "Floriane")
    assert floriane["peak_ratio"] > 1.0, \
        f"Floriane's deepest own-date hour is {floriane['peak_ratio']}, not above 1"
    assert min(r["peak_ratio"] for r in peak) < 0.5, \
        "no storm's peak hour halves the country's moving messages any more"
    # and sql/52 says so in a column now, so the charts can draw "no dip" as no
    # dip. Exactly one storm, and it is that one.
    nodip = {r["storm"] for r in peak if not r["is_dip"]}
    assert nodip == {"Floriane"}, f"storms with no dip on their own date: {nodip}"
    # (j) EVERY PEAK HOUR IS INSIDE ITS STORM'S OWN DATES. sql/52 bounds the
    # search with `offset_h >= 0 AND hour < end_day + 1`; drop either half and
    # the peak wanders into the run-up or the recovery, which is finding 46's
    # whole subject. Checked against sql/50's window length, i.e. across files.
    for r in peak:
        assert 0 <= r["peak_offset_h"] < 24 * ndays[r["storm"]], \
            (f"{r['storm']}: peak offset {r['peak_offset_h']} is outside "
             f"0 .. {24 * ndays[r['storm']] - 1}")
    # (k) PIA'S TWO STORM DATES, IN DANISH-END FERRY DEPARTURES. Measured
    # directly on `ferry_crossing` by the supervising session:
    # 1 076 on 2023-12-21 and 880 on 2023-12-22 for kind IN ('island',
    # 'domestic', 'international'). Summed here out of sql/50's HOURLY rows, so
    # the hour bucketing and the kind filter are both on the hook.
    pia_ferry = collections.Counter()
    for r in win:
        if (r["storm"] == "Pia" and r["mobile"] == "Class A"
                and r["ship_group"] == "passenger" and 0 <= r["offset_h"] < 48):
            pia_ferry[r["hour"][:10]] += r["ferry_crossings"]
    assert (pia_ferry["2023-12-21"], pia_ferry["2023-12-22"]) == (1076, 880), \
        f"Pia's Danish-end departures by date: {sorted(pia_ferry.items())}"
    assert sum(pia_ferry.values()) == 1956, "…and 1 076 + 880 = 1 956"
    # (l) THE LEISURE FLOOR SELECTS THREE STORMS AND THEY ARE THE THREE THAT
    # FALL IN A SAILING SEASON. The floor is a judgement call in a constant, so
    # the SET it produces is pinned rather than the constant: a winter storm
    # crossing it, or Knud dropping under it, changes which lines chart 1 draws
    # as data and which findings 43 and 44 are allowed to talk about.
    solid_leisure = {s for s in ndays if ndays[s]
                     and leisure_ref_moved(panel, s, ndays) >= LEISURE_FLOOR}
    assert solid_leisure == {"Amy", "Johanne", "Knud"}, \
        (f"leisure is drawn as data on {sorted(solid_leisure)}, not on Amy, "
         "Johanne and Knud")
    # (m) THE HALVING TABLE, finding 40's spine. Fishing halves on every storm
    # and cargo on at most two — that ORDER is the chapter's claim, and it is
    # computed by stops_at() here rather than by any query, so nothing else
    # checks it.
    halved = {key: sum(stops_at(win, s, *key, ndays)[0] is not None
                       for s in ndays if ndays[s]) for key in PLOTTED}
    assert halved[("Class A", "fishing")] == 14, \
        f"fishing halves on {halved[('Class A', 'fishing')]} of the 14 storms, not all"
    assert halved[("Class A", "cargo")] <= 2, \
        f"cargo halves on {halved[('Class A', 'cargo')]} storms — it used to be 2"
    # (n) THE ANCHORAGE LABELS AND THE ANCHORAGE MEDIANS. 37 names carry a
    # source in data/context/anchorages.csv (the file has 143 rows over 37
    # anchorage names plus 69 'not an anchorage' cells); block 3 profiles those
    # names and only those, so an excluded cell — the Lindø yard, the oil
    # fields, the harbours — can never reach chart 2. And finding 48/49's two
    # medians, which are the chapter's negative result.
    labelled = labelled_names(cells)
    assert len(labelled) == 37, \
        f"{len(labelled)} anchorage names carry a source, not 37: {sorted(labelled)}"
    profiled = {r["name"] for r in prof}
    assert profiled <= labelled and "Lindø yard" not in profiled, \
        f"sql/51 block 3 profiles cells it should not: {sorted(profiled - labelled)}"
    assert set(DANISH_ANCHORAGES) <= profiled, \
        (f"chart 2 asks for anchorages block 3 does not emit: "
         f"{sorted(set(DANISH_ANCHORAGES) - profiled)}")
    anch = [c for c in anchor_cells(prof, ndays) if c["r_ref"] and c["r_pre"]]
    assert len(anch) == 70, f"{len(anch)} storm × anchorage cells, not 70"
    for label, key, expect in (("the 72 hours before", "r_pre", 1.02),
                               ("the fortnight-away hours", "r_ref", 1.06)):
        got = statistics.median(c[key] for c in anch)
        assert abs(got - expect) < 0.005, \
            f"median storm ÷ {label} is {got:.4f}, measured {expect}"

    thin, solid = chart_window(win, start, ndays, peak, panel)
    chart_anchorage(prof)
    chart_who_stays(panel, peak, ndays)

    out = Tee()
    sys.stdout = out
    numbers(win, start, ndays, cells, prof, panel, peak, fleet, fish, aero,
            thin, solid)
    sys.stdout = sys.__stdout__
    # (i) THE MMSI GUARD, as in plot_ch03.py. CLAUDE.md forbids a private
    # vessel's MMSI anywhere near an output; a 9-digit integer is an MMSI or a
    # coincidence and this grep cannot tell them apart. The h3 cell ids sql/51
    # emits are 18-digit and are never printed anyway.
    hit = re.search(r"\b\d{9}\b", out.getvalue())
    assert hit is None, f"a 9-digit integer reached stdout: {hit.group(0)!r}"
    print(f"\nno 9-digit integer in {len(out.getvalue())} characters of output "
          "(the MMSI guard)")
    print(f"wrote {IMG}/ch04-window.png, ch04-anchorage.png, ch04-who-stays.png",
          file=sys.stderr)
