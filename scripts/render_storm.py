#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib>=3.9"]
# ///
"""The sea empties — an hour-by-hour map of Danish waters through one storm.

    uv run scripts/render_storm.py            # every storm below
    uv run scripts/render_storm.py pia        # one of them
    uv run scripts/render_storm.py --no-video # data files only, no ffmpeg

Writes, per storm:
    site/media/storm-<key>.mp4   1280x720 H.264, ~24 s, the clip for the page
    site/media/storm-<key>.webm  the same clip at 640 px, for posting
    site/media/storm-<key>.js    the same frames for site/js/storm-player.js
and once:
    site/media/land.js           the coastline, clipped to the box

WHAT IT READS.  Only `dist/dataset/class_a_hourly_<year>.parquet` — the public
fleets (cargo, ferries, fishing), already privacy-tested by
`scripts/test_export.py`.  It never touches `data/ch` and never runs
`scripts/ch.sh`: the store lock is exclusive and other sessions hold it.  There
is no small-boat data in this piece at all, so nothing here can leak a private
vessel; the export's k >= 5 floor is upstream of everything below.

WHAT A BOAT MEANS.  One mark is one hexagon of sea about seven kilometres across
(H3 resolution 6, the published resolution-7 cells folded up one level) in which
that kind of boat sent at least one message while under way during that hour.
So the counter counts PLACES, not boats: the dataset has no distinct-vessel
state for the moving subset, and summing `vessels` over cells would count one
trawler five times as it crosses five of them.  Places is what the picture
shows, so places is what the number says.

The magnitudes of `moving_msgs` are inflated from 2023 on (dataset card, bias
2), which is why nothing here compares one storm's numbers with another's — the
only comparison made is inside a single storm's own week, where the instrument
does not change.

H3 ARGUMENT ORDER IS PINNED, not inherited: ClickHouse's h3ToGeo has returned
(lat, lon) only since 25.1 and a silent swap mirrors Denmark into the Arabian
Sea (S4-redo, 35 hours of reload).  `--h3togeo_lon_lat_result_order=0` says
which convention we mean, and `check_geography()` refuses to render if the
Drogden channel is not where it should be.
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
from matplotlib.collections import PolyCollection
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patheffects as pe
from matplotlib.path import Path as MPath

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "site" / "media"
LAND_GEOJSON = ROOT / "data" / "context" / "ne_10m_land.geojson"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

BBOX = (3.0, 53.0, 17.0, 59.0)  # lon0, lat0, lon1, lat1 — the dataset's box
LAT0 = 56.0  # the latitude the plain lon/lat map is true at
H3_RES = 6  # ~36 km2, ~7 km across; res 7 is 5x the dots and 5x the bytes

W, H, DPI = 1280, 720, 100
MAP_ASPECT = (BBOX[2] - BBOX[0]) * math.cos(math.radians(LAT0)) / (BBOX[3] - BBOX[1])

# site/css/site.css, light theme. The video is light-theme only; the in-page
# player reads the live custom properties instead.
GROUND, SURFACE, HAIRLINE = "#e9eeef", "#f7f9f9", "#cfdadc"
INK, LABEL, ACCENT, ACCENT_TX = "#0f1a1d", "#55676c", "#eb6834", "#b8441a"
WORKING, REF = "#7d8f94", "#a8b8bc"
# --surface is a card colour, not a sea. These four are the map's own, and the
# same four are in site/js/storm-player.js.
SEA_TOP, SEA_BOT, LAND_FILL, COAST = "#dceaef", "#b4cdd8", "#f1f4f3", "#9fb3ba"

# ship_group -> (reader's word, colour, draw order, marker size).
# Fishing carries the story, so it is the accent and the only fleet drawn as a
# boat; cargo and the ferries are faint marks that keep the lanes visible
# without competing. The same three in site/js/storm-player.js.
FLEETS = {
    "cargo": ("Cargo ships", WORKING, 0, 6),
    "passenger": ("Ferries", LABEL, 1, 7),
    "fishing": ("Fishing boats", ACCENT, 2, 118),
}
DRAW_ORDER = sorted(FLEETS, key=lambda g: FLEETS[g][2])
ALPHAS = {"cargo": 0.34, "passenger": 0.45, "fishing": 0.95}

CLAIM = "Fishing boats go in. Cargo ships carry on."

# A hull with a cabin, bow to the right, in units of the icon's length.
# matplotlib's y is up, so the deck is positive where the canvas player's is
# negative; the shape is the same one.
BOAT = MPath(
    [(-0.52, -0.06), (0.55, -0.06), (0.30, -0.34), (-0.40, -0.34), (0, 0),
     (-0.16, 0.30), (0.14, 0.30), (0.19, -0.06), (-0.21, -0.06), (0, 0)],
    [MPath.MOVETO, MPath.LINETO, MPath.LINETO, MPath.LINETO, MPath.CLOSEPOLY,
     MPath.MOVETO, MPath.LINETO, MPath.LINETO, MPath.LINETO, MPath.CLOSEPOLY],
)

# Enough of a map for a stranger to know which sea this is, and which coast.
# (lon, lat, name, is a town). Quiet, and never on the point of the picture.
PLACES = [
    (10.58, 57.72, "Skagen", 1), (8.62, 57.12, "Hanstholm", 1),
    (8.45, 55.47, "Esbjerg", 1), (12.57, 55.68, "Copenhagen", 1),
    (14.92, 55.13, "Bornholm", 0),
    (11.5, 56.75, "KATTEGAT", 0), (4.9, 55.4, "NORTH SEA", 0),
]

# Windows are the storm's DMI dates plus three days on each side, except Pia,
# whose +3 d lands on Christmas Eve: a fleet tied up for the holiday is not the
# storm, and a viewer who never sees the fleet come back learns something
# false.  Pia therefore runs to 27 December and the timeline says which band is
# which.  `bands` are extra shaded stretches on the timeline: (start, end
# date-inclusive, label).
STORMS = [
    {
        "key": "pia",
        "name": "Pia",
        "dates": "21–22 December 2023",
        "year": 2023,
        "window": ("2023-12-18", "2023-12-27"),
        "storm": ("2023-12-21", "2023-12-22"),
        "bands": [("2023-12-24", "2023-12-25", "Christmas")],
    },
    {
        "key": "malik",
        "name": "Malik",
        "dates": "29–30 January 2022",
        "year": 2022,
        "window": ("2022-01-26", "2022-02-02"),
        "storm": ("2022-01-29", "2022-01-30"),
        "bands": [],
    },
    {
        "key": "amy",
        "name": "Amy",
        "dates": "4 October 2025",
        "year": 2025,
        "window": ("2025-10-01", "2025-10-07"),
        "storm": ("2025-10-04", "2025-10-04"),
        "bands": [],
    },
]

# A base64 alphabet with no digits in it, so the "no nine-digit integer under
# site/" privacy test can never trip over a run of characters inside a frame
# blob.  52 letters + 12 punctuation marks, none of them " \ or < .
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-*/=_.~!@#$"
STD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_TR = str.maketrans(STD, B64)


def day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- the data


def ch(sql: str) -> list[list[str]]:
    """One clickhouse local query over the exported parquet. No --path: the
    persistent store is not ours to lock."""
    out = subprocess.run(
        [
            "clickhouse",
            "local",
            "--h3togeo_lon_lat_result_order=0",
            "--geotoh3_argument_order=lat_lon",
            "-q",
            sql,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ln.split("\t") for ln in out.splitlines()]


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Kilometres between two (lat, lon) points, flat-earth over 5 km of the
    Sound. Good to a metre at this size and it needs no library."""
    return math.dist(
        (a[0], a[1] * math.cos(math.radians(a[0]))),
        (b[0], b[1] * math.cos(math.radians(b[0]))),
    ) * 111.19


