"""site/storms.html — chapter four. Four figures, one dict.

The page opens with T2, the exact head count, and puts T1 under it as the
hour-by-hour detail — so the order here is not the order on the page.

    chart  what it says                              where the numbers come from
    T2     who was out at all, storm day vs usual    sql/52_who_stays.sql  block 1
    T1     one storm, hour by hour, all 14 selectable  sql/50_storm_window.sql
    T3     the anchorages do not fill                sql/51_anchorage_fill.sql b3
    T4     the animation                             site/media/storm-*.js (S14)
    prose  who stops first, and how many hours in    sql/50 + sql/52
    prose  the ferry timetable, thinned              sql/50, `ferry_crossings`
    prose  the quiet storm, the storm with no dip    sql/52 blocks 1 and 2

THE TWO INSTRUMENTS, and why the page never mixes them. T2 is the exact one:
a boat either covered a nautical mile that day or it did not, counted per boat
per day, and every magnitude the prose states as a fleet number comes from it.
T1 is a MESSAGE ratio: one fleet's moving messages against the same fleet's
moving messages at the same hour a fortnight earlier. Reporting rates differ
between fleets and rise with speed, so that number may be compared to the same
fleet's own quiet week and to nothing else — its shape is trustworthy and its
level is not. It is on the page for one thing the day count cannot give: WHEN
inside the day a fleet gives up. notes/ch04-findings.md § caveats is the long
version.

PRIVACY. The private fleet appears here as a SHARE and never as a count, and
in one figure only: T2's sailing dumbbell, the share of the boats heard that
covered a mile. It is drawn for the storms whose reference day had at least
LEISURE_FLOOR private boats covering a mile (S9's floor, read off sql/52) — in
a January gale the whole country has ten to twenty of them out and a ratio over
that is one marina's afternoon. T1 draws NO sailing line at all: hour by hour
that fleet swings from 5 % to 418 % inside one storm, which is true, useless
and distracting. No radio ID, name, position or track of a private boat is read
or written here.
"""
import datetime
import statistics
from collections import defaultdict

from . import (D1, D1_INT, FLEET_KEY, STOP_ORDER, W, W_INT, blocks, clips,
               hourly_series, onset, onset_words, private_count,
               sailing_storms, smooth5, sp, storms_named, typed)

D2 = ("storm peak_hour peak_offset_h peak_ratio mobile ship_group heard "
      "moving_share ref_heard ref_moving_share is_dip").split()
D2_INT = "peak_offset_h heard is_dip".split()
A3 = "storm name hour offset_h present still_share ref_hour ref_present".split()
A3_INT = "offset_h present".split()

# T1's default panel has to survive a screenshot with no caption, so it is
# chosen by the data rather than by taste: of the storms with a clean quiet
# week (see `overlaps`), the one whose fishing fleet was closest to an
# ordinary level before the storm, given that it then collapsed and came back.
DIP_CEILING = 40      # per cent of a normal day the fishing line must reach
RECOVERY = 0.5        # …and it must return to half its own pre-storm level

# The five Danish anchorages chapter 04 charts, in size order. The sixth
# labelled Danish one, the Øresund berth off Helsingør, holds one ship at a
# time and is empty a fortnight away; notes/plot_ch04.py drops it for the same
# reason and says so.
ANCHORAGES = ["Skagen Red", "Ålbæk Bugt", "Copenhagen roads – Øresund",
              "Øresund anchorage off Landskrona", "Isefjord entrance anchorage"]
ANCHOR_SHORT = {"Skagen Red": "Skagen Red",
                "Ålbæk Bugt": "Ålbæk Bugt",
                "Copenhagen roads – Øresund": "Copenhagen roads",
                "Øresund anchorage off Landskrona": "off Landskrona",
                "Isefjord entrance anchorage": "Isefjord entrance"}


def level(line, lo, hi):
    """The typical value of a smoothed line over an offset range, or None."""
    v = [y for x, y in line if lo <= x <= hi]
    return statistics.median(v) if v else None


