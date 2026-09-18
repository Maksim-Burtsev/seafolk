#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""The four clocks, with a hand sweeping the day.

    uv run scripts/render_clocks.py

Writes site/media/day-clocks.mp4 — 1280x720 H.264, sixteen seconds, one turn of
the hour hand through a Danish summer day. It is the moving version of chart P1
on site/pulse.html and it is linked from that page's footer.

WHAT IT READS. site/pulse.html's own <script type="application/json" id="data">
block, which scripts/build_site_data.py wrote from the store. Not the store: the
`clickhouse local` lock is exclusive and other sessions hold it, and a second
query would be a second chance for the film and the page to disagree. Run
scripts/build_site_data.sh first; this script reads whatever that left behind.

There is nothing private in here. The four curves are each fleet's share of its
own day, pooled over the whole country and six summers — the same numbers the
page prints in its table.

The geometry is site/day-clocks.html's, the same one site/js/pulse.js and
notes/plot_ch02.py draw: midnight at the top, hours clockwise, an inner hole,
and the radius linear in the hour's share of that fleet's day up to PEAK at the
rim. matplotlib gets the hole from set_rorigin.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "pulse.html"
OUT = ROOT / "site" / "media" / "day-clocks.mp4"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

W, H, DPI = 1280, 720, 100
FPS, STEPS = 24, 16          # 16 sub-steps an hour: 384 frames, 16 seconds
PEAK = 13.0                  # the share that reaches the rim
R_IN, R_MAX = 20, 92         # site/day-clocks.html's hole, as a fraction
R_ORIGIN = -PEAK * R_IN / (R_MAX - R_IN)
FLAT = 100 / 24              # 4.17 % — a day with no rhythm

# site/css/site.css, light theme. The film is light-theme only.
SURFACE, HAIRLINE = "#f7f9f9", "#cfdadc"
INK, LABEL, ACCENT, ACCENT_TX, REF = "#0f1a1d", "#55676c", "#eb6834", "#b8441a", "#a8b8bc"

# key in the page's data -> the reader's word, and whether it is the subject.
FLEETS = [("sailing", "Sailing boats", True), ("ferries", "Ferries", False),
          ("cargo", "Cargo ships", False), ("fishing", "Fishing boats", False)]
MARKS = [(0, "midnight"), (6, "6 am"), (12, "noon"), (18, "6 pm")]

TITLE = "Four fleets, one sea, four different clocks"
DECK = ("Where each fleet's movement falls across the day — Danish waters, "
        "six summers, local time")
FOOT = ("The dashed circle is a day with no rhythm: 4.2 % of the movement in "
        "every hour.\nEach fleet is measured against its own day — compare the "
        "shapes, never the sizes.")


def hour_word(hour: int) -> str:
    if hour == 0:
        return "midnight"
    if hour == 12:
        return "noon"
    return f"{hour % 12} {'am' if hour < 12 else 'pm'}"


def load() -> dict[str, list[float]]:
    block = re.search(r'<script type="application/json" id="data">(.*?)</script>',
                      PAGE.read_text(), re.S)
    if not block:
        sys.exit(f"{PAGE}: no data block — run scripts/build_site_data.sh first")
    clocks = json.loads(block.group(1)).get("clocks")
    if not clocks:
        sys.exit(f"{PAGE}: the data block holds no clocks — has the page been built?")
    for key, _, _ in FLEETS:
        curve = clocks[key]
        assert len(curve) == 24 and abs(sum(curve) - 100) < 0.5, \
            f"{key}: {len(curve)} hours summing to {sum(curve)}, not 24 and 100"
        assert max(curve) < PEAK, f"{key}: {max(curve)} % would run off the rim"
    return clocks


