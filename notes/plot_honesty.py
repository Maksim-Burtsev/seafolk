#!/usr/bin/env python3
"""S10 honesty-layer charts: three PNGs into notes/img/, and the numbers behind
them.

    uv run --project notes notes/plot_honesty.py
    CH_PATH=data/ch_a uv run --project notes notes/plot_honesty.py   # on a clone

Same contract as notes/plot.py and plot_ch01/02/03/04.py, whose helpers this
file imports: every query runs through scripts/ch.sh against the
`clickhouse local` store, ONE FILE AT A TIME (the store lock is exclusive —
two clickhouse processes on one --path is an error, not a slowdown), there is
no client library, matplotlib is the one dependency, and every number
notes/honesty.md quotes is printed by numbers() below. `rows()` honours
CH_PATH because scripts/ch.sh does.

Three query files, each read exactly ONCE, split into blocks by column width
the way plot_ch04.py splits sql/51 and sql/52:

    sql/60_coverage_index.sql   9  Class A vessels/msgs per res-4 region-day
                               14  the store-wide daily reference + load_log
                               11  the Sep-2015 factor, one row per class
                               17  the region-month step table (blocks 4 and
                                   4b share a width — see split_steps())
                                7  night shares, three fleets
                                6  cargo msgs per vessel-hour, night vs day
                               12  BLOCK 6: msgs per Class A vessel-day, the
                                   distribution, per loaded month
                               10  BLOCK 6b: the same for Class B, per year
    sql/61_adoption.sql        13  the adoption series, both windows
                                5  the first-seen cohort
                                9  retention between loaded years
                               10  Class B message counts per vessel-day and
                                   per vessel-hour, and the flag shares
    sql/62_emodnet_compare.sql  9  per-cell pairs (res 7 then res 5, the `res`
                                   column tells them apart)
                               13  the summary, one row per resolution
                               10  the ten densest cells on each side
                                5  the missed EMODnet hours by zone

WHAT THIS FILE IS FOR. Chapters 01-04 measured the sea. This one measures the
INSTRUMENT: which of the eleven-year changes are boats and which are the
archive. Three charts, in the order the note reads them — the instrument, the
fleet, somebody else's numbers.

PRIVACY. Class B appears here at ONE grain only, store-wide (the whole bbox)
per year or per day, exactly as sql/60 and sql/61 emit it; there is no Class B
number per region or per cell anywhere in this file. sql/62's cell rows are
floored at k >= 5 distinct leisure vessels by the query and asserted here.
No MMSI, name, callsign or track of any private vessel is read, printed or
plotted.
THE NINE-DIGIT GUARD IS STRICT HERE, and that is a deliberate choice. sql/60
and sql/61 do emit columns that pass nine digits — `rows_read` (up to 3.0e8
for a monthly file), `msgs`, `moving_msgs`, `night_msgs` and `vessel_hours`,
all of them fleet-wide counts that cannot be an MMSI. plot_ch04.py exempts its
equivalents by inspection. THIS FILE INSTEAD NEVER PRINTS THEM: every one of
them is consumed as a ratio, a share or a per-vessel figure before it reaches
stdout, so guard (z) in main can be `no 9-digit integer at all` with no
exemption list to keep honest. If a future edit needs to print a raw message
total, print it in millions.
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

from plot import GRID, IMG, INK, MUTED, label_ends, rows, tidy

# Colour follows the entity across all five chapters (plot.GROUPS is the
# source): leisure/Class B blue, cargo green, ferries orange. The INSTRUMENT
# — anything that describes the receiver network rather than a fleet — is
# ch04's contrast grey, because it is not a fleet.
BLUE, GREEN, ORANGE, SLATE = "#2a78d6", "#1baf7a", "#eb6834", "#5b6b73"
RED = "#7d2c10"          # ch04's "storm" ink, reused for a contamination mark

# THE PHYSICAL CEILINGS, both from ITU-R M.1371 and both also stated in
# sql/60's block 6 header. Class A autonomous mode reports at most every 2 s,
# so 86 400 / 2 = 43 200 position reports in a day. Class B SO reports at most
# every 5 s (17 280); Class B CS, which most leisure boats carry, at best
# every 30 s (2 880), so the Class B cap is a loose upper bound over a fleet
# whose transponder type the archive does not record.
CAP_A, CAP_B = 43_200, 17_280

# THE SIX MAIN YEARS. 2022 and 2023 hold storm months only (59 days each) and
# have no day in sql/61's common window at all; they are never in an adoption
# series. sql/61's header says so at length.
MAIN_YEARS = [2015, 2018, 2021, 2024, 2025, 2026]

# THE DUPLICATION WINDOW, the published one: sql/24 excludes it, sql/60 flags
# it, docs/STATUS.md § S4-tails established it.
DUP0, DUP1 = datetime.date(2015, 8, 28), datetime.date(2015, 9, 30)

# PLACE NAMES READ OFF A COORDINATE, NOT A DATA FIELD. Every key is the res-4
# cell CENTRE as sql/60 block 1 prints it (h3ToGeo, rounded to 4 dp); every
# value is this session's reading of an atlas at that point, and a res-4 cell
# is ~1 770 km2, so the name says roughly where the panel is and nothing more.
# No name here comes from the archive — `vessel_day` has no place column. A
# region with no entry is labelled by its coordinate, so the chart cannot
# break on an unrecognised one.
PLACES = {
    ("57.6227", "11.619"):  "Kattegat, the Göteborg approach",
    ("57.6811", "10.9384"): "Kattegat, north of Læsø",
    ("57.7356", "10.2583"): "Skagerrak, west of Skagen",
    ("54.5351", "11.3286"): "Fehmarn Belt",
    ("54.4669", "11.9745"): "Kadetrenden",
    ("55.1832", "14.1022"): "west of Bornholm",
    ("55.4403", "14.6061"): "Bornholmsgat",
    ("54.7344", "12.46"):   "south of Møn",
    ("54.9233", "13.6033"): "north of Rügen",
    ("55.6694", "12.6282"): "Øresund off Copenhagen",
    ("57.7863", "9.5788"):  "Skagerrak, off Hirtshals",
    ("57.9965", "10.7602"): "Skagerrak, the Skagen–Norway approach",
    ("56.9812", "11.9626"): "Kattegat, off Anholt",
    ("54.5996", "10.6831"): "Kiel Bight",
    ("54.3255", "10.2098"): "Kiel Fjord",
    ("57.3633", "11.1147"): "Læsø, the west coast",
    ("57.3031", "11.7917"): "Kattegat, east of Læsø",
}
# THE ONE LARGE-REGION HEAD-COUNT STEP IN THE STORE (sql/60 header point 3),
# pinned by its coordinate so the chart draws it whether or not it is one of
# the twelve busiest regions — it is not (median 106 a day, rank ~20).
SKAGERRAK = ("57.9965", "10.7602")

B1 = "day region lat lon vessels msgs moving_msgs msgs_per_vessel dup_window".split()
B2 = ("day class_a_vessels class_b_vessels class_a_msgs class_b_msgs "
      "class_b_per_class_a class_a_msgs_per_vessel_day class_b_msgs_per_vessel_day "
      "rows_read pct_out_of_bbox pct_non_vessel pct_sentinel grain dup_window").split()
B3 = ("mobile window_days window_vessel_days window_median_per_vd "
      "before_median_per_vd after_median_per_vd factor_per_vd "
      "window_median_daily_mean before_median_daily_mean after_median_daily_mean "
      "factor_daily_mean").split()
B4 = ("region lat lon region_size mon prev_mon gap_months days_in_month "
      "med_vessels prev_med_vessels v_ratio med_msgs_per_vessel "
      "prev_med_msgs_per_vessel mpv_ratio flag_vessels flag_msgs "
      "dup_month").split()
B5 = "year season fleet local_days moving_msgs night_msgs night_share".split()
B5B = ("year part vessel_hours msgs msgs_per_vessel_hour "
       "moving_msgs_per_vessel_hour").split()
B6 = ("mon loaded_days vessel_days median_msgs mean_msgs p90_msgs p99_msgs "
      "max_msgs vd_over_cap share_over_cap max_over_cap_x dup_month").split()
B6B = ("year loaded_days vessel_days median_msgs mean_msgs p90_msgs p99_msgs "
       "max_msgs vd_over_cap share_over_cap").split()

A1 = ("year window coverage loaded_days class_b_vessels class_b_leisure_vessels "
      "class_a_vessels class_a_vessels_5d leisure_per_class_a "
      "leisure_per_class_a_5d class_b_5d class_b_1d class_a_1d").split()
A2 = "year_heard cohort_first_seen years_since_first vessels share_of_year".split()
A3 = ("year_from year_to gap_years vessels_from vessels_next retained_next "
      "leisure_from retained_next_leisure heard_any_later").split()
A4 = ("year vessel_days median_msgs_per_vessel_day vessel_hours msgs "
      "msgs_per_vessel_hour vessel_days_moving median_dist_nm_moving "
      "danish_share german_share").split()

E1 = ("res h3 our_vessel_hours our_vessels emodnet_hours emodnet_sailing "
      "emodnet_pleasure rank_ours rank_emodnet").split()
E3 = ("res n_both n_emodnet_only n_ours_only rankcorr_both rankcorr_union "
      "pearson_log1p top10_overlap top25_overlap top200_floored_out "
      "emo_hours_in_our_zero our_vh_in_emo_zero n_union").split()
E4 = ("res side h3 lat lon our_vessel_hours our_vessels emodnet_hours "
      "rank_ours rank_emodnet").split()
E5 = "zone emodnet_hours emodnet_hours_in_our_zero share_missed n_cells".split()

INTS = {"vessels", "msgs", "moving_msgs", "class_a_vessels", "class_b_vessels",
        "class_a_msgs", "class_b_msgs", "rows_read", "dup_window", "dup_month",
        "window_days", "window_vessel_days", "gap_months", "days_in_month",
        "region_size", "local_days", "night_msgs", "vessel_hours",
        "loaded_days", "vessel_days", "max_msgs", "vd_over_cap",
        "class_b_leisure_vessels", "class_a_vessels_5d", "class_b_5d",
        "class_b_1d", "class_a_1d", "year", "year_heard", "cohort_first_seen",
        "years_since_first", "year_from", "year_to", "gap_years",
        "vessels_from", "vessels_next", "leisure_from", "vessel_days_moving",
        "res", "our_vessel_hours", "our_vessels", "rank_ours", "rank_emodnet",
        "n_both", "n_emodnet_only", "n_ours_only", "top10_overlap",
        "top25_overlap", "top200_floored_out", "n_union", "n_cells",
        "flag_vessels", "flag_msgs"}


def typed(names, r):
    """One TSV row -> a dict, with the integer columns cast and the rest left
    as float where they parse as one. Dates and labels stay strings."""
    d = dict(zip(names, r))
    for k, v in d.items():
        if k in INTS:
            d[k] = int(v)
        elif re.fullmatch(r"-?\d+\.?\d*(e-?\d+)?", v) and k not in (
                "mon", "prev_mon", "day", "h3", "lat", "lon"):
            d[k] = float(v)
    return d


def split_steps(seventeen):
    """sql/60's blocks 4 and 4b are both 17 columns wide, and 4b's rows are a
    SUBSET of 4's (the gap_months = 1 ones, re-sorted). So the split is where
    a (region, mon) key first repeats: within one block it is unique.
    Hard-coding 2 572 would work today and lie the day a month is loaded."""
    seen, cut = set(), len(seventeen)
    for i, r in enumerate(seventeen):
        key = (r["region"], r["mon"])
        if key in seen:
            cut = i
            break
        seen.add(key)
    return seventeen[:cut], seventeen[cut:]


def coverage():
    """sql/60 -> the eight blocks, keyed by name."""
    w = collections.defaultdict(list)
    for r in rows("60_coverage_index.sql"):
        w[len(r)].append(r)
    assert set(w) == {9, 14, 11, 17, 7, 6, 12, 10}, \
        f"sql/60 emits widths {sorted(w)}, not the eight this file parses"
    b4, b4b = split_steps([typed(B4, r) for r in w[17]])
    return {"b1": [typed(B1, r) for r in w[9]],
            "b2": [typed(B2, r) for r in w[14]],
            "b3": [typed(B3, r) for r in w[11]],
            "b4": b4, "b4b": b4b,
            "b5": [typed(B5, r) for r in w[7]],
            "b5b": [typed(B5B, r) for r in w[6]],
            "b6": [typed(B6, r) for r in w[12]],
            "b6b": [typed(B6B, r) for r in w[10]]}


def adoption():
    """sql/61 -> four blocks, keyed by name."""
    w = collections.defaultdict(list)
    for r in rows("61_adoption.sql"):
        w[len(r)].append(r)
    assert set(w) == {13, 5, 9, 10}, f"sql/61 emits widths {sorted(w)}"
    return {"b1": [typed(A1, r) for r in w[13]],
            "b2": [typed(A2, r) for r in w[5]],
            "b3": [typed(A3, r) for r in w[9]],
            "b4": [typed(A4, r) for r in w[10]]}


def emodnet():
    """sql/62 -> the pair rows split by resolution, the summary, the extremes.

    Blocks 1 and 2 share a width on purpose (sql/62's header says so) and
    carry `res` as their first column, which is what tells them apart.
    """
    w = collections.defaultdict(list)
    for r in rows("62_emodnet_compare.sql"):
        w[len(r)].append(r)
    assert set(w) == {9, 13, 10, 5}, f"sql/62 emits widths {sorted(w)}"
    pairs = [typed(E1, r) for r in w[9]]
    return {"p7": [r for r in pairs if r["res"] == 7],
            "p5": [r for r in pairs if r["res"] == 5],
            "sum": {typed(E3, r)["res"]: typed(E3, r) for r in w[13]},
            "top": [typed(E4, r) for r in w[10]],
            "zones": [typed(E5, r) for r in w[5]]}


# ------------------------------------------------------------ the x axis ----
def runs(days):
    """The loaded calendar split into contiguous runs.

    2016, 2017, 2019, 2020 and most of 2022-2023 are not in the store, so a
    line drawn straight through would invent five years of sea. Every series
    in chart 1 is drawn one run at a time, and the x axis is an INDEX over
    loaded days with a blank between runs — the gaps are compressed to a
    visible break rather than kept to scale, because kept to scale the four
    loaded stretches would be four thin stripes.
    """
    out, cur = [], [days[0]]
    for d in days[1:]:
        if (d - cur[-1]).days == 1:
            cur.append(d)
        else:
            out.append(cur)
            cur = [d]
    out.append(cur)
    return out


def axis_index(runs_, gap=40):
    """{date: x} with `gap` blank units between runs, and the tick positions."""
    x, ticks, pos = {}, [], 0
    for run in runs_:
        ticks.append((pos + len(run) / 2, run[0], run[-1]))
        for d in run:
            x[d] = pos
            pos += 1
        pos += gap
    return x, ticks


def mean7(vals):
    """A centred 7-day mean, computed inside one run only. Short runs (2023-02
    is 28 days, 2023-12 is 31) keep their ends."""
    out = []
    for i in range(len(vals)):
        lo, hi = max(0, i - 3), min(len(vals), i + 4)
        out.append(sum(vals[lo:hi]) / (hi - lo))
    return out


# ------------------------------------------------------------- chart 1 ----
def chart_coverage(cov):
    """Chart 1 — the instrument. Twelve region panels of the Class A head
    count, and one panel of the message-size distribution.

    The head count is the immune quantity (uniqExact over MMSI) and the
    message count is the contaminated one; putting them in one figure is the
    argument: the top three rows barely move, the bottom row doubles.
    """
    b1, b6 = cov["b1"], cov["b6"]
    days = sorted({datetime.date.fromisoformat(r["day"]) for r in b1})
    rr = runs(days)
    x, ticks = axis_index(rr)

    per_region = collections.defaultdict(dict)
    for r in b1:
        per_region[(r["lat"], r["lon"])][datetime.date.fromisoformat(r["day"])] = r["vessels"]
    med = {k: statistics.median(v.values()) for k, v in per_region.items()}
    picked = sorted(med, key=lambda k: -med[k])[:11]
    if SKAGERRAK not in picked:
        picked.append(SKAGERRAK)          # the store's one head-count step
    picked = sorted(picked, key=lambda k: -med[k])

    fig = plt.figure(figsize=(14.5, 10.5))
    gs = fig.add_gridspec(4, 4, height_ratios=[1, 1, 1, 1.35], hspace=0.62,
                          wspace=0.16)
    for i, key in enumerate(picked):
        ax = fig.add_subplot(gs[i // 4, i % 4])
        ax.axvspan(x[DUP0], x[DUP1], color=RED, alpha=0.22, linewidth=0)
        for run in rr:
            ys = mean7([per_region[key].get(d, 0) for d in run])
            ax.plot([x[d] for d in run], ys,
                    color=RED if key == SKAGERRAK else SLATE, linewidth=1.1)
        if key == SKAGERRAK:
            ax.axvline(x[datetime.date(2021, 1, 1)], color=RED, linewidth=1,
                       linestyle=(0, (3, 2)))
            ax.text(0.02, 0.97, "the store's ONE head-count step\n"
                                "2018-12 → 2021-01, ×1.507",
                    transform=ax.transAxes, color=RED, fontsize=7,
                    va="top", ha="left")
        # only the long runs are labelled: 2023-02 and 2023-12 are 28 and 31
        # days and their labels collide with each other at this panel width.
        # The break in the line is what says they are separate.
        ax.set_xticks([t[0] for t in ticks if (t[2] - t[1]).days > 200])
        ax.set_xticklabels([t[1].strftime("%Y") for t in ticks
                            if (t[2] - t[1]).days > 200], fontsize=7)
        ax.set_xlim(-20, max(x.values()) + 20)
        # extra headroom on the Skagerrak panel, whose corner carries a label
        ax.set_ylim(0, max(per_region[key].values())
                    * (1.3 if key == SKAGERRAK else 1.05))
        name = PLACES.get(key, f"{key[0]} N {key[1]} E")
        ax.set_title(f"{name}\n{key[0]} N {key[1]} E · median {med[key]:.0f}/day",
                     color=INK, fontsize=8, loc="left")
        tidy(ax)
        if i % 4 == 0:
            ax.set_ylabel("Class A vessels heard\nper day, 7-day mean",
                          color=MUTED, fontsize=7.5)

    ax = fig.add_subplot(gs[3, :])
    months = [datetime.date.fromisoformat(r["mon"]) for r in b6]
    mrun = []
    cur = [months[0]]
    for m in months[1:]:
        prev = cur[-1]
        nxt = datetime.date(prev.year + (prev.month == 12), prev.month % 12 + 1, 1)
        (cur.append(m) if m == nxt else (mrun.append(cur), cur := [m]))
    mrun.append(cur)
    mx, mticks = axis_index(mrun, gap=8)
    by_mon = {datetime.date.fromisoformat(r["mon"]): r for r in b6}
    ax.axhline(CAP_A, color=RED, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.annotate(f"{CAP_A:,} — one position report every 2 s for 24 h,\n"
                "the fastest a Class A transponder can send (ITU-R M.1371)"
                .replace(",", " "),
                (0, CAP_A), xytext=(4, 7), textcoords="offset points",
                color=RED, fontsize=8,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    for run in mrun:
        xs = [mx[m] for m in run]
        ax.plot(xs, [by_mon[m]["p90_msgs"] for m in run], color=SLATE, linewidth=2)
        ax.plot(xs, [by_mon[m]["median_msgs"] for m in run], color=BLUE, linewidth=2)
        ax.scatter(xs, [by_mon[m]["max_msgs"] for m in run], s=7, color=RED,
                   alpha=0.65, linewidths=0)
    ax.set_yscale("log")
    ax.set_xticks([t[0] for t in mticks])
    ax.set_xticklabels([t[1].strftime("%Y-%m") for t in mticks], fontsize=7.5,
                       rotation=30, ha="right")
    ax.set_xlim(-2, max(mx.values()) + 30)
    tidy(ax)
    ax.set_ylabel("messages per Class A\nvessel-day (log)", color=MUTED, fontsize=8)
    # NOT label_ends(): its minimum gap is (hi - lo) * gap_frac in DATA units,
    # and on a log axis that is tens of thousands, which pushes every label but
    # the top one off the panel. Three direct labels instead.
    last = by_mon[months[-1]]
    for value, text in ((last["max_msgs"], "worst vessel-day of the month"),
                        (last["p90_msgs"], "p90"),
                        (last["median_msgs"], "median")):
        ax.annotate(text, (max(mx.values()), value), xytext=(7, -3),
                    textcoords="offset points", fontsize=8,
                    color=RED if "worst" in text else
                          (SLATE if text == "p90" else BLUE),
                    annotation_clip=False)
    ax.set_title("Messages per Class A vessel-day, every loaded month: median, "
                 "p90, and the month's worst vessel-day (sql/60 block 6)",
                 color=INK, fontsize=9.5, loc="left")

    fig.suptitle(
        "The instrument, 2015 → 2026\n"
        "top: Class A vessels HEARD per day, the eleven busiest res-4 regions "
        "plus the one whose head count steps · uniqExact, immune to duplication\n"
        "bottom: how BIG a Class A vessel-day is · contaminated. Unloaded years "
        "are cut out of the x axis, never drawn across; the red band is "
        "2015-08-28 → 09-30",
        color=INK, fontsize=11.5, x=0.006, ha="left")
    fig.tight_layout(rect=(0, 0, 0.985, 0.935))
    fig.savefig(IMG / "honesty-coverage.png", dpi=160, facecolor="white")
    return picked, med


# ------------------------------------------------------------- chart 2 ----
def chart_adoption(ado):
    """Chart 2 — the fleet. Class B transponders on the common window, stacked
    by the year each was first heard, with the Class A instrument over it."""
    b1 = {r["year"]: r for r in ado["b1"] if r["window"] == "mar_aug"}
    coh = collections.defaultdict(dict)
    for r in ado["b2"]:
        coh[r["year_heard"]][r["cohort_first_seen"]] = r["vessels"]

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.4),
                             gridspec_kw={"width_ratios": [2.35, 1]})
    ax = axes[0]
    shades = ["#0d3c6e", "#1b5fa8", "#2a78d6", "#63a0e4", "#9cc4ef", "#cfe1f8"]
    xs = range(len(MAIN_YEARS))
    bottom = [0.0] * len(MAIN_YEARS)
    for c, colour in zip(MAIN_YEARS, shades):
        vals = [coh[y].get(c, 0) for y in MAIN_YEARS]
        ax.bar(xs, vals, bottom=bottom, width=0.62, color=colour, linewidth=0,
               label=f"first heard {c}")
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v > 2600:
                ax.annotate(f"{v:,}".replace(",", " "), (i, b + v / 2),
                            ha="center", va="center", fontsize=7.5,
                            color="white" if c in MAIN_YEARS[:3] else INK)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.plot(xs, [b1[y]["class_a_vessels_5d"] for y in MAIN_YEARS],
            color=SLATE, linewidth=2.2, marker="o", markersize=4)
    # the label used to sit ON the line at x = 0 and ran straight through the
    # 2018 bar's cohort numbers. It goes into the empty band above the 2015 and
    # 2018 bars instead, with a leader down to the line's left end — the only
    # part of the panel no bar, no cohort number and no legend reaches.
    ax.annotate("Class A vessels heard on ≥ 5 days — the instrument, and it is flat",
                (0, b1[2015]["class_a_vessels_5d"]), xytext=(10, 120),
                textcoords="offset points", ha="left", va="bottom",
                color=SLATE, fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=SLATE, linewidth=0.8))
    for i, y in enumerate(MAIN_YEARS):
        ax.annotate(f"{b1[y]['leisure_per_class_a_5d']:.2f}×", (i, bottom[i]),
                    xytext=(0, 6), textcoords="offset points", ha="center",
                    color=BLUE, fontsize=9)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(MAIN_YEARS)
    ax.set_ylim(0, max(bottom) * 1.16)
    ax.set_ylabel("distinct Class B transponders", color=MUTED, fontsize=9)
    ax.set_title("Class B transponders heard between 1 March and 26 August, "
                 "by the year each was first heard\n"
                 "· the label over each bar is leisure vessels per Class A "
                 "vessel heard on ≥ 5 days",
                 color=INK, fontsize=9.5, loc="left")
    ax.legend(frameon=False, fontsize=7.5, labelcolor=MUTED, ncol=2,
              loc="upper left")
    tidy(ax)

    ax = axes[1]
    ret = ado["b3"]
    xs = range(len(ret))
    ax.bar([i - 0.17 for i in xs], [r["retained_next"] for r in ret], width=0.32,
           color=SLATE, linewidth=0, label="all Class B")
    ax.bar([i + 0.17 for i in xs], [r["retained_next_leisure"] for r in ret],
           width=0.32, color=BLUE, linewidth=0, label="leisure → leisure")
    for i, r in enumerate(ret):
        ax.annotate(f"{r['retained_next']:.3f}", (i - 0.17, r["retained_next"]),
                    xytext=(0, 3), textcoords="offset points", ha="center",
                    fontsize=7, color=MUTED)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{r['year_from']}→{r['year_to']}\n{r['gap_years']} y"
                        for r in ret], fontsize=7.5)
    ax.set_ylim(0, 1)
    ax.set_ylabel("share heard again in the next loaded year",
                  color=MUTED, fontsize=8.5)
    ax.set_title("Retention — MIND THE GAP ROW:\nthree-year survivals, then "
                 "two one-year ones", color=INK, fontsize=9.5, loc="left")
    ax.legend(frameon=False, fontsize=7.5, labelcolor=MUTED, loc="upper left")
    tidy(ax)

    fig.suptitle("The fleet, divided by the instrument (sql/61)", color=INK,
                 fontsize=12, x=0.006, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(IMG / "honesty-adoption.png", dpi=160, facecolor="white")
    return b1, coh


# ------------------------------------------------------------- chart 3 ----
def chart_emodnet(emo):
    """Chart 3 — somebody else's numbers. Rank against rank at res 7."""
    s7, s5 = emo["sum"][7], emo["sum"][5]
    ours7 = [r for r in emo["top"] if r["res"] == 7 and r["side"] == "ours"]
    laeso = min(ours7, key=lambda r: -r["rank_emodnet"])

    fig, ax = plt.subplots(figsize=(9.5, 7.6))
    hi = max(max(r["rank_ours"] for r in emo["p7"]),
             max(r["rank_emodnet"] for r in ours7)) * 1.4
    ax.plot([1, hi], [1, hi], color=GRID, linewidth=1.2)
    ax.annotate("the two sources agree exactly", (hi * 0.06, hi * 0.06),
                xytext=(0, 6), textcoords="offset points", rotation=45,
                color=MUTED, fontsize=8, ha="center")
    ax.scatter([r["rank_emodnet"] for r in emo["p7"]],
               [r["rank_ours"] for r in emo["p7"]],
               s=16, color=SLATE, alpha=0.55, linewidths=0,
               label="the 200 densest res-7 cells with k ≥ 5 vessels of ours,\n"
                     "ranked by EMODnet — not EMODnet's own top 200:\n"
                     f"{s7['top200_floored_out']} of those are below the floor "
                     "and are replaced")
    ax.scatter([r["rank_emodnet"] for r in ours7],
               [r["rank_ours"] for r in ours7],
               s=44, facecolor="none", edgecolor=BLUE, linewidths=1.4,
               label="our 10 densest res-7 cells")
    ax.annotate(f"our rank {laeso['rank_ours']}, EMODnet's "
                f"{laeso['rank_emodnet']:,}".replace(",", " ") +
                f"\n{laeso['lat']} N {laeso['lon']} E ≈ a marina on Læsø\n"
                f"{laeso['our_vessel_hours']:,}".replace(",", " ") +
                f" vessel-hours from {laeso['our_vessels']} leisure vessels, "
                f"never moving\nagainst {laeso['emodnet_hours']} EMODnet hours: "
                "a boat at a berth draws no line",
                (laeso["rank_emodnet"], laeso["rank_ours"]),
                xytext=(-14, 34), textcoords="offset points", ha="right",
                color=BLUE, fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=BLUE, linewidth=0.8))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("EMODnet's rank for the cell (1 = densest)", color=MUTED, fontsize=9)
    ax.set_ylabel("our rank for the same cell", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=MUTED, loc="lower right")
    tidy(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_title(
        "Where the leisure fleet was in July 2021, ranked: this archive against "
        "EMODnet Human Activities\n"
        f"res 7 (~5 km²): Spearman {s7['rankcorr_both']} where both sources see "
        f"the cell, {s7['rankcorr_union']} over every cell either sees; "
        f"{s7['top10_overlap']} of the top 10 shared\n"
        f"res 5 (~250 km²): {s5['rankcorr_both']} / {s5['rankcorr_union']}, "
        f"{s5['top10_overlap']} of the top 10 — the coarser grid agrees more, "
        "so some of the res-7 scatter is griddling",
        color=INK, fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(IMG / "honesty-emodnet.png", dpi=160, facecolor="white")
    return laeso


# ------------------------------------------------------------- numbers ----
def numbers(cov, ado, emo, picked, med, b1a, coh, laeso):
    """Every figure notes/honesty.md quotes. Printed, never hand-typed.

    NOTHING HERE PRINTS A RAW MESSAGE TOTAL — see the module docstring's note
    on the nine-digit guard.
    """
    b1, b2, b3, b4, b5, b5b, b6, b6b = (cov[k] for k in
                                        "b1 b2 b3 b4 b5 b5b b6 b6b".split())

    print("== the loaded calendar (sql/60 block 2) ==")
    days = sorted(datetime.date.fromisoformat(r["day"]) for r in b2)
    rr = runs(days)
    print(f"{len(days)} loaded days in {len(rr)} contiguous runs:")
    for run in rr:
        print(f"  {run[0]} .. {run[-1]}  {len(run):4d} days")
    grain = collections.Counter(r["grain"] for r in b2)
    print(f"days from a MONTHLY file {grain['month']}, from a DAILY file {grain['day']}")
    print("\ndropped shares, % of rows_read, by file grain (min .. max):")
    for g in ("month", "day"):
        sel = [r for r in b2 if r["grain"] == g]
        for col in ("pct_out_of_bbox", "pct_non_vessel", "pct_sentinel"):
            v = [r[col] for r in sel]
            print(f"  grain={g:5s} {col:16s} {min(v):6.3f} .. {max(v):6.3f}")
    print("sql/13_coverage_daily.sql, S4's coverage query, keyed load_log on")
    print("toDate(ts_min), which files a whole monthly zip under the 1st; it is")
    print("removed in S10 and sql/60 block 2 replaces it, expanding the day range")
    print(f"instead, so every one of the {len(b2)} loaded days carries a share.")

    print("\n== finding: the Sep-2015 duplication (sql/60 block 3) ==")
    for r in b3:
        print(f"{r['mobile']}  window {r['window_days']} days · median msgs per "
              f"vessel-day {r['window_median_per_vd']:.0f} against "
              f"{r['before_median_per_vd']:.0f} before / "
              f"{r['after_median_per_vd']:.0f} after = ×{r['factor_per_vd']}"
              f"  |  median over days of the daily mean "
              f"{r['window_median_daily_mean']:.0f} vs "
              f"{r['before_median_daily_mean']:.0f} / "
              f"{r['after_median_daily_mean']:.0f} = ×{r['factor_daily_mean']}")

    print("\n== finding: the ceiling test, per loaded month (sql/60 block 6) ==")
    print(f"cap = {CAP_A} messages a vessel-day: one position report every 2 s "
          "for 24 h (ITU-R M.1371)")
    print(f"{'month':9s} {'days':>4} {'p50':>6} {'p90':>7} {'p99':>7} "
          f"{'max':>8} {'max/cap':>8} {'over cap':>8} {'% over':>7}")
    for r in b6:
        flag = "  ← duplication window" if r["dup_month"] else ""
        # the share is recomputed from the two counts rather than read out of
        # `share_over_cap`, which sql/60 rounds to five decimals — at
        # 0.000 05 resolution the pre-2023 months all read the same.
        print(f"{r['mon'][:7]:9s} {r['loaded_days']:4d} {r['median_msgs']:6.0f} "
              f"{r['p90_msgs']:7.0f} {r['p99_msgs']:7.0f} {r['max_msgs']:8d} "
              f"{r['max_over_cap_x']:8.2f} {r['vd_over_cap']:8d} "
              f"{100 * r['vd_over_cap'] / r['vessel_days']:7.4f}{flag}")

    clean = [r for r in b6 if r["mon"] < "2023-01-01" and not r["dup_month"]]
    stepped = [r for r in b6 if r["mon"] >= "2023-12-01"]
    mid = [r for r in b6 if r["mon"] == "2023-02-01"][0]
    for label, sel in (("clean months before 2023", clean),
                       ("2023-02 alone", [mid]),
                       ("2023-12 onward", stepped)):
        print(f"{label:26s} n={len(sel):3d}  p50 {min(r['median_msgs'] for r in sel):6.0f}"
              f" .. {max(r['median_msgs'] for r in sel):6.0f}"
              f"   p90 {min(r['p90_msgs'] for r in sel):6.0f}"
              f" .. {max(r['p90_msgs'] for r in sel):6.0f}"
              f"   p99 {min(r['p99_msgs'] for r in sel):6.0f}"
              f" .. {max(r['p99_msgs'] for r in sel):6.0f}"
              f"   %over {100 * min(r['vd_over_cap'] / r['vessel_days'] for r in sel):6.4f}"
              f" .. {100 * max(r['vd_over_cap'] / r['vessel_days'] for r in sel):6.4f}")
    jul = {r["mon"][:4]: r for r in b6 if r["mon"][5:7] == "07"}
    print(f"July only, p50 {jul['2021']['median_msgs']:.0f} (2021) -> "
          f"{jul['2024']['median_msgs']:.0f} (2024), ×"
          f"{jul['2024']['median_msgs'] / jul['2021']['median_msgs']:.3f}   "
          f"p90 {jul['2021']['p90_msgs']:.0f} -> {jul['2024']['p90_msgs']:.0f}, ×"
          f"{jul['2024']['p90_msgs'] / jul['2021']['p90_msgs']:.3f}")
    print("the median barely moves and the tail doubles: a TAIL step, not a level step")
    print(f"sporadic duplication PREDATES the step: "
          f"{len([r for r in clean if r['max_msgs'] > CAP_A])} of the {len(clean)} "
          f"clean pre-2023 months already hold a vessel-day above the cap, "
          f"{len([r for r in clean if r['max_msgs'] > 79_000])} of them above "
          f"79 000 messages (worst {max(r['max_msgs'] for r in clean)}, "
          f"{max(clean, key=lambda r: r['max_msgs'])['mon'][:7]})")

    print("\n== the same test on Class B, per year (sql/60 block 6b) ==")
    print(f"loose cap = {CAP_B} (Class B SO at 5 s; a Class B CS transponder "
          "cannot pass 2 880)")
    print(f"{'year':5s} {'days':>4} {'p50':>5} {'p90':>6} {'p99':>6} {'max':>7} "
          f"{'over cap':>8}")
    for r in b6b:
        print(f"{r['year']:5d} {r['loaded_days']:4d} {r['median_msgs']:5.0f} "
              f"{r['p90_msgs']:6.0f} {r['p99_msgs']:6.0f} {r['max_msgs']:7d} "
              f"{r['vd_over_cap']:8d}")

    print("\n== finding: region steps (sql/60 blocks 1 and 4) ==")
    print(f"{len(med)} res-4 regions pass the >= 20 vessels/day floor; "
          f"{len(b1)} region-days")
    print(f"block 4 emits {len(b4)} flagged region-months, block 4b "
          f"{len(cov['b4b'])} of them at gap_months = 1")
    big = [r for r in b4 if r["region_size"] >= 80]
    # sql/60 block 4 decides the band on the UNROUNDED ratios and emits the
    # verdict as `flag_vessels` / `flag_msgs`. Re-deriving it here from the
    # rounded `v_ratio` is a second spelling of the same rule and it answers
    # differently: 1 311 of block 4's rows clear `< 0.75 or > 1.3333` on the
    # rounded column against 1 349 that carry flag_vessels = 1 — every exact
    # 4/3 ratio rounds to 1.333 and falls out of the band.
    bigv = [r for r in big if r["flag_vessels"]]
    print(f"of the flagged rows, {len(big)} are in a region of >= 80 vessels/day; "
          f"{len(bigv)} of those flag on the HEAD COUNT:")
    for r in bigv:
        print(f"  {r['lat']} N {r['lon']} E  ≈ "
              f"{PLACES.get((r['lat'], r['lon']), 'unnamed')}  "
              f"{r['prev_mon'][:7]} → {r['mon'][:7]} (gap {r['gap_months']} months)  "
              f"median daily vessels {r['prev_med_vessels']:.0f} → "
              f"{r['med_vessels']:.0f} = ×{r['v_ratio']}")
    bym = collections.Counter(r["mon"][:7] for r in big)
    print("large-region flags of ANY kind, by month, top 8: " +
          ", ".join(f"{m} {n}" for m, n in bym.most_common(8)))
    print("the message-rate flags cluster on 2015-09/10 and on 2023-02/2023-12 — "
          "the two duplication events, not a receiver history")

    print("\n== the twelve charted regions (sql/60 block 1) ==")
    print("the step table compares one month with the previous one, so an "
          "eleven-year DRIFT is invisible to it; these are the yearly medians "
          "of the daily Class A head count, and the last column is 2026 / 2015")
    drift = {}
    for k in picked:
        sy = per_year_median(b1, k)
        drift[k] = sy["2026"] / sy["2015"]
        print(f"  {PLACES.get(k, 'unnamed'):38s} {k[0]:>8} N {k[1]:>8} E  "
              f"median {med[k]:5.0f}/day   by year: " +
              " ".join(f"{y} {v:.0f}" for y, v in sorted(sy.items())) +
              f"   2015 {sy['2015']:.0f} -> 2026 {sy['2026']:.0f} = "
              f"x{drift[k]:.2f}")
    # the Skagerrak is left out of the range on purpose: its x1.5 IS the one
    # step the table flags, and mixing it into a drift range would hide both.
    d = {k: v for k, v in drift.items() if k != SKAGERRAK}
    lo, hi = min(d, key=d.get), max(d, key=d.get)
    print(f"drift over the eleven regions the step table does NOT flag: "
          f"x{d[lo]:.2f} ({PLACES.get(lo, 'unnamed')}) .. x{d[hi]:.2f} "
          f"({PLACES.get(hi, 'unnamed')}) — real, inside +-20 %, and invisible "
          "to a month-against-previous-month ratio. The twelfth region, "
          f"{PLACES[SKAGERRAK]}, is x{drift[SKAGERRAK]:.2f} and is the flagged "
          "step. Drift is traffic and reception together and this store cannot "
          "separate them.")

    print("\n== finding: the night-share verdict (sql/60 blocks 5 and 5b) ==")
    ns = {(r["year"], r["fleet"]): r for r in b5 if r["season"] == "Oct-Apr"}
    print("Oct-Apr night share of moving messages (local hours 22,23,0-4):")
    print(f"{'fleet':17s} " + " ".join(f"{y:>7}" for y in MAIN_YEARS))
    for fleet in ("leisure Class B", "ferry Class A", "cargo Class A"):
        print(f"{fleet:17s} " +
              " ".join(f"{ns[(y, fleet)]['night_share']:7.4f}" for y in MAIN_YEARS))
    print(f"{'local days':17s} " +
          " ".join(f"{ns[(y, 'cargo Class A')]['local_days']:7d}" for y in MAIN_YEARS))
    print("\nrelative change in the Oct-Apr night share, each year against 2015 "
          "and against 2018:")
    print(f"{'fleet':17s} " + " ".join(f"{y:>15}" for y in MAIN_YEARS[2:]))
    for fleet in ("leisure Class B", "cargo Class A"):
        print(f"{fleet:17s} " + " ".join(
            f"{100 * (ns[(y, fleet)]['night_share'] / ns[(2015, fleet)]['night_share'] - 1):+7.1f} %"
            f"/{100 * (ns[(y, fleet)]['night_share'] / ns[(2018, fleet)]['night_share'] - 1):+6.1f} %"
            for y in MAIN_YEARS[2:]))
    print("READ 2026's Oct-Apr AS HALF A WINTER: its 119 local days are "
          "January-April only — the loaded archive ends 2026-08-26, so the "
          "autumn half of that season does not exist. 2025 is the last full "
          "Oct-Apr, and it is the +43 % / +90 % the essay quotes.")
    print("\ncargo Class A, night vs day, by year (sql/60 block 5b):")
    hb = {(r["year"], r["part"]): r for r in b5b}
    yrs = sorted({r["year"] for r in b5b})
    print(f"{'year':5s} {'msgs/vessel-hour night÷day':>27} "
          f"{'vessel-hours night÷day':>24}  (7/17 = 0.4118 is the clock's own share)")
    for y in yrs:
        n, d = hb[(y, "night")], hb[(y, "day")]
        print(f"{y:5d} {n['msgs_per_vessel_hour'] / d['msgs_per_vessel_hour']:27.4f} "
              f"{n['vessel_hours'] / d['vessel_hours']:24.4f}")
    print("the head count — immune to duplication — does not move; only the "
          "message ratio does, and it moves across the 2023 step")
    print("\nand the LEVEL of that mean, which is the column sql/60's header "
          "point 2 warns about — cargo messages per vessel-hour, day part:")
    print("  " + "  ".join(f"{y} {hb[(y, 'day')]['msgs_per_vessel_hour']:.0f}"
                           for y in yrs))

    print("\n== finding: the adoption curve (sql/61 block 1) ==")
    for w in ("mar_aug", "full_year"):
        print(f"-- window {w}")
        print(f"{'year':5s} {'days':>4} {'ClassB':>7} {'leisure':>8} {'ClassA':>7} "
              f"{'ClassA5d':>9} {'leis/A':>7} {'leis/A5d':>9} {'B 1-day':>8} "
              f"{'A 1-day':>8}  coverage")
        for r in sorted((r for r in ado["b1"] if r["window"] == w),
                        key=lambda r: r["year"]):
            print(f"{r['year']:5d} {r['loaded_days']:4d} {r['class_b_vessels']:7d} "
                  f"{r['class_b_leisure_vessels']:8d} {r['class_a_vessels']:7d} "
                  f"{r['class_a_vessels_5d']:9d} {r['leisure_per_class_a']:7.4f} "
                  f"{r['leisure_per_class_a_5d']:9.4f} {r['class_b_1d']:8d} "
                  f"{r['class_a_1d']:8d}  {r['coverage']}")
    raw = b1a[2026]["class_b_leisure_vessels"] / b1a[2015]["class_b_leisure_vessels"]
    per = b1a[2026]["leisure_per_class_a_5d"] / b1a[2015]["leisure_per_class_a_5d"]
    print(f"common window 2015 → 2026: leisure ×{raw:.3f}; "
          f"per Class A ≥5-day vessel ×{per:.3f}; "
          f"the instrument itself ×"
          f"{b1a[2026]['class_a_vessels_5d'] / b1a[2015]['class_a_vessels_5d']:.3f}")
    print(f"dividing by the instrument costs {100 * (1 - per / raw):.1f} % of the rise")

    print("\n== finding: cohorts (sql/61 block 2) ==")
    for y in MAIN_YEARS:
        tot = sum(coh[y].values())
        print(f"{y}  {tot:6d} Class B in the window = " +
              " + ".join(f"{coh[y][c]} ({c})" for c in sorted(coh[y])))
    print(f"2026: {100 * coh[2026][2026] / sum(coh[2026].values()):.1f} % first "
          f"heard this year, {100 * coh[2026][2015] / sum(coh[2026].values()):.1f} % "
          "carried from 2015")

    print("\n== finding: retention (sql/61 block 3) ==")
    for r in ado["b3"]:
        print(f"{r['year_from']} → {r['year_to']} (gap {r['gap_years']} y)  "
              f"of {r['vessels_from']:6d} Class B, {r['retained_next']:.4f} heard "
              f"again; leisure→leisure {r['retained_next_leisure']:.4f}; "
              f"heard in ANY later year {r['heard_any_later']:.4f}")

    print("\n== finding: Class B message counts and flags (sql/61 block 4) ==")
    print(f"{'year':5s} {'vessel-days':>12} {'median msgs/vd':>15} "
          f"{'msgs/vessel-hour':>17} {'median nm moving':>17} "
          f"{'Danish':>7} {'German':>7}")
    for r in ado["b4"]:
        print(f"{r['year']:5d} {r['vessel_days']:12d} "
              f"{r['median_msgs_per_vessel_day']:15.0f} "
              f"{r['msgs_per_vessel_hour']:17.1f} "
              f"{r['median_dist_nm_moving']:17.2f} "
              f"{r['danish_share']:7.4f} {r['german_share']:7.4f}")
    m21 = next(r for r in ado["b4"] if r["year"] == 2021)
    m24 = next(r for r in ado["b4"] if r["year"] == 2024)
    for w, label in (("mar_aug", "common window"),):
        for r in sorted((r for r in ado["b1"] if r["window"] == w),
                        key=lambda r: r["year"]):
            print(f"one-day Class B transponders, {label} {r['year']}: "
                  f"{r['class_b_1d']} of {r['class_b_vessels']} = "
                  f"{100 * r['class_b_1d'] / r['class_b_vessels']:.1f} % of the "
                  "window's fleet")
    print(f"messages per Class B vessel-hour 2021 → 2024: "
          f"{m21['msgs_per_vessel_hour']} → {m24['msgs_per_vessel_hour']} = "
          f"{100 * (m24['msgs_per_vessel_hour'] / m21['msgs_per_vessel_hour'] - 1):+.0f} %,"
          " while the vessel-DAY median goes "
          f"{m21['median_msgs_per_vessel_day']:.0f} → "
          f"{m24['median_msgs_per_vessel_day']:.0f}")

    print("\n== finding: EMODnet, July 2021 (sql/62) ==")
    print(f"blocks 1 and 2 emit the {len(emo['p7'])} densest res-7 cells AMONG "
          f"THOSE THAT CLEAR k >= 5 (and the {len(emo['p5'])} at res 5), which "
          "is not the same list as EMODnet's own top 200: "
          f"{emo['sum'][7]['top200_floored_out']} of EMODnet's true top 200 at "
          f"res 7 are floored out and replaced from further down the ranking "
          f"({emo['sum'][5]['top200_floored_out']} at res 5). Block 3's ranks "
          "and correlations are over every cell, floored or not")
    for res in (7, 5):
        s = emo["sum"][res]
        print(f"res {res}: {s['n_union']:6d} cells either source sees · both "
              f"{s['n_both']:6d} · EMODnet only {s['n_emodnet_only']:6d} · ours "
              f"only {s['n_ours_only']:5d}")
        print(f"        Spearman both {s['rankcorr_both']} · union "
              f"{s['rankcorr_union']} · Pearson log1p {s['pearson_log1p']} · "
              f"top-10 overlap {s['top10_overlap']} · top-25 {s['top25_overlap']}")
        print(f"        EMODnet hours in cells we have nothing in "
              f"{100 * s['emo_hours_in_our_zero']:.2f} % · our vessel-hours in "
              f"cells EMODnet has nothing in {100 * s['our_vh_in_emo_zero']:.2f} %")
    print("\nthe asymmetry is the bbox, not the fleet — the missed EMODnet hours "
          "by zone at res 7 (sql/62 block 5, first match wins on the cell "
          "centre, so the four zones partition the bbox):")
    for r in emo["zones"]:
        print(f"  {r['zone']:18s} {r['emodnet_hours'] / 1000:9.1f} k EMODnet "
              f"hours, {100 * r['share_missed']:5.2f} % of them in cells we "
              f"have no vessel-hour in  ({r['n_cells']} cells)")
    print(f"  {'all four':18s} {sum(r['n_cells'] for r in emo['zones'])} cells "
          f"= block 3's n_union {emo['sum'][7]['n_union']}")
    print(f"\nthe unit mismatch in one cell: {laeso['lat']} N {laeso['lon']} E "
          f"(≈ a marina on Læsø, a place name read off the coordinate) — our "
          f"rank {laeso['rank_ours']}, EMODnet's rank {laeso['rank_emodnet']}, "
          f"{laeso['our_vessel_hours']} vessel-hours from {laeso['our_vessels']} "
          f"leisure vessels against {laeso['emodnet_hours']} EMODnet hours")
    print("\nour ten densest res-7 cells, July 2021 (k >= 5 floored, both sides):")
    for r in [r for r in emo["top"] if r["res"] == 7 and r["side"] == "ours"]:
        print(f"  rank {r['rank_ours']:2d}  {r['lat']:>8} N {r['lon']:>8} E  "
              f"{r['our_vessel_hours']:6d} vessel-hours · {r['our_vessels']:4d} "
              f"vessels · EMODnet {r['emodnet_hours']:9.1f} h, its rank "
              f"{r['rank_emodnet']}")
    print("EMODnet's ten densest res-7 cells (same floor):")
    for r in [r for r in emo["top"] if r["res"] == 7 and r["side"] == "emodnet"]:
        print(f"  rank {r['rank_emodnet']:2d}  {r['lat']:>8} N {r['lon']:>8} E  "
              f"EMODnet {r['emodnet_hours']:9.1f} h · ours {r['our_vessel_hours']:6d} "
              f"vessel-hours, our rank {r['rank_ours']}")


def per_year_median(b1, key):
    """Median daily Class A vessels per year for one res-4 region."""
    per = collections.defaultdict(list)
    for r in b1:
        if (r["lat"], r["lon"]) == key:
            per[r["day"][:4]].append(r["vessels"])
    return {y: statistics.median(v) for y, v in per.items()}


class Tee(io.StringIO):
    """stdout, recorded, so guard (z) can be run against the real output."""

    def write(self, s):
        sys.__stdout__.write(s)
        return super().write(s)


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    # ONE QUERY FILE AT A TIME: the store lock is exclusive (docs/DECISIONS.md).
    cov, ado, emo = coverage(), adoption(), emodnet()

    # ---- asserts. Every literal below is stated in the header of the query
    # ---- file it checks, or was measured by the supervising session on the
    # ---- store with its own query, or is a physical constant. None is read
    # ---- back out of the rows it checks.

    # (a) THE SHAPE OF EACH FILE. Row counts from the three headers. A block
    # that lost rows, or a block parsed into the wrong bucket, lands here
    # before any number below is computed.
    assert len(cov["b1"]) == 284_399, f"sql/60 block 1: {len(cov['b1'])} rows"
    assert len(cov["b2"]) == 2_122, f"sql/60 block 2: {len(cov['b2'])} rows"
    assert (len(cov["b4"]), len(cov["b4b"])) == (2572, 2277), \
        (f"sql/60 blocks 4/4b split at {len(cov['b4'])}/{len(cov['b4b'])}, "
         "not 2 572 / 2 277 — see split_steps()")
    assert all(r["gap_months"] == 1 for r in cov["b4b"]), \
        "the second 17-column block is not the gap_months = 1 one"
    # THE FLAG COLUMNS. sql/60's header point 3: of the 9 568 region-month
    # pairs with a predecessor, 1 349 flag on the head count and 2 216 on the
    # message rate, and every emitted row flags on at least one of the two.
    assert (sum(r["flag_vessels"] for r in cov["b4"]),
            sum(r["flag_msgs"] for r in cov["b4"])) == (1349, 2216), \
        (f"block 4 flags {sum(r['flag_vessels'] for r in cov['b4'])} on vessels "
         f"and {sum(r['flag_msgs'] for r in cov['b4'])} on messages, not "
         "1 349 / 2 216")
    assert all(r["flag_vessels"] or r["flag_msgs"] for r in cov["b4"] + cov["b4b"]), \
        "a step-table row carries neither flag — the WHERE and the flags disagree"
    assert len(cov["b6"]) == 70 and len(cov["b6b"]) == 8, \
        f"sql/60 block 6: {len(cov['b6'])} months, 6b: {len(cov['b6b'])} years"
    assert len(ado["b1"]) == 14 and len(ado["b2"]) == 21 and len(ado["b3"]) == 5, \
        "sql/61 lost rows"
    assert len(emo["p7"]) == 200 and len(emo["p5"]) == 200, \
        f"sql/62: {len(emo['p7'])} / {len(emo['p5'])} pair rows, not 200 each"

    # (b) THE LOADED CALENDAR, from docs/DATA.md and sql/61's header: monthly
    # files for 2015, 2018, 2021, 2022-01/02, 2023-02, 2023-12 (1 213 days) and
    # 909 daily files from 2024-03-01. If a year is loaded between two runs of
    # this file, every "eleven years" sentence in the note is stale.
    grain = collections.Counter(r["grain"] for r in cov["b2"])
    assert (grain["month"], grain["day"]) == (1213, 909), \
        f"loaded days by file grain: {dict(grain)}, not 1 213 monthly / 909 daily"
    cal = runs(sorted(datetime.date.fromisoformat(r["day"]) for r in cov["b2"]))
    assert [len(r) for r in cal] == [365, 365, 424, 28, 31, 909], \
        (f"the loaded calendar is {[len(r) for r in cal]} days per contiguous "
         "run, not 365 / 365 / 424 / 28 / 31 / 909 — note that 2021 and "
         "2022-01/02 are ONE run, the archive has no gap at 2021-12-31")

    # (c) THE Sep-2015 DUPLICATION. sql/60's header point 1 measures 2.199 on
    # the vessel-day median and 2.552 on the daily mean; the planner's bound
    # for the note is "between 2.0 and 2.7 on Class A".
    ca = next(r for r in cov["b3"] if r["mobile"] == "Class A")
    assert ca["factor_per_vd"] == 2.199 and ca["factor_daily_mean"] == 2.552, \
        f"Sep-2015 Class A factors {ca['factor_per_vd']} / {ca['factor_daily_mean']}"
    assert 2.0 < ca["factor_per_vd"] < 2.7 and 2.0 < ca["factor_daily_mean"] < 2.7, \
        "the Sep-2015 factor left the 2.0 .. 2.7 band the note quotes"
    cb = next(r for r in cov["b3"] if r["mobile"] == "Class B")
    assert cb["factor_per_vd"] < ca["factor_per_vd"], \
        "Class B is no longer the less inflated of the two"

    # (d) THE CEILING TEST. 43 200 is ITU-R M.1371, not a threshold anyone
    # chose, so these asserts are against physics and against sql/60 block 6's
    # header.
    b6 = {r["mon"][:7]: r for r in cov["b6"]}
    clean = [r for r in cov["b6"] if r["mon"] < "2023-01-01" and not r["dup_month"]]
    stepped = [r for r in cov["b6"] if r["mon"] >= "2023-12-01"]
    assert len(clean) == 36 and len(stepped) == 31, \
        f"{len(clean)} clean pre-2023 months and {len(stepped)} stepped ones"
    assert 8749 <= min(r["p90_msgs"] for r in clean) and \
           max(r["p90_msgs"] for r in clean) <= 9428, \
        ("the clean months' p90 left 8 749 .. 9 428, the band sql/60's header "
         "point 2 states")
    assert min(r["p90_msgs"] for r in stepped) >= 16000, \
        "some month from 2023-12 on has a p90 back under 16 000"
    assert b6["2023-02"]["p90_msgs"] == 11877, \
        f"2023-02's p90 is {b6['2023-02']['p90_msgs']}, not 11 877 — the halfway month"
    # THE PLANNER'S PROPOSED ASSERT WAS "max above 43 200 only from 2023-12 on"
    # AND IT IS FALSE ON THIS STORE, which is worth an assert of its own rather
    # than a silent correction: 13 of the 36 clean months already hold a
    # vessel-day above the ceiling, and nine of those exceed 79 000 — nearly
    # twice it — with 106 122 in 2018-01 the worst. Sporadic duplication
    # PREDATES 2023. What 2023 changes is the RATE, and that is what the two
    # share_over_cap asserts below pin.
    over_clean = [r for r in clean if r["max_msgs"] > CAP_A]
    assert len(over_clean) == 13 and \
        len([r for r in clean if r["max_msgs"] > 79_000]) == 9, \
        (f"{len(over_clean)} clean pre-2023 months hold a vessel-day above "
         f"{CAP_A}, measured 13 (nine of them above 79 000) — the pre-existing "
         "sporadic duplication")
    assert max(r["share_over_cap"] for r in clean) <= 0.0007, \
        "a clean pre-2023 month now puts more than 0.07 % of vessel-days over the cap"
    assert min(r["share_over_cap"] for r in stepped) >= 0.0017, \
        "a month from 2023-12 on dropped under 0.17 % of vessel-days over the cap"
    assert all(r["max_msgs"] > CAP_A for r in stepped), \
        "some month from 2023-12 on no longer holds an impossible vessel-day"
    # the ceiling test finds the known window with no date in the query
    assert b6["2015-09"]["share_over_cap"] > 0.02 > \
           max(r["share_over_cap"] for r in stepped), \
        ("2015-09 is no longer the worst month by share over the cap — the "
         "ceiling test is supposed to rediscover point 1's window unaided")
    # A TAIL STEP, NOT A LEVEL STEP, on the planner's July pair (2021 → 2024).
    r21, r24 = b6["2021-07"], b6["2024-07"]
    assert r24["median_msgs"] / r21["median_msgs"] < 1.3, \
        "July's MEDIAN messages per Class A vessel-day moved by more than 30 %"
    assert r24["p90_msgs"] / r21["p90_msgs"] > 1.8, \
        "July's p90 no longer nearly doubles between 2021 and 2024"
    # Class B steps too, and by less. 979 / 1 306 / 1 500 are block 6b's own
    # measured p90s for 2021 / 2015 / 2025.
    b6b = {r["year"]: r for r in cov["b6b"]}
    assert b6b[2021]["p90_msgs"] == 979 and b6b[2025]["p90_msgs"] == 1500, \
        "Class B's p90 messages per vessel-day moved off 979 (2021) / 1 500 (2025)"
    assert b6b[2025]["p90_msgs"] / b6b[2021]["p90_msgs"] < \
           r24["p90_msgs"] / r21["p90_msgs"], \
        "Class B's tail step is no longer the smaller of the two"

    # (e) THE ONE LARGE-REGION HEAD-COUNT STEP. sql/60's header point 3: over
    # the region-months with a predecessor, exactly one region of >= 80 Class A
    # vessels a day changes its head count by more than a third, and it is the
    # Skagerrak at 2018-12 → 2021-01, v_ratio 1.507.
    # THE FLAG COMES FROM THE QUERY, not from a band re-typed here: sql/60
    # block 4 computes flag_vessels / flag_msgs from the same unrounded
    # expressions its WHERE uses (see block 4's header).
    bigv = [r for r in cov["b4"] if r["region_size"] >= 80 and r["flag_vessels"]]
    assert len(bigv) == 1, f"{len(bigv)} large-region head-count steps, not 1"
    step = bigv[0]
    assert step["v_ratio"] == 1.507 and (step["lat"], step["lon"]) == SKAGERRAK \
        and (step["prev_mon"][:7], step["mon"][:7]) == ("2018-12", "2021-01"), \
        f"the store's one head-count step moved: {step}"
    assert step["gap_months"] == 25, \
        ("the Skagerrak step is a 25-month comparison across two unloaded years "
         "and must be reported as one")
    # and the region floor sql/60's header states
    regions = {(r["lat"], r["lon"]) for r in cov["b1"]}
    assert len(regions) == 139, f"{len(regions)} res-4 regions pass the floor, not 139"

    # (f) THE NIGHT-SHARE CONTROLS. sql/60's header point 4 measures cargo
    # 0.3006 → 0.3123 (+3.9 %) against leisure's +43 % / +90 %, and this
    # session measured the immune head-count control (cargo vessel-hours,
    # night ÷ day) as flat at 0.409 .. 0.424 across all eight years.
    ns = {(r["year"], r["fleet"]): r["night_share"] for r in cov["b5"]
          if r["season"] == "Oct-Apr"}
    assert ns[(2015, "cargo Class A")] == 0.3006 and ns[(2026, "cargo Class A")] == 0.3123, \
        "the cargo night-share control moved off 0.3006 / 0.3123"
    assert 0.03 < ns[(2026, "cargo Class A")] / ns[(2015, "cargo Class A")] - 1 < 0.05, \
        "cargo's eleven-year night-share move left the 3-5 % band"
    assert ns[(2026, "leisure Class B")] / ns[(2018, "leisure Class B")] > 1.6, \
        "leisure's winter night share no longer rises against 2018"
    hb = {(r["year"], r["part"]): r for r in cov["b5b"]}
    yrs = sorted({r["year"] for r in cov["b5b"]})
    vh = [hb[(y, "night")]["vessel_hours"] / hb[(y, "day")]["vessel_hours"] for y in yrs]
    assert 0.40 < min(vh) and max(vh) < 0.43, \
        (f"cargo's night÷day VESSEL-HOURS ran {min(vh):.4f} .. {max(vh):.4f}; the "
         "immune control is supposed to be flat near 7/17 = 0.4118")
    mr = {y: hb[(y, "night")]["msgs_per_vessel_hour"]
             / hb[(y, "day")]["msgs_per_vessel_hour"] for y in yrs}
    assert mr[2021] < 1.03 < mr[2026], \
        "the night÷day MESSAGE ratio no longer steps across 2023"

    # (g) THE ADOPTION CURVE. sql/61's header point 1: 6 137 → 22 773 leisure
    # vessels on the common window (3.71x) and 0.6087 → 2.1117 per Class A
    # vessel heard on >= 5 days (3.47x), agreeing to within 7 %.
    b1a = {r["year"]: r for r in ado["b1"] if r["window"] == "mar_aug"}
    assert sorted(b1a) == MAIN_YEARS, \
        f"the common window covers {sorted(b1a)}, not the six main years"
    assert (b1a[2015]["class_b_leisure_vessels"],
            b1a[2026]["class_b_leisure_vessels"]) == (6137, 22773), \
        "the common-window leisure counts moved off 6 137 → 22 773"
    raw = b1a[2026]["class_b_leisure_vessels"] / b1a[2015]["class_b_leisure_vessels"]
    per = b1a[2026]["leisure_per_class_a_5d"] / b1a[2015]["leisure_per_class_a_5d"]
    assert abs(raw - 3.71) < 0.005, f"the raw rise is {raw:.4f}x, not 3.71x"
    assert abs(per - 3.47) < 0.005, f"the per-instrument rise is {per:.4f}x, not 3.47x"
    assert abs(per / raw - 1) < 0.07, \
        f"dividing by the instrument now costs {100 * (1 - per / raw):.1f} %, over 7"
    # THE BROKEN DENOMINATOR, header point 2: yearly distinct Class A falls by
    # a third between 2018 and 2021 and the >= 5-day count does not.
    fy = {r["year"]: r for r in ado["b1"] if r["window"] == "full_year"}
    assert (fy[2015]["class_a_1d"], fy[2018]["class_a_1d"]) == (8428, 9527), \
        "the one-day Class A ghost counts moved off 8 428 / 9 527"
    assert fy[2021]["class_a_1d"] < 3300 and fy[2024]["class_a_1d"] < 3000, \
        "the ghost MMSIs no longer collapse after 2018"
    assert fy[2021]["class_a_vessels"] / fy[2018]["class_a_vessels"] < 0.7, \
        "yearly distinct Class A no longer falls by a third — check the ghosts"
    assert 0.85 < fy[2021]["class_a_vessels_5d"] / fy[2018]["class_a_vessels_5d"] < 1.0, \
        "the >= 5-day Class A count is supposed to be the stable denominator"

    # (h) COHORTS AND RETENTION. The cohort block must add up to block 1's own
    # totals — two different queries over the same window — and the gap column
    # must still say what it says, because five bars in a row look like a
    # series and three of them are three-year survivals.
    coh = collections.defaultdict(dict)
    for r in ado["b2"]:
        coh[r["year_heard"]][r["cohort_first_seen"]] = r["vessels"]
    for y in MAIN_YEARS:
        assert sum(coh[y].values()) == b1a[y]["class_b_vessels"], \
            (f"{y}: cohorts sum to {sum(coh[y].values())}, block 1 says "
             f"{b1a[y]['class_b_vessels']}")
    assert [r["gap_years"] for r in ado["b3"]] == [3, 3, 3, 1, 1], \
        "the retention gaps are no longer 3, 3, 3, 1, 1"
    r15 = ado["b3"][0]
    assert r15["retained_next"] == 0.6495 and ado["b3"][-1]["retained_next"] == 0.7584, \
        "retention moved off 0.6495 (2015→2018) / 0.7584 (2025→2026)"
    assert min(r["retained_next"] for r in ado["b3"] if r["gap_years"] == 1) > \
           max(r["retained_next"] for r in ado["b3"] if r["gap_years"] == 3), \
        "a three-year survival now beats a one-year one — check gap_years"

    # (i) THE GERMAN FLEET IN THE BOX. sql/61 block 4's header: the bbox
    # reaches Kiel, Flensburg, Rügen and the Dutch Wadden, and German-flagged
    # Class B outnumbers Danish in every loaded year. The note says "the fleet
    # in the box, not the fleet of Denmark" on the strength of this.
    assert all(r["german_share"] > r["danish_share"] for r in ado["b4"]), \
        "German-flagged Class B is no longer the larger group in the bbox"

    # (j) EMODnet. sql/62's header states 0.6427 → 0.6987 on the union; the
    # planner's bound for the note is Spearman > 0.8 where both sources see the
    # cell, and a top-10 overlap of exactly 4 at res 7.
    s7, s5 = emo["sum"][7], emo["sum"][5]
    assert s7["rankcorr_both"] > 0.8 and s5["rankcorr_both"] > 0.8, \
        f"Spearman where both see the cell: {s7['rankcorr_both']} / {s5['rankcorr_both']}"
    assert s7["top10_overlap"] == 4 and s5["top10_overlap"] == 5, \
        f"top-10 overlap {s7['top10_overlap']} (res 7) / {s5['top10_overlap']} (res 5)"
    assert s7["rankcorr_union"] < s5["rankcorr_union"], \
        "the coarser grid no longer agrees more — the griddling argument is gone"
    assert s7["emo_hours_in_our_zero"] > 10 * s7["our_vh_in_emo_zero"], \
        ("the bbox-edge asymmetry is gone: EMODnet hours we miss vs our hours "
         "EMODnet misses")
    # BLOCK 1 IS NOT EMODnet's TOP 200. The k floor is applied before the
    # limit, so cells EMODnet ranks in its true top 200 drop out and cells
    # further down take their place — 18 of them at res 7, 23 at res 5.
    assert (s7["top200_floored_out"], s5["top200_floored_out"]) == (18, 23), \
        (f"{s7['top200_floored_out']} / {s5['top200_floored_out']} of EMODnet's "
         "true top 200 are floored out of blocks 1 / 2, measured 18 / 23")
    assert max(r["rank_emodnet"] for r in emo["p7"]) == 225, \
        "block 1 no longer reaches EMODnet rank 225 filling the floored gaps"
    # BLOCK 5, THE ZONE SPLIT. These four shares used to be a literal in
    # sql/62's header that no query produced; they are measured now, and the
    # four zones must partition block 3's domain.
    zones = {r["zone"]: r for r in emo["zones"]}
    assert sum(r["n_cells"] for r in emo["zones"]) == s7["n_union"], \
        "the four zones do not partition the res-7 union — check the zone rule"
    for zone, share in (("west of lon 7", 0.612), ("east of lon 13.5", 0.330),
                        ("south of 54.5 N", 0.071), ("Danish core", 0.011)):
        assert abs(zones[zone]["share_missed"] - share) < 0.005, \
            (f"{zone}: {zones[zone]['share_missed']} of EMODnet's leisure hours "
             f"in cells we have nothing in, measured {share}")
    # THE PRIVACY FLOOR, asserted rather than trusted: every row of sql/62 that
    # carries a cell id must be a cell with at least five distinct leisure
    # vessels in the month (CLAUDE.md's k >= 5 rule).
    assert all(r["our_vessels"] >= 5 for r in emo["p7"] + emo["p5"] + emo["top"]), \
        "a cell id reached the output with fewer than 5 distinct leisure vessels"
    # THE UNIT MISMATCH IN ONE CELL, sql/62's header: 57.3177 N 11.1397 E is
    # our 9th densest res-7 cell and EMODnet's 16 984th.
    ours7 = [r for r in emo["top"] if r["res"] == 7 and r["side"] == "ours"]
    laeso = min(ours7, key=lambda r: -r["rank_emodnet"])
    assert (laeso["lat"], laeso["lon"]) == ("57.3177", "11.1397") and \
        laeso["rank_ours"] == 9 and laeso["rank_emodnet"] == 16984, \
        f"the marina cell moved: {laeso}"
    assert laeso["emodnet_hours"] < 10, \
        "EMODnet now sees hours in the marina cell — the unit mismatch is gone"

    picked, med = chart_coverage(cov)
    b1a_chart, coh_chart = chart_adoption(ado)
    laeso_chart = chart_emodnet(emo)

    out = Tee()
    sys.stdout = out
    numbers(cov, ado, emo, picked, med, b1a, coh, laeso)
    sys.stdout = sys.__stdout__
    # (z) THE MMSI GUARD, and it is STRICT here: no nine-digit integer at all,
    # with no exempt columns. plot_ch04.py has to exempt fleet-wide message
    # totals; this file simply never prints one (see the module docstring).
    # A nine-digit integer in this output is an MMSI or a coincidence, and this
    # grep cannot tell them apart. The h3 cell ids are 18-digit and \b\d{9}\b
    # does not match inside them; they are k >= 5 floored anyway.
    hit = re.search(r"\b\d{9}\b", out.getvalue())
    assert hit is None, f"a 9-digit integer reached stdout: {hit.group(0)!r}"
    print(f"\nno 9-digit integer in {len(out.getvalue())} characters of output "
          "(the MMSI guard, strict: no exempt columns)")
    print(f"wrote {IMG}/honesty-coverage.png, honesty-adoption.png, "
          "honesty-emodnet.png", file=sys.stderr)
