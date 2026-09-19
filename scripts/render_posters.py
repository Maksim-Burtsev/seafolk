#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""Two A3 posters, portrait, 297 x 420 mm.

    uv run scripts/render_posters.py

Writes into site/posters/:

    season-hills.pdf  .svg  .png     chart I1 from site/index.html
    four-clocks.pdf   .svg  .png     chart P1 from site/pulse.html

PDF and SVG are vector and are the files to print; the PNG is a 1600-px-wide
preview so the poster can be looked at inside the repo.

WHAT IT READS. The built pages' own <script type="application/json" id="data">
blocks, exactly like scripts/render_clocks.py and for the same two reasons: the
`clickhouse local` lock is exclusive, and a second query would be a second
chance for the poster and the page to disagree. Run scripts/build_site_data.sh
first; this script reads whatever that left behind and dies loudly if the block
or a key it needs is missing.

PRIVACY. The season poster prints small-boat head counts. They are store-wide
daily counts, already floored by the build, and load() asserts every value it
draws counts at least five boats. The clocks are shares of each fleet's own
day — no count at all.

TYPOGRAPHY. The site sets Bodoni Moda for headlines, Karla for text and IBM
Plex Mono for labels; none of the three is installed on this machine (checked
with fc-list). The closest already on macOS: Bodoni 72 for the headlines,
Avenir Next for everything else. No new dependency, no font to download.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "posters"

W_MM, H_MM = 297.0, 420.0            # A3 portrait
MM = 1 / 25.4
PNG_W = 1600                         # the preview's width, in pixels

# site/css/site.css, light theme. A poster is printed on paper: light only.
GROUND, SURFACE, HAIRLINE = "#e9eeef", "#f7f9f9", "#cfdadc"
INK, LABEL, ACCENT = "#0f1a1d", "#55676c", "#eb6834"
ACCENT_TX, WORKING, REF, PALE = "#b8441a", "#7d8f94", "#a8b8bc", "#c6d2d5"

HEAD = ["Bodoni 72", "Didot", "Baskerville", "serif"]
TEXT = ["Avenir Next", "Helvetica Neue", "Avenir", "sans-serif"]
# Avenir Next's bold cut is a family of its own to fontconfig; naming it
# outright is what keeps matplotlib from falling back and warning.
BOLD = ["Avenir Next Demi Bold", "Helvetica Neue", "sans-serif"]

SOURCE = "Danish Maritime Authority AIS archive · github.com/Maksim-Burtsev/seafolk"
K_FLOOR = 5                          # CLAUDE.md: no published cell under five boats

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
# first day of the year of each month, on a common year.
FIRST = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]

FLEETS = [("sailing", "Sailing boats", True), ("ferries", "Ferries", False),
          ("cargo", "Cargo ships", False), ("fishing", "Fishing boats", False)]
MARKS = [(0, "midnight"), (6, "6 am"), (12, "noon"), (18, "6 pm")]
PEAK = 13.0                          # the share that reaches the rim
R_IN, R_MAX = 20, 92                 # site/js/pulse.js's hole, as a fraction
R_ORIGIN = -PEAK * R_IN / (R_MAX - R_IN)
FLAT = 100 / 24                      # 4.2 % — a day with no rhythm


# ------------------------------------------------------------------ data ----
def block(page: Path) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>',
                  page.read_text(), re.S)
    if not m:
        sys.exit(f"{page}: no data block — run scripts/build_site_data.sh first")
    return json.loads(m.group(1))


def load_season() -> dict[str, list[tuple[int, float]]]:
    page = ROOT / "site" / "index.html"
    season = block(page).get("season")
    if not season:
        sys.exit(f"{page}: the data block holds no season — has the page been built?")
    out = {y: [(int(d), float(v)) for d, v in pts] for y, pts in season.items()}
    if len(out) < 2:
        sys.exit(f"{page}: season has {len(out)} years, and the poster is about the years")
    low = min(v for pts in out.values() for _, v in pts)
    assert low >= K_FLOOR, f"season holds a cell of {low} boats, under the floor of {K_FLOOR}"
    return out


def load_clocks() -> dict[str, list[float]]:
    page = ROOT / "site" / "pulse.html"
    clocks = block(page).get("clocks")
    if not clocks:
        sys.exit(f"{page}: the data block holds no clocks — has the page been built?")
    for key, _, _ in FLEETS:
        if key not in clocks:
            sys.exit(f"{page}: clocks has no '{key}' — the poster needs all four fleets")
        curve = clocks[key]
        assert len(curve) == 24 and abs(sum(curve) - 100) < 0.5, \
            f"{key}: {len(curve)} hours summing to {sum(curve)}, not 24 and 100"
        assert max(curve) < PEAK, f"{key}: {max(curve)} % would run off the rim"
    return clocks


