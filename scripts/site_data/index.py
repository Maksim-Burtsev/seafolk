"""site/index.html — the story page. Seven charts, one dict.

Every number the page shows is computed here from the store, through the query
files the chapters already use. Nothing on this page is hand-typed.

    chart  what it says                        where the numbers come from
    I1     the season, one line per year       sql/10_season_daily.sql
    I2     small boats tripled, ships did not  sql/61_adoption.sql   block 1
    I3     whose boats these are               sql/80_site_flags.sql
    I4     every storm at once, two fleets     sql/52_who_stays.sql  block 1
    I5     who stays in on a storm day         sql/52_who_stays.sql  block 1
    I7     a day that cannot happen            sql/60_coverage_index.sql block 6
    T4     storm Amy, three chart sheets      site/media/charts, scripts/charts_storms.py
    prose  the ferry nobody can see            sql/44_hidden_fleet.sql   block 3
    prose  what was loaded, and how big        vessel_day, load_log, du

ROUND 2 (docs/SITE.md § Round 2). The story page carries no buttons: I4 is one
static chart over every usable storm, and I5's onset strip is gone, replaced by
five bars. The Arabian-Sea sketch (I8) is off the story and survives as one
paragraph on how.html.

PRIVACY. The private fleet appears here at two head-count grains and no others:
a store-wide daily count (I1 — minimum 12 boats, on a January day in 2015,
measured in sql/20's header) and a store-wide yearly count (I2 — minimum
6 137). I4 draws public fleets only. I5's sailing bar is a share divided by a
share, pooled over the three storms whose reference days had enough boats out
to mean anything (S9's floor: 250 boats that covered a mile, read off sql/52),
and no count behind it reaches the page. No MMSI, name, callsign, position or
track of a private boat is read or written here.
"""
import datetime
import os
import statistics
from collections import defaultdict

from . import (A1, A1_INT, A4, B6, B6_INT, CAP_A, D1, D1_INT, FLEET_KEY,
               FLEET_NAME, H1, H1_INT, H3, H3_INT, K_FLOOR, REPORT_SECONDS,
               ROOT, STOP_ORDER, W, W_INT, WINDOW_DAYS, YEARS, blocks, clips,
               hourly_series, onset, onset_words, private_count,
               sailing_storms, sp, typed)

FL = "year flag share".split()

# Chart I4's x axis: the three days before a storm's FIRST date, that date, and
# the three days after. A storm that lasted two days has its second day inside
# the window like any other day; the caption says the alignment is on the first.
OFFSETS = list(range(-WINDOW_DAYS, WINDOW_DAYS + 1))


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
    """sql/50 + sql/52 -> charts I4 and I5, the ferry timetable's cost, and the
    hour each fleet goes in.

    The storm-day count is read off sql/50's window rather than off storms.csv:
    the window runs from 72 h before the first date to 72 h after the last, so
    n = (max offset + 1 - 72) / 24. Alfrida comes out at 0 — 2019 is not in the
    store, so only its three run-up days survive and the storm itself was never
    observed. That is what drops it, rather than a name in a list.
    """
    rows, off = [], defaultdict(set)
    for r in ch("50_storm_window.sql"):
        row = typed(W, r, W_INT)
        rows.append(row)
        off[row["storm"]].add(row["offset_h"])
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
    onsets = onset(hourly_series(rows), ndays, sailing_ok)

    # The ferry timetable, POOLED the way every other number in Act 2 now is:
    # departures on the storms' own days against the same days a fortnight
    # away, summed over every observed storm rather than read off one.
    now = ref = 0
    for r in rows:
        if (r["mobile"] == "Class A" and r["ship_group"] == "passenger"
                and 0 <= r["offset_h"] < 24 * ndays.get(r["storm"], 0)):
            now += r["ferry_crossings"]
            ref += r["ref_ferry_crossings"] or 0

    curves = storm_curves(day_rows, ndays)
    return (curves, stayed_in(day_rows, ndays, sailing_ok),
            (now, round(ref)), onsets, len(observed))


