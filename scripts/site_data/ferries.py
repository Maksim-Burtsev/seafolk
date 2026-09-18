"""site/ferries.html — the island ferries. Four charts, one dict.

Everything on the page comes out of three query files the chapter already
uses, run through scripts/ch.sh. No new SQL: sql/41 carries the crossings and
the coverage columns, sql/42 the crossing times, sql/44 the fleet nobody can
see.

    chart  what it says                            where the numbers come from
    F1     one island's year, day by day           sql/41_ferry_daily.sql
    F2     the winter timetable, line by line      sql/41_ferry_daily.sql
    F3     storms: small lines against big ones    sql/41 + data/context/storms.csv
    F4     the battery ferry's crossing, in min    sql/42_ferry_speed.sql
    prose  the ferries the archive cannot see      sql/44_hidden_fleet.sql
    prose  the timetable check                     sql/41 + ferry_timetable.csv

PRIVACY. Ferries are public vessels and CLAUDE.md allows them to be named;
sql/41 emits no vessel at all and sql/42 emits the modal ship's NAME, never its
radio ID. The one trap on this page is not privacy but the line label: sql/40
used to fall back to `way:<id>` for an unmapped OSM route, and an OSM id is
nine digits — the same shape as a radio ID, and the build's guard cannot tell
them apart. `check_labels` refuses any label with nine digits in it, so an
unmapped route fails the build here rather than being reported as a privacy
breach there.
"""
import collections
import csv
import datetime
import statistics

from . import ROOT, blocks, typed

# The six years the store holds whole or nearly so; 2022 and 2023 are 59-day
# winter windows and belong in no per-year comparison. Same list as the chapter
# (notes/plot_ch03.py). The storm chart is the one place the windows are used,
# and there they are used as days, not as years.
YEARS = [2015, 2018, 2021, 2024, 2025, 2026]

# F1 draws one whole recent year. 2025 is the last one the archive holds end to
# end — 2026 stops on 26 August.
F1_YEAR = 2025

# The four biggest lines with one end in Denmark. The pooling in F3 is by SIZE,
# not by sql/41's `kind`: Køge – Rønne is an island line in ferry_lines.csv and
# is a big ship on a long crossing here.
BIG = ["Helsingør – Helsingborg", "Rødby – Puttgarden",
       "Køge – Rønne", "Gedser – Rostock"]

# F1's selector: a dozen island lines picked for range — the busiest line in
# the country, the thinnest, four that run much the same timetable all year,
# two excursion lines that all but close in winter, and Orø, whose spring refit
# is what a ship out of service looks like next to a storm.
F1_LINES = ["Frederikshavn – Vesterø Havn", "Svendborg – Ærøskøbing",
            "Hou – Sælvig", "Branden – Fur", "Grenaa – Anholt",
            "Kragenæs – Fejø", "Holbæk – Orø", "Havnsø – Sejerø",
            "Snaptun – Endelave", "Hou – Tunø", "Aalborg – Egholm",
            "Gudhjem – Christiansø"]
F1_DEFAULT = "Frederikshavn – Vesterø Havn"

# F2's floor, straight out of finding 26: the island lines that run ten or more
# crossings a day in July. Below that the typical day is two or three sailings
# and a "share of the summer timetable" is one sailing wide.
F2_FLOOR = 10

# F4's line. Søby – Fynshav is the reference case for a vessel replacement: one
# ship at a time in all six loaded years, and ten miles of water that never
# moves.
F4_LINE = "Søby – Fynshav"
F4_SHIP = "ELLEN"

# sql/41 gives a line its island; four labels would collide or mislead.
# Christiansø's island column says Bornholm (the line starts at Gudhjem), and
# Ærø has three separate lines to three different mainland ports.
LABEL = {"Gudhjem – Christiansø": "Christiansø",
         "Svendborg – Ærøskøbing": "Ærø (Ærøskøbing)",
         "Marstal – Rudkøbing": "Ærø (Marstal)",
         "Søby – Faaborg": "Ærø (Søby)"}

DAILY = ("line kind island day year season daytype dow crossings vessels "
         "routes baseline missed is_storm_day fleet_positions fleet_sog_known "
         "fleet_moving fleet_vessels").split()
DAILY_INT = ("year dow crossings vessels routes baseline missed is_storm_day "
             "fleet_positions fleet_sog_known fleet_moving fleet_vessels").split()