def check_dates() -> None:
    """The storm windows are hand-typed up there. data/context/storms.csv is
    the DMI list this project actually cites, so the two have to agree.

    Only Pia's window is allowed to differ, and only at its end: +3 d from its
    last date lands on Christmas Eve, and a viewer who never sees the fleet
    come back learns something false, so the clip runs to 27 December. The
    timeline says which band is which.
    """
    listed = {}
    with (ROOT / "data" / "context" / "storms.csv").open() as f:
        for row in csv.DictReader(f):
            listed[row["name"]] = (row["start_utc"][:10], row["end_utc"][:10])
    for s in STORMS:
        want = listed.get(s["name"])
        if want is None:
            sys.exit(f"{s['name']} is not in data/context/storms.csv")
        if tuple(s["storm"]) != want:
            sys.exit(f"{s['name']}: the clip says {tuple(s['storm'])}, "
                     f"data/context/storms.csv says {want}")
        span = (str(day(want[0]).date() - timedelta(days=3)),
                str(day(want[1]).date() + timedelta(days=3)))
        allowed = [span]
        if s["key"] == "pia":                       # the documented exception
            allowed.append((span[0], "2023-12-27"))
        if tuple(s["window"]) not in [tuple(a) for a in allowed]:
            sys.exit(f"{s['name']}: window {tuple(s['window'])} is neither the "
                     f"storm's dates +/- 3 days {span} nor a documented "
                     f"exception")
    print(f"  dates ok: {len(STORMS)} clips against "
          f"data/context/storms.csv ({len(listed)} storms)")


