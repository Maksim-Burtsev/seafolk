#!/usr/bin/env python3
"""S6 chapter-01 charts: three PNGs into notes/img/, and the numbers behind them.

    uv run --project notes notes/plot_ch01.py

Same contract as notes/plot.py, whose helpers this file imports: queries are run
through scripts/ch.sh against the `clickhouse local --path data/ch` store, there
is no client library, matplotlib is the one dependency, and every number printed
below comes out of a file in sql/.

Colour: years are an ORDERED category, so they get a single-hue ordinal ramp
(light -> dark, monotone lightness, validated) rather than six categorical hues,
and every line is direct-labelled at its right end. The two categorical series in
chart 3 keep slots 1 and 2 of the project palette that notes/plot.py fixed.

2022 and 2023 hold 59 winter days each and are excluded from every chart here;
they appear only in the printed numbers and as a caveat in notes/ch01-findings.md.
"""
import datetime
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot import IMG, INK, MUTED, label_ends, rows, tidy

YEARS = [2015, 2018, 2021, 2024, 2025, 2026]
# Ordinal ramp, one hue, light -> dark. Validated: monotone L, adjacent dL >= 0.06,
# light end 2.45:1 against the surface, hue spread 7 degrees.
RAMP = ["#6fa8e0", "#4e8ed8", "#2a78d6", "#1e63b4", "#154b8c", "#0d3565"]
YEAR_COLOUR = dict(zip(YEARS, RAMP))
BLUE, ORANGE = "#2a78d6", "#eb6834"
# Month starts in a non-leap year; good enough for an axis, the data is per-day.
MONTH_DOY = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
MONTH_TICK = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Kieler Woche is a German regatta in a Danish story: kept, drawn quieter.
REGATTA_ORDER = ["Classic Fyn Rundt", "Fyn Cup", "Sjælland Rundt", "Silverrudder",
                 "Kieler Woche"]


def doy(day):
    return datetime.date.fromisoformat(day).timetuple().tm_yday


def season_daily():
    """Daily moved Class B leisure vessels, and their trailing 7-day mean.

    The mean is computed here rather than read from sql/10_season_daily.sql's
    `active_7d`: that column is PARTITIONed by month (phase 0 loaded three
    separate months), and this chart needs a mean that runs across the year.
    """
    by_year = defaultdict(list)
    for day, mobile, present, active, _ in rows("10_season_daily.sql"):
        if mobile != "Class B":
            continue
        assert int(active) <= int(present), f"{day}: active > present"
        by_year[int(day[:4])].append((day, int(active)))

    out = {}
    for year, days in by_year.items():
        days.sort()
        assert len({d for d, _ in days}) == len(days), f"{year}: duplicate day rows"
        window, series = [], []
        for day, moved in days:
            window.append(moved)
            if len(window) > 7:
                window.pop(0)
            # Same rule as sql/20_season_bounds.sql: a mean over fewer than 7
            # days is not a 7-day mean and never defines a season edge.
            series.append((doy(day), moved, sum(window) / 7 if len(window) == 7 else None))
        out[year] = series
    return out


def season_bounds():
    """sql/20 keyed by year: (peak_7d, peak_doy, 25 % span, 50 % span)."""
    out = {}
    for (year, days, first_day, last_day, censored, peak_7d, peak_day,
         s25, e25, len_25, s50, e50, len_50) in rows("20_season_bounds.sql"):
        assert int(len_25) >= int(len_50), f"{year}: 50 % core wider than 25 % season"
        # The 7-day mean in sql/20 is a ROWS window, which is a 7-CALENDAR-day
        # window only while the year's day rows are contiguous. If a day ever
        # goes missing from vessel_day the window silently reaches further back
        # and every bound in this table shifts, so check it here rather than
        # trust the header's one-off verification.
        assert int(days) == (datetime.date.fromisoformat(last_day)
                             - datetime.date.fromisoformat(first_day)).days + 1, \
            f"{year}: {days} day rows over {first_day}..{last_day} — not contiguous"
        out[int(year)] = dict(days=int(days), censored=censored, peak_7d=float(peak_7d),
                              peak_day=peak_day, s25=s25, e25=e25, len_25=int(len_25),
                              s50=s50, e50=e50, len_50=int(len_50))
    return out