# ------------------------------------------------------------------ page ----
def fx(mm: float) -> float:
    return mm / W_MM


def fy(mm: float) -> float:
    """Millimetres down from the top edge, as a figure fraction."""
    return 1 - mm / H_MM


def sheet():
    fig = plt.figure(figsize=(W_MM * MM, H_MM * MM), facecolor=GROUND)
    fig.patches.append(Rectangle((0, 0), 1, 1, transform=fig.transFigure,
                                 facecolor=GROUND, zorder=-10))
    return fig


def head(fig, kicker: str, lines: list[str], standfirst: list[str]) -> None:
    """The top of both posters: kicker, headline, a short plain-English deck."""
    fig.text(fx(22), fy(26), kicker, color=ACCENT_TX, family=BOLD, fontsize=13,
             va="baseline")
    fig.add_artist(plt.Line2D([fx(22), fx(275)], [fy(32)] * 2, color=INK, lw=1.2))
    for i, line in enumerate(lines):
        fig.text(fx(22), fy(56 + 22 * i), line, color=INK, family=HEAD,
                 fontsize=60, va="baseline")
    top = 56 + 22 * (len(lines) - 1)
    for i, line in enumerate(standfirst):
        fig.text(fx(22), fy(top + 20 + 8.2 * i), line, color=LABEL, family=TEXT,
                 fontsize=16, va="baseline")


def foot(fig) -> None:
    fig.add_artist(plt.Line2D([fx(22), fx(275)], [fy(398)] * 2, color=HAIRLINE, lw=1))
    fig.text(fx(22), fy(406), SOURCE, color=LABEL, family=TEXT, fontsize=11.5,
             va="baseline")


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext, kw in (("pdf", {}), ("svg", {}),
                    ("png", {"dpi": PNG_W / (W_MM * MM)})):
        path = OUT / f"{name}.{ext}"
        fig.savefig(path, facecolor=GROUND, **kw)
        print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1e3:.0f} kB")
    plt.close(fig)


# --------------------------------------------------------- season hills ----
def runs(points):
    """Break a year over the stretches of calendar that were never loaded."""
    out = [[points[0]]]
    for prev, cur in zip(points, points[1:]):
        if cur[0] - prev[0] > 1:
            out.append([])
        out[-1].append(cur)
    return out


def season_poster(season) -> None:
    years = sorted(season)
    first, last = years[0], years[-1]
    top = max(v for pts in season.values() for _, v in pts)

    fig = sheet()
    head(fig, "SEAFOLK · A YEAR AT SEA",
         ["Every summer", "more small boats go out", "than the summer before"],
         ["Every small boat that moved in Danish waters, day by day, smoothed over a week.",
          "One line per year. The sea is empty from November until the end of March."])

    ax = fig.add_axes([fx(30), fy(356), fx(245), 208 / H_MM])
    ax.set_facecolor(SURFACE)
    ax.set_xlim(1, 366)
    ax.set_ylim(0, top * 1.16)
    for a, b in ((1, FIRST[3]), (FIRST[10], 366)):     # the empty half, shaded
        ax.axvspan(a, b, color=HAIRLINE, alpha=0.45, lw=0)
    ax.grid(axis="y", color=HAIRLINE, lw=0.8, zorder=0)
    ax.set_axisbelow(True)

    for year in years:
        strong = year in (first, last)
        colour = ACCENT if year == last else INK if year == first else PALE
        width = 3.2 if year == last else 2.2 if year == first else 1.0
        for run in runs(season[year]):
            ax.plot([d for d, _ in run], [v for _, v in run], color=colour,
                    lw=width, solid_capstyle="round", zorder=3 if strong else 2)

    # two quiet annotations: the first year's peak and the last one's.
    for year, dy, ha, dx in ((last, 16, "center", 0), (first, 12, "left", 6)):
        day, value = max(season[year], key=lambda p: p[1])
        colour = ACCENT_TX if year == last else INK
        ax.plot([day], [value], "o", ms=7, color=ACCENT if year == last else INK,
                zorder=4)
        ax.annotate(f"{year} · {value:,.0f} boats".replace(",", " "),
                    (day, value), textcoords="offset points", xytext=(dx, dy),
                    ha=ha, va="bottom", color=colour, family=BOLD, fontsize=15,
                    bbox=dict(facecolor=GROUND, edgecolor="none", pad=1.5))

    for year in years[1:-1]:                            # the pale years, named once
        day, value = max(season[year], key=lambda p: p[1])
        ax.annotate(year, (day, value), textcoords="offset points", xytext=(7, -2),
                    ha="left", va="center", color=WORKING, family=TEXT, fontsize=12,
                    bbox=dict(facecolor=GROUND, edgecolor="none", pad=1.2))

    ax.set_xticks(FIRST)
    ax.set_xticklabels([m[:3] if i % 2 else m for i, m in enumerate(MONTHS)])
    ax.tick_params(axis="x", colors=LABEL, labelsize=12, length=4, pad=5)
    ax.tick_params(axis="y", colors=LABEL, labelsize=12, length=0, pad=5)
    ax.yaxis.set_major_formatter(
        lambda t, _: f"{t:,.0f}".replace(",", " "))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(HAIRLINE)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_family(TEXT)

    fig.text(fx(30), fy(142), "boats out that day", color=LABEL, family=TEXT,
             fontsize=13, va="baseline")
    fig.text(fx(30), fy(376),
             "Winter is shaded. A line stops where the archive was never pulled "
             f"down: {first} to {last} is six loaded years, not twelve.",
             color=LABEL, family=TEXT, fontsize=13, va="baseline")
    foot(fig)
    save(fig, "season-hills")


