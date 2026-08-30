#!/usr/bin/env python3
"""S3 phase-0 charts: three PNGs into notes/img/, and the numbers behind them.

    uv run --project notes notes/plot.py

Reads the queries in sql/ through scripts/ch.sh. There is no ClickHouse server
to connect to -- the store is `clickhouse local --path data/ch` (docs/DECISIONS)
-- so there is no client library either, and matplotlib is the one dependency.

These are validation plots for a human to eyeball, not published artefacts; the
essay's charts are D3 (S12). The palette is still the project's categorical one,
assigned by entity and fixed across all three charts.
"""
import datetime
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "notes" / "img"

# Colour follows the entity, never the rank: leisure is blue in every chart.
# Slots 1-4 of the categorical palette, validated on the adjacent pairlist
# (worst CVD dE 9.1, normal-vision 22.9). Cargo and fishing sit under 3:1
# against the surface, so every line is also labelled at its right end.
GROUPS = [
    ("leisure",   "Class B", "leisure",  "#2a78d6"),
    ("passenger", "Class A", "ferries",  "#eb6834"),
    ("cargo",     "Class A", "cargo",    "#1baf7a"),
    ("fishing",   "Class A", "fishing",  "#eda100"),
]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d8d7d2"
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAME = {"202501": "January 2025", "202506": "June 2025", "202507": "July 2025"}


def rows(sql_file):
    """Run a query file and return its rows as lists of strings (TSV)."""
    p = subprocess.run(
        [str(ROOT / "scripts" / "ch.sh"), str(ROOT / "sql" / sql_file)],
        capture_output=True, text=True,
    )
    if p.returncode:
        # check=True would report the exit status and swallow the reason. The
        # most likely reason has a known cause worth naming.
        sys.exit(f"{sql_file} failed (exit {p.returncode}):\n{p.stderr.strip()}\n"
                 "  'Cannot lock file data/ch/status' means a load is running:\n"
                 "  clickhouse local locks the store (docs/DECISIONS.md).")
    r = [line.split("\t") for line in p.stdout.splitlines() if line]
    assert r, f"{sql_file} returned no rows -- nothing to plot"
    return r


def label_ends(ax, x, items, gap_frac=0.05):
    """Direct labels at the right edge, nudged apart so two never overlap.

    Cargo and fishing sit under 3:1 contrast against white, so their lines are
    labelled rather than left to the legend alone. Call after plotting: the
    minimum gap is read off the finished y-axis.
    """
    items = sorted(items, key=lambda t: -t[0])
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * gap_frac
    ys = [t[0] for t in items]
    for i in range(1, len(ys)):
        ys[i] = min(ys[i], ys[i - 1] - gap)
    for (_, text, colour), y in zip(items, ys):
        ax.annotate(text, (x, y), xytext=(6, 0), textcoords="offset points",
                    color=colour, fontsize=8, va="center", annotation_clip=False)


def tidy(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0)


