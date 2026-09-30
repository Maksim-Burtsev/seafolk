"""The chart sheets and the two animations of site/ferries.html.

    CH_PATH=<clone> uv run --project notes scripts/charts_ferries.py

Run it AFTER scripts/build_site_data.sh: the race in F4 is two real crossings
whose length is the one the page already prints (`ellen_before`,
`ellen_after`), and those numbers are read back out of the page rather than
computed a second time here.

Writes site/media/charts/ferries-*.webp, site/media/charts/ferries.js (the
manifest) and site/media/charts/ferries-tracks.js (the day of island ferries
the F0 pen draws, and the two crossings the F4 race runs).

Ferries are public and may be named. Every track comes from the store's
public_track (Class A passenger ships), and before anything is drawn every
radio ID in the date range is checked against vessel_day: Class A, never
leisure — the same check as scripts/charts_index.py. Radio IDs are used to
split points into tracks and then dropped; none reaches a written file.
"""
import bisect
import datetime
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartkit as ck                          # noqa: E402
from charts_index import ch, public_only, segments   # noqa: E402
from site_data.ferries import BIG, F4_LINE, F4_SHIP  # noqa: E402

MONTH = ("2025-07-01", "2025-07-31")
DAY = "2025-07-08"                # an ordinary Tuesday in July; any weekday would do
# the islands: Fanø in the west to Orø in the east, Ærø to Læsø. Bornholm and
# Christiansø are a sea away and stay on the country sheet of the story page.
ISLANDS = (8.2, 12.1, 54.72, 57.52)
# Søby on Ærø to Fynshav on Als, with Als, the tip of Ærø and Horne Land round it.
ELLEN_BOX = (9.84, 10.42, 54.875, 55.105)


def lit(text):
    """A string literal for SQL that survives `clickhouse local -q`: its query
    text turns an en dash into "--", so a line name is passed as bytes."""
    return f"unhex('{text.encode().hex()}')"


def in_box(box, pad=.15):
    x0, x1, y0, y1 = box
    return (f"lon BETWEEN {x0 - pad} AND {x1 + pad} AND lat BETWEEN {y0 - pad} AND {y1 + pad}")


def island_windows(day_from, day_to):
    """{radio ID: sorted [(dep, arr)]} of every island-line crossing — the small
    lines, not the four big ones. Kept in memory only."""
    big = ",".join(lit(b) for b in BIG)
    rows = ch(f"""SELECT mmsi, toUnixTimestamp(dep), toUnixTimestamp(arr) FROM ferry_crossing
                  WHERE kind = 'island' AND line NOT IN ({big})
                  AND toDate(dep) BETWEEN '{day_from}' AND '{day_to}' ORDER BY mmsi, dep""", store=True)
    out = {}
    for m, a, b in rows:
        out.setdefault(m, []).append((int(a), int(b)))
    return out


def tracks(day_from, day_to, box, step_min, where=""):
    """{radio ID: [(t, lon, lat, sog)]} inside the box."""
    rows = ch(f"""SELECT mmsi, toUnixTimestamp(ts), round(lon, 4), round(lat, 4), sog
                  FROM public_track WHERE toDate(ts) BETWEEN '{day_from}' AND '{day_to}'
                  AND toMinute(ts) % {step_min} = 0 AND {in_box(box)} {where}
                  ORDER BY mmsi, ts""", store=True)
    out = {}
    for m, t, lon, lat, sog in rows:
        out.setdefault(m, []).append((int(t), float(lon), float(lat), float(sog)))
    return out


def split_island(trs, windows):
    """(island-crossing tracks, everything else), radio IDs dropped here."""
    isl, rest = [], []
    for m, pts in trs.items():
        w = windows.get(m, [])
        starts = [a for a, _ in w]
        cur, cur_is = [], None
        for p in pts:
            k = bisect.bisect_right(starts, p[0]) - 1
            on = k >= 0 and p[0] <= w[k][1]
            if cur and on != cur_is:
                (isl if cur_is else rest).append(cur)
                cur = [cur[-1]] if on else []      # the first point of a crossing joins it
            cur.append(p)
            cur_is = on
        if cur:
            (isl if cur_is else rest).append(cur)
    return isl, rest


def fine_base(s, k=8, soundings=90):
    """A chart base for a zoom of a few miles, where Natural Earth's coast is a
    kilometre off: land, shallows and contours all from EMODnet's own grid,
    upsampled k times and smoothed so the coast is a line and not a staircase."""
    d, lons, lats, _ = ck.bathy()
    x0, x1, y0, y1 = s.box
    j = (lons >= x0 - .03) & (lons <= x1 + .03)
    i = (lats >= y0 - .03) & (lats <= y1 + .03)
    sub = d[np.ix_(i, j)]
    sea = np.kron(np.where(np.nan_to_num(sub) > .5, 1., 0.), np.ones((k, k)))
    dep = np.kron(np.nan_to_num(sub), np.ones((k, k)))
    step = lons[1] - lons[0]
    lo = np.linspace(lons[j][0] - step / 2, lons[j][-1] + step / 2, sea.shape[1])
    la = np.linspace(lats[i][0] + step / 2, lats[i][-1] - step / 2, sea.shape[0])
    sea = ck._gauss(sea, k * .55)
    dep = ck._gauss(dep, k * .6)
    ax = s.ax
    ax.contourf(lo, la, np.where(sea > .5, dep, np.nan), levels=[0, 5, 10, 20],
                colors=ck.C["shoal"], zorder=1)
    ax.contour(lo, la, np.where(sea > .5, dep, np.nan), levels=[5, 10, 20],
               colors=ck.C["contour"], linewidths=.5, alpha=.8, zorder=2)
    ax.contourf(lo, la, sea, levels=[-1, .5], colors=[ck.C["land"]], zorder=20)
    ax.contour(lo, la, sea, levels=[.5], colors=[ck.C["coast"]], linewidths=.8, zorder=21)
    # soundings on a loose grid, off the shallows' edge
    rng = np.random.default_rng(5)
    for _ in range(soundings):
        a, b = rng.integers(0, sub.shape[0]), rng.integers(0, sub.shape[1])
        v = sub[a, b]
        if np.isnan(v) or v < 3:
            continue
        ax.text(lons[j][b], lats[i][a], f"{v:.0f}", fontsize=s.w / 240, color=ck.C["sounding"],
                style="italic", family="serif", ha="center", va="center", zorder=3, alpha=.85)
    return s