def check_geography() -> None:
    """An external oracle for the H3 pin: the Drogden channel, the deep-water
    gate of the Sound south of Copenhagen, carries cargo every hour of every
    day.  If the cell centre nearest 55.536 N 12.712 E is not within 5 km of
    it, the grid is mirrored and nothing below is worth rendering.

    This checks the QUERY layer only.  check_emitted() below checks the same
    fact on what was actually written, because a swap between here and the
    page is a mirrored clip with every check above it green."""
    lat, lon = 55.536, 12.712
    rows = ch(
        f"""
        SELECT round(tupleElement(g, 1), 4), round(tupleElement(g, 2), 4)
        FROM (SELECT h3ToGeo(h3ToParent(h3, {H3_RES})) AS g
              FROM file('dist/dataset/class_a_hourly_2023.parquet')
              WHERE hour = '2023-12-20 12:00:00' AND ship_group = 'cargo')
        ORDER BY greatCircleDistance({lon}, {lat},
                 tupleElement(g, 2), tupleElement(g, 1)) LIMIT 1"""
    )
    got = (float(rows[0][0]), float(rows[0][1]))
    km = km_between((lat, lon), got)
    if km > 5.0:
        sys.exit(
            f"H3 geography check failed: nearest cargo cell to Drogden is "
            f"{got} — {km:.0f} km away. Check the h3ToGeo argument order."
        )
    print(f"  geography ok: cargo at Drogden within {km:.1f} km of {lat},{lon}")


DROGDEN = (55.536, 12.712)  # lat, lon — see check_geography()


def check_axis_order(points, what: str) -> None:
    """The same Drogden oracle, on the coordinates as the CONSUMER will read
    them.  `points` are (lat, lon) after applying whatever axis convention the
    consumer applies, so a swap anywhere between the query and the pixel — at
    the emit, in the player, in the matplotlib offsets — comes out as Drogden
    six thousand kilometres away instead of as a mirrored picture nobody looks
    at twice.

    check_geography() cannot see any of that: it asks clickhouse the question
    and never looks at what this file does with the answer."""
    km = min(km_between(DROGDEN, p) for p in points)
    if km > 5.0:
        sys.exit(
            f"{what}: the nearest cargo cell to the Drogden channel is "
            f"{km:.0f} km away. The coordinates are mirrored or transposed "
            f"somewhere between the query and this point."
        )
    print(f"  {what}: cargo at Drogden within {km:.1f} km")