def build(clocks):
    """The still parts of the picture, plus the handles the frames move."""
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=SURFACE)
    fx = lambda px: px / W            # noqa: E731  — pixels, as fig fractions
    fy = lambda px: 1 - px / H        # noqa: E731  — measured from the top

    fig.text(fx(48), fy(62), TITLE, color=INK, fontsize=30, fontweight="bold",
             va="baseline")
    fig.text(fx(48), fy(96), DECK, color=LABEL, fontsize=14.5, va="baseline")
    fig.add_artist(plt.Line2D([fx(48), fx(1232)], [fy(120)] * 2,
                              color=HAIRLINE, lw=1))

    bars, hands = [], []
    width = math.radians(15 - 1.8)                     # the page's gapped wedge
    ring = [math.radians(a) for a in range(0, 361, 3)]
    theta = [math.radians(15 * h) for h in range(24)]
    for i, (key, name, subject) in enumerate(FLEETS):
        curve = clocks[key]
        cx = 1280 / 4 * (i + 0.5)
        peak = max(range(24), key=lambda h: curve[h])
        fig.text(fx(cx), fy(160), name, color=ACCENT_TX if subject else INK,
                 fontsize=17, fontweight="bold" if subject else "normal",
                 ha="center", va="baseline")
        fig.text(fx(cx), fy(182), f"busiest at {hour_word(peak)} · "
                                  f"{curve[peak]:.1f} % of its day",
                 color=LABEL, fontsize=11, ha="center", va="baseline")

        # a polar axes fills its box with the r = PEAK circle and hangs the
        # hour words OUTSIDE it, so the box has to start below the sub-line or
        # "midnight" lands on top of it.
        ax = fig.add_axes([fx(cx - 108), fy(216 + 216), fx(216), 216 / H],
                          projection="polar")
        ax.set_facecolor(SURFACE)
        ax.bar(theta, curve, width=width, linewidth=0,
               color=ACCENT if subject else "#7d8f94", zorder=2)
        bars.append(ax.containers[0])
        ax.plot(ring, [FLAT] * len(ring), color=REF, lw=0.9,
                linestyle=(0, (2, 3)), zorder=1)
        # the hand stops just inside the rim: at PEAK it runs over the "6 am"
        # and "6 pm" words, which sit outside the circle.
        hands.append(ax.plot([0, 0], [0, PEAK * 0.85], color=INK, lw=1.8,
                             solid_capstyle="round", zorder=4)[0])
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rorigin(R_ORIGIN)
        ax.set_ylim(0, PEAK)
        ax.set_xticks([math.radians(15 * h) for h, _ in MARKS])
        ax.set_xticklabels([t for _, t in MARKS], color=LABEL, fontsize=9)
        ax.set_yticks([])
        ax.grid(False)
        ax.spines["polar"].set_visible(False)
        ax.tick_params(pad=1)

    clock = fig.text(fx(640), fy(510), "", color=INK, fontsize=38,
                     family="monospace", ha="center", va="baseline")
    fig.text(fx(48), fy(576), FOOT, color=LABEL, fontsize=12, va="top",
             linespacing=1.7)
    fig.text(fx(48), fy(668), "Danish Maritime Authority AIS archive · seafolk",
             color=LABEL, fontsize=10.5, va="baseline")
    return fig, bars, hands, clock


def main() -> None:
    clocks = load()
    fig, bars, hands, clock = build(clocks)
    frames = 24 * STEPS
    OUT.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-", "-an",
         "-c:v", "libx264", "-preset", "slow", "-crf", "24",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)],
        stdin=subprocess.PIPE)

    lit = -1
    for frame in range(frames):
        t = frame / STEPS                       # the hour, as a float
        hour = int(t)
        angle = math.radians(15 * t)
        for hand in hands:
            hand.set_xdata([angle, angle])
        if hour != lit:
            for (key, _, subject), container in zip(FLEETS, bars):
                base = ACCENT if subject else "#7d8f94"
                for h, patch in enumerate(container):
                    patch.set_facecolor(INK if h == hour else base)
            clock.set_text(f"{hour:02d}:00")
            lit = hour
        fig.canvas.draw()
        proc.stdin.write(fig.canvas.buffer_rgba())

    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed")
    mb = OUT.stat().st_size / 1e6
    print(f"  {OUT.relative_to(ROOT)}  {mb:.2f} MB, {frames} frames at {FPS} fps "
          f"= {frames / FPS:.0f} s")
    if mb > 4:
        sys.exit(f"{OUT.name} is {mb:.1f} MB, over the 4 MB budget for a page asset")


if __name__ == "__main__":
    main()