def window(ch):
    """sql/50 -> the hourly rows, each storm's length, and its first date.

    The storm-day count is read off the window (72 h before the first date to
    72 h after the last), not off storms.csv: Alfrida comes out at 0 because
    2019 is unloaded and only its three run-up days survive, and that is what
    drops it — a fact about the store, not a name in a list.
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
    return rows, ndays, start


def overlaps(rows, ndays):
    """The two ways a storm in this archive is not independent of another one,
    both of them measured rather than listed — a storm loaded later could join
    either. sql/50's header measures the same two.

    Returns {storm: [note, …]} for the panels, and the same storms are the ones
    T1's default may not be drawn from: on a panel whose 100 % belongs partly
    to another storm, 100 % is not an ordinary week.

      * the fortnight-away hours fall inside another storm's window — the
        panel's own reference is that storm's weather (Nora, inside Malik);
      * the windows themselves overlap, so the shared hours are drawn twice
        under two names (Gorm and Helga, five days apart).
    """
    hours, refs = defaultdict(set), defaultdict(set)
    for r in rows:
        if not ndays.get(r["storm"]):
            continue
        hours[r["storm"]].add(r["hour"])
        if r["ref_hour"] != "\\N":
            refs[r["storm"]].add(r["ref_hour"])

    out = defaultdict(list)
    for storm in hours:
        for other in hours:
            if other == storm:
                continue
            if refs[storm] & hours[other]:
                out[storm].append(
                    f"its quiet fortnight away is {other}'s own week, so this "
                    f"panel's 100 % is lower than a calm week would be")
            if hours[storm] & hours[other]:
                out[storm].append(
                    f"its window overlaps {other}'s — the days they share are "
                    f"drawn on both panels")
    return out


# ------------------------------------------------------------------- T1 ----
def panels(ch, rows, ndays, start, overlap, no_dip):
    """One panel per observed storm: each PUBLIC fleet's hourly movement as a
    share of a normal day, and the honest note that panel needs.

    THE SAILING FLEET IS NOT DRAWN HERE and that is deliberate. Hour by hour it
    is a ratio over a few dozen boats and it swings from 5 % to 418 % inside one
    storm — true, useless, and it pulls the eye off the claim. Counted by the
    boat over a whole day it is the sharpest signal in the chapter, which is
    what T2 draws. site_data.onset still pools it, because the hour a fleet
    halves is a comparison against its own quiet week and survives the noise.
    """
    series = hourly_series(rows)

    out = {}
    for storm, n in sorted(ndays.items()):
        if not n:
            continue
        lines = {FLEET_KEY[g]: smooth5(series[(storm, g)], -72, 24 * n + 71)
                 for g in STOP_ORDER if g != "leisure"}
        first = datetime.date.fromisoformat(start[storm])
        notes = []
        if storm in no_dip:
            notes.append("there is no dip here at all — on this storm's own "
                         "date the country's commercial fleet was moving more "
                         "than it was a fortnight before")
        if n > 1 and "·" in storm:
            notes.append("two storms the weather service named separately, "
                         "three days end to end")
        notes += overlap.get(storm, [])
        # a calendar fact about the window, not an opinion about the storm
        if any((first + datetime.timedelta(days=d)).strftime("%m-%d")
               in ("12-24", "12-25", "12-26") for d in range(n, n + 4)):
            notes.append("the days after it are Christmas, and the country "
                         "stops for that too")
        out[storm] = {"days": n, "start": start[storm], "lines": lines,
                      "notes": notes}
    return out, series


def arc(panel):
    """How much of the whole story a panel's fishing line tells: the smaller of
    the fall into the storm and the climb back out of it. The clip that opens
    T4 is the one with the biggest arc, not the deepest fall — the deepest is
    Pia, whose "after" is Christmas, and a clip whose sea never fills again
    makes its own headline false. The same rule index.py uses for I6."""
    fish, n = panel["lines"]["fishing"], panel["days"]
    pre, post = level(fish, -72, -25), level(fish, 24 * n + 24, 24 * n + 71)
    dip = min((y for x, y in fish if 0 <= x < 24 * n), default=None)
    if None in (pre, post, dip):
        return float("-inf")
    return min(pre - dip, post - dip)


def pick_default(panels_, borrowed):
    """T1's opening panel, chosen by the data.

    A screenshot of this figure has to carry the sentence on its own, so the
    panel wants a fishing line that starts at an ordinary level, falls to
    almost nothing and comes back. Storms that share hours with another storm
    are out of the running — their 100 % is not 100 % (see `overlaps`).
    """
    scored = []
    for storm, p in panels_.items():
        if storm in borrowed:
            continue
        fish = p["lines"]["fishing"]
        n = p["days"]
        pre = level(fish, -72, -25)
        dip = min((y for x, y in fish if 0 <= x < 24 * n), default=None)
        post = level(fish, 24 * n + 24, 24 * n + 71)
        if pre is None or dip is None or post is None:
            continue
        if dip <= DIP_CEILING and post >= RECOVERY * pre:
            scored.append((abs(pre - 100), storm, pre, dip, post))
    assert scored, "no storm has a clean run-up, a collapse and a recovery"
    return min(scored), sorted(scored)


# ------------------------------------------------------------------- T2 ----
def moved(ch, ndays):
    """sql/52 block 1 -> per storm and fleet, the share of the boats heard
    that covered at least a nautical mile, on the storm's own dates and on the
    days a fortnight away.

    Pooled over the storm's dates as a ratio of sums, not a mean of daily
    shares: a three-day storm has one busy date and two quiet ones and the
    mean of the shares would weight them equally.
    """
    day = [typed(D1, r, D1_INT) for r in
           blocks(ch("52_who_stays.sql"), "sql/52_who_stays.sql")[12]]
    pool = defaultdict(lambda: [0, 0, 0, 0])
    winter = []
    for r in day:
        n = ndays.get(r["storm"], 0)
        own = n and 0 <= r["offset_d"] < n
        if own and r["ref_moved"] is not None:
            p = pool[(r["storm"], r["mobile"], r["ship_group"])]
            p[0] += r["moved"]
            p[1] += r["heard"]
            p[2] += r["ref_moved"]
            p[3] += r["ref_heard"]
        if (r["mobile"] == "Class B" and r["ship_group"] == "leisure"
                and r["day"][5:7] in ("12", "01", "02")):
            winter.append(r["moved"])
    return pool, day, sorted(winter)


def share(pool, storm, group, mobile="Class A"):
    """(a usual day, the storm's own dates) as shares, or None."""
    now, heard, ref, ref_heard = pool[(storm, mobile, group)]
    if not heard or not ref_heard:
        return None
    return [round(ref / ref_heard, 4), round(now / heard, 4)]


# ------------------------------------------------------------------- T3 ----
def anchorages(ch, ndays):
    """sql/51 block 3 -> per storm and anchorage, how full it was during the
    storm's own hours against the 72 hours before them.

    Block 3 is only sound with block 2 — the labelling guard — ahead of it in
    the same run, which is why the whole file is run and only its third block
    read. The guard is block 2's single column and it must read 1.
    """
    guard, prof = None, []
    for r in ch("51_anchorage_fill.sql"):
        if len(r) == 1:
            guard = int(r[0])
        elif len(r) == 8:
            prof.append(typed(A3, r, A3_INT))
    assert guard == 1, \
        (f"sql/51's labelling guard returned {guard}, not 1 — an unlabelled "
         f"anchorage would ride into this chart unnoticed")

    by = defaultdict(dict)
    for r in prof:
        by[(r["storm"], r["name"])][r["offset_h"]] = r["present"]

    out = []
    for storm, n in sorted(ndays.items()):
        if not n:
            continue
        for name in ANCHORAGES:
            p = by.get((storm, name))
            if not p:
                continue
            pre = [v for o, v in p.items() if o < 0]
            sto = [v for o, v in p.items() if 0 <= o < 24 * n]
            if not (pre and sto and statistics.mean(pre)):
                continue
            out.append({"storm": storm, "name": ANCHOR_SHORT[name],
                        "pre": round(statistics.mean(pre), 2),
                        "during": round(statistics.mean(sto), 2),
                        "ratio": round(statistics.mean(sto) / statistics.mean(pre), 3)})
    return out


# ------------------------------------------------------------------ page ----
def build(ch):
    rows, ndays, start = window(ch)
    pool, day_rows, winter = moved(ch, ndays)
    sailing_ok = sailing_storms(day_rows, ndays)
    overlap = overlaps(rows, ndays)

    # the derived peak hour, and the storms that have no dip on their own date:
    # read before the panels, because a no-dip storm needs saying so on its own
    # panel and not only in the prose
    peak = [typed(D2, r, D2_INT) for r in
            blocks(ch("52_who_stays.sql"), "sql/52_who_stays.sql")[11]]
    no_dip = sorted({r["storm"] for r in peak if not r["is_dip"]})
    clock = sorted(int(h[11:13]) for h in {r["peak_hour"] for r in peak})

    pans, series = panels(ch, rows, ndays, start, overlap, no_dip)
    # The hour each fleet halves, from site_data, with the sailing fleet
    # counted only over the storms that clear S9's floor — the same rule
    # site/index.html states, because it is the same measurement.
    onsets = onset(series, ndays, sailing_ok)
    sailing_hours, sailing_when = onset_words(onsets["leisure"])
    (_, default, pre, dip, post), scored = pick_default(pans, set(overlap))
    observed = sorted(pans)

    # T2: one row per storm, sorted by how much of the fishing fleet stayed in
    t2 = []
    for storm in observed:
        row = {"storm": storm, "start": start[storm]}
        for g in STOP_ORDER:
            if g == "leisure" and storm not in sailing_ok:
                continue
            v = share(pool, storm, g, "Class B" if g == "leisure" else "Class A")
            if v:
                row[FLEET_KEY[g]] = v
        t2.append(row)
    t2.sort(key=lambda r: r["fishing"][1] - r["fishing"][0])

    # T2's picture: of every hundred boats heard, how many covered a mile —
    # every storm pooled as one ratio of sums, public fleets only. Two fleets,
    # the two ends of the range; the rest are in the table.
    pooled = {}
    for g in ("fishing", "cargo"):
        s_ = [sum(pool[(st, "Class A", g)][i] for st in observed) for i in range(4)]
        pooled[FLEET_KEY[g]] = [round(100 * s_[2] / s_[3]), round(100 * s_[0] / s_[1])]

    anch = anchorages(ch, ndays)
    ratios = sorted(a["ratio"] for a in anch)

    # the ferry timetable: departures on the lines with a Danish end, over the
    # storm's own hours, against the same hours a fortnight away
    ferry = {}
    for storm in observed:
        rs = [r for r in rows if r["storm"] == storm and r["mobile"] == "Class A"
              and r["ship_group"] == "passenger"
              and 0 <= r["offset_h"] < 24 * ndays[storm]]
        now = sum(r["ferry_crossings"] for r in rs)
        ref = round(sum(r["ref_ferry_crossings"] or 0 for r in rs))
        ferry[storm] = (now, ref, now / ref if ref else None)
    worst_ferry = min(ferry, key=lambda s: ferry[s][2])

    # the fleet-wide spreads the prose quotes, off T2's exact instrument
    def spread(group):
        d = {s: share(pool, s, group)[1] - share(pool, s, group)[0]
             for s in observed if share(pool, s, group)}
        return d, min(d, key=d.get), max(d, key=d.get)

    fish, fish_worst, _ = spread("fishing")
    cargo, cargo_worst, cargo_best = spread("cargo")
    work, work_worst, _ = spread("other")
    ferries, _, _ = spread("passenger")

    # "the storm that shows nothing on any instrument" — every fleet AND the
    # ferry timetable, added up. A storm with no dip at all on its own date
    # (Floriane) is disqualified rather than crowned: it is a different claim,
    # and it is the one the paragraph above this makes.
    def flat(s):
        return (abs(fish[s]) + abs(cargo[s]) + abs(work[s]) + abs(ferries[s])
                + abs(1 - ferry[s][2]))
    quiet = min((s for s in observed if s not in no_dip), key=flat)
    dflt = pans[default]
    have = clips(pans)

    # What the hourly chart adds and the day count cannot: the fishing fleet is
    # already below its own quiet week by the first midnight of the date the
    # weather service named — before any of the storm has happened.
    zero = {s: dict(p["lines"]["fishing"]).get(0) for s, p in pans.items()}
    early = [s for s, v in zero.items()
             if v is not None and v < level(pans[s]["lines"]["fishing"], -72, -25)]

    data = {
        "t1": {"default": default, "panels": pans},
        "t2": {"rows": t2, "sailing": sailing_ok, "pooled": pooled},
        "t3": {"names": [ANCHOR_SHORT[n] for n in ANCHORAGES], "rows": anch},
        # the clip that opens: the one whose fishing line tells the whole arc
        # (see `arc`). The clips that exist, discovered once in site_data.clips — not a
        # literal here, a glob there and three <script> tags in the page. The
        # key comes back with the storm it belongs to, so the default is chosen
        # by looking a storm up rather than by k.capitalize(), which turns
        # "dagmaregon" into "Dagmaregon" and finds nothing.
        "t4": {"clips": list(have), "names": dict(have),
               "default": max(have, key=lambda k: arc(pans[have[k]]))},
    }
    data["n"] = {
        # the shape of the chapter
        # the list itself, counted: data/context/storms.csv
        "storms_named": str(storms_named()),
        "storm_windows": str(len(ndays)),
        "storm_count": str(len(observed)),
        # T1 — the default panel
        "default_storm": default,
        "default_pre": f"{pre:.0f}",
        "default_low": f"{dip:.0f}",
        "default_cargo": f"{level(dflt['lines']['cargo'], 0, 24 * dflt['days'] - 1):.0f}",
        "default_at_zero": f"{zero[default]:.0f}",
        "fish_early_storms": str(len(early)),
        "sailing_storms": str(len(sailing_ok)),
        # who stops first, and how many hours in
        "fishing_storms": str(len(onsets["fishing"])),
        "sailing_hours": sailing_hours,
        "sailing_when": sailing_when,
        "work_hours": str(round(statistics.median(onsets["other"]))),
        "ferry_hours": str(round(statistics.median(onsets["passenger"]))),
        "cargo_storms": str(len(onsets["cargo"])),
        # T2 — the exact instrument
        "fish_worst_storm": fish_worst,
        "fish_worst_ref": f"{100 * share(pool, fish_worst, 'fishing')[0]:.0f}",
        "fish_worst_now": f"{100 * share(pool, fish_worst, 'fishing')[1]:.0f}",
        "cargo_worst_storm": cargo_worst,
        "cargo_worst_ref": f"{100 * share(pool, cargo_worst, 'cargo')[0]:.0f}",
        "cargo_worst_now": f"{100 * share(pool, cargo_worst, 'cargo')[1]:.0f}",
        "cargo_best_storm": cargo_best,
        "fish_down_storms": str(sum(v < 0 for v in fish.values())),
        "work_down_storms": str(sum(v < 0 for v in work.values())),
        "work_worst_storm": work_worst,
        "no_dip_storm": no_dip[0] if no_dip else "none",
        "quiet_storm": quiet,
        "quiet_ferry_share": f"{100 * ferry[quiet][2]:.0f}",
        # the ferries
        "ferry_worst_storm": worst_ferry,
        "ferry_worst_now": sp(ferry[worst_ferry][0]),
        "ferry_worst_ref": sp(ferry[worst_ferry][1]),
        "ferry_worst_share": f"{100 * ferry[worst_ferry][2]:.0f}",
        # the sailing fleet in winter
        # The winter list itself runs down to nothing — these are the two
        # quartiles of 68 whole days, and they go through the floor so that a
        # winter quiet enough to put Q1 under five boats stops the build
        # instead of printing it.
        "winter_sailing_lo": str(private_count(
            round(statistics.quantiles(winter, n=4)[0]),
            "the quiet quarter of a winter day's private fleet")),
        "winter_sailing_hi": str(private_count(
            round(statistics.quantiles(winter, n=4)[2]),
            "the busy quarter of a winter day's private fleet")),
        # T3 — the anchorages
        "anchorage_cells": str(len(anch)),
        "anchorage_mid": f"{statistics.median(ratios):.2f}",
        "anchorage_near": str(sum(0.8 <= r <= 1.2 for r in ratios)),
        "anchorage_low_storm": min(anch, key=lambda a: a["ratio"])["storm"],
        "anchorage_low_pre": f"{min(anch, key=lambda a: a['ratio'])['pre']:.0f}",
        "anchorage_low_during": f"{min(anch, key=lambda a: a['ratio'])['during']:.0f}",
        "skagen_mid": f"{statistics.median([a['ratio'] for a in anch if a['name'] == 'Skagen Red']):.2f}",
        # the derived hour
        "peak_early": str(min(clock)),
        "peak_late": str(max(clock)),
    }

    # the ledger a reviewer reads: how the default panel was chosen, and what
    # it was chosen against.
    print("\n  T1 default candidates (|pre-100|, storm, pre, dip, recovery):")
    for s in scored:
        print(f"    {s[1]:14s} |pre-100| {s[0]:6.1f}   pre {s[2]:6.1f} "
              f"dip {s[3]:5.1f} back {s[4]:6.1f}")
    print(f"    chosen: {default}; not eligible, hours shared with another "
          f"storm: {', '.join(sorted(overlap)) or 'none'}")
    print(f"  T2 fishing falls on {sum(v < 0 for v in fish.values())} of "
          f"{len(fish)} storms, cargo on {sum(v < 0 for v in cargo.values())}")
    print(f"  T3 {len(anch)} storm x anchorage cells, "
          f"middle ratio {statistics.median(ratios):.3f}, "
          f"range {min(ratios):.2f}..{max(ratios):.2f}")
    return data