def chart_season(daily, bounds):
    """Chart 1 -- the season curve per year, over a strip of the season bounds."""
    fig, (ax, ax_b) = plt.subplots(
        2, 1, figsize=(11, 5.4), sharex=True,
        gridspec_kw={"height_ratios": [3, 1.15], "hspace": 0.18})

    # Direct labels sit at each year's PEAK, not at the right edge: every line
    # ends near zero in December, where six labels would collapse into one blob,
    # and the peaks are separated on the y axis by construction. The colour key
    # is the bounds strip below, whose year ticks carry the same ramp.
    for year in YEARS:
        pts = [(d, m7) for d, _, m7 in daily[year] if m7 is not None]
        colour = YEAR_COLOUR[year]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=colour, linewidth=2)
        b = bounds[year]
        ax.plot([doy(b["peak_day"])], [b["peak_7d"]], "o", markersize=8, color=colour,
                markeredgecolor="white", markeredgewidth=2, zorder=5)
        ax.annotate(str(year), (doy(b["peak_day"]), b["peak_7d"]), xytext=(10, 0),
                    textcoords="offset points", color=colour, fontsize=9,
                    fontweight="bold", va="center",
                    bbox=dict(facecolor="white", edgecolor="none", pad=1.5))

    ax.set_ylabel("leisure vessels that moved\n(7-day mean)", color=MUTED, fontsize=9)
    ax.set_title("The season, year by year — and where it starts and ends",
                 color=INK, fontsize=12, loc="left")
    tidy(ax)

    # The bounds strip: 25 % of the peak (pale) with the 50 % core inside it.
    for i, year in enumerate(YEARS):
        b = bounds[year]
        y = len(YEARS) - 1 - i
        colour = YEAR_COLOUR[year]
        ax_b.barh(y, doy(b["e25"]) - doy(b["s25"]), left=doy(b["s25"]), height=0.55,
                  color=colour, alpha=0.28, linewidth=0)
        ax_b.barh(y, doy(b["e50"]) - doy(b["s50"]), left=doy(b["s50"]), height=0.55,
                  color=colour, linewidth=0)
        ax_b.annotate(f"{b['len_25']} d / {b['len_50']} d", (366, y), xytext=(6, 0),
                      textcoords="offset points", color=MUTED, fontsize=8,
                      va="center", annotation_clip=False)
        if b["censored"]:
            ax_b.text(doy(b["e25"]) + 3, y, "censored", color=MUTED, fontsize=7,
                      va="center", style="italic")
    ax_b.set_yticks(range(len(YEARS)))
    ax_b.set_yticklabels([str(y) for y in reversed(YEARS)], fontsize=8)
    for tick, year in zip(ax_b.get_yticklabels(), reversed(YEARS)):
        tick.set_color(YEAR_COLOUR[year])      # this strip is the colour key
        tick.set_fontweight("bold")
    ax_b.set_ylim(-0.7, len(YEARS) - 0.3)
    ax_b.set_xlabel("day of year (dot = the peak of the 7-day mean)", color=MUTED, fontsize=8)
    ax_b.set_title("pale = above 25 % of that year's peak · solid = above 50 %",
                   color=MUTED, fontsize=8.5, loc="left")
    ax_b.annotate("length, 25 % / 50 %", (366, len(YEARS) - 0.45), xytext=(6, 0),
                  textcoords="offset points", color=MUTED, fontsize=8,
                  va="center", annotation_clip=False)
    tidy(ax_b)
    ax_b.grid(axis="y", linewidth=0)
    for a in (ax, ax_b):
        a.set_xticks(MONTH_DOY)
        a.set_xlim(1, 366)
    ax_b.set_xticklabels(MONTH_TICK)

    # subplots_adjust, not tight_layout: the right-hand annotations live outside
    # the axes and tight_layout cannot see them.
    fig.subplots_adjust(left=0.10, right=0.88, top=0.92, bottom=0.11, hspace=0.30)
    fig.savefig(IMG / "ch01-season.png", dpi=160, facecolor="white")


def regattas():
    """sql/22 grouped by (regatta, year), race days in order."""
    ev = defaultdict(list)
    for (name, year, place, race_day, dow, race_vessels, base_days, base_mean,
         base_min, base_max, ratio, event_mean) in rows("22_regatta_spikes.sql"):
        # 4 offsets (-14, -7, +7, +14); sql/22 drops the ones outside the
        # archive and the ones inside the event's own range, and a 9-day
        # Kieler Woche loses one of the four on each of its four edge days.
        assert 1 <= int(base_days) <= 4, f"{name} {year} {race_day}: base_days {base_days}"
        assert ratio != "\\N", f"{name} {year} {race_day}: empty baseline"
        assert float(ratio) > 0, f"{name} {year} {race_day}: ratio {ratio}"
        ev[(name, int(year))].append(
            dict(day=race_day, vessels=int(race_vessels), base=float(base_mean),
                 ratio=float(ratio), event_mean=float(event_mean)))
    for key, days in ev.items():
        days.sort(key=lambda d: d["day"])
    assert set(n for n, _ in ev) == set(REGATTA_ORDER), \
        f"regatta names changed: {sorted({n for n, _ in ev})}"
    return ev