SPEED = ("line kind island year crossings vessels routes modal_vessel "
         "modal_share med_kn max_kn med_sog_kn med_min p10_min p90_min "
         "med_nm").split()
SPEED_INT = "year crossings vessels routes med_min p10_min p90_min".split()
HID = ("line kind island year fleet_vessels visible_days hidden_days "
       "hidden_share hidden_vessels").split()
HID_YEAR = ("year fleet_vessels visible_days hidden_days hidden_share "
            "hidden_vessels").split()
HID_INT = "year fleet_vessels visible_days hidden_days hidden_vessels".split()

MONTH = ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]
WORD = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
        12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
        16: "sixteen", 20: "twenty", 23: "twenty-three", 35: "thirty-five"}


def word(n):
    return WORD.get(n, str(n))


# ------------------------------------------------------------ the store ----
def day_state(row):
    """sql/41's four-word vocabulary for a line-day, in one letter.

    Straight off the header of sql/41, and it is the whole point of this page:

      s  sailed
      c  the fleet was heard, lay still all day, on a day of the week the line
         normally sails — the only thing here that is a cancellation
      o  the same, on a day of the week it does not sail: the timetable
      u  nothing usable was heard, or the fleet moved and no crossing matched —
         a day the data cannot judge, and NEVER a zero

    Grouping "moved, nothing matched" with silence is the conservative
    reading: the ferry was under way and this project could not tell where,
    which is the same admission as not having heard it at all.
    """
    if row["crossings"] > 0:
        return "s"
    if row["fleet_positions"] == 0 or row["fleet_sog_known"] == 0:
        return "u"
    if row["fleet_moving"] > 0:
        return "u"
    return "c" if row["baseline"] > 0 else "o"


def check_labels(lines):
    """No nine-digit integer in a line label. See this module's docstring."""
    for line in lines:
        digits = "".join(c if c.isdigit() else " " for c in line).split()
        assert not any(len(d) >= 9 for d in digits), \
            f"line label {line!r} holds a nine-digit integer — an unmapped route?"


def label_of(line, island):
    return LABEL.get(line) or island or line


def median_day(rows, pred=lambda r: True):
    """Typical crossings a day over the loaded years, days the fleet was HEARD.

    Silent days are excluded rather than counted as zero, for the same reason
    sql/41's own comparable-day figure excludes them: a receiver that heard
    nothing is not a ferry that did not sail.
    """
    vals = [r["crossings"] for r in rows
            if r["year"] in YEARS and r["fleet_positions"] > 0 and pred(r)]
    return statistics.median(vals) if vals else None


def july(rows):
    return median_day(rows, lambda r: r["day"][5:7] == "07"
                      and r["daytype"] == "weekday")


def january(rows):
    return median_day(rows, lambda r: r["day"][5:7] == "01"
                      and r["daytype"] == "weekday")


def _when(day, month=True):
    return f"{int(day[8:])} {MONTH[int(day[5:7]) - 1]}" if month else str(int(day[8:]))


def _delta(a, b):
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


