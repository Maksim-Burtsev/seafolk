#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""The sea empties — an hour-by-hour storm on the nautical chart.

    uv run --project notes scripts/charts_storms.py   # first: the chart it plays on
    uv run scripts/render_storm.py                    # every storm below
    uv run scripts/render_storm.py pia                # one of them
    uv run scripts/render_storm.py --no-video         # data files only, no ffmpeg

Writes, per storm:
    site/media/storm-<key>.js    the hours, for site/js/storm-player.js
    site/media/storm-<key>.mp4   1280x720 H.264, the same picture as a clip to post
    site/media/storm-<key>.webm  the same clip at 640 px

THE CHART.  Both the page and the clip play on `storms-sea`, the bare chart
sheet scripts/charts_storms.py draws with scripts/chartkit.py. Its box and
image come from site/media/charts/storms.js, so the fleets and the sea can
never disagree about where Denmark is.

WHAT IT READS.  Only `dist/dataset/class_a_hourly_<year>.parquet` — the public
fleets (cargo, ferries, fishing), already privacy-tested by
`scripts/test_export.py`.  It never touches `data/ch`.  There is no small-boat
data in this piece at all, so nothing here can show a private vessel.

WHAT A MARK MEANS.  One mark is one published patch of sea (H3 resolution 7,
about two kilometres across) in which that fleet sent at least one message
while under way during that hour. So the counters count PLACES, not boats: the
dataset has no distinct-vessel count for the moving subset, and summing
`vessels` over cells would count one trawler five times as it crosses five of
them.

The magnitudes are only compared inside one storm's own week (dataset card,
bias 2: message counts are inflated from 2023 on).

THE H3 PIN.  `--h3togeo_lon_lat_result_order=0` and
`--geotoh3_argument_order=lat_lon`, and `check_axis_order()` refuses to render
if the Drogden channel is not where it should be, on the query and on the
written file (S4-redo: a silent swap mirrored Denmark into the Arabian Sea).
The pixel step after the file is chart.project in site/js/chart.js, held to
known places by scripts/test_charts.py.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "site" / "media"
MANIFEST = MEDIA / "charts" / "storms.js"
SHEET = "storms-sea"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
W, H, DPI = 1280, 720, 100

# site/css/site.css and scripts/chartkit.py — the chart palette.
PAPER, SURFACE, INK, LABEL = "#f4eddb", "#f8f3e6", "#1d2a37", "#5a5446"
FISHING, CARGO, FERRY, REF, HAIRLINE = "#1e6b5a", "#a3246a", "#b32a1f", "#b3a98c", "#d8ccaa"
STORM_INK = "#2b3d4d"            # the sea darkening while it blows

FLEETS = ("cargo", "passenger", "fishing")      # draw order: fishing on top

# A boat seen from above, as a chart plotter draws a ship it hears: the same
# shape as BOAT in site/js/storm-player.js. Here they all head east.
BOAT = MPath([(.6, 0), (.12, -.26), (-.5, -.24), (-.5, .24), (.12, .26), (0, 0)],
             [MPath.MOVETO] + [MPath.LINETO] * 4 + [MPath.CLOSEPOLY])

# Windows are the storm's DMI dates plus three days on each side, except Pia,
# whose +3 d lands on Christmas Eve: the clip runs to 27 December so the fleet
# is seen coming back, and the timeline says which band is Christmas.
STORMS = [
    {"key": "pia", "name": "Pia", "dates": "21–22 December 2023", "year": 2023,
     "window": ("2023-12-18", "2023-12-27"), "storm": ("2023-12-21", "2023-12-22"),
     "bands": [("2023-12-24", "2023-12-25", "Christmas")]},
    {"key": "malik", "name": "Malik", "dates": "29–30 January 2022", "year": 2022,
     "window": ("2022-01-26", "2022-02-02"), "storm": ("2022-01-29", "2022-01-30"),
     "bands": []},
    {"key": "amy", "name": "Amy", "dates": "4 October 2025", "year": 2025,
     "window": ("2025-10-01", "2025-10-07"), "storm": ("2025-10-04", "2025-10-04"),
     "bands": []},
]

# A base64 alphabet with no digits in it, so the "no nine-digit integer under
# site/" privacy test can never trip over a run of characters inside a frame.
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-*/=_.~!@#$"
STD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_TR = str.maketrans(STD, B64)