def chart_regatta(ev):
    """Chart 2 -- race-day vessels against the same-weekday baseline, per event."""
    fig, axes = plt.subplots(1, len(REGATTA_ORDER), figsize=(11, 3.9), sharey=True)
    years = sorted({y for _, y in ev})
    for ax, name in zip(axes, REGATTA_ORDER):
        quiet = name == "Kieler Woche"          # German event: kept, drawn secondary
        colour = MUTED if quiet else BLUE
        ax.axhline(1.0, color=MUTED, linewidth=1, zorder=2)   # the baseline itself
        for year in years:
            days = ev.get((name, year))
            if not days:
                continue
            x = years.index(year)
            for i, d in enumerate(days):
                last = i == len(days) - 1 and len(days) > 1
                # A 2px surface ring keeps overlapping race days apart; the
                # hollow marker is the event's last day (a second channel, not
                # colour), so it is ringed the other way round.
                ax.plot([x], [d["ratio"]], "o", markersize=8, zorder=3,
                        markerfacecolor="white" if last else colour,
                        markeredgecolor=colour if last else "white",
                        markeredgewidth=1.8, alpha=0.65 if quiet else 1.0)
            if len(days) > 1:                    # the event's own spread
                ax.plot([x, x], [min(d["ratio"] for d in days),
                                 max(d["ratio"] for d in days)],
                        color=colour, linewidth=1, alpha=0.35, zorder=1)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels([str(y)[2:] for y in years], fontsize=8)
        ax.set_xlim(-0.6, len(years) - 0.4)
        ax.set_title(name, color=MUTED if quiet else INK, fontsize=9.5, loc="left")
        tidy(ax)
    axes[0].set_ylabel("race-day vessels ÷ baseline mean", color=MUTED, fontsize=9)
    # shared y across the five panels: the tallest ratio in the file plus 6 %,
    # so the top marker keeps its ring instead of being clipped by the spine.
    axes[0].set_ylim(0, 1.06 * max(d["ratio"] for days in ev.values() for d in days))
    fig.suptitle("Does a regatta show up in the start area? "
                 "(hollow = the event's last day; the rule = the baseline, 1.0)",
                 color=INK, fontsize=11, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(IMG / "ch01-regatta.png", dpi=160, facecolor="white")


def radius():
    """sql/23 keyed by year. 2022/2023 are kept here and dropped by the chart."""
    out = {}
    for (year, days, vessel_days, share_idle, moved_days, p25, p50, p75, p90, p99,
         lt5, ge30, in_cell, near) in rows("23_radius.sql"):
        q = [float(p25), float(p50), float(p75), float(p90), float(p99)]
        assert q == sorted(q), f"{year}: quantiles not monotone"
        assert 0 <= float(share_idle) <= 1, f"{year}: share_idle out of range"
        assert int(moved_days) <= int(vessel_days), f"{year}: moved > vessel-days"
        # ring 0 is a subset of ring 1 by construction; if this ever flips, the
        # two marina CTEs in sql/23 have been crossed.
        assert float(in_cell) <= float(near), f"{year}: ring 0 {in_cell} > ring 1 {near}"
        out[int(year)] = dict(days=int(days), vessel_days=int(vessel_days),
                              share_idle=float(share_idle), moved_days=int(moved_days),
                              q=q, lt5=float(lt5), ge30=float(ge30),
                              in_cell=float(in_cell), near=float(near))
    return out


def chart_radius(rad):
    """Chart 3 -- how far a moved day goes, and how many days are not a trip."""
    # x is the calendar year itself, not a category slot: the loaded years are
    # 2015/2018/2021 then 2024/2025/2026, and equal spacing would draw a
    # three-year gap as one step.
    years = [y for y in YEARS if y in rad]
    x = years
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 3.8),
                                  gridspec_kw={"width_ratios": [1.35, 1]})

    labels = ["p25", "p50", "p75", "p90"]
    ends = []
    for i, lab in enumerate(labels):
        ys = [rad[y]["q"][i] for y in years]
        colour = RAMP[i + 1]
        ax.plot(x, ys, color=colour, linewidth=2, marker="o", markersize=6,
                markeredgecolor="white", markeredgewidth=1.5)
        ends.append((ys[-1], lab, colour))
    label_ends(ax, years[-1], ends, gap_frac=0.06)
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], fontsize=8)
    ax.set_xlim(years[0] - 0.4, years[-1] + 0.2)
    ax.set_ylim(0, None)
    ax.set_ylabel("nautical miles in a day", color=MUTED, fontsize=9)
    p99 = [rad[y]["q"][4] for y in years]
    ax.set_title("How far a boat gets on a day it moved "
                 f"(p99 off-scale, {min(p99):.0f}–{max(p99):.0f} nm)",
                 color=INK, fontsize=10, loc="left")
    tidy(ax)

    for key, colour, lab in (("share_idle", BLUE, "never left the berth"),
                             ("ge30", ORANGE, "30 nm or more")):
        ys = [100 * rad[y][key] for y in years]
        ax2.plot(x, ys, color=colour, linewidth=2, marker="o", markersize=6,
                 markeredgecolor="white", markeredgewidth=1.5, label=lab)
    ax2.set_xticks(years)
    ax2.set_xticklabels([str(y) for y in years], fontsize=8)
    ax2.set_xlim(years[0] - 0.4, years[-1] + 0.4)
    # 20 % headroom over the tallest of the two series — the legend sits in the
    # lower left, so the room is needed at the top.
    ax2.set_ylim(0, 1.2 * max(100 * max(rad[y][k] for y in years)
                              for k in ("share_idle", "ge30")))
    ax2.set_ylabel("% of vessel-days / of moved days", color=MUTED, fontsize=9)
    ax2.set_title("Idle days (of all) and long days (of moved)", color=INK,
                  fontsize=10, loc="left")
    ax2.legend(frameon=False, fontsize=8, labelcolor=MUTED, loc="lower left")
    tidy(ax2)

    fig.tight_layout(rect=(0, 0, 0.97, 1))
    fig.savefig(IMG / "ch01-radius.png", dpi=160, facecolor="white")