def season():
    """Chart 1 -- distinct leisure vessels per day, one panel per loaded month."""
    by_month = defaultdict(list)
    for day, mobile, present, active, active_7d in rows("10_season_daily.sql"):
        if mobile != "Class B":
            continue
        assert int(active) <= int(present), f"{day}: active > present"
        by_month[day[:7]].append((int(day[8:10]), int(present), int(active), float(active_7d),
                                  datetime.date.fromisoformat(day).weekday() >= 5))
    months = sorted(by_month)

    fig, axes = plt.subplots(
        1, len(months), figsize=(11, 3.6), sharey=True,
        gridspec_kw={"width_ratios": [len(by_month[m]) for m in months]},
    )
    axes = [axes] if len(months) == 1 else list(axes)
    for ax, m in zip(axes, months):
        d = sorted(by_month[m])
        x = [v[0] for v in d]
        for dd, _, _, _, weekend in d:               # weekends shaded: the question
            if weekend:                              # this chart exists to answer
                ax.axvspan(dd - 0.5, dd + 0.5, color=GRID, alpha=0.45, linewidth=0)
        ax.fill_between(x, [v[1] for v in d], color="#2a78d6", alpha=0.13, linewidth=0)
        ax.plot(x, [v[2] for v in d], color="#2a78d6", linewidth=1, alpha=0.55)
        ax.plot(x, [v[3] for v in d], color="#2a78d6", linewidth=2.5)
        ax.set_xticks([dd for dd in x if dd % 5 == 0 or dd == 1])
        ax.set_xlim(min(x) - 0.5, max(x) + 0.5)
        ax.set_title(MONTH_NAME.get(m.replace("-", ""), m), color=INK, fontsize=10, loc="left")
        ax.set_xlabel("day of month (weekends shaded)", color=MUTED, fontsize=8)
        tidy(ax)
    axes[0].set_ylabel("distinct leisure vessels", color=MUTED, fontsize=9)
    # Direct labels instead of a legend box: three views of one series.
    last = sorted(by_month[months[-1]])[-1]
    label_ends(axes[-1], last[0],
               [(last[1], "present", "#7fb0e6"), (last[3], "moved, 7-day mean", "#2a78d6")],
               gap_frac=0.09)
    fig.suptitle("Leisure vessels in Danish waters, by day", color=INK, fontsize=12, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 0.93, 0.95))
    fig.savefig(IMG / "s3-season.png", dpi=160, facecolor="white")
    return by_month