# ------------------------------------------------------------------- I4 ----
def storm_curves(day_rows, ndays):
    """sql/52 block 1 -> chart I4: of every hundred boats the radio heard that
    day, how many went somewhere — every storm, and the mean of them.

    "Went somewhere" is sql/52's definition and it is an exact count, not a
    message rate: a vessel whose positions that day add up to at least one
    nautical mile. Both halves of the fraction are `uniqExact` over the same
    day's own fleet, so there is no reference fortnight in this chart at all —
    an earlier version divided each hour by the same hour two weeks earlier,
    and a reader cannot read a baseline that is itself weather.

    A storm is in the chart only if BOTH fleets have all seven days of the
    window, so the two means are drawn over one set of storms and a hole in
    the calendar cannot make one of them step. Public fleets only.
    """
    by = defaultdict(dict)
    for r in day_rows:
        g = r["ship_group"]
        if (g in ("fishing", "cargo") and r["mobile"] == "Class A"
                and ndays.get(r["storm"], 0) > 0 and r["offset_d"] in OFFSETS):
            by[(g, r["storm"])][r["offset_d"]] = round(100 * r["share_moved"], 1)

    whole = sorted({s for _g, s in by
                    if all(len(by.get((g, s), {})) == len(OFFSETS)
                           for g in ("fishing", "cargo"))})
    assert len(whole) >= 5, \
        f"only {len(whole)} storms have a whole window — a mean of that is one storm"

    out = {"offsets": OFFSETS, "storms": whole}
    for g in ("fishing", "cargo"):
        out[FLEET_KEY[g]] = {
            "mean": [[o, round(statistics.mean(by[(g, s)][o] for s in whole), 1)]
                     for o in OFFSETS],
            "each": [[[o, by[(g, s)][o]] for o in OFFSETS] for s in whole]}
    return out


# ------------------------------------------------------------------- I5 ----
def stayed_in(day_rows, ndays, sailing_ok):
    """sql/52 block 1 -> chart I5: of every hundred boats of a fleet that go out
    on a usual day, how many stayed in on a storm day.

    One number per fleet, pooled over the storms: sum the boats that moved and
    the boats heard across every storm's own dates, do the same for those days'
    reference days a fortnight away, and the answer is

        1 - (moved / heard on the storm days) / (the same on the usual days)

    Pooled rather than averaged per storm, so a small storm does not weigh the
    same as a large one. A row is dropped from both halves unless the day has a
    reference day at all, which keeps numerator and denominator over one set of
    days.

    PRIVACY. The sailing fleet is measured over the three storms that clear
    S9's floor and NOTHING BUT THE SHARE LEAVES THIS FUNCTION — the counts it
    is divided from stay here, and go through private_count on the way past.
    """
    tot = defaultdict(lambda: [0, 0, 0.0, 0.0, set()])
    for r in day_rows:
        g = r["ship_group"]
        if r["mobile"] != ("Class B" if g == "leisure" else "Class A"):
            continue
        if not 0 <= r["offset_d"] < ndays.get(r["storm"], 0):
            continue
        if g == "leisure" and r["storm"] not in sailing_ok:
            continue
        if r["ref_share_moved"] is None or not r["ref_heard"]:
            continue
        t = tot[g]
        t[0] += r["moved"]
        t[1] += r["heard"]
        t[2] += r["ref_moved"]
        t[3] += r["ref_heard"]
        t[4].add(r["storm"])

    rows = []
    for g in STOP_ORDER:
        moved, heard, ref_moved, ref_heard, seen = tot[g]
        if g == "leisure":
            private_count(moved, "sql/52 pooled: small boats that moved")
            private_count(heard, "sql/52 pooled: small boats heard")
        rows.append({"fleet": FLEET_KEY[g], "label": FLEET_NAME[g],
                     "storms": len(seen),
                     "value": round(100 * (1 - (moved / heard)
                                           / (ref_moved / ref_heard)), 1)})
    return sorted(rows, key=lambda r: -r["value"])


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
             # the two bars: what the radio can send in a day, and the most one
             # ship's day in this archive actually holds.
             "worst": {"month": worst["mon"][:7], "msgs": worst["max_msgs"],
                       "times": round(worst["max_msgs"] / CAP_A, 1)}}, rows, worst)


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