def day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def sheet() -> dict:
    """The storms-sea entry of the chart manifest: {src, box, w, h}."""
    if not MANIFEST.exists():
        sys.exit(f"{MANIFEST} is missing: run  uv run --project notes scripts/charts_storms.py")
    m = re.search(r"Object\.assign\(window\.SEAFOLK_CHARTS\|\|\{\},(\{.*\})\);", MANIFEST.read_text())
    entry = json.loads(m.group(1)).get(SHEET)
    if not entry:
        sys.exit(f"no {SHEET} in {MANIFEST}")
    return entry


# ---------------------------------------------------------------- the data


def ch(sql: str) -> list[list[str]]:
    """One clickhouse local query over the exported parquet. No --path: the
    persistent store is not ours to lock."""
    out = subprocess.run(
        ["clickhouse", "local", "--h3togeo_lon_lat_result_order=0",
         "--geotoh3_argument_order=lat_lon", "-q", sql],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ln.split("\t") for ln in out.splitlines()]


def km_between(a, b) -> float:
    """Kilometres between two (lat, lon) points, flat-earth — good to a metre
    over the few kilometres this is used for."""
    return math.dist((a[0], a[1] * math.cos(math.radians(a[0]))),
                     (b[0], b[1] * math.cos(math.radians(b[0])))) * 111.19


DROGDEN = (55.536, 12.712)  # lat, lon: the deep-water gate of the Sound


def check_dates() -> None:
    """The windows above are hand-typed; data/context/storms.csv is the DMI list
    this project cites, so the two have to agree. Only Pia's end may differ."""
    listed = {}
    with (ROOT / "data" / "context" / "storms.csv").open() as f:
        for row in csv.DictReader(f):
            listed[row["name"]] = (row["start_utc"][:10], row["end_utc"][:10])
    for s in STORMS:
        want = listed.get(s["name"])
        if want is None:
            sys.exit(f"{s['name']} is not in data/context/storms.csv")
        if tuple(s["storm"]) != want:
            sys.exit(f"{s['name']}: the clip says {tuple(s['storm'])}, storms.csv says {want}")
        span = (str(day(want[0]).date() - timedelta(days=3)),
                str(day(want[1]).date() + timedelta(days=3)))
        allowed = [span] + ([(span[0], "2023-12-27")] if s["key"] == "pia" else [])
        if tuple(s["window"]) not in allowed:
            sys.exit(f"{s['name']}: window {tuple(s['window'])} is neither {span} "
                     f"nor a documented exception")
    print(f"  dates ok: {len(STORMS)} clips against data/context/storms.csv")


def check_axis_order(points, what: str) -> None:
    """An external oracle on coordinates as the CONSUMER reads them, (lat, lon):
    cargo passes Drogden every hour of every day, so a cell within 5 km of it
    must exist. A swap anywhere between the query and the pixel fails here."""
    km = min(km_between(DROGDEN, p) for p in points)
    if km > 5.0:
        sys.exit(f"{what}: nearest cargo cell to Drogden is {km:.0f} km away — "
                 f"mirrored or transposed coordinates")
    print(f"  {what}: cargo at Drogden within {km:.1f} km")


