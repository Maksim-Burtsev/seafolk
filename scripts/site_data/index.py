"""site/index.html — the story page. Eight charts, one dict.

Every number the page shows is computed here from the store, through the query
files the chapters already use. One constant is hand-typed; it is marked, and
it is a line in a log that no query can reach.

    chart  what it says                        where the numbers come from
    I1     the season, one line per year       sql/10_season_daily.sql
    I2     small boats tripled, ships did not  sql/61_adoption.sql   block 1
    I3     whose boats these are               sql/80_site_flags.sql
    I4     one storm, four fleets              sql/50_storm_window.sql
    I5     who stops first                     sql/50_storm_window.sql + sql/52
    I7     days that cannot have happened      sql/60_coverage_index.sql block 6
    I8     Copenhagen in the Arabian Sea       geoToH3 + ne_10m_land.geojson
    I6     the sea empties                     site/media/, rendered by S14
    prose  the ferry nobody can see            sql/44_hidden_fleet.sql   block 3
    prose  what was loaded, and how big        vessel_day, load_log, du

PRIVACY. The private fleet appears here at two grains and no others: a
store-wide daily head count (I1 — minimum 12 boats, on a January day in 2015,
measured in sql/20's header) and a store-wide yearly head count (I2 — minimum
6 137). I4's and I5's sailing lines are one fleet's messages against the same
fleet a fortnight earlier, never a count, and I4 draws that line only for the
storms whose reference days had enough boats out to mean anything (S9's floor:
250 boats that covered a mile, read off sql/52). No MMSI, name, callsign,
position or track of a private boat is read or written here.
"""
import datetime
import json
import math
import os
import statistics
from collections import defaultdict

from . import (A1, A1_INT, A4, B6, B6_INT, CAP_A, D1, D1_INT, FLEET_KEY,
               FLEET_NAME, H1, H1_INT, H3, H3_INT, K_FLOOR, REPORT_SECONDS,
               ROOT, STOP_ORDER, W, W_INT, WINDOW_DAYS, YEARS, blocks, clips,
               hourly_series, media_key, onset, onset_words, private_count,
               sailing_storms, sp, typed)

# THE ONE HAND-TYPED NUMBER ON THE PAGE. The S4-redo reload ran 2026-09-06
# 14:56:59 -> 2026-09-08 01:50:30 UTC = 34 h 54 min, docs/STATUS.md § S4-redo.
# It is a wall clock in a log, not a column in any table.
RELOAD_HOURS = 35

# Copenhagen, and the first store's idea of Copenhagen. ClickHouse changed
# geoToH3's argument order in 25.5 — it takes (lat, lon) now and took
# (lon, lat) before — and the swap does not error, it mirrors every position
# across lat = lon. mirror() computes the mirrored point by handing the pinned
# function its arguments the wrong way round, which is what the bug did.
CPH = (55.6761, 12.5683)

FL = "year flag share".split()


def mean7(days, values):
    """A centred 7-day mean over a list of CALENDAR days.

    A point is the mean of whichever of its seven neighbours are loaded, so a
    run keeps its ends and a hole in the calendar — 2016 through 2020, most of
    2022 and 2023 — simply has no days to average. The chart breaks its line
    there rather than inventing five years of sea.

    Centred, where sql/20's season bounds use a trailing mean: a hill drawn
    from a trailing mean leans a few days late, and a peak read off this one
    can sit a day or two from the peak sql/20 reports. Neither is wrong; they
    answer different questions and only one of them is a chart.
    """
    have = dict(zip(days, values))
    out = []
    for d in days:
        w = [have[d + datetime.timedelta(days=k)] for k in range(-3, 4)
             if d + datetime.timedelta(days=k) in have]
        out.append(round(sum(w) / len(w), 1))
    return out