def weekend_and_night():
    """sql/21 and sql/24, printed only -- both are tables in the note, not charts."""
    week, late = {}, {}
    for metric, year, season, bucket, n, value, ratio in rows("21_weekend_effect.sql"):
        (week if metric == "weekend_effect" else late)[(int(year), season, bucket)] = \
            (int(n), float(value), float(ratio))
    for (year, season, bucket), (n, value, ratio) in sorted(week.items()):
        assert n > 0 and value >= 0, f"{year} {season} {bucket}: empty bucket"
        # A weekend is busier than a weekday but not by an order of magnitude:
        # the file's own spread is 1.09-1.88. The bounds are wide enough to
        # survive a new year and tight enough that an inverted or mis-joined
        # ratio (a weekday/weekend swap lands near 0.5-0.9) fails here.
        assert 0.8 < ratio < 3, f"{year} {season} {bucket}: weekend ratio {ratio}"
    for (year, season, bucket), (n, value, ratio) in sorted(late.items()):
        # Share of moved vessel-days whose first position lands after 15:00
        # LOCAL. The lower bound on Mon-Thu is 0.08 on purpose: the six loaded
        # years give 0.093-0.108, and reading first_ts as UTC instead of
        # Europe/Copenhagen moves the cut two hours later in summer and roughly
        # halves the share (~0.06), which this bound catches and a 0.03 one
        # would not. Fri/Sat/Sun run 0.053-0.147 and only need the loose bound.
        lo = 0.08 if bucket == "Mon-Thu" else 0.03
        assert lo < value < 0.5, f"{year} {bucket}: late-start share {value}"

    night = {}
    for year, season, fleet, local_days, mm, nm, share in rows("24_night.sql"):
        assert 0 <= float(share) <= 1, f"{year} {season} {fleet}: night share out of range"
        assert int(nm) <= int(mm), f"{year} {season} {fleet}: night > total"
        night[(int(year), season, fleet)] = (int(local_days), float(share))
    return week, late, night