# ------------------------------------------------------------------- F1 ----
def one_year(by_line, island_of, storm_named):
    """A dozen island lines, one calendar year each, day by day.

    The year is a fixed 365 slots so the strip is a calendar and not a list of
    rows: a day sql/41 has no row for — outside the line's own first-to-last
    crossing of that year — is drawn as unknown, like any other day the data
    cannot judge.
    """
    jan1 = datetime.date(F1_YEAR, 1, 1)
    ndays = (datetime.date(F1_YEAR + 1, 1, 1) - jan1).days
    out = {}
    for line in F1_LINES:
        have = {r["day"]: r for r in by_line[line] if r["year"] == F1_YEAR}
        assert len(have) > ndays - 12, \
            f"{line}: only {len(have)} days of {F1_YEAR} — not a whole year"
        counts, state, missed = [], [], []
        for i in range(ndays):
            day = (jan1 + datetime.timedelta(days=i)).isoformat()
            row = have.get(day)
            counts.append(row["crossings"] if row else 0)
            state.append(day_state(row) if row else "u")
            if state[-1] == "c":
                missed.append((i, day))
        # The annotation is computed here rather than in the browser, so the
        # chart never has to guess what a missing day was: the LONGEST run of
        # days the line owed and did not sail, named after the storm when it is
        # a single day that fell on one. A run of days is a ship in a yard and
        # a single day is usually weather, and the note should not say the
        # second while pointing at the first.
        note = None
        if missed:
            runs, cur = [], []
            for i, day in missed:
                if cur and i == cur[-1][0] + 1:
                    cur.append((i, day))
                else:
                    if cur:
                        runs.append(cur)
                    cur = [(i, day)]
            runs.append(cur)
            run = max(runs, key=len)
            head = _when(run[0][1])
            if len(run) > 1:
                a, b = run[0][1], run[-1][1]
                head = (f"{_when(a, False)}–{_when(b)}" if a[5:7] == b[5:7]
                        else f"{_when(a)} – {_when(b)}")
                tail = f"{word(len(run))} days in a row"
            elif len(missed) == 1:
                storm = storm_named.get(run[0][1])
                head = f"{head}: storm {storm}" if storm else head
                tail = "the only day it did not sail"
            else:
                tail = f"{word(len(missed))} days lost in the year"
            note = {"i": run[0][0], "text": [head, tail]}
        out[label_of(line, island_of[line])] = {
            "line": line, "counts": counts, "state": "".join(state),
            "july": july(by_line[line]), "january": january(by_line[line]),
            "note": note}
    return {"year": F1_YEAR,
            "default": label_of(F1_DEFAULT, island_of[F1_DEFAULT]),
            "lines": out}


# ------------------------------------------------------------------- F2 ----
def summer_winter(by_line, island_of, island, hidden_share):
    """July against January, per island line, as a share of the line's summer.

    Absolute crossings on one axis would say the wrong thing: the Fur ferry
    losing two sailings of a hundred and forty draws a longer bar than
    Christiansø losing four of five. The share is what the sentence is about,
    and both counts ride along as labels.

    A line whose own fleet was partly invisible in EVERY loaded year is left
    out — that is Fanø, where two of the three ferries have called themselves
    something other than a passenger ship since 2015, so its winter count is a
    lower bound of a lower bound (finding 23). A line with one bad year is
    kept: sql/41 drops the days its fleet was not heard, and the typical day is
    taken over the days that remain.
    """
    out, dropped = [], []
    for line in island:
        summer, winter = july(by_line[line]), january(by_line[line])
        if summer is None or winter is None or summer < F2_FLOOR:
            continue
        if min(hidden_share.get((line, y), 0.0) for y in YEARS) > 0.2:
            dropped.append(line)
            continue
        out.append({"label": label_of(line, island_of[line]), "line": line,
                    "summer": summer, "winter": winter,
                    "share": round(100 * winter / summer)})
    out.sort(key=lambda d: (d["share"], d["label"]))
    return {"rows": out, "excluded": dropped}