def frac(box, pts, t0):
    """[minute since t0, x, y] with x, y as fractions of the sheet."""
    x0, x1, y0, y1 = box
    return [[round((p[0] - t0) / 60, 1), round((p[1] - x0) / (x1 - x0), 4),
             round((y1 - p[2]) / (y1 - y0), 4)] for p in pts]


def page_number(key):
    """A number the build already wrote into site/ferries.html."""
    html = (ck.ROOT / "site" / "ferries.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="data">(.*?)</script>', html, re.S).group(1))
    return int(data["n"][key])


def race_crossing(ship, year, minutes):
    """The Søby -> Fynshav crossing of `ship` in July of `year` that took the
    typical time and left closest to eleven in the morning. Deterministic, and
    both runners of the race start at the same hour of a summer day."""
    rows = ch(f"""SELECT mmsi, toUnixTimestamp(dep), toUnixTimestamp(arr) FROM ferry_crossing
                  WHERE line = {lit(F4_LINE)} AND name = '{ship}' AND toYear(dep) = {year}
                  AND toMonth(dep) = 7 AND minutes = {minutes} AND lon_a > lon_b
                  ORDER BY abs(toHour(dep) * 60 + toMinute(dep) - 9 * 60) LIMIT 1""", store=True)
    assert rows, f"no {minutes}-minute July {year} crossing of {ship}"
    m, a, b = rows[0]
    pts = ch(f"""SELECT toUnixTimestamp(ts), lon, lat FROM public_track
                 WHERE mmsi = {m} AND ts BETWEEN {a} AND {b} ORDER BY ts""", store=True)
    public_only(*(datetime.datetime.fromtimestamp(int(x), datetime.UTC).date() for x in (a, b)))
    return [(int(t), float(x), float(y)) for t, x, y in pts], int(a)


def main():
    charts = {}
    public_only(*MONTH)

    # F0: every passenger ship's track through July 2025 on the islands'
    # sheet — the island crossings in strong red ink, the rest as a faint web.
    tr = tracks(*MONTH, ISLANDS, 2)
    isl, rest = split_island(tr, island_windows(*MONTH))
    s = ck.Sheet(ISLANDS, 1800).base()
    s.tracks(segments(rest, 600), "ferry", lw=.3, alpha=.07)
    s.tracks(segments(isl, 600), "ferry", lw=.6, alpha=.2)
    charts["ferries-web"] = s.save("ferries-web")
    print(f"ferries-web: {len(isl)} island crossings, {len(rest)} other pieces of track")

    # …and the Tuesday the pen draws: every island ferry, whole day, 2-minute steps.
    wins = island_windows(DAY, DAY)
    day = tracks(DAY, DAY, ISLANDS, 2)
    t0 = min(p[0] for m in day for p in day[m]) // 86400 * 86400
    ships = [frac(ISLANDS, pts, t0) for m, pts in day.items()
             if m in wins and max(p[3] for p in pts) >= 3]
    print(f"ferries-day: {len(ships)} island ferries under way on {DAY}")

    # F4: the Søby – Fynshav lane (a month of ELLEN), and the race.
    s = fine_base(ck.Sheet(ELLEN_BOX, 1600))
    lane = tracks(*MONTH, ELLEN_BOX, 1, f"AND name = '{F4_SHIP}'")
    s.tracks(segments(list(lane.values()), 300), "ferry", lw=.5, alpha=.05)
    charts["ferries-ellen"] = s.save("ferries-ellen")
    before, after = page_number("ellen_before"), page_number("ellen_after")
    old, old_t = race_crossing("SKJOLDNAES", 2018, before)
    new, new_t = race_crossing(F4_SHIP, 2025, after)
    race = [{"ship": "SKJOLDNAES", "year": 2018, "minutes": before, "track": frac(ELLEN_BOX, old, old_t)},
            {"ship": F4_SHIP, "year": 2025, "minutes": after, "track": frac(ELLEN_BOX, new, new_t)}]
    print(f"race: SKJOLDNAES {before} min ({len(old)} fixes), ELLEN {after} min ({len(new)} fixes)")

    body = json.dumps({"day": DAY, "ships": ships, "race": race}, separators=(",", ":"))
    assert not re.search(r"(?<![\d.])\d{9}(?![\d.])", body), "a nine-digit integer in the tracks"
    (ck.OUT / "ferries-tracks.js").write_text(
        "// Written by scripts/charts_ferries.py: the island ferries of one July day and the\n"
        "// F4 race, minutes from the start and position as a fraction of their sheet.\n"
        f"window.SEAFOLK_FERRIES={body};\n")
    ck.write_manifest(charts, "ferries")


if __name__ == "__main__":
    main()