# ------------------------------------------------------------------- I1 ----
def season(ch):
    """sql/10 -> one line per year: day of the year against boats out that day.

    The measure is sql/20's — distinct private transponders that MOVED that day
    (`moving_msgs > 0`). A set left on at the berth is not a boat out sailing;
    the reasoning is in sql/10's header and it is the decision the whole project
    runs on. sql/10's own 7-day mean is partitioned by MONTH, because it was
    written when three separate months were loaded, so the mean is recomputed
    here across the year — which is what a season needs.

    x is the day of the year, so the six years lie over one calendar. A leap
    day shifts the second half of a leap year one day against a common year; at
    this width that is a fifth of a pixel.
    """
    per_year = defaultdict(list)
    for day, mobile, _present, active, _m7 in ch("10_season_daily.sql"):
        if mobile == "Class B":
            d = datetime.date.fromisoformat(day)
            per_year[d.year].append((d, int(active)))

    out = {}
    for year in YEARS:
        rows = sorted(per_year[year])
        days = [d for d, _ in rows]
        # The floor goes on the DAILY counts, not on the 7-day means drawn from
        # them: a week holding one day of two boats averages to something
        # comfortably over five, and the shape on screen is still that day.
        # The smallest in the store is 12, on a January day in 2015.
        vals = [private_count(v, f"sql/10 {d}: small boats that moved")
                for d, v in rows]
        out[str(year)] = [[d.timetuple().tm_yday, v] for d, v
                          in zip(days, mean7(days, vals))]
    return out


# ------------------------------------------------------------------- I2 ----
def fleet(ch):
    """sql/61 block 1, the common window -> private boats and big ships a year.

    Both counts run 1 March to 26 August, the only window all six years share:
    the daily archive begins on 2024-03-01 and the store ends on 2026-08-26, so
    a full-year count would compare a year against three quarters of one.

    The big-ship line counts Class A vessels heard on at least FIVE days, not
    all of them. All days reads 25 421 in 2015 against 17 512 in 2024 — a
    commercial fleet that shrank by a third and did not. What it counts is
    one-day, one-message radio IDs, 7 617 of 2015's 8 428 of which sent three
    messages or fewer in the whole year. sql/61's header lays it out; the
    five-day count is the only denominator this project uses.
    """
    rows = [typed(A1, r, A1_INT) for r in
            blocks(ch("61_adoption.sql"), "sql/61_adoption.sql")[13]]
    win = {r["year"]: r for r in rows if r["window"] == "mar_aug"}
    return {"years": YEARS,
            "small_boats": [private_count(win[y]["class_b_leisure_vessels"],
                                          f"sql/61 {y}: small boats heard")
                            for y in YEARS],
            "big_ships": [win[y]["class_a_vessels_5d"] for y in YEARS]}, win


# ------------------------------------------------------------------- I3 ----
FLAG_ORDER = ["German", "Danish", "Swedish", "Norwegian", "Dutch",
              "everyone else"]


def flags(ch):
    """sql/80 -> the flag split of the private fleet, over the common window.

    A registration country, over thousands of boats, is the only attribute of a
    private vessel anywhere on this site. sql/80's header says why it is its own
    file rather than three more columns on sql/61 block 4, and the two overlap
    on Denmark and Germany — which is checked here, because a chart drawn from
    the wrong population would look exactly like a chart drawn from the right
    one.
    """
    rows = [typed(FL, r, ("year",)) for r in
            blocks(ch("80_site_flags.sql"), "sql/80_site_flags.sql")[3]]
    raw, by = defaultdict(dict), defaultdict(dict)
    for r in rows:
        raw[r["year"]][r["flag"]] = r["share"]
        by[r["year"]][r["flag"]] = round(100 * r["share"], 1)

    check = {int(r["year"]): r for r in
             (typed(A4, r) for r in
              blocks(ch("61_adoption.sql"), "sql/61_adoption.sql")[10])}
    for y in YEARS:
        assert abs(sum(by[y].values()) - 100) < 0.2, \
            f"sql/80 {y}: the flag shares sum to {sum(by[y].values())}, not 100"
        for flag, col in (("German", "german_share"), ("Danish", "danish_share")):
            # both sides are rounded to four places by ClickHouse, so they
            # should be equal to the digit; the tolerance is for the float.
            assert abs(raw[y][flag] - check[y][col]) < 1e-4, \
                (f"sql/80 and sql/61 block 4 disagree about {flag} in {y}: "
                 f"{raw[y][flag]} against {check[y][col]} — they are supposed "
                 f"to count the same fleet over the same window")
    return {"years": YEARS, "order": FLAG_ORDER,
            "shares": {f: [by[y][f] for y in YEARS] for f in FLAG_ORDER}}