def fetch(storm: dict) -> dict:
    """Per hour, per fleet, the set of cells where that fleet moved."""
    t0 = day(storm["window"][0])
    t1 = day(storm["window"][1]) + timedelta(days=1)
    hours = int((t1 - t0).total_seconds() // 3600)
    groups = "', '".join(FLEETS)
    rows = ch(
        f"""
        SELECT toUnixTimestamp(hour) AS ts, ship_group AS g,
               round(tupleElement(p, 1), 4) AS lat,
               round(tupleElement(p, 2), 4) AS lon
        FROM (SELECT hour, ship_group, h3ToGeo(h3ToParent(h3, {H3_RES})) AS p
              FROM file('dist/dataset/class_a_hourly_{storm["year"]}.parquet')
              WHERE hour >= '{t0:%Y-%m-%d %H:%M:%S}'
                AND hour <  '{t1:%Y-%m-%d %H:%M:%S}'
                AND moving_msgs > 0
                AND ship_group IN ('{groups}')
              GROUP BY hour, ship_group, p)
        GROUP BY ts, g, lat, lon"""
    )
    if not rows:
        sys.exit(f"{storm['key']}: no rows — is {storm['year']} loaded?")

    base = int(t0.timestamp())
    per = {g: {} for g in FLEETS}  # fleet -> (lat, lon) -> set of hour indices
    for ts, g, lat, lon in rows:
        t = (int(ts) - base) // 3600
        if not 0 <= t < hours:
            continue
        lat, lon = float(lat), float(lon)
        # m: a res-6 parent of an edge res-7 cell can have its centre just
        # outside the box. A mirrored grid is out by tens of degrees, not 0.3.
        m = 0.3
        if not (BBOX[1] - m <= lat <= BBOX[3] + m
                and BBOX[0] - m <= lon <= BBOX[2] + m):
            sys.exit(f"cell centre {lat},{lon} outside the box — mirrored grid?")
        per[g].setdefault((lat, lon), set()).add(t)

    fleets = {}
    for g, cells in per.items():
        order = sorted(cells)  # stable: south-west first
        idx = {c: i for i, c in enumerate(order)}
        frames = [[] for _ in range(hours)]
        for c, ts_set in cells.items():
            for t in ts_set:
                frames[t].append(idx[c])
        fleets[g] = {
            "cells": order,
            "frames": [sorted(f) for f in frames],
            "counts": [len(f) for f in frames],
        }
    return {"t0": t0, "hours": hours, "fleets": fleets}


# ---------------------------------------------------------------- the land


def clip_ring(ring, box):
    """Sutherland-Hodgman against the bounding box: the whole-world land
    polygons are 446 k points and 6 k of them are in our sea."""
    x0, y0, x1, y1 = box

    def cut(pts, keep, at):
        out, s = [], pts[-1]
        for e in pts:
            ke, ks = keep(e), keep(s)
            if ke and not ks or ks and not ke:
                out.append(at(s, e))
            if ke:
                out.append(e)
            s = e
        return out

    def ix(axis, val):
        def f(a, b):
            t = (val - a[axis]) / (b[axis] - a[axis])
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))

        return f

    pts = [tuple(p[:2]) for p in ring]
    for keep, at in (
        (lambda p: p[0] >= x0, ix(0, x0)),
        (lambda p: p[0] <= x1, ix(0, x1)),
        (lambda p: p[1] >= y0, ix(1, y0)),
        (lambda p: p[1] <= y1, ix(1, y1)),
    ):
        if not pts:
            return []
        pts = cut(pts, keep, at)
    return pts


def load_land() -> list[list[tuple[float, float]]]:
    box = (BBOX[0] - 0.2, BBOX[1] - 0.2, BBOX[2] + 0.2, BBOX[3] + 0.2)
    rings = []
    for feat in json.loads(LAND_GEOJSON.read_text())["features"]:
        geom = feat["geometry"]
        polys = (
            [geom["coordinates"]]
            if geom["type"] == "Polygon"
            else geom["coordinates"]
        )
        for poly in polys:  # [0] is the outer ring; this box has no holes
            r = clip_ring(poly[0], box)
            if len(r) < 3:
                continue
            out = []
            for x, y in r:  # ~0.001 deg is ~100 m, finer than a 1280 px map
                p = (round(x, 3), round(y, 3))
                if not out or p != out[-1]:
                    out.append(p)
            if len(out) >= 3:
                rings.append(out)
    return rings