# ----------------------------------------------------------- four clocks ----
def hour_word(hour: int) -> str:
    if hour == 0:
        return "midnight"
    if hour == 12:
        return "noon"
    return f"{hour % 12} {'am' if hour < 12 else 'pm'}"


def clocks_poster(clocks) -> None:
    fig = sheet()
    head(fig, "SEAFOLK · THE SEA BY THE HOUR",
         ["Sailing boats go out at noon.", "The rest of the sea",
          "runs all night"],
         ["Where each fleet's movement falls across the day — Danish waters, "
          "six summers, local time."])

    fig.text(fx(22), fy(126),
             "How to read a dial: midnight is at the top and the hours run "
             "clockwise; the bar reaches further out\nthe busier that hour is. "
             "The dashed circle is a day with no rhythm — 4.2 % of the movement "
             "in every hour.\nEach fleet is measured against its own day — "
             "compare the shapes, never the sizes.",
             color=LABEL, family=TEXT, fontsize=14, va="top", linespacing=1.55)

    width = math.radians(15 - 1.8)                      # the page's gapped wedge
    ring = [math.radians(a) for a in range(0, 361, 3)]
    theta = [math.radians(15 * h) for h in range(24)]
    size = 80                                           # the dial's box, in mm

    for i, (key, name, subject) in enumerate(FLEETS):
        curve = clocks[key]
        cx = 22 + 63 + 127 * (i % 2)
        cy = 186 + 118 * (i // 2)                        # the box's top edge
        peak = max(range(24), key=lambda h: curve[h])

        fig.text(fx(cx), fy(cy - 22), name,
                 color=ACCENT_TX if subject else INK,
                 family=BOLD if subject else TEXT, fontsize=20, ha="center",
                 va="baseline")
        fig.text(fx(cx), fy(cy - 13),
                 f"busiest at {hour_word(peak)} · {curve[peak]:.1f} % of its day",
                 color=LABEL, family=TEXT, fontsize=13, ha="center", va="baseline")

        ax = fig.add_axes([fx(cx - size / 2), fy(cy + size), fx(size), size / H_MM],
                          projection="polar")
        ax.set_facecolor(GROUND)
        ax.bar(theta, curve, width=width, linewidth=0,
               color=ACCENT if subject else WORKING, zorder=2)
        ax.plot(ring, [FLAT] * len(ring), color=REF, lw=1.1,
                linestyle=(0, (2, 3)), zorder=1)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rorigin(R_ORIGIN)
        ax.set_ylim(0, PEAK)
        ax.set_xticks([math.radians(15 * h) for h, _ in MARKS])
        ax.set_xticklabels([t for _, t in MARKS])
        ax.tick_params(colors=LABEL, labelsize=12, pad=4)
        for label in ax.get_xticklabels():
            label.set_family(TEXT)
        ax.set_yticks([])
        ax.grid(False)
        ax.spines["polar"].set_visible(False)

    foot(fig)
    save(fig, "four-clocks")


def main() -> None:
    season_poster(load_season())
    clocks_poster(load_clocks())


if __name__ == "__main__":
    main()