# ---------------------------------------------------------------- I4, I5 ----
def storms(ch):
    """sql/50 + sql/52 -> chart I5, the ferry timetable's cost, and the storms
    whose sailing fleet is big enough to draw.

    I5 pools the storms: per fleet, the median hour at which its movement
    halves, and on how many of the storms it halved at all. That one is HOURLY,
    because "who goes in first" is a question about hours; chart I4 next door
    counts whole days, because "how many went out" is a question about days.

    The storm-day count is read off sql/50's window rather than off storms.csv:
    the window runs from 72 h before the first date to 72 h after the last, so
    n = (max offset + 1 - 72) / 24. Alfrida comes out at 0 — 2019 is not in the
    store, so only its three run-up days survive and the storm itself was never
    observed. That is what drops it, rather than a name in a list.
    """
    rows, off, start = [], defaultdict(set), {}
    for r in ch("50_storm_window.sql"):
        row = typed(W, r, W_INT)
        rows.append(row)
        off[row["storm"]].add(row["offset_h"])
        start[row["storm"]] = row["start_day"]
    ndays = {}
    for storm, o in off.items():
        assert min(o) == -72 and len(o) == max(o) + 73, \
            f"{storm}: the window has a hole — the storm-day count is a guess"
        ndays[storm] = max((max(o) + 1 - 72) // 24, 0)
    observed = sorted(s for s, n in ndays.items() if n > 0)

    day_rows = [typed(D1, r, D1_INT)
                for r in blocks(ch("52_who_stays.sql"), "sql/52_who_stays.sql")[12]]
    # The storms whose private fleet is big enough to say anything about, and
    # the hour each fleet halves — both from site_data, because site/storms.html
    # asks the same two questions and the two pages have to give one answer.
    sailing_ok = sailing_storms(day_rows, ndays)
    series = hourly_series(rows)
    onsets = onset(series, ndays, sailing_ok)

    ferry = {}
    for storm in observed:
        n = ndays[storm]
        rs = [r for r in rows if r["storm"] == storm and r["mobile"] == "Class A"
              and r["ship_group"] == "passenger" and 0 <= r["offset_h"] < 24 * n]
        ferry[storm] = (sum(r["ferry_crossings"] for r in rs),
                        round(sum(r["ref_ferry_crossings"] or 0 for r in rs)))

    # `of` is per fleet because the sailing fleet is measured over fewer storms
    # than the rest, and a row reading "3 of 14" would lie about what was seen.
    strip = {"of": len(observed), "rows": [
        {"fleet": FLEET_KEY[g], "label": FLEET_NAME[g], "storms": len(onsets[g]),
         "of": len(sailing_ok) if g == "leisure" else len(observed),
         "hour": round(statistics.median(onsets[g])) if onsets[g] else None}
        for g in STOP_ORDER]}
    panels = daily_panels(day_rows, ndays, start, sailing_ok)
    default = pick_default(panels)
    return ({"default": default, "media": media_key(default),
             "sailing_shown": sailing_ok, "panels": panels},
            strip, ferry, onsets)


# ------------------------------------------------------------------- I4 ----
def daily_panels(day_rows, ndays, start, sailing_ok):
    """sql/52 block 1 -> chart I4: of every hundred boats the radio heard that
    day, how many went somewhere.

    "Went somewhere" is sql/52's definition and it is an exact count, not a
    message rate: a vessel whose positions that day add up to at least one
    nautical mile. Both halves of the fraction are `uniqExact` over the same
    day's own fleet, so there is no reference fortnight in this chart at all —
    the earlier version divided each hour by the same hour two weeks earlier,
    and a reader cannot read a baseline that is itself weather.

    `usual` is kept per fleet for the same storm's reference days, and it is
    used to CHOOSE the default panel, not drawn: a panel whose run-up already
    sits far below the fleet's ordinary level has no fall left to show.

    PRIVACY. The sailing line carries a SHARE AND NO COUNT, and only for the
    storms that clear S9's floor. Every public fleet carries its head count too,
    because a ferry and a coaster are public (CLAUDE.md) and the number makes
    the readout useful.
    """
    want = {"fishing": "Class A", "cargo": "Class A", "passenger": "Class A",
            "other": "Class A", "leisure": "Class B"}
    by = defaultdict(list)
    for r in day_rows:
        g = r["ship_group"]
        if want.get(g) != r["mobile"] or r["storm"] not in ndays:
            continue
        if g == "leisure" and r["storm"] not in sailing_ok:
            continue
        by[(r["storm"], g)].append(r)

    panels = {}
    for (storm, g), rs in by.items():
        rs.sort(key=lambda r: r["offset_d"])
        p = panels.setdefault(storm, {"days": ndays[storm], "start": start[storm],
                                      "lines": {}, "usual": {}})
        p["lines"][FLEET_KEY[g]] = [
            [r["offset_d"], round(100 * r["share_moved"], 1),
             None if g == "leisure" else r["heard"]] for r in rs]
        ref = [r["ref_share_moved"] for r in rs if r["ref_share_moved"] is not None]
        p["usual"][FLEET_KEY[g]] = round(100 * statistics.mean(ref), 1) if ref else None
    return {s: p for s, p in sorted(panels.items()) if ndays[s] > 0}


def drop(panel):
    """How far the fishing fleet fell, and whether the days before the storm
    were an ordinary week for it.

    `pre` is the mean over the three days before; `usual` is the same fleet on
    the reference days; `low` is the worst day of the storm itself.
    """
    pts = panel["lines"]["fishing"]
    pre = statistics.mean(v for o, v, _h in pts if o < 0)
    low = min(v for o, v, _h in pts if 0 <= o < panel["days"])
    return {"pre": pre, "low": low, "usual": panel["usual"]["fishing"],
            "fall": pre - low}


def pick_default(panels):
    """Which storm chart I4 opens on — chosen from the data, not by hand.

    The candidates are the storms S14 rendered an animation for, because chart
    I6 mounts that animation and Act 2 is written about the same storm. Among
    them the best panel is the one with the LARGEST fall in the fishing fleet
    whose run-up still sits near what that fleet ordinarily does, so that the
    fall on screen is the storm and not a fortnight of December.
    """
    scored = {s: drop(panels[s]) for s in clips(panels).values()}
    return max(scored, key=lambda s: scored[s]["fall"]
               - abs(scored[s]["pre"] - scored[s]["usual"]))


# ------------------------------------------------------------------- I7 ----
def impossible(ch):
    """sql/60 block 6 -> per loaded month, the share of big-ship days holding
    more messages than a transponder can send in a day.

    The share is recomputed from the two counts rather than read out of
    `share_over_cap`, which sql/60 rounds to five places — at that resolution
    every clean pre-2023 month reads the same.
    """
    rows = [typed(B6, r, B6_INT) for r in blocks(ch("60_coverage_index.sql"), "sql/60_coverage_index.sql")[12]]
    worst = max(rows, key=lambda r: r["max_msgs"])
    return ({"cap": CAP_A, "step": "2023-12",
             "months": [[r["mon"][:7],
                         round(100 * r["vd_over_cap"] / r["vessel_days"], 3),
                         r["dup_month"]] for r in rows],
             "worst": {"month": worst["mon"][:7],
                       "times": round(worst["max_msgs"] / CAP_A, 1)}}, rows, worst)


# ------------------------------------------------------------------- I8 ----
def mirror(ch):
    """Where the first store put Copenhagen, computed rather than asserted.

    scripts/ch.sh pins geoToH3 to (lat, lon). Handing it (lon, lat) IS the bug,
    so the mirrored cell is produced by doing exactly that, and h3ToGeo gives
    back its centre. Both points then go on a sketch of the world.
    """
    lat, lon = CPH
    got = ch("-q", f"SELECT h3ToGeo(geoToH3({lon}, {lat}, 5)), "
                   f"h3ToGeo(geoToH3({lat}, {lon}, 5))")[0]
    wrong, right = ([round(float(v), 2) for v in g.strip("()").split(",")]
                    for g in got)
    assert abs(right[0] - lat) < 0.5 and abs(right[1] - lon) < 0.5, \
        f"the pinned geoToH3 no longer round-trips Copenhagen: {right}"
    return {"cph": right, "mirrored": wrong, "land": coastline()}


def coastline(step=2):
    """A world coastline small enough to inline: Natural Earth 1:10 m land,
    10 MB on disk, snapped to a `step`-degree grid — 75 rings, 5 783 points,
    53 KB of JSON.

    Snapping, rather than Douglas-Peucker, is the whole simplification: round
    every vertex to the grid, drop the ones that then repeat, drop a ring left
    with fewer than four points or spanning less than six degrees in total.
    Holes go with them. Chart I8's subject is two dots and the distance between
    them; it needs the continents recognisable and nothing more.
    """
    src = json.loads((ROOT / "data" / "context" / "ne_10m_land.geojson").read_text())
    out = []
    for feature in src["features"]:
        geom = feature["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        for poly in polys:
            ring, prev = [], None
            for lon, lat in poly[0]:
                p = [round(lon / step) * step, round(lat / step) * step]
                if p != prev:
                    ring.append(p)
                    prev = p
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            if len(ring) >= 4 and max(xs) - min(xs) + max(ys) - min(ys) >= 6:
                out.append(ring)
    return out


# ----------------------------------------------------------------- prose ----
def hidden(ch):
    """sql/44 -> the share of ferry vessel-days filed as something other than a
    passenger ship, in the last year the store holds whole."""
    rows = [typed(H1, r, H1_INT) for r in
            blocks(ch("44_hidden_fleet.sql"), "sql/44_hidden_fleet.sql")[6]]
    return next(r for r in rows if r["year"] == 2025)


def scale(ch):
    """What was actually loaded, and how big the result is.

    THE PAGE MUST NOT SAY "ELEVEN YEARS". The store holds 2 122 calendar days
    between 2015-01-01 and 2026-08-26, which is six years' worth spread over
    twelve: 2015, 2018, 2021 and 2025 whole, 2024 from March, 2026 to August,
    and two winter months of storms in 2022 and 2023. Every one of those
    numbers is counted here rather than typed, because the last version of this
    page rounded it up to "eleven years of ship radio" and that was false.

    `du` runs on the store this build is actually reading, so the size
    describes this machine rather than a sentence in a document.
    """
    read, kept = ch("-q", "SELECT round(sum(rows_read)/1e9, 1), "
                          "round(sum(rows_kept)/1e9, 1) FROM load_log")[0]
    cal = ch("-q", "SELECT toYear(day), count(), max(day) FROM (SELECT DISTINCT "
                   "day FROM vessel_day) GROUP BY 1 ORDER BY 1")
    days = {int(y): int(n) for y, n, _ in cal}
    last = datetime.date.fromisoformat(cal[-1][2])
    store = ROOT / os.environ.get("CH_PATH", "data/ch")
    return {"read_billion": float(read), "kept_billion": float(kept),
            "days": sum(days.values()),
            "last_day": f"{last:%-d %B %Y}",
            "years_worth": round(sum(days.values()) / 365.25),
            "years_spanned": max(days) - min(days) + 1,
            "main_years": sum(1 for n in days.values() if n >= 200),
            "store_gb": round(sum(f.stat().st_size for f in store.rglob("*")
                                  if f.is_file()) / 2 ** 30)}


def hidden_ship(ch):
    """sql/44 block 3 -> the single ship the archive hides best.

    Block 3 is per (vessel, year) and only for the days a ferry was filed as
    something other than a passenger ship, so summing a vessel's days over the
    loaded years and taking the largest gives the worst case with its own name
    on it. Ferries are public and may be named (CLAUDE.md), which is the whole
    reason this paragraph can be concrete instead of a percentage.
    """
    rows = [typed(H3, r, H3_INT) for r in
            blocks(ch("44_hidden_fleet.sql"), "sql/44_hidden_fleet.sql")[7]]
    by = defaultdict(lambda: {"days": 0, "years": set()})
    for r in rows:
        v = by[(r["vessel"], r["line"], r["island"])]
        v["days"] += r["hidden_days"]
        v["years"].add(r["year"])
        v["type"] = r["dominant_hidden_type"]
    (vessel, line, island), worst = max(by.items(), key=lambda kv: kv[1]["days"])
    return {"vessel": vessel, "line": line, "island": island,
            "days": worst["days"], "years": len(worst["years"]),
            "type": worst["type"]}


def km_apart(a, b):
    """Great-circle kilometres between two (lat, lon) points — how far the
    mirrored grid moved Copenhagen, so the page does not have to say
    "a few hundred miles" and mean six thousand kilometres."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    d = math.radians(b[1] - a[1])
    return round(6371 * math.acos(min(1, math.sin(p1) * math.sin(p2)
                                      + math.cos(p1) * math.cos(p2) * math.cos(d))))


# ------------------------------------------------------------------ page ----
def build(ch):
    charts = {"season": season(ch)}
    charts["fleet"], win = fleet(ch)
    charts["flags"] = flags(ch)
    charts["storms"], charts["onset"], ferry, onsets = storms(ch)
    charts["impossible"], months, worst = impossible(ch)
    charts["mirror"] = mirror(ch)
    hid, ship, size = hidden(ch), hidden_ship(ch), scale(ch)

    peak = max(charts["season"]["2026"], key=lambda p: p[1])[1]
    first = max(charts["season"]["2015"], key=lambda p: p[1])[1]

    # Act 2 is written about whichever storm chart I4 opens on, so its numbers
    # come out of that panel rather than being typed for a storm that may not
    # be the one on screen.
    name = charts["storms"]["default"]
    panel = charts["storms"]["panels"][name]
    shape = drop(panel)
    day0 = {f: next(v for o, v, _h in pts if o == 0)
            for f, pts in panel["lines"].items()}
    before = {f: next(v for o, v, _h in pts if o == -1)
              for f, pts in panel["lines"].items()}
    now, ref = ferry[name]
    start = datetime.date.fromisoformat(panel["start"])
    end = start + datetime.timedelta(days=panel["days"] - 1)
    when = (f"{start.day}\u2013{end:%-d %B %Y}" if panel["days"] > 1
            else f"{start:%-d %B %Y}")
    pia_low = drop(charts["storms"]["panels"]["Pia"])["low"]

    # `dup_month` flags 2015-08 and 2015-09, the other duplication event, which
    # this same ceiling test finds unaided — that is what validates the test
    # (finding 59) and it is why those two months are not part of "before".
    clean = [r for r in months if r["mon"] < "2023-01-01" and not r["dup_month"]]
    recent = [r for r in months if r["mon"] >= "2023-12-01"]
    row = {r["fleet"]: r for r in charts["onset"]["rows"]}
    sailing_hours, sailing_when = onset_words(onsets["leisure"])
    flag = charts["flags"]["shares"]

    charts["n"] = {
        # what was loaded, and how big it is
        "days_loaded": sp(size["days"]),
        "last_day": size["last_day"],
        "years_worth": str(size["years_worth"]),
        "years_spanned": str(size["years_spanned"]),
        "rows_billion": f"{size['read_billion']:.0f}",
        "store_gb": str(size["store_gb"]),
        "k_floor": str(K_FLOOR),
        # I1 — the season
        "peak_2026": sp(peak),
        "peak_2015": sp(first),
        "season_growth": f"{peak / first:.1f}",
        # I2 — the fleet against the instrument
        "boats_2015": sp(win[2015]["class_b_leisure_vessels"]),
        "boats_2026": sp(win[2026]["class_b_leisure_vessels"]),
        "boats_growth": f"{win[2026]['class_b_leisure_vessels'] / win[2015]['class_b_leisure_vessels']:.1f}",
        "ships_2015": sp(win[2015]["class_a_vessels_5d"]),
        "ships_2026": sp(win[2026]["class_a_vessels_5d"]),
        "boats_per_ship_2015": f"{win[2015]['leisure_per_class_a_5d']:.1f}",
        "boats_per_ship_2026": f"{win[2026]['leisure_per_class_a_5d']:.1f}",
        # I3 — the flags
        "german_2026": f"{flag['German'][-1]:.0f}",
        "danish_2026": f"{flag['Danish'][-1]:.0f}",
        "swedish_2026": f"{flag['Swedish'][-1]:.0f}",
        "norwegian_2026": f"{flag['Norwegian'][-1]:.0f}",
        "dutch_2026": f"{flag['Dutch'][-1]:.0f}",
        # I4, I5, I6 — the storms
        "storm_count": str(charts["onset"]["of"]),
        "storm_window_days": str(WINDOW_DAYS),
        "storm_name": name,
        "storm_when": when,
        "storm_fishing_first": f"{panel['lines']['fishing'][0][1]:.0f}",
        "storm_fishing_low": f"{shape['low']:.0f}",
        "storm_cargo_day": f"{day0['cargo']:.0f}",
        "storm_cargo_usual": f"{panel['usual']['cargo']:.0f}",
        "storm_sailing_before": f"{before['sailing']:.0f}",
        "storm_sailing_day": f"{day0['sailing']:.0f}",
        "storm_ferry_now": sp(now),
        "storm_ferry_ref": sp(ref),
        "storm_ferry_share": f"{100 * now / ref:.0f}",
        "pia_fishing_low": f"{pia_low:.0f}",
        "cargo_storms": str(row["cargo"]["storms"]),
        "ferry_hours": str(row["ferries"]["hour"]),
        "ferry_storms": str(row["ferries"]["storms"]),
        "sailing_storms": str(len(charts["storms"]["sailing_shown"])),
        # how many hours, and which side of the storm's first midnight — both
        # from site_data.onset_words, so this page and site/storms.html cannot
        # say "three hours before" and "about six hours in" about one fleet.
        "sailing_hours": sailing_hours,
        "sailing_when": sailing_when,
        # I7 — the impossible days
        "cap": sp(CAP_A),
        "cap_seconds": str(REPORT_SECONDS),
        "over_cap_before": f"{100 * max(r['vd_over_cap'] / r['vessel_days'] for r in clean):.2f}",
        "over_cap_now": f"{100 * max(r['vd_over_cap'] / r['vessel_days'] for r in recent):.1f}",
        "worst_times": f"{worst['max_msgs'] / CAP_A:.1f}",
        # I8 — the mirrored grid
        "reload_hours": str(RELOAD_HOURS),
        "mirror_lat": f"{charts['mirror']['mirrored'][0]:.0f}",
        "mirror_lon": f"{charts['mirror']['mirrored'][1]:.0f}",
        "mirror_km": sp(km_apart(charts["mirror"]["cph"],
                                 charts["mirror"]["mirrored"])),
        # the ferries nobody can see
        "hidden_share": f"{100 * hid['hidden_share']:.0f}",
        "hidden_fleet": sp(hid["fleet"]),
        "hidden_ship": ship["vessel"],
        "hidden_ship_line": ship["line"],
        "hidden_ship_island": ship["island"],
        "hidden_ship_type": ship["type"],
        "hidden_ship_days": sp(ship["days"]),
    }
    return charts