# ---------------------------------------------------------------- the video


def label_hour(t: datetime) -> str:
    return f"{t:%a} {t.day} {t:%b} · {t:%H}:00"


def build_figure(storm: dict, data: dict, land):
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=SURFACE)
    px = lambda v, n: v / n  # noqa: E731

    # --- map
    mh = 604
    mw = mh * MAP_ASPECT
    ax = fig.add_axes(
        [px(W - 44 - mw, W), px(720 - 638, H), px(mw, W), px(mh, H)]
    )
    ax.set_facecolor(SEA_BOT)
    ax.set_xlim(BBOX[0], BBOX[2])
    ax.set_ylim(BBOX[1], BBOX[3])
    ax.set_aspect(1 / math.cos(math.radians(LAT0)))
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    # Water, as a soft vertical gradient. A 64-row image stretched over the
    # box; no numpy import needed for a list of lists.
    water = LinearSegmentedColormap.from_list("sea", [SEA_BOT, SEA_TOP])
    ax.imshow([[i / 63] for i in range(64)], cmap=water, vmin=0, vmax=1,
              extent=(BBOX[0], BBOX[2], BBOX[1], BBOX[3]), aspect="auto",
              interpolation="bilinear", zorder=0)
    ax.add_collection(
        PolyCollection(land, facecolors=LAND_FILL, edgecolors=COAST,
                       linewidths=0.9, zorder=1)
    )
    # Above the boats, with a soft halo: a place name a trawler sits on top of
    # is not a place name.
    halo = [pe.withStroke(linewidth=2.6, foreground=SURFACE, alpha=0.85)]
    for lon, lat, text, town in PLACES:
        if town:
            ax.plot([lon], [lat], "o", ms=3, color=LABEL, alpha=0.9, zorder=7,
                    path_effects=halo)
            ax.text(lon, lat + 0.13, text, color=LABEL, fontsize=9,
                    ha="center", va="bottom", zorder=7, path_effects=halo)
        else:
            ax.text(lon, lat, " ".join(text), color=LABEL, fontsize=8.5,
                    alpha=0.7, ha="center", va="center", zorder=7,
                    path_effects=halo)

    # The storm itself: the whole sea one shade darker while it blows.
    gale = ax.add_patch(plt.Rectangle(
        (BBOX[0], BBOX[1]), BBOX[2] - BBOX[0], BBOX[3] - BBOX[1],
        facecolor="#1b333f", alpha=0.0, lw=0, zorder=2.5))

    dots = {}
    for g in DRAW_ORDER:
        _, colour, _, size = FLEETS[g]
        dots[g] = ax.scatter(
            [], [], s=size, c=colour, linewidths=0, zorder=3 + FLEETS[g][2],
            alpha=ALPHAS[g], marker=BOAT if g == "fishing" else "o",
        )
    # A hairline of sea around every boat, so a crowded fishing ground reads as
    # a crowd of boats instead of as one orange blob.
    dots["fishing"].set_edgecolors("#ffffff")
    dots["fishing"].set_linewidths(0.45)

    # --- left column: the point, in words, in the picture
    x = px(44, W)
    fig.text(x, px(720 - 52, H), f"Storm {storm['name']} · {storm['dates']}",
             color=LABEL, fontsize=12.5, va="baseline")
    phase = fig.text(x, px(720 - 96, H), "", color=INK, fontsize=30,
                     fontweight="bold", va="baseline")
    clock = fig.text(x, px(720 - 128, H), "", color=LABEL, fontsize=16,
                     family="monospace", va="baseline")
    fig.add_artist(plt.Line2D([x, px(420, W)], [px(720 - 152, H)] * 2,
                              color=HAIRLINE, lw=1))

    nums = {}
    nums["fishing"] = fig.text(x, px(720 - 238, H), "", color=ACCENT,
                               fontsize=58, fontweight="bold",
                               family="monospace", va="baseline")
    fig.text(x, px(720 - 268, H),
             "patches of sea with\nfishing boats moving",
             color=LABEL, fontsize=13.5, va="top", linespacing=1.5)
    fig.text(x, px(720 - 358, H), CLAIM, color=INK, fontsize=15,
             va="baseline")

    for g, y in (("passenger", 402), ("cargo", 440)):
        name, colour, _, _ = FLEETS[g]
        fig.text(x, px(720 - y, H), "●", color=colour, fontsize=12,
                 va="baseline")
        fig.text(x + px(22, W), px(720 - y, H), name, color=LABEL,
                 fontsize=14, va="baseline")
        nums[g] = fig.text(px(420, W), px(720 - y, H), "", color=LABEL,
                           fontsize=18, family="monospace", ha="right",
                           va="baseline")

    fig.text(x, px(720 - 490, H),
             "Each boat is a patch of sea about seven kilometres\n"
             "across where that kind of boat was under way\n"
             "in that hour. The number counts the patches.",
             color=LABEL, fontsize=11.5, va="top", linespacing=1.6)
    fig.text(x, px(720 - 600, H),
             "Danish Maritime Authority AIS archive\nseafolk",
             color=LABEL, fontsize=10, va="top", linespacing=1.6)

    # --- timeline: the whole story at a glance, plus where we are in it
    tl = fig.add_axes([px(44, W), px(720 - 706, H), px(1192, W), px(60, H)])
    tl.set_facecolor(SURFACE)
    for s in tl.spines.values():
        s.set_visible(False)
    tl.set_xticks([])
    tl.set_yticks([])
    n = data["hours"]
    tl.set_xlim(0, n - 1)
    tl.set_ylim(-0.38, 1.38)

    t0 = data["t0"]
    hix = lambda d: int((day(d) - t0).total_seconds() // 3600)  # noqa: E731
    for a, b, text, col in [
        (storm["storm"][0], storm["storm"][1], "the storm", ACCENT)
    ] + [(a, b, t, WORKING) for a, b, t in storm["bands"]]:
        lo, hi = hix(a), hix(b) + 24
        tl.axvspan(lo, hi, color=col, alpha=0.15, lw=0)
        tl.text((lo + hi) / 2, 1.36, text, color=ACCENT_TX if col == ACCENT
                else LABEL, fontsize=10.5, ha="center", va="top")

    fish = data["fleets"]["fishing"]["counts"]
    top = max(fish) or 1
    ys = [c / top for c in fish]
    tl.fill_between(range(n), ys, color=ACCENT, alpha=0.3, lw=0)
    tl.plot(range(n), ys, color=ACCENT, lw=1.2)
    tl.text(n - 1, 1.36, "fishing boats, hour by hour", color=LABEL,
            fontsize=10, ha="right", va="top")
    for h in range(0, n, 24):
        d = t0 + timedelta(hours=h)
        tl.text(h + 3, -0.11, f"{d:%a} {d.day}", color=LABEL, fontsize=9.5,
                ha="left", va="top")
        tl.plot([h, h], [0, -0.07], color=REF, lw=1)
    cursor = tl.axvline(0, color=INK, lw=1.3, zorder=5)
    head, = tl.plot([0], [ys[0]], "o", ms=4.5, color=INK, zorder=6)

    return fig, dots, phase, clock, nums, gale, cursor, head, ys


def render(storm: dict, data: dict, land, video: bool) -> None:
    # The matplotlib half of the axis oracle: exactly the expression
    # set_offsets is fed below, read back as (lat, lon). Swap the two indices
    # in the loop and this stops before a mirrored clip is encoded.
    cells = data["fleets"]["cargo"]["cells"]
    check_axis_order([(y, x) for x, y in
                      [(c[1], c[0]) for c in cells]],
                     f"{storm['key']} matplotlib offsets")

    fig, dots, phase, clock, nums, gale, cursor, head, ys = build_figure(
        storm, data, land)
    n = data["hours"]
    fps = max(6, round(n / 24))
    out = MEDIA / f"storm-{storm['key']}.mp4"

    t0 = data["t0"]
    lo = int((day(storm["storm"][0]) - t0).total_seconds() // 3600)
    hi = int((day(storm["storm"][1]) - t0).total_seconds() // 3600) + 24

    proc = None
    if video:
        proc = subprocess.Popen(
            [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo",
             "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", str(fps),
             "-i", "-", "-an", "-c:v", "libx264", "-preset", "slow",
             "-crf", "24", "-pix_fmt", "yuv420p", "-r", "24",
             "-movflags", "+faststart", str(out)],
            stdin=subprocess.PIPE,
        )

    for t in range(n):
        for g in DRAW_ORDER:
            f = data["fleets"][g]
            cells = f["cells"]
            dots[g].set_offsets(
                [(cells[i][1], cells[i][0]) for i in f["frames"][t]] or [(0, 0)]
            )
            nums[g].set_text(f"{f['counts'][t]}")
        # the phase label, and the sea darkening over six hours at each edge
        if t < lo:
            phase.set_text("Before the storm")
            phase.set_color(INK)
        elif t < hi:
            phase.set_text(f"Storm {storm['name']}")
            phase.set_color(ACCENT_TX)
        else:
            phase.set_text("After the storm")
            phase.set_color(INK)
        gale.set_alpha(0.26 * max(0.0, min(1.0, (t - lo + 6) / 6,
                                           (hi + 6 - t) / 6)))
        clock.set_text(label_hour(data["t0"] + timedelta(hours=t)))
        cursor.set_xdata([t, t])
        head.set_data([t], [ys[t]])
        fig.canvas.draw()
        if proc:
            proc.stdin.write(fig.canvas.buffer_rgba())

    if proc:
        proc.stdin.close()
        if proc.wait() != 0:
            sys.exit("ffmpeg failed")
        print(f"  {out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.2f} MB, "
              f"{n} frames at {fps} fps = {n / fps:.0f} s")
        loop_clip(out)
    plt.close(fig)


def loop_clip(mp4: Path) -> None:
    """A small looping clip to post — the owner asked for "a GIF". A real GIF
    of 240 frames at 640 px is 30 MB of dithered mush; VP9 is a twentieth of
    that and loops the same way in a browser and in every chat app that
    matters."""
    out = mp4.with_suffix(".webm")
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4),
         "-vf", "scale=640:-2", "-an", "-c:v", "libvpx-vp9", "-b:v", "0",
         "-crf", "40", "-row-mt", "1", "-deadline", "good", str(out)],
        check=True,
    )
    mb = out.stat().st_size / 1e6
    if mb > 5:
        sys.exit(f"{out}: {mb:.1f} MB — over the 5 MB budget for the loop")
    print(f"  {out.relative_to(ROOT)}  {mb:.2f} MB, 640 px loop")