def fetch(storm: dict, box) -> dict:
    """Per hour, per fleet, the set of res-7 cells (inside the sheet) where that
    fleet moved."""
    x0, x1, y0, y1 = box
    t0 = day(storm["window"][0])
    t1 = day(storm["window"][1]) + timedelta(days=1)
    hours = int((t1 - t0).total_seconds() // 3600)
    groups = "', '".join(FLEETS)
    rows = ch(f"""
        SELECT toUnixTimestamp(hour), ship_group,
               round(tupleElement(p, 1), 4) AS lat, round(tupleElement(p, 2), 4) AS lon
        FROM (SELECT hour, ship_group, h3ToGeo(h3) AS p
              FROM file('dist/dataset/class_a_hourly_{storm["year"]}.parquet')
              WHERE hour >= '{t0:%Y-%m-%d %H:%M:%S}' AND hour < '{t1:%Y-%m-%d %H:%M:%S}'
                AND moving_msgs > 0 AND ship_group IN ('{groups}'))
        WHERE lat BETWEEN {y0} AND {y1} AND lon BETWEEN {x0} AND {x1}""")
    if not rows:
        sys.exit(f"{storm['key']}: no rows — is {storm['year']} exported?")

    base = int(t0.timestamp())
    per = {g: {} for g in FLEETS}          # fleet -> (lat, lon) -> hour indices
    for ts, g, lat, lon in rows:
        t = (int(ts) - base) // 3600
        if 0 <= t < hours:
            per[g].setdefault((float(lat), float(lon)), set()).add(t)

    fleets = {}
    for g, cells in per.items():
        order = sorted(cells)
        idx = {c: i for i, c in enumerate(order)}
        frames = [[] for _ in range(hours)]
        for c, ts_set in cells.items():
            for t in ts_set:
                frames[t].append(idx[c])
        fleets[g] = {"cells": order, "frames": [sorted(f) for f in frames],
                     "counts": [len(f) for f in frames]}
    check_axis_order(fleets["cargo"]["cells"], f"{storm['key']} query")
    return {"t0": t0, "hours": hours, "fleets": fleets}


def hour_of(t0, d: str) -> int:
    return int((day(d) - t0).total_seconds() // 3600)


def bands(storm, t0):
    """[start hour, end hour, label, 1 if it is the storm]."""
    return ([[hour_of(t0, storm["storm"][0]), hour_of(t0, storm["storm"][1]) + 24, "the storm", 1]]
            + [[hour_of(t0, a), hour_of(t0, b) + 24, t, 0] for a, b, t in storm["bands"]])


# ---------------------------------------------------------------- the player


def bits(idx: list[int], n: int) -> str:
    """A set of cell indices as a bitmap: smaller than a list and a fixed size."""
    buf = bytearray((n + 7) // 8)
    for i in idx:
        buf[i >> 3] |= 128 >> (i & 7)
    return base64.b64encode(buf).decode().rstrip("=").translate(_TR)


def emit_storm_js(storm: dict, data: dict) -> None:
    t0 = data["t0"]
    obj = {
        "name": storm["name"], "dates": storm["dates"], "sheet": SHEET,
        "t0": f"{t0:%Y-%m-%dT%H:%M:%SZ}", "hours": data["hours"],
        "bands": bands(storm, t0),
        "fleets": {g: {
            # lon, lat interleaved, in thousandths of a degree
            "cells": [round(v * 1000) for lat, lon in f["cells"] for v in (lon, lat)],
            "counts": f["counts"],
            "frames": [bits(fr, len(f["cells"])) for fr in f["frames"]],
        } for g, f in data["fleets"].items()},
    }
    body = ("window.SEAFOLK_STORM = window.SEAFOLK_STORM || {};\n"
            f"window.SEAFOLK_STORM[{json.dumps(storm['key'])}] = "
            + json.dumps(obj, separators=(",", ":")) + ";\n")
    if re.search(r"\d{9}", body):
        sys.exit(f"storm-{storm['key']}.js: a nine-digit integer got into the data file")
    path = MEDIA / f"storm-{storm['key']}.js"
    path.write_text(body)
    print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1e3:.0f} kB")
    # read it back the way the player does — cells are (lon, lat) pairs
    flat = json.loads(re.search(r"\] = (\{.*\});\s*\Z", path.read_text(), re.S)
                      .group(1))["fleets"]["cargo"]["cells"]
    check_axis_order([(flat[i + 1] / 1000, flat[i] / 1000) for i in range(0, len(flat), 2)],
                     f"{storm['key']} written file")


# ---------------------------------------------------------------- the clip


def local(t: datetime) -> datetime:
    """Danish time: the clip is watched by people who live by it."""
    y = t.year
    # EU summer time: last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC
    last_sun = lambda m: max(datetime(y, m, d, 1, tzinfo=timezone.utc)   # noqa: E731
                             for d in range(25, 32) if datetime(y, m, d).weekday() == 6)
    return t + timedelta(hours=2 if last_sun(3) <= t < last_sun(10) else 1)


def render(storm: dict, data: dict, sh: dict) -> None:
    """The page's picture as a 1280x720 clip: the chart on the right, the
    cartouche on the left. One matplotlib figure, the fleets' offsets updated
    per hour, frames piped raw into ffmpeg."""
    from PIL import Image
    img = Image.open(ROOT / "site" / sh["src"]).convert("RGB")
    x0, x1, y0, y1 = sh["box"]
    n, t0 = data["hours"], data["t0"]
    bd = bands(storm, t0)
    lo, hi = bd[0][0], bd[0][1]

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=PAPER)
    mh = H - 36
    mw = mh * sh["w"] / sh["h"]
    left = W - 18 - mw
    ax = fig.add_axes([left / W, 18 / H, mw / W, mh / H])
    ax.imshow(img, extent=(x0, x1, y0, y1), aspect="auto", zorder=0)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(INK)
        s.set_linewidth(1.4)
    gale = ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=STORM_INK,
                                      alpha=0, lw=0, zorder=1))
    plt.rcParams["hatch.linewidth"] = .6
    rain = ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="none",
                                      edgecolor=STORM_INK + "44", hatch="/", lw=0, zorder=1.1,
                                      visible=False))
    for lon, lat, name in [(9.3, 57.8, "SKAGERRAK"), (11.45, 56.75, "KATTEGAT"),
                           (8.4, 56.45, "NORDSØEN"), (14.1, 54.72, "ØSTERSØEN")]:
        ax.text(lon, lat, " ".join(name), color="#3b5b6b", fontsize=11, style="italic",
                family="serif", ha="center", va="center", zorder=2, alpha=.85)

    # cargo and ferries with a two-hour wake, fishing as boats
    wake = {g: [ax.scatter([], [], s=sz, c=col, lw=0, alpha=a, zorder=3 + i * .1)
                for i, a in enumerate((.18, .35, .75))]
            for g, col, sz in (("cargo", CARGO, 3.2), ("passenger", FERRY, 5))}
    boats = ax.scatter([], [], s=70, c=FISHING, marker=BOAT, lw=.5, edgecolors=SURFACE, zorder=5)

    # --- the cartouche, on the left
    cx = 34 / W
    fig.add_artist(plt.Rectangle((18 / W, 18 / H), (left - 36) / W, (H - 36) / H,
                                 transform=fig.transFigure, facecolor=SURFACE,
                                 edgecolor=INK, lw=1.4, zorder=-1))
    fig.text(cx, 1 - 62 / H, f"STORM {storm['name'].upper()} · {storm['dates'].upper()}",
             color=FERRY, fontsize=11, family="monospace")
    phase = fig.text(cx, 1 - 126 / H, "", fontsize=31, family="serif", style="italic",
                     fontweight="bold")
    clock = fig.text(cx, 1 - 164 / H, "", color=INK, fontsize=15, family="monospace")
    num = fig.text(cx, 1 - 262 / H, "", color=FISHING, fontsize=64, family="serif",
                   fontweight="bold")
    fig.text(cx, 1 - 292 / H, "places at sea with fishing boats moving",
             color=LABEL, fontsize=12.5, style="italic", family="serif")
    cnum = fig.text(cx, 1 - 346 / H, "", color=CARGO, fontsize=30, family="serif",
                    fontweight="bold")
    fig.text(cx, 1 - 372 / H, "with cargo ships moving", color=LABEL, fontsize=12.5,
             style="italic", family="serif")

    # the strip: each fleet against its own days before the storm
    tl = fig.add_axes([cx, 1 - 560 / H, (left - 70) / W, 130 / H])
    tl.set_facecolor(SURFACE)
    for s in tl.spines.values():
        s.set_visible(False)
    tl.set_xticks([])
    tl.set_yticks([])
    tl.set_xlim(0, n - 1)
    tl.set_ylim(-28, 165)
    for a, b, text, is_storm in bd:
        tl.axvspan(a, b, color=FERRY if is_storm else REF, alpha=.12 if is_storm else .25, lw=0)
        tl.text((a + b) / 2, 160, text, color=FERRY if is_storm else LABEL, fontsize=10,
                ha="center", va="top", style="italic", family="serif")
    tl.axhline(100, color=REF, lw=.8, ls=(0, (3, 3)))
    for g, col, lab in (("fishing", FISHING, "fishing"), ("cargo", CARGO, "cargo")):
        c = data["fleets"][g]["counts"]
        ref = sum(c[:lo]) / lo or 1
        ys = [min(150, 100 * v / ref) for v in c]
        tl.plot(range(n), ys, color=col, lw=1.6 if g == "fishing" else 1.2)
        # the two end labels are a line apart whatever the lines do
        tl.text(n + 2, 118 if g == "cargo" else 82, lab, color=col, fontsize=10, va="center",
                style="italic", family="serif")
    for h in range(0, n, 24):
        d = local(t0 + timedelta(hours=h))
        tl.text(h + 12, -24, f"{d:%a}", color=LABEL, fontsize=8.5, ha="center",
                family="monospace")
    cursor = tl.axvline(0, color=INK, lw=1.2)
    fig.text(cx, 1 - 590 / H, "100 = the days before the storm",
             color=LABEL, fontsize=10, family="monospace")
    fig.text(cx, 1 - 660 / H, "One mark: a patch of sea where that fleet moved this hour.\n"
             "Danish Maritime Authority AIS archive · seafolk",
             color=LABEL, fontsize=9.5, family="serif", style="italic", linespacing=1.5)

    fps = max(6, round(n / 24))
    out = MEDIA / f"storm-{storm['key']}.mp4"
    proc = subprocess.Popen(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{W}x{H}", "-framerate", str(fps), "-i", "-", "-an", "-c:v", "libx264",
         "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-r", "24",
         "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)

    F = data["fleets"]

    def pts(g, t):
        cells = F[g]["cells"]
        return [(cells[i][1], cells[i][0]) for i in F[g]["frames"][t]] if 0 <= t else []

    for t in range(n):
        for g, layers in wake.items():
            for k, sc in enumerate(layers):
                sc.set_offsets(pts(g, t - (2 - k)) or [(0, 0)])
        boats.set_offsets(pts("fishing", t) or [(0, 0)])
        wx = max(0.0, min(1.0, (t - lo + 6) / 6, (hi + 6 - t) / 6))
        gale.set_alpha(.2 * wx)
        rain.set_visible(wx > .5)
        in_storm = lo <= t < hi
        phase.set_text(f"Storm {storm['name']}" if in_storm
                       else "Before the storm" if t < lo else "After the storm")
        phase.set_color(FERRY if in_storm else INK)
        clock.set_text(f"{local(t0 + timedelta(hours=t)):%a %-d %b · %H:00}")
        num.set_text(str(F["fishing"]["counts"][t]))
        cnum.set_text(str(F["cargo"]["counts"][t]))
        cursor.set_xdata([t, t])
        fig.canvas.draw()
        proc.stdin.write(fig.canvas.buffer_rgba())
    proc.stdin.close()
    if proc.wait():
        sys.exit("ffmpeg failed")
    plt.close(fig)
    print(f"  {out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.2f} MB, "
          f"{n} frames at {fps} fps = {n / fps:.0f} s")

    webm = out.with_suffix(".webm")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(out), "-vf", "scale=640:-2",
                    "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-row-mt", "1",
                    "-deadline", "good", str(webm)], check=True)
    print(f"  {webm.relative_to(ROOT)}  {webm.stat().st_size / 1e6:.2f} MB, 640 px loop")


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keys", nargs="*", help="storm keys; default all")
    ap.add_argument("--no-video", action="store_true", help="data files only")
    args = ap.parse_args()
    picked = [s for s in STORMS if not args.keys or s["key"] in args.keys]
    if not picked:
        sys.exit(f"unknown storm; have: {', '.join(s['key'] for s in STORMS)}")

    check_dates()
    sh = sheet()
    for storm in picked:
        print(f"{storm['name']} ({storm['window'][0]} .. {storm['window'][1]})")
        data = fetch(storm, sh["box"])
        lo, hi = bands(storm, data["t0"])[0][:2]
        # places per hour before / during / after — comparable only within this week
        for g in FLEETS:
            c = data["fleets"][g]["counts"]
            print(f"  {g:<10} before {sum(c[:lo]) / lo:6.0f} | during "
                  f"{sum(c[lo:hi]) / (hi - lo):6.0f} | after {sum(c[hi:]) / (len(c) - hi):6.0f}"
                  f" | {len(data['fleets'][g]['cells'])} cells")
        emit_storm_js(storm, data)
        if not args.no_video:
            render(storm, data, sh)


if __name__ == "__main__":
    main()