def numbers(daily, bounds, ev, rad, week, late, night):
    """Every figure notes/ch01-findings.md quotes. Printed, never hand-typed."""
    print("\n== season bounds (sql/20) ==")
    for y in sorted(bounds):
        b = bounds[y]
        print(f"{y}  days {b['days']:3d}  peak {b['peak_day']} at {b['peak_7d']:7.1f}"
              f"  25% {b['s25']}..{b['e25']} = {b['len_25']:3d} d"
              f"  50% {b['s50']}..{b['e50']} = {b['len_50']:3d} d"
              f"  {b['censored'] or '-'}")

    print("\n== weekend / weekday (sql/21) ==")
    for (y, season, bucket), (n, value, ratio) in sorted(week.items()):
        if bucket == "weekend":
            print(f"{y} {season:8s} weekend {value:7.1f} / weekday "
                  f"{week[(y, season, 'weekday')][1]:7.1f} = {ratio:.3f}x  (n {n})")

    print("\n== late start, first position after 15:00 local, May-Sep (sql/21) ==")
    for y in sorted({y for y, _, _ in late}):
        cells = " ".join(f"{b} {100*late[(y, 'May-Sep', b)][1]:5.2f}% "
                         f"({late[(y, 'May-Sep', b)][2]:.2f}x)"
                         for b in ("Mon-Thu", "Fri", "Sat", "Sun"))
        print(f"{y}  {cells}")

    print("\n== regattas (sql/22) ==")
    for name in REGATTA_ORDER:
        for year in sorted(y for n, y in ev if n == name):
            days = ev[(name, year)]
            print(f"{name:18s} {year}  mean ratio {days[0]['event_mean']:5.3f}  "
                  + " ".join(f"{d['day'][5:]}:{d['ratio']:5.2f}" for d in days))

    print("\n== radius (sql/23) ==")
    for y in sorted(rad):
        r = rad[y]
        print(f"{y}  days {r['days']:3d}  vessel-days {r['vessel_days']:7d}"
              f"  idle {100*r['share_idle']:5.2f}%  p50 {r['q'][1]:6.2f} nm"
              f"  >=30 nm {100*r['ge30']:5.2f}%  <5 nm {100*r['lt5']:5.2f}%"
              f"  home in a marina cell {100*r['in_cell']:5.2f}%"
              f"  (ring 1 {100*r['near']:5.2f}%)")

    print("\n== night share, 22:00-05:00 local (sql/24) ==")
    for (y, season, fleet), (days, share) in sorted(night.items()):
        print(f"{y} {season:8s} {fleet:16s} {100*share:5.2f}%  ({days} local days)")

    print("\n== the last day of a multi-day Danish regatta (finding 6) ==")
    multi = {k: d for k, d in ev.items() if len(d) > 1 and k[0] != "Kieler Woche"}
    firsts = [d[0]["ratio"] for d in multi.values()]
    lasts = [d[-1]["ratio"] for d in multi.values()]
    is_min = sum(d[-1]["ratio"] == min(x["ratio"] for x in d) for d in multi.values())
    at_or_below = sum(d[-1]["ratio"] <= 1.0 for d in multi.values())
    print(f"{len(multi)} multi-day Danish event-years: mean first-day ratio "
          f"{sum(firsts)/len(firsts):.3f}, mean last-day ratio {sum(lasts)/len(lasts):.3f}; "
          f"last day is the event minimum in {is_min}, at or below 1.0 in {at_or_below} "
          + "(" + ", ".join(f"{n} {y} {d[-1]['ratio']:.2f}"
                            for (n, y), d in sorted(multi.items())
                            if d[-1]["ratio"] <= 1.0) + ")")
    kiel = [d for (n, y), days in ev.items() if n == "Kieler Woche" for d in days]
    print(f"Kieler Woche: {sum(d['ratio'] < 1 for d in kiel)} of {len(kiel)} race days "
          f"below baseline")

    print("\n== peak day drift (sql/20) and season length spread ==")
    l25 = [bounds[y]["len_25"] for y in bounds if not bounds[y]["censored"]]
    l50 = [bounds[y]["len_50"] for y in bounds if not bounds[y]["censored"]]
    print(f"uncensored years only: len_25 {min(l25)}-{max(l25)} d, "
          f"len_50 {min(l50)}-{max(l50)} d")


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    daily, bounds = season_daily(), season_bounds()
    assert set(YEARS) <= set(bounds), f"sql/20 lost a year: {sorted(bounds)}"
    ev, rad = regattas(), radius()
    week, late, night = weekend_and_night()
    # Cross-check: sql/20's peak_7d is a ClickHouse window function, the curves
    # in chart 1 are the same mean recomputed in Python from sql/10. If the two
    # ever disagree the dot is not on the line it is drawn on. 0.06 covers
    # sql/20's round(, 1) and nothing else.
    for year, b in bounds.items():
        m7 = dict((d, m) for d, _, m in daily[year])[doy(b["peak_day"])]
        assert abs(m7 - b["peak_7d"]) < 0.06, \
            f"{year}: python 7-day mean {m7:.2f} vs sql/20 peak_7d {b['peak_7d']}"
    chart_season(daily, bounds)
    chart_regatta(ev)
    chart_radius(rad)
    numbers(daily, bounds, ev, rad, week, late, night)
    print(f"\nwrote {IMG}/ch01-season.png, ch01-regatta.png, ch01-radius.png",
          file=sys.stderr)