# ---------------------------------------------------------------- the player


def bits(idx: list[int], n: int) -> str:
    """A set of cell indices as a bitmap. Smaller than a list of numbers and,
    unlike one, a fixed size the player can trust."""
    buf = bytearray((n + 7) // 8)
    for i in idx:
        buf[i >> 3] |= 128 >> (i & 7)
    return base64.b64encode(buf).decode().rstrip("=").translate(_TR)


def write_js(path: Path, body: str) -> None:
    if re.search(r"\d{9}", body):
        sys.exit(f"{path}: a nine-digit integer got into the data file")
    path.write_text(body)
    print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1e3:.0f} kB")


def emit_storm_js(storm: dict, data: dict) -> None:
    t0 = data["t0"]
    hix = lambda d: int((day(d) - t0).total_seconds() // 3600)  # noqa: E731
    obj = {
        "name": storm["name"],
        "title": f"Storm {storm['name']}, {storm['dates']}",
        "claim": CLAIM,
        "t0": f"{t0:%Y-%m-%dT%H:%M:%SZ}",
        "hours": data["hours"],
        "bands": [[hix(storm["storm"][0]), hix(storm["storm"][1]) + 24,
                   "the storm", 1]]
        + [[hix(a), hix(b) + 24, t, 0] for a, b, t in storm["bands"]],
        "order": DRAW_ORDER,
        "fleets": {
            g: {
                "label": FLEETS[g][0],
                # lon, lat interleaved, in thousandths of a degree
                "cells": [round(v * 1000) for lat, lon in f["cells"]
                          for v in (lon, lat)],
                "counts": f["counts"],
                "frames": [bits(fr, len(f["cells"])) for fr in f["frames"]],
            }
            for g, f in data["fleets"].items()
        },
    }
    body = (
        "window.SEAFOLK_STORM = window.SEAFOLK_STORM || {};\n"
        f"window.SEAFOLK_STORM[{json.dumps(storm['key'])}] = "
        + json.dumps(obj, separators=(",", ":"))
        + ";\n"
    )
    path = MEDIA / f"storm-{storm['key']}.js"
    write_js(path, body)
    check_written(path, storm)


STORM_JS = re.compile(r'window\.SEAFOLK_STORM\["[^"]+"\] = (\{.*\});\s*\Z', re.S)


def check_written(path: Path, storm: dict) -> None:
    """Re-read the file that was just written and ask it where Drogden is.

    `cells` is lon, lat interleaved and site/js/storm-player.js reads it that
    way — `project(f.cells[c] / 1000, f.cells[c + 1] / 1000)` with the
    signature `project(lon, lat)`. So the pairs come back (lon, lat) and are
    handed to the oracle as (lat, lon); if the emit above ever writes them the
    other way round, or the player is changed to read them the other way round
    and this is updated to match, the check fails rather than the map silently
    turning inside out."""
    m = STORM_JS.search(path.read_text())
    if not m:
        sys.exit(f"{path}: cannot read back what was just written")
    flat = json.loads(m.group(1))["fleets"]["cargo"]["cells"]
    check_axis_order([(flat[i + 1] / 1000, flat[i] / 1000)
                      for i in range(0, len(flat), 2)],
                     f"{storm['key']} written coordinates")


def emit_land_js(land) -> None:
    rings = [[v for x, y in r for v in (round(x * 1000), round(y * 1000))]
             for r in land]
    write_js(
        MEDIA / "land.js",
        "// Natural Earth 10m land, clipped to the dataset's box, in\n"
        "// thousandths of a degree: lon, lat, lon, lat, ... per ring.\n"
        "window.SEAFOLK_LAND = "
        + json.dumps(rings, separators=(",", ":"))
        + ";\n",
    )


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keys", nargs="*", help="storm keys; default all")
    ap.add_argument("--no-video", action="store_true", help="data files only")
    args = ap.parse_args()

    picked = [s for s in STORMS if not args.keys or s["key"] in args.keys]
    if not picked:
        sys.exit(f"unknown storm; have: {', '.join(s['key'] for s in STORMS)}")

    MEDIA.mkdir(parents=True, exist_ok=True)
    check_dates()
    check_geography()
    land = load_land()
    print(f"  land: {len(land)} rings, {sum(len(r) for r in land)} points")
    emit_land_js(land)

    for storm in picked:
        print(f"{storm['name']} ({storm['window'][0]} .. {storm['window'][1]})")
        data = fetch(storm)
        n = data["hours"]
        t0 = data["t0"]
        lo = int((day(storm["storm"][0]) - t0).total_seconds() // 3600)
        hi = int((day(storm["storm"][1]) - t0).total_seconds() // 3600) + 24
        # Mean places per hour over the three days before, the storm's own
        # dates, and the days after — plus the single emptiest hour. Only
        # comparable within this storm's own week (dataset card, bias 2).
        for g in DRAW_ORDER:
            c = data["fleets"][g]["counts"]
            worst = min(range(lo, hi), key=lambda t: c[t])
            print(f"  {FLEETS[g][0]:<13} before {sum(c[:lo]) / lo:6.0f} | "
                  f"during {sum(c[lo:hi]) / (hi - lo):6.0f} | "
                  f"after {sum(c[hi:]) / (n - hi):6.0f} | "
                  f"emptiest hour {c[worst]:5d} "
                  f"({label_hour(t0 + timedelta(hours=worst))})")
        emit_storm_js(storm, data)
        render(storm, data, land, video=not args.no_video)


if __name__ == "__main__":
    main()