# ------------------------------------------------------------------- F3 ----
def storm_runs(rows):
    """Consecutive storm-flagged days, named from data/context/storms.csv.

    The days come from sql/41's own `is_storm_day` flag and the names from the
    file, joined on the start date. Dagmar and Egon share a run because their
    windows touch — the same fold notes/plot_ch03.py makes.
    """
    named = {}
    with open(ROOT / "data" / "context" / "storms.csv", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            named[rec["start_utc"][:10]] = rec["name"]

    runs, cur = [], []
    for day in sorted({r["day"] for r in rows if r["is_storm_day"]}):
        if cur and _delta(cur[-1], day) == 1:
            cur.append(day)
        else:
            if cur:
                runs.append(cur)
            cur = [day]
    if cur:
        runs.append(cur)

    out = []
    for run in runs:
        names = [named[d] for d in run if d in named]
        assert names, f"storm run {run} matches no row of storms.csv"
        out.append((" · ".join(names), run))
    assert len(out) == 14, f"{len(out)} storm runs in the loaded days, not 14"
    return out, named


def pooled(index, group, day):
    """Σ crossings ÷ Σ comparable day, over one group of lines on one day.

    Pooled and not averaged: the Fur ferry's hundred and forty sailings count
    for a hundred and forty and Anholt's two count for two. A line whose fleet
    was not heard, or which has no comparable day to be judged against, is
    dropped — never counted as a cancellation.
    """
    num = den = seen = 0
    for line in group:
        r = index.get((line, day))
        if r is None or r["fleet_positions"] == 0 or r["baseline"] == 0:
            continue
        num += r["crossings"]
        den += r["baseline"]
        seen += 1
    return (num / den if den else None), seen


def storms(rows, island, deepest=5):
    """The worst day of each storm: the small island lines against the big.

    "Worst" is the storm day on which the ISLAND pool ran the least, and the
    big lines are read on that same day — the question is what the big ships
    did while the small ferries were in, not what their own worst day was.
    """
    index = {(r["line"], r["day"]): r for r in rows}
    out = []
    for name, run in storm_runs(rows)[0]:
        best = None
        for day in run:
            ratio, seen = pooled(index, island, day)
            if ratio is not None and (best is None or ratio < best[1]):
                best = (day, ratio, seen)
        if best is None:
            continue
        day, ratio, seen = best
        big, big_seen = pooled(index, BIG, day)
        assert big is not None, f"{name}: the four big lines are missing on {day}"
        out.append({"storm": name, "day": day, "island": round(100 * ratio),
                    "big": round(100 * big), "island_lines": seen,
                    "big_lines": big_seen})
    out.sort(key=lambda d: d["island"])
    return {"rows": out[:deepest], "of": len(out)}


# ------------------------------------------------------------------- F4 ----
def crossing_minutes(speed, line):
    """sql/42 -> the crossing time of one line, year by year, with the ship.

    Loaded years only: 2022 and 2023 are 59-day winter windows, and a winter's
    worth of crossings on a line that changed ship is exactly the comparison
    finding 36 says not to make.
    """
    years = [speed[(line, y)] for y in YEARS]
    # The control sql/42's header asks for: if the crossing's own length moved,
    # the berths moved and the step is geometry rather than a ship.
    span = max(r["med_nm"] for r in years) / min(r["med_nm"] for r in years)
    assert span < 1.03, f"{line}: the crossing's own length moved by {span:.1%}"
    return {"line": line, "years": YEARS,
            "minutes": [r["med_min"] for r in years],
            "vessel": [r["modal_vessel"] for r in years],
            "nm": round(statistics.median(r["med_nm"] for r in years), 1)}


# ---------------------------------------------------------------- prose ----
def timetable(by_line):
    """The committed timetable anchor against what the archive counted.

    data/context/ferry_timetable.csv is eleven rows read by hand off the
    operators' 2026 pages, three of which publish no number at all. For the
    eight that do: the operator's departures per direction, doubled, against
    the typical July weekday of 2026 on the days the line's fleet was heard.
    Nothing in sql/40 knows a timetable exists, so a match is a check and not a
    fit.
    """
    names = {"Frederikshavn – Læsø": "Frederikshavn – Vesterø Havn",
             "Esbjerg – Fanø": "Esbjerg – Nordby",
             "Rønne – Ystad": "Ystad – Rønne"}
    match, total, unheard = 0, 0, []
    with open(ROOT / "data" / "context" / "ferry_timetable.csv",
              encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            dep = rec["summer_weekday_departures_per_direction"]
            if not dep:
                continue
            total += 1
            line = names.get(rec["route"], rec["route"])
            assert line in by_line, f"{rec['route']} -> {line}: sql/41 has no such line"
            got = median_day(by_line[line],
                             lambda r: r["year"] == 2026 and r["day"][5:7] == "07"
                             and r["daytype"] == "weekday")
            if got is None:
                unheard.append(line)
            elif got == 2 * int(dep):
                match += 1
    return match, total, unheard


def still_runs(by_line, island, minimum=3):
    """Runs of three days or more on which a line's fleet lay still.

    Every still day counts, whatever the day of the week — a ship in a yard
    does not care that its line has no Wednesday sailing. The longest of them
    are refits, which is why the storm question is asked over a week around the
    storm and never over a year.
    """
    runs = []
    for line in island:
        cur = []
        for day in sorted(r["day"] for r in by_line[line]
                          if r["crossings"] == 0 and r["fleet_sog_known"] > 0
                          and r["fleet_moving"] == 0):
            if cur and _delta(cur[-1], day) == 1:
                cur.append(day)
            else:
                if len(cur) >= minimum:
                    runs.append((line, cur))
                cur = [day]
        if len(cur) >= minimum:
            runs.append((line, cur))
    line, longest = max(runs, key=lambda t: len(t[1]))
    return {"runs": len(runs), "days": sum(len(r) for _, r in runs),
            "longest": len(longest), "line": line, "from": longest[0]}


def lost_days(by_line, island):
    """Days a line owed and did not sail: per loaded year as a share of all
    island line-days, and per line as a count over the loaded years."""
    per_line, loaded = collections.Counter(), collections.Counter()
    per_year = {}
    for year in YEARS:
        days = lost = 0
        for line in island:
            for r in by_line[line]:
                if r["year"] != year:
                    continue
                days += 1
                loaded[line] += 1
                if day_state(r) == "c":
                    lost += 1
                    per_line[line] += 1
        per_year[year] = 100 * lost / days
    return per_year, per_line, loaded


# ----------------------------------------------------------------- page ----
def sp(x):
    return f"{round(x):,}".replace(",", " ")


def build(ch):
    rows = [typed(DAILY, r, DAILY_INT)
            for r in blocks(ch("41_ferry_daily.sql"))[18]]
    assert rows, "sql/41's 18-column block is missing"
    check_labels({r["line"] for r in rows})

    by_line = collections.defaultdict(list)
    island_of = {}
    for r in rows:
        by_line[r["line"]].append(r)
        island_of[r["line"]] = r["island"]
    island = sorted(line for line, rs in by_line.items()
                    if rs[0]["kind"] == "island" and line not in BIG)

    speed = {(r["line"], r["year"]): r for r in
             (typed(SPEED, s, SPEED_INT)
              for s in blocks(ch("42_ferry_speed.sql"))[16])}
    hid = blocks(ch("44_hidden_fleet.sql"))
    hid_line = {(r["line"], r["year"]): r for r in
                (typed(HID, h, HID_INT) for h in hid[9])}
    hid_year = {r["year"]: r for r in
                (typed(HID_YEAR, h, HID_INT) for h in hid[6])}
    share = {k: v["hidden_share"] for k, v in hid_line.items()}

    charts = {
        "f1": one_year(by_line, island_of, storm_runs(rows)[1]),
        "f2": summer_winter(by_line, island_of, island, share),
        "f3": storms(rows, island),
        "f4": crossing_minutes(speed, F4_LINE),
    }

    # --- F1's default line, for the caption
    f1 = charts["f1"]["lines"][charts["f1"]["default"]]
    f1_loaded = [r for r in by_line[F1_DEFAULT] if r["year"] in YEARS]
    f1_lost = sum(1 for r in f1_loaded if day_state(r) == "c")

    # --- F2's two ends
    f2 = {d["label"]: d for d in charts["f2"]["rows"]}
    worst = charts["f2"]["rows"][0]
    same = [d for d in charts["f2"]["rows"] if d["share"] == 100]

    # --- F3, and the one storm that contradicts the headline
    f3 = {d["storm"]: d for d in charts["f3"]["rows"]}
    deepest = charts["f3"]["rows"][0]
    index = {(r["line"], r["day"]): r for r in rows}
    aero = [index[("Svendborg – Ærøskøbing", d)]
            for d in ("2022-01-29", "2022-01-30")]

    # --- F4, and the honesty note beside it
    mins = charts["f4"]["minutes"]
    ships = charts["f4"]["vessel"]
    before = statistics.median(m for m, v in zip(mins, ships) if v != F4_SHIP)
    after = statistics.median(m for m, v in zip(mins, ships) if v == F4_SHIP)
    livo = [speed[("Rønbjerg – Livø", y)]["med_min"] for y in (2021, 2024, 2025, 2026)]
    control = [speed[("Hou – Sælvig", y)]["med_min"] for y in YEARS]
    nerthus = [speed[("Bøjden – Fynshav", y)]["med_min"] for y in (2025, 2026)]

    # --- prose
    still = still_runs(by_line, island)
    per_year, lost_line, loaded = lost_days(by_line, island)
    perfect = [line for line in island
               if lost_line[line] == 0 and loaded[line] > 1900]
    bjorno = (median_day(by_line["Faaborg – Bjørnø"],
                         lambda r: r["daytype"] == "weekday"),
              median_day(by_line["Faaborg – Bjørnø"],
                         lambda r: r["daytype"] == "sun"))
    sunday = [line for line in island
              if median_day(by_line[line], lambda r: r["daytype"] == "weekday")
              and median_day(by_line[line], lambda r: r["daytype"] == "sun")
              == median_day(by_line[line], lambda r: r["daytype"] == "weekday")]
    match, publishes, unheard = timetable(by_line)
    assert unheard, "every line with a published timetable was heard — finding 24 moved"
    anholt = [r for r in by_line["Grenaa – Anholt"] if r["year"] == 2025]
    dows = {s: len({r["dow"] for r in anholt if r["season"] == s
                    and r["baseline"] > 0}) for s in ("may-sep", "oct-apr")}
    anholt_speed = speed[("Grenaa – Anholt", 2025)]
    fano = hid_line[("Esbjerg – Nordby", 2025)]

    charts["n"] = {
        # the shape of the thing
        "crossings_m": f"{sum(r['crossings'] for r in rows) / 1e6:.1f}",
        "island_lines": word(len(island)),
        "f1_lines": word(len(F1_LINES)),
        # F1 — one island's year
        "f1_july": f"{f1['july']:.0f}",
        "f1_january": f"{f1['january']:.0f}",
        "f1_lost": word(f1_lost),
        "f1_days": sp(len(f1_loaded)),
        "laeso_min": str(speed[(F1_DEFAULT, F1_YEAR)]["med_min"]),
        # F2 — the winter timetable
        "f2_lines": word(len(charts["f2"]["rows"])),
        "f2_same": word(len(same)),
        "f2_worst_summer": f"{worst['summer']:.0f}",
        "f2_worst_winter": f"{worst['winter']:.0f}",
        "fur_summer": f"{f2['Fur']['summer']:.0f}",
        "fur_winter": f"{f2['Fur']['winter']:.0f}",
        "fur_minutes": str(speed[("Branden – Fur", 2025)]["med_min"]),
        "egholm_summer": f"{f2['Egholm']['summer']:.0f}",
        "egholm_winter": f"{f2['Egholm']['winter']:.0f}",
        "egholm_minutes": str(speed[("Aalborg – Egholm", 2025)]["med_min"]),
        "bjorno_sunday": str(round(100 * bjorno[1] / bjorno[0])),
        # Anholt, in prose
        "anholt_crossings": word(round(july(anholt))),
        "anholt_summer_days": word(dows["may-sep"]),
        "anholt_winter_days": word(dows["oct-apr"]),
        "anholt_hours": word(round(anholt_speed["med_min"] / 60)),
        "anholt_nm": f"{anholt_speed['med_nm']:.0f}",
        # Sundays, lost days, shipyards
        "sunday_same": word(len(sunday)),
        "lost_low": f"{min(per_year.values()):.1f}",
        "lost_high": f"{max(per_year.values()):.1f}",
        "perfect_days": sp(max(loaded[line] for line in perfect)),
        "still_runs": sp(still["runs"]),
        "still_longest": str(still["longest"]),
        # F3 — the storms
        "f3_storms": word(len(charts["f3"]["rows"])),
        "deepest_island": str(deepest["island"]),
        "deepest_big": str(deepest["big"]),
        "floriane_island": str(f3["Floriane"]["island"]),
        "floriane_big": str(f3["Floriane"]["big"]),
        "oresund_min": str(speed[("Helsingør – Helsingborg", 2025)]["med_min"]),
        "malik_island": str(f3["Malik"]["island"]),
        "malik_big": str(f3["Malik"]["big"]),
        "aero_malik_a": str(round(100 * aero[0]["crossings"] / aero[0]["baseline"])),
        "aero_malik_b": str(round(100 * aero[1]["crossings"] / aero[1]["baseline"])),
        # F4 — the battery ferry
        "ellen_before": f"{before:.0f}",
        "ellen_after": f"{after:.0f}",
        "ellen_cut": word(round(before - after)),
        "ellen_nm": f"{charts['f4']['nm']:.0f}",
        "livo_low": f"{min(livo):.0f}",
        "livo_high": f"{max(livo):.0f}",
        "control_low": f"{min(control):.0f}",
        "control_high": f"{max(control):.0f}",
        "nerthus_before": f"{nerthus[0]:.0f}",
        "nerthus_after": f"{nerthus[1]:.0f}",
        # what the archive cannot see
        "hidden_share": f"{100 * hid_year[2025]['hidden_share']:.0f}",
        "hidden_fleet": sp(hid_year[2025]["fleet_vessels"]),
        "fano_hidden": word(fano["hidden_vessels"]),
        "fano_fleet": word(fano["fleet_vessels"]),
        "tt_match": word(match),
        "tt_publishes": word(publishes),
    }
    return charts