# ------------------------------------------------------------------ page ----
def build(ch):
    charts = {"season": season(ch)}
    charts["fleet"], win = fleet(ch)
    charts["flags"] = flags(ch)
    charts["storms"], charts["stayed"], ferry, onsets, observed = storms(ch)
    charts["impossible"], months, worst = impossible(ch)
    hid, ship, size = hidden(ch), hidden_ship(ch), scale(ch)

    peak = max(charts["season"]["2026"], key=lambda p: p[1])[1]
    first = max(charts["season"]["2015"], key=lambda p: p[1])[1]

    # Act 2 is written about the POOLED chart, so its numbers are read off the
    # two mean lines that are actually on screen rather than off one storm
    # somebody chose. Pia is the one storm named in the prose and its own line
    # is read out of the same block the chart draws.
    S = charts["storms"]
    mean = {f: dict(S[f]["mean"]) for f in ("fishing", "cargo")}
    pia = dict(S["fishing"]["each"][S["storms"].index("Pia")])
    now, ref = ferry
    bar = {r["fleet"]: r for r in charts["stayed"]}
    # Act 2 says "every one of them" about the storms in chart I4. That is true
    # only while every observed storm has a whole seven-day window; if one ever
    # loses a day, the sentence has to change and this stops the build first.
    assert len(S["storms"]) == observed, (
        f'chart I4 draws {len(S["storms"])} of {observed} observed storms — the '
        f'page says "every one of them"; give the count a data-n span again')

    # `dup_month` flags 2015-08 and 2015-09, the other duplication event, which
    # this same ceiling test finds unaided — that is what validates the test
    # (finding 59) and it is why those two months are not part of "before".
    clean = [r for r in months if r["mon"] < "2023-01-01" and not r["dup_month"]]
    recent = [r for r in months if r["mon"] >= "2023-12-01"]
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
        "storm_count": str(observed),
        "storm_fishing_before": f"{mean['fishing'][-WINDOW_DAYS]:.0f}",
        "storm_fishing_day": f"{mean['fishing'][0]:.0f}",
        "storm_cargo_before": f"{mean['cargo'][-WINDOW_DAYS]:.0f}",
        "storm_cargo_day": f"{mean['cargo'][0]:.0f}",
        "pia_fishing_low": f"{min(pia.values()):.0f}",
        "stayed_fishing": f"{bar['fishing']['value']:.0f}",
        "stayed_cargo": f"{bar['cargo']['value']:.0f}",
        "storm_ferry_now": sp(now),
        "storm_ferry_ref": sp(ref),
        "storm_ferry_share": f"{100 * now / ref:.0f}",
        # how many hours, and which side of the storm's first midnight — both
        # from site_data.onset_words, so this page and site/storms.html cannot
        # say "three hours before" and "about six hours in" about one fleet.
        "sailing_hours": sailing_hours,
        "sailing_when": sailing_when,
        # I7 — a day that cannot happen
        "cap": sp(CAP_A),
        "cap_seconds": str(REPORT_SECONDS),
        "over_cap_before": f"{100 * max(r['vd_over_cap'] / r['vessel_days'] for r in clean):.2f}",
        "over_cap_now": f"{100 * max(r['vd_over_cap'] / r['vessel_days'] for r in recent):.1f}",
        "worst_msgs": sp(worst["max_msgs"]),
        "worst_times": f"{worst['max_msgs'] / CAP_A:.1f}",
        # the ferries nobody can see
        "hidden_share": f"{100 * hid['hidden_share']:.0f}",
        "hidden_fleet": sp(hid["fleet"]),
        "hidden_ship": ship["vessel"],
        "hidden_ship_line": ship["line"],
        "hidden_ship_island": ship["island"],
        "hidden_ship_type": ship["type"],
        "hidden_ship_days": sp(ship["days"]),
    }
    # Round 4: the site is this one page. The old chapters are its parts —
    # site_data/_<part>.py, skipped by the driver's discovery — and each part's
    # numbers arrive here as "<part>_<key>", its figures' data as "part_<part>".
    # Only the parts the page draws from; _season and _storms stay importable
    # for the chart builders' constants and for whoever brings a part back.
    from . import _ferries, _how, _pulse
    for name, part in (("pulse", _pulse), ("ferries", _ferries), ("how", _how)):
        d = part.build(ch)
        charts["n"].update({f"{name}_{k}": v for k, v in d.pop("n", {}).items()})
        charts[f"part_{name}"] = d
    return charts