def week():
    """Chart 2 -- share of a typical week's movement, by weekday and group."""
    data = defaultdict(dict)          # (month, group) -> {dow: share}
    total = defaultdict(float)
    for month, grp, mobile, dow, days, mean_moving, share in rows("11_week_profile.sql"):
        data[(month, grp, mobile)][int(dow)] = float(share)
        total[(month, grp, mobile)] += float(share)
    for k, s in total.items():
        assert abs(s - 1.0) < 0.005, f"{k}: weekday shares sum to {s}, not 1"

    months = sorted({m for m, _, _ in data})
    fig, axes = plt.subplots(1, len(months), figsize=(11, 3.8), sharey=True)
    axes = [axes] if len(months) == 1 else list(axes)
    width = 0.8 / len(GROUPS)
    for ax, m in zip(axes, months):
        for i, (grp, mobile, label, colour) in enumerate(GROUPS):
            series = data.get((m, grp, mobile))
            if not series:
                continue
            xs = [d - 1 + (i - (len(GROUPS) - 1) / 2) * width for d in range(1, 8)]
            ax.bar(xs, [100 * series.get(d, 0) for d in range(1, 8)], width=width * 0.80,
                   color=colour, label=label, linewidth=0)
        ax.axhline(100 / 7, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
        ax.annotate("a flat week", (6.55, 100 / 7), color=MUTED, fontsize=7,
                    xytext=(0, 3), textcoords="offset points", ha="right")
        ax.set_xticks(range(7))
        ax.set_xticklabels(DOW)
        ax.set_title(MONTH_NAME.get(m, m), color=INK, fontsize=10, loc="left")
        tidy(ax)
    axes[0].set_ylabel("% of the week's movement", color=MUTED, fontsize=9)
    fig.legend(*axes[0].get_legend_handles_labels(), frameon=False, fontsize=8,
               labelcolor=MUTED, ncol=4, loc="upper right", bbox_to_anchor=(0.99, 1.0))
    fig.suptitle("Which day of the week does each fleet move?", color=INK, fontsize=12,
                 x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(IMG / "s3-week.png", dpi=160, facecolor="white")
    return data


def day():
    """Chart 3 -- the shape of a day: summer weekday vs summer Saturday."""
    data = defaultdict(dict)          # (month, daytype, group) -> {hour: share}
    total = defaultdict(float)
    for month, grp, mobile, daytype, hour, moving, share in rows("12_day_profile.sql"):
        data[(month, daytype, grp, mobile)][int(hour)] = float(share)
        total[(month, daytype, grp, mobile)] += float(share)
    for k, s in total.items():
        assert abs(s - 1.0) < 0.005, f"{k}: hourly shares sum to {s}, not 1"

    month = "202507" if any(m == "202507" for m, _, _, _ in data) else sorted(data)[0][0]
    panels = [("weekday", "Weekday (Mon-Fri)"), ("sat", "Saturday")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, (daytype, title) in zip(axes, panels):
        ends = []
        for grp, mobile, label, colour in GROUPS:
            series = data.get((month, daytype, grp, mobile))
            if not series:
                continue
            ys = [100 * series.get(h, 0) for h in range(24)]
            ax.plot(range(24), ys, color=colour, linewidth=2, label=label)
            ends.append((ys[23], label, colour))
        label_ends(ax, 23, ends)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlim(0, 23)
        ax.set_xlabel("hour of day, Europe/Copenhagen", color=MUTED, fontsize=8)
        ax.set_title(title, color=INK, fontsize=10, loc="left")
        tidy(ax)
    axes[0].set_ylabel("% of that day's movement", color=MUTED, fontsize=9)
    fig.legend(*axes[0].get_legend_handles_labels(), frameon=False, fontsize=8,
               labelcolor=MUTED, ncol=4, loc="upper right", bbox_to_anchor=(0.99, 1.0))
    fig.suptitle(f"The shape of a day, {MONTH_NAME.get(month, month)}", color=INK,
                 fontsize=12, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 0.93, 0.94))
    fig.savefig(IMG / "s3-day.png", dpi=160, facecolor="white")
    return data


def numbers(season_data, week_data, day_data):
    """The figures notes/s3-phase0.md quotes. Printed, never hand-typed."""
    print("\n== season ==")
    for m in sorted(season_data):
        d = season_data[m]
        peak = max(d, key=lambda v: v[2])
        print(f"{m}  days {len(d):2d}  present max {max(v[1] for v in d):5d}"
              f"  moved max {peak[2]:5d} (on the {peak[0]:02d})"
              f"  moved mean {sum(v[2] for v in d)/len(d):7.1f}"
              f"  moved min {min(v[2] for v in d):5d}")
    jul = season_data.get("2025-07")
    jan = season_data.get("2025-01")
    if jul and jan:
        rj = sum(v[2] for v in jul) / len(jul)
        ra = sum(v[2] for v in jan) / len(jan)
        print(f"summer/winter, mean vessels that moved: {rj:.1f} / {ra:.1f} = {rj/ra:.1f}x")

    print("\n== week (share of the week's movement, %) ==")
    for (m, grp, mobile), series in sorted(week_data.items()):
        wk = sum(series.get(d, 0) for d in range(1, 6)) / 5
        we = sum(series.get(d, 0) for d in (6, 7)) / 2
        print(f"{m} {grp:9s} {mobile}  " + " ".join(f"{100*series.get(d,0):5.1f}" for d in range(1, 8))
              + (f"   weekend/weekday {we/wk:.2f}x" if wk else ""))

    print("\n== day (peak local hour, and 22:00-05:00 share) ==")
    for (m, daytype, grp, mobile), series in sorted(day_data.items()):
        peak = max(series, key=series.get)
        night = sum(series.get(h, 0) for h in list(range(22, 24)) + list(range(0, 5)))
        print(f"{m} {daytype:7s} {grp:9s} {mobile}  peak {peak:02d}:00"
              f"  ({100*series[peak]:.1f}% of the day)   night 22-05 {100*night:.1f}%")


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    s, w, d = season(), week(), day()
    numbers(s, w, d)
    print(f"\nwrote {IMG}/s3-season.png, s3-week.png, s3-day.png", file=sys.stderr)
