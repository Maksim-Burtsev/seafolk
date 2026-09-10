#!/usr/bin/env python3
"""S8 chapter-03 charts: three PNGs into notes/img/, and the numbers behind them.

    uv run --project notes notes/plot_ch03.py

Same contract as notes/plot.py, plot_ch01.py and plot_ch02.py, whose helpers
this file imports: every query runs through scripts/ch.sh against the
`clickhouse local --path data/ch` store, ONE AT A TIME (the store lock is
exclusive — two clickhouse processes on data/ch is an error, not a slowdown),
there is no client library, matplotlib is the one dependency, and every number
notes/ch03-findings.md quotes is printed by numbers() below.

Four query files, each read exactly once:
    sql/41_ferry_daily.sql   one row per (ferry line, local day), 17 columns,
                             + a second block of per-year unmatched shares
    sql/42_ferry_speed.sql   one row per (line, year): speed, duration, the
                             modal vessel, and max_kn
    sql/43_ferry_oracle.sql  the external oracle, July 2025 on one line
    sql/44_hidden_fleet.sql  the fleet `public_track` cannot see, three blocks

THE YEARS. 2015 / 2018 / 2021 / 2024 (from 03-01) / 2025 / 2026 (to 08-26) are
full-ish years; 2022 and 2023 are WINTER WINDOWS of ~60 days. The windows are
excluded from every per-year comparison and used only in the storm chart, where
Malik, Nora (2022), Otto and Pia (2023) fall inside them.

THE FIVE KINDS are island / domestic / international / foreign / harbour.
`harbour` is NOT A SERVICE — five OSM objects that are intra-harbour legs
between two berths of one port (sql/40's header names all five). They are
emitted like any other line and are EXCLUDED from every pool, table and chart
here; the one place they appear is the printed line-count, so their exclusion
is visible rather than silent.

PRIVACY. `ferry_crossing` and `ferry_day` carry MMSI, `sql/41`–`44` emit none,
and this file asserts that its own stdout holds no 9-digit integer (guard (e)
in main). Ferries are public and are named — that is what chart 3 is about.
"""
import collections
import csv
import datetime
import io
import re
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot import GRID, IMG, INK, MUTED, ROOT, rows, tidy

FERRY = "#eb6834"                      # the project's ferry orange, plot.GROUPS[1]
SLATE = "#5b6b73"                      # the contrast series: the big lines
HIDDEN = "#7d2c10"                     # the hidden-fleet marker
YEARS = [2015, 2018, 2021, 2024, 2025, 2026]
WINDOWS = [2022, 2023]                 # storm windows, ~60 winter days each
KINDS = {"island", "domestic", "international", "foreign", "harbour"}
HIDDEN_MARK = 0.2                      # hidden_share above which chart 1 marks a row

# Chart 1. Eight small-island lifelines, one per island, chosen for range: the
# busiest line in the country (Fur, a 3-minute strait), the thinnest (Anholt,
# one round trip a day), the two the timetable check anchors on, and four in
# between. Fanø is in deliberately: sql/44 says two of its three ferries are
# invisible in every year, and the chart has to show what that looks like.
LIFELINES = [
    ("Branden – Fur", "Fur"),
    ("Esbjerg – Nordby", "Fanø"),
    ("Svendborg – Ærøskøbing", "Ærø"),
    ("Hou – Sælvig", "Samsø"),
    ("Frederikshavn – Vesterø Havn", "Læsø"),
    ("Snaptun – Endelave", "Endelave"),
    ("Hou – Tunø", "Tunø"),
    ("Grenaa – Anholt", "Anholt"),
]
# Chart 2's contrast: the four biggest lines with one end in Denmark. Køge –
# Rønne is `island` in ferry_lines.csv (a Bornholm lifeline whichever flag the
# far quay flies) and is a BIG line here — the pooling is by size, not by
# `kind`, and the island pool excludes these four explicitly.
BIG = ["Helsingør – Helsingborg", "Rødby – Puttgarden",
       "Køge – Rønne", "Gedser – Rostock"]

# data/context/ferry_timetable.csv names the ROUTE as the operator prints it;
# sql/40 resolves the LINE off OSM through data/context/ferry_lines.csv. Three
# of the eleven differ (a quay name against an island name, and one reversed
# pair), so the mapping is written out and every entry is asserted to resolve.
TIMETABLE_LINE = {
    "Svendborg – Ærøskøbing": "Svendborg – Ærøskøbing",
    "Frederikshavn – Læsø": "Frederikshavn – Vesterø Havn",
    "Grenaa – Anholt": "Grenaa – Anholt",
    "Hou – Tunø": "Hou – Tunø",
    "Branden – Fur": "Branden – Fur",
    "Esbjerg – Fanø": "Esbjerg – Nordby",
    "Hou – Sælvig": "Hou – Sælvig",
    "Snaptun – Endelave": "Snaptun – Endelave",
    "Hals – Egense": "Hals – Egense",
    "Rønne – Ystad": "Ystad – Rønne",
    "Helsingør – Helsingborg": "Helsingør – Helsingborg",
}
# The two cells sql/43 hard-codes in its header and recomputes in its last two
# columns. geoToH3 takes (lat, lon, res) under scripts/ch.sh's pins; a
# ClickHouse that flips the order again mirrors Denmark into the Arabian Sea
# without erroring, and these two literals are where that shows up.
CELL_SV, CELL_AE = 608531604905656319, 608531599906045951


# ------------------------------------------------------------- sql/41 ----
DAILY = ("line kind island day year season daytype dow crossings vessels "
         "routes baseline missed is_storm_day fleet_positions fleet_sog_known "
         "fleet_moving fleet_vessels").split()
DAILY_INT = ("year dow crossings vessels routes baseline missed is_storm_day "
             "fleet_positions fleet_sog_known fleet_moving fleet_vessels").split()


def daily():
    """sql/41 -> (panel rows, per-year unmatched rows), with the row asserts.

    The file emits TWO blocks on one stdout and `rows()` concatenates them, so
    they are separated by width: 18 columns for the line-day panel, 8 for the
    unmatched summary. Anything else is a changed file, not a parse to guess at.
    """
    panel, unmatched = [], []
    for r in rows("41_ferry_daily.sql"):
        if len(r) == 8:
            unmatched.append(dict(
                year=int(r[0]), crossings=int(r[1]), lt1km=int(r[2]),
                ge1km=int(r[3]), share=float(r[4]), ge1km_share=float(r[5]),
                below_floor=int(r[6]), in_first_block=int(r[7])))
            continue
        assert len(r) == 18, f"sql/41: {len(r)} columns, not 18: {r[:4]}"
        row = dict(zip(DAILY, r))
        for k in DAILY_INT:
            # The four coverage columns are the whole vocabulary of § 3 and the
            # exclusion rule of chart 2. If the LEFT JOIN onto `cover` were
            # dropped, or join_use_nulls flipped to 1, they would arrive empty
            # or as the string \N — which must fail here and not be read as
            # "the fleet reported nothing today".
            assert re.fullmatch(r"-?\d+", row[k]), \
                f"sql/41 {row['line']} {row['day']}: {k} = {row[k]!r}"
            row[k] = int(row[k])
        # `dow` is the baseline's key and this file never computes it: an
        # off-by-one, or a dow taken from the UTC date rather than the local
        # one, would move every baseline by a day of the week and leave every
        # number plausible. Python's own calendar is the independent literal.
        assert datetime.date.fromisoformat(row["day"]).isoweekday() == row["dow"], \
            (f"{row['line']} {row['day']}: sql/41 says dow {row['dow']}, the "
             f"calendar says {datetime.date.fromisoformat(row['day']).isoweekday()}")
        # (g) the invariants the charts lean on. `missed` is
        # greatest(baseline - crossings, 0): recomputing it here catches a
        # baseline that stopped being the thing `missed` is measured against —
        # the storm chart divides crossings by that same baseline.
        assert row["missed"] == max(row["baseline"] - row["crossings"], 0), \
            (f"{row['line']} {row['day']}: missed {row['missed']} is not "
             f"baseline {row['baseline']} - crossings {row['crossings']}")
        # The coverage columns are nested counts over the same positions:
        # moving <= sog_known <= positions by construction in sql/40's
        # `ferry_day`. Swapping two of them in sql/41's `cover` CTE — the
        # cheapest possible edit there — leaves every count plausible and
        # inverts "lay still" and "cannot tell"; this is what catches it.
        assert row["fleet_moving"] <= row["fleet_sog_known"] <= row["fleet_positions"], \
            (f"{row['line']} {row['day']}: moving {row['fleet_moving']} / "
             f"sog_known {row['fleet_sog_known']} / positions "
             f"{row['fleet_positions']} are not nested")
        # (5) five kinds, and nothing else. A sixth kind means
        # data/context/ferry_lines.csv gained a category and every pool below
        # (which filters `harbour` out by name) is quietly wrong.
        assert row["kind"] in KINDS, f"{row['line']}: kind {row['kind']!r}"
        panel.append(row)
    assert panel and unmatched, "sql/41 returned only one of its two blocks"

    # (5) THE MMSI GUARD CANNOT TELL AN OSM ID FROM AN MMSI. Both are 9-digit
    # integers, and sql/40's old fallback label put `way:93308405` into the
    # line column. sql/40 now fails its build instead, so no line label may
    # carry one — checked here rather than left to the stdout grep in main,
    # which would report a privacy breach for what is really an unmapped route.
    for line in {row["line"] for row in panel}:
        assert not re.search(r"\b\d{9}\b", line), \
            f"line label {line!r} contains a 9-digit integer — an unmapped OSM route?"

    # The archive's own shape, asserted rather than trusted, because every
    # "per year" statement in the note depends on which years are years.
    days = collections.defaultdict(set)
    for row in panel:
        days[row["year"]].add(row["day"])
    assert sorted(days) == sorted(YEARS + WINDOWS), \
        f"sql/41 covers years {sorted(days)}"
    for year in YEARS:
        assert len(days[year]) > 230, f"{year}: only {len(days[year])} days — not a year"
    for year in WINDOWS:
        # 60 and 61 days. The bound is 100 because the point is that these are
        # WINDOWS: pool them into a year comparison and a line's baseline
        # becomes a February baseline. A `> 0` check would pass a full 2022.
        assert len(days[year]) < 100, \
            f"{year} has {len(days[year])} days — it is no longer a storm window"
    return panel, unmatched


def services(panel):
    """The line-days that are services: everything but `kind = 'harbour'`."""
    return [row for row in panel if row["kind"] != "harbour"]


def loaded(row):
    """A row usable in a per-year comparison: a full-ish year, not a window."""
    return row["year"] in YEARS


def zero_kind(row):
    """sql/41's four-word vocabulary for a day, plus 'sailed'.

    Straight out of sql/41's header, and it only applies to a day with no
    crossing: `fleet_*` counts the line's OWN-MAJORITY fleet, so a day the line
    sailed with borrowed tonnage can carry zeros in all four columns (1 202
    island line-days do). Classifying a day that sailed would turn those into
    silence.
    """
    if row["crossings"] > 0:
        return "sailed"
    if row["fleet_positions"] == 0:
        return "silent"
    if row["fleet_sog_known"] == 0:
        return "cannot tell"
    if row["fleet_moving"] == 0:
        return "lay still"
    return "moved, nothing matched"


# ------------------------------------------------------------- sql/42 ----
SPEED = ("line kind island year crossings vessels routes modal_vessel "
         "modal_share med_kn max_kn med_sog_kn med_min p10_min p90_min "
         "med_nm").split()


def speed():
    """sql/42 -> ({line: {year: row}}, the rows where made-good beats the log).

    A crossing's speed made good is berth centroid to berth centroid over the
    elapsed time, and the vessel's own reported sog is measured while under
    way, so med_kn should sit BELOW med_sog_kn on every line. It does, on 1 277
    of the 1 281 rows; the four that do not are returned rather than asserted
    away, and the note names them.
    """
    out = collections.defaultdict(dict)
    faster_than_log = []
    for r in rows("42_ferry_speed.sql"):
        assert len(r) == 16, f"sql/42: {len(r)} columns, not 16: {r[:4]}"
        row = dict(zip(SPEED, r))
        for k in ("year", "crossings", "vessels", "routes", "med_min",
                  "p10_min", "p90_min"):
            row[k] = int(row[k])
        for k in ("modal_share", "med_kn", "max_kn", "med_sog_kn", "med_nm"):
            row[k] = float(row[k])
        assert row["kind"] in KINDS, f"{row['line']}: kind {row['kind']!r}"
        # (6) One vessel made every crossing, so the modal vessel made every
        # crossing: modal_share must be exactly 1. The modal join is the one
        # place in sql/42 where a per-name aggregate is folded back onto a
        # per-line-year one, and a fold on the wrong key (line only, or year
        # only) still returns a share between 0 and 1 on every row. This is
        # the row where that cannot hide.
        assert row["vessels"] != 1 or row["modal_share"] == 1.0, \
            (f"{row['line']} {row['year']}: one vessel but modal_share "
             f"{row['modal_share']}")
        assert 0 < row["modal_share"] <= 1, \
            f"{row['line']} {row['year']}: modal share {row['modal_share']}"
        # (6) sql/40 drops any crossing implying more than 30 kn — lowered
        # from 40 after this column showed a 10.17 nm crossing recorded in 16
        # minutes. max_kn is the consumer that makes the guard visible; a row
        # above it means the guard is gone. Observed store-wide maximum
        # 29.65 kn, Danish maximum 29.07 kn.
        assert row["max_kn"] <= 30, \
            (f"{row['line']} {row['year']}: max_kn {row['max_kn']} — sql/40's "
             "30 kn guard is not doing its job")
        # (6) A Danish ferry line's median speed made good is 1.9-21 kn. The
        # floor of 1 catches the mistake this column invites: med_kn is
        # nm / (minutes / 60), and dropping the /60 gives 0.05-0.4 kn on every
        # row while leaving med_sog_kn, med_min and med_nm untouched and
        # plausible. `harbour` and `foreign` are excluded because an
        # intra-harbour leg genuinely reads 0.45-0.66 kn.
        assert row["kind"] not in ("island", "domestic") or row["med_kn"] > 1, \
            (f"{row['line']} {row['year']}: med_kn {row['med_kn']} — is the "
             "minutes-to-hours conversion still there?")
        if row["med_kn"] > row["med_sog_kn"] + 0.01:
            faster_than_log.append(row)
        out[row["line"]][row["year"]] = row
    # Measured: 4 of 1 281, every one of them a thin foreign row of 1-90
    # crossings (printed by numbers()). This is not a hard invariant — two
    # medians over different populations can cross on a handful of samples —
    # so the assert bounds BOTH the count and the thinness: a fat line-year
    # whose berth-to-berth speed beats its own log means `nm`/`minutes` and
    # `med_sog` have stopped describing the same crossing.
    assert len(faster_than_log) <= 8, \
        (f"{len(faster_than_log)} sql/42 rows have speed made good above the "
         "vessel's own median sog — nm/minutes and med_sog have come apart")
    fat = [r for r in faster_than_log if r["crossings"] >= 200]
    assert not fat, \
        ("speed made good beats the vessel's own log on a line-year with 200+ "
         f"crossings: {[(r['line'], r['year'], r['crossings']) for r in fat]}")
    return out, faster_than_log


# ------------------------------------------------------------- sql/43 ----
def oracle():
    """sql/43 -> the July-2025 Ærø check, and assert (a) on it.

    The oracle recomputes Svendborg – Ærøskøbing from raw positions and two
    hard-coded H3 cells, sharing nothing with sql/40's stays, sessions, guards
    or route matcher. sql/43's header states the measured result: all 31 days
    agree exactly, both sides read 22 crossings a day, and both see 2 vessels.
    """
    out = []
    for r in rows("43_ferry_oracle.sql"):
        assert len(r) == 8, f"sql/43: {len(r)} columns, not 8"
        day, o_cross, t_cross, gap, o_vess, t_vess, cell_sv, cell_ae = r
        # The coordinate-order canary. sql/43 recomputes both cell ids from the
        # two harbour coordinates in its own header every run; scripts/ch.sh
        # pins geoToH3 to (lat, lon, res) and a ClickHouse that flips it back
        # returns two different integers here while every count stays green.
        assert int(cell_sv) == CELL_SV and int(cell_ae) == CELL_AE, \
            f"sql/43: cells {cell_sv} / {cell_ae} — geoToH3 argument order moved"
        out.append(dict(day=day, oracle=int(o_cross), table=int(t_cross),
                        gap=int(gap), oracle_vessels=int(o_vess),
                        table_vessels=int(t_vess)))
    assert len(out) == 31, f"sql/43 returned {len(out)} days, not 31"
    # (a) MEASURED max |gap| = 0 on all 31 days. The bound is the measured
    # maximum plus one — one whole crossing of slack on every day of the month.
    worst = max(abs(r["gap"]) for r in out)
    assert worst <= 1, f"sql/43: |gap| reaches {worst}, the bound is 1"
    # (1) THE GAP ALONE IS NOT THE CHECK, and a finder proved it: delete the
    # oracle's 24-hour bound and 07-04, 07-09 and 07-15 read 23 crossings from
    # THREE vessels — sail-training ships lying in Svendborg and turning up in
    # Ærøskøbing days later. |gap| <= 1 stayed green on all three. The vessel
    # count is what does not: this line is two ferries, on both sides, on every
    # day of the month.
    for r in out:
        assert r["oracle_vessels"] == 2 and r["table_vessels"] == 2, \
            (f"sql/43 {r['day']}: {r['oracle_vessels']} oracle vessels and "
             f"{r['table_vessels']} table vessels, not 2 and 2")
    # And the LEVEL, on the side this chapter actually quotes: 22 crossings a
    # day is 11 round trips, which is the 2026 Ærøfærgerne timetable read by
    # hand into data/context/ferry_timetable.csv.
    at_22 = sum(1 for r in out if r["table"] == 22)
    assert at_22 >= 28, f"sql/43: the table reads 22 on only {at_22} of 31 days"
    return out, worst, at_22


# ------------------------------------------------------------- sql/44 ----
HID_LINE = ("line kind island year fleet_vessels visible_days hidden_days "
            "hidden_share hidden_vessels").split()
HID_YEAR = ("year fleet_vessels visible_days hidden_days hidden_share "
            "hidden_vessels").split()
HID_VESSEL = "vessel year line kind island hidden_days dominant_hidden_type".split()


def hidden():
    """sql/44 -> ({(line, year): row}, {year: row}, [per-vessel rows]).

    Three blocks on one stdout, separated by width: 9 columns per (line, year),
    6 per year store-wide, 7 per (vessel, year, line) for the Danish lines.
    """
    per_line, per_year, vessels = {}, {}, []
    for r in rows("44_hidden_fleet.sql"):
        if len(r) == 9:
            row = dict(zip(HID_LINE, r))
            for k in ("year", "fleet_vessels", "visible_days", "hidden_days",
                      "hidden_vessels"):
                row[k] = int(row[k])
            row["hidden_share"] = float(row["hidden_share"])
            # hidden + visible is the number of vessel-days the fleet reported
            # anything at all; the share is one over the other. A denominator
            # that quietly became "days in the year" would leave every share
            # plausible and every one of them wrong.
            total = row["visible_days"] + row["hidden_days"]
            assert total > 0 and abs(row["hidden_share"]
                                     - row["hidden_days"] / total) < 5e-4, \
                (f"sql/44 {row['line']} {row['year']}: hidden_share "
                 f"{row['hidden_share']} is not {row['hidden_days']}/{total}")
            assert row["hidden_vessels"] <= row["fleet_vessels"]
            per_line[(row["line"], row["year"])] = row
        elif len(r) == 6:
            row = dict(zip(HID_YEAR, r))
            for k in ("year", "fleet_vessels", "visible_days", "hidden_days",
                      "hidden_vessels"):
                row[k] = int(row[k])
            row["hidden_share"] = float(row["hidden_share"])
            per_year[row["year"]] = row
        else:
            assert len(r) == 7, f"sql/44: {len(r)} columns, not 9 / 6 / 7"
            row = dict(zip(HID_VESSEL, r))
            row["year"] = int(row["year"])
            row["hidden_days"] = int(row["hidden_days"])
            assert row["kind"] in ("island", "domestic"), \
                f"sql/44 block 3 is Danish lines only, got {row['kind']!r}"
            vessels.append(row)
    assert per_line and per_year and vessels, "sql/44 lost one of its three blocks"
    return per_line, per_year, vessels


def hidden_share(hid_line, line, year):
    row = hid_line.get((line, year))
    return row["hidden_share"] if row else 0.0


# --------------------------------------------------------- timetable ----
def timetable(panel):
    """The committed anchor file, joined to the observed July medians.

    Asserts only that every row of the file resolves to a line sql/41 emits —
    the numbers themselves are the finding, not a test.
    """
    lines = {row["line"] for row in panel}
    out = []
    with open(ROOT / "data" / "context" / "ferry_timetable.csv",
              encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            line = TIMETABLE_LINE.get(rec["route"])
            # (d) the row was found. A renamed line in ferry_lines.csv, or a
            # route dropping below sql/40's 200-crossing floor, silently
            # removes a row from this table; the timetable check is the plan's
            # own Validate and it may not thin out unnoticed.
            assert line is not None, f"{rec['route']}: no entry in TIMETABLE_LINE"
            assert line in lines, f"{rec['route']} -> {line}: sql/41 has no such line"
            dep = rec["summer_weekday_departures_per_direction"]
            out.append(dict(
                route=rec["route"], line=line, operator=rec["operator"],
                departures=int(dep) if dep else None,
                minutes=int(rec["crossing_minutes"]) if rec["crossing_minutes"] else None,
                observed={year: july_weekday_median(panel, line, year)
                          for year in (2025, 2026)}))
    assert len(out) == 11, f"ferry_timetable.csv has {len(out)} rows, not 11"
    return out


def july_weekday_median(panel, line, year):
    """Median crossings on the July weekdays of `year` the fleet was heard on."""
    vals = [row["crossings"] for row in panel
            if row["line"] == line and row["year"] == year
            and row["day"][5:7] == "07" and row["daytype"] == "weekday"
            and row["fleet_positions"] > 0]
    return statistics.median(vals) if vals else None


def baseline_of(panel, line, year, season, dow):
    """The one baseline value of a (line, year, season, day-of-week) group.

    Read off the rows, never recomputed: the point of (2) is to check sql/41's
    own baseline against an outside number, and a baseline this file computed
    for itself would only check the file against itself.
    """
    vals = {row["baseline"] for row in panel
            if row["line"] == line and row["year"] == year
            and row["season"] == season and row["dow"] == dow}
    assert len(vals) == 1, \
        f"{line} {year} {season} dow {dow}: {len(vals)} distinct baselines, not 1"
    return vals.pop()


# ------------------------------------------------- the derived tables ----
def storm_windows(panel):
    """[(names, [local storm days])] for every named storm in a loaded year.

    The DAYS come from sql/41's `is_storm_day` flag, not from a second copy of
    the calendar here: a change there must move this chart rather than be
    contradicted by it. Consecutive flagged days are one run — which is why
    Dagmar (2015-01-09) and Egon (2015-01-10/11) share a panel: their windows
    touch. The NAMES and the check come from data/context/storms.csv.
    """
    flagged = sorted({row["day"] for row in panel if row["is_storm_day"]})
    runs, cur = [], []
    for day in flagged:
        if cur and days_between(cur[-1], day) == 1:
            cur.append(day)
        else:
            if cur:
                runs.append(cur)
            cur = [day]
    if cur:
        runs.append(cur)

    with open(ROOT / "data" / "context" / "storms.csv", encoding="utf-8") as fh:
        storms = [(rec["name"], rec["start_utc"][:10], rec["end_utc"][:10])
                  for rec in csv.DictReader(fh)]
    # (3) EVERY CALENDAR DATE OF EVERY STORM, and nothing else. sql/41 used to
    # convert the UTC window to local dates, which pushed a window ending at
    # 23:59:59 UTC into the next local day and flagged 59 days for 35 dates;
    # the file now reads them as dates and this is the assert that says so. It
    # is built from storms.csv independently of the flag: expand each storm to
    # its calendar dates, intersect with the days the panel holds, and demand
    # set equality with the flagged days.
    covered = {row["day"] for row in panel}
    expected = set()
    per_storm = {}
    for name, start, end in storms:
        dates = [shift(start, i)
                 for i in range(days_between(start, end) + 1)]
        seen = sorted(set(dates) & covered)
        if seen:
            per_storm[name] = seen
        expected |= set(dates) & covered
    assert set(flagged) == expected, \
        (f"is_storm_day flags {len(flagged)} days, storms.csv's calendar dates "
         f"cover {len(expected)}; symmetric difference "
         f"{sorted(set(flagged) ^ expected)}")
    for name, seen in per_storm.items():
        assert all(day in flagged for day in seen), \
            f"storm {name}: {seen} not all flagged"
    # 14 runs for 15 storms — Dagmar and Egon are consecutive. A fifteenth run
    # means a storm window moved or a year was loaded; a thirteenth means one
    # went missing.
    assert len(runs) == 14, f"{len(runs)} storm runs in the loaded days, not 14"

    out = []
    for run in runs:
        names = [name for name, seen in per_storm.items()
                 if seen[0] >= run[0] and seen[0] <= run[-1]]
        assert names, f"storm run {run} matches no row of storms.csv"
        out.append((" · ".join(names), run))
    return out, per_storm


def days_between(a, b):
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


def shift(day, delta):
    return (datetime.date.fromisoformat(day)
            + datetime.timedelta(days=delta)).isoformat()


def per_line_year(panel, lines):
    """{(line, year): Counter of zero_kind} over the given lines."""
    out = collections.defaultdict(collections.Counter)
    for row in panel:
        if row["line"] in lines:
            cell = out[(row["line"], row["year"])]
            kind = zero_kind(row)
            cell[kind] += 1
            cell["days"] += 1
            cell["crossings"] += row["crossings"]
            # A lay-still day whose baseline is 0 is the timetable, not a
            # stoppage. With the baseline keyed on the day of the week this is
            # now a much smaller bucket than it was: Grenaa – Anholt's 237
            # Wednesdays became ordinary days rather than 237 cancellations.
            if kind == "lay still":
                cell["lay still, scheduled" if row["baseline"] > 0
                     else "lay still, no baseline"] += 1
    return out


def storm_profile(index, group, run, span=3):
    """Pooled crossings / baseline from -span to +span around a storm run.

    The offset is counted from the storm's FIRST local day, so offsets
    0 .. len(run) - 1 are the storm itself and the chart shades exactly those.
    Pooled, not averaged over lines: Σcrossings / Σbaseline, so the Fur ferry's
    138 sailings a day count for 138 and Anholt's two count for two. The
    unweighted mean of the per-line ratios is returned beside it, because the
    pool is dominated by a few high-frequency straits and where the two
    disagree the dip belongs to one line, not to the group.
    A line-day is dropped when the line's fleet was not heard (fleet_positions
    = 0) or the group has no baseline: a receiver that heard nothing is not a
    ferry that did not sail, and the storm chapter is where that confusion
    would be expensive.
    """
    out, dropped = [], 0
    for offset in range(-span, span + 1):
        day = shift(run[0], offset)
        num = den = 0
        ratios = []
        for line in group:
            row = index.get((line, day))
            if row is None:
                continue
            if row["fleet_positions"] == 0 or row["baseline"] == 0:
                dropped += 1
                continue
            num += row["crossings"]
            den += row["baseline"]
            ratios.append(row["crossings"] / row["baseline"])
        out.append((offset, num / den if den else None, len(ratios),
                    sum(ratios) / len(ratios) if ratios else None))
    return out, dropped


def replacements(spd):
    """The lines where the modal vessel changed between two loaded years.

    The filter is not "the name string changed": on a two-ferry line the modal
    vessel flips between the two ships every other year (Svendborg –
    Ærøskøbing alternates AEROESKOEBING and MARSTAL at a modal share of 0.50),
    and half the remaining changes are the SAME ship spelled differently by the
    transponder — TUNOEFAERGEN / TUNOFAERGEN, OROE / ORO, MF ENDELAVE /
    ENDELAVE, FEMOESUND / FEMOUSUND. So:
      * modal_share >= 0.8 in BOTH years — one ship ran the line, so a change
        of name is a change of ship;
      * the normalised names differ and neither is a prefix of the other,
        which is what separates M/F SKJOLDNAES from SKJOLDNAES;
      * med_nm within 3 % — the control sql/42's header asks for. If the
        distance moved too, the berths moved and the step is geometry.
    """
    def norm(name):
        return re.sub(r"[^A-Z]", "", re.sub(r"\b(M/F|M/S|MF|M\.F\.|MS)\b", "",
                                            name.upper()))

    out = []
    for line, years in spd.items():
        loaded_years = [y for y in sorted(years) if y in YEARS]
        for a, b in zip(loaded_years, loaded_years[1:]):
            ra, rb = years[a], years[b]
            na, nb = norm(ra["modal_vessel"]), norm(rb["modal_vessel"])
            if na == nb or na.startswith(nb) or nb.startswith(na):
                continue
            if min(ra["modal_share"], rb["modal_share"]) < 0.8:
                continue
            if min(ra["crossings"], rb["crossings"]) < 200:
                continue
            d_nm = abs(rb["med_nm"] - ra["med_nm"]) / ra["med_nm"]
            if d_nm >= 0.03:
                continue
            out.append(dict(line=line, kind=ra["kind"], y0=a, y1=b,
                            v0=ra["modal_vessel"], v1=rb["modal_vessel"],
                            kn0=ra["med_kn"], kn1=rb["med_kn"],
                            min0=ra["med_min"], min1=rb["med_min"],
                            d_kn=(rb["med_kn"] - ra["med_kn"]) / ra["med_kn"],
                            d_nm=d_nm))
    out.sort(key=lambda r: -abs(r["d_kn"]))
    return out


# ------------------------------------------------------------- charts ----
def month_median(panel, line, month):
    """Median crossings on the WEEKDAYS of one month the fleet was heard on.

    The same figure the § 2 table prints, so a panel subtitle and the note
    cannot drift apart: weekdays only, because a July that pooled Sundays in
    would not be the number finding 26 quotes.
    """
    vals = [row["crossings"] for row in panel
            if row["line"] == line and loaded(row) and row["fleet_positions"] > 0
            and row["day"][5:7] == month and row["daytype"] == "weekday"]
    return statistics.median(vals) if vals else None


def still_runs(days, minimum=3):
    """Maximal runs of >= `minimum` consecutive dates in a sorted list."""
    out, cur = [], []
    for day in sorted(days):
        if cur and days_between(cur[-1], day) == 1:
            cur.append(day)
        else:
            if len(cur) >= minimum:
                out.append(cur)
            cur = [day]
    if len(cur) >= minimum:
        out.append(cur)
    return out


def rolling(series, window=7, need=4):
    """Centred `window`-day mean of {date: crossings}, over signal days only.

    Returns {date: mean}. A date whose window holds fewer than `need` signal
    days has no value at all, so a week the fleet was not heard is a GAP in the
    drawn line and never a zero — the distinction the whole chapter turns on.
    """
    half = window // 2
    keys = sorted(series)
    out = {}
    for day in keys:
        vals = [series[shift(day, k)] for k in range(-half, half + 1)
                if shift(day, k) in series]
        if len(vals) >= need:
            out[day] = sum(vals) / len(vals)
    return out


def chart_lifelines(panel, hid_line, per_ly):
    """Chart 1 -- eight island lines as one contiguous six-year time series.

    One panel per line; x is calendar time with the loaded years laid end to
    end (2015 | 2018 | 2021 | 2024 | 2025 | 2026) and a visible gap where the
    archive skips. The two 59-day winter windows are not drawn: a 59-day stub
    beside a full year reads as a collapse in traffic, which is the one thing
    this chart must not say.
    y is crossings per day as a 7-day mean over the days the fleet was heard;
    a week of silence is a gap in the line, never a zero. The dashed grey rule
    is the line's own May-Sep median, so the winter shortfall is legible
    without a second axis, and the grey band is Oct-Apr — sql/41's own season
    split.
    The dark ticks at y = 0 are runs of three days or more on which the line
    lay still on a day of the week it normally sails; the longest run in each
    panel carries its length. A year drawn DASHED is a year in which more than
    20 % of the line's fleet-days were filed as something other than a
    passenger ship (sql/44): the line is a lower bound there, not a
    measurement.
    """
    order = [y for y in YEARS]
    # Consecutive years touch (a short gap so the blocks are countable); a jump
    # in the archive gets a wide one, so the eye reads 2015 | 2018 as a skip and
    # 2024 | 2025 as a turn of the year.
    NEAR, FAR = 10, 60
    offset, x0 = {}, 0
    for i, year in enumerate(order):
        offset[year] = x0
        length = (datetime.date(year + 1, 1, 1) - datetime.date(year, 1, 1)).days
        nxt = order[i + 1] if i + 1 < len(order) else None
        x0 += length + (0 if nxt is None else NEAR if nxt == year + 1 else FAR)

    def xof(day):
        d = datetime.date.fromisoformat(day)
        return offset[d.year] + (d - datetime.date(d.year, 1, 1)).days

    index = collections.defaultdict(dict)
    for row in panel:
        if loaded(row):
            index[row["line"]][row["day"]] = row

    fig, axes = plt.subplots(4, 2, figsize=(12.0, 9.8), sharex=True)
    top_row = set(axes[0])
    for ax, (line, island) in zip(axes.flatten(), LIFELINES):
        rows_by_day = index[line]
        drawn_years = 0
        top = 0
        for year in order:
            days = {d: r["crossings"] for d, r in rows_by_day.items()
                    if r["year"] == year and r["fleet_positions"] > 0}
            if not days:
                continue
            smooth = rolling(days)
            if not smooth:
                continue
            drawn_years += 1
            hidden = hidden_share(hid_line, line, year) > HIDDEN_MARK
            # one segment per unbroken stretch, so a silent week is a hole in
            # the line and not a dive to zero
            style = (0, (4, 2)) if hidden else "solid"
            seg_x, seg_y, prev = [], [], None
            for day in sorted(smooth):
                if prev is not None and days_between(prev, day) > 1:
                    ax.plot(seg_x, seg_y, color=FERRY, linewidth=1.3,
                            linestyle=style)
                    seg_x, seg_y = [], []
                seg_x.append(xof(day))
                seg_y.append(smooth[day])
                prev = day
            ax.plot(seg_x, seg_y, color=FERRY, linewidth=1.3, linestyle=style)
            top = max(top, max(smooth.values()))
            # Oct-Apr, sql/41's own season split, shaded under the curve
            for a, b in (("01-01", "04-30"), ("10-01", "12-31")):
                ax.axvspan(xof(f"{year}-{a}"), xof(f"{year}-{b}"),
                           color=GRID, alpha=0.35, linewidth=0, zorder=0)
        # (new) every panel must carry nearly the whole archive; a line that
        # lost a year to a filter would otherwise be read as a line that ran.
        assert drawn_years >= 5, \
            f"{line}: only {drawn_years} of {len(order)} loaded years drawn"

        top = top * 1.22 or 1
        ax.set_ylim(-0.03 * top, top)
        tick_y = 0.012 * top
        median = month_median(panel, line, "07")
        summer = [r["crossings"] for r in rows_by_day.values()
                  if r["season"] == "may-sep" and r["fleet_positions"] > 0]
        if summer:
            ax.axhline(statistics.median(summer), color=MUTED, linewidth=0.8,
                       linestyle=(0, (4, 3)), zorder=1)
        # the still-day ticks
        due = [d for d, r in rows_by_day.items() if zero_kind(r) == "lay still"
               and r["baseline"] > 0]
        runs = still_runs(due)
        for run in runs:
            ax.plot([xof(run[0]), xof(run[-1]) + 1], [tick_y, tick_y],
                    color=INK, linewidth=3.4, solid_capstyle="butt", zorder=4)
        if runs:
            longest = max(runs, key=len)
            ax.annotate(f"{len(longest)} d",
                        (xof(longest[0]) + len(longest) / 2, tick_y),
                        xytext=(0, 6), textcoords="offset points", color=INK,
                        fontsize=7, ha="center", zorder=5)
        if any(hidden_share(hid_line, line, y) > HIDDEN_MARK for y in order):
            ax.annotate("part of the fleet outside the archive", (0.995, 0.94),
                        xycoords="axes fraction", color=MUTED, fontsize=7,
                        ha="right", va="top")
        cell = collections.Counter()
        for year in order:
            if (line, year) in per_ly:
                cell.update(per_ly[(line, year)])
        lost = 100 * cell["lay still, scheduled"] / cell["days"]
        ax.set_title(f"{island} · {line}\nJuly {fmt(median)} · January "
                     f"{fmt(month_median(panel, line, '01'))} · lost "
                     f"{lost:.1f} % of due days",
                     color=INK, fontsize=8.5, loc="left",
                     pad=16 if ax in top_row else 6)
        tidy(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_xlim(-NEAR, x0 + NEAR)
    for ax in axes[:, 0]:
        ax.set_ylabel("crossings/day, 7-day mean", color=MUTED, fontsize=8)
    for ax in axes[-1]:
        ax.set_xticks([offset[y] + 182 for y in order])
        ax.set_xticklabels([str(y) for y in order], fontsize=8)
    for ax in axes[0]:                     # the year label at each block's top
        for year in order:
            ax.annotate(str(year), (offset[year] + 182, 1.005),
                        xycoords=("data", "axes fraction"), color=MUTED,
                        fontsize=7.5, ha="center", va="bottom",
                        annotation_clip=False)
    fig.suptitle("The lifelines: crossings per day, 7-day mean · grey = "
                 "Oct–Apr · dashed = part of the fleet outside the archive · "
                 "ticks = ≥ 3 still days with the fleet heard",
                 color=INK, fontsize=10, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(IMG / "ch03-lifelines.png", dpi=160, facecolor="white")


def chart_storm(panel, runs, island_lines):
    """Chart 2 -- every named storm in a loaded year, island lines against big."""
    index = {(row["line"], row["day"]): row for row in panel}
    cols = 4
    rowsn = (len(runs) + cols - 1) // cols
    fig, axes = plt.subplots(rowsn, cols, figsize=(11.5, 2.2 * rowsn),
                             sharey=True)
    flat = axes.flatten()
    dropped = 0
    for ax, (names, run) in zip(flat, runs):
        for group, colour, label in ((island_lines, FERRY, "island lines"),
                                     (BIG, SLATE, "big lines")):
            prof, drop = storm_profile(index, group, run)
            dropped += drop
            xs = [o for o, v, _, _ in prof if v is not None]
            ys = [v for _, v, _, _ in prof if v is not None]
            ax.plot(xs, ys, color=colour, linewidth=1.8, marker="o",
                    markersize=3, label=label)
        for offset in range(len(run)):
            ax.axvspan(offset - 0.5, offset + 0.5, color=GRID, alpha=0.55,
                       linewidth=0)
        ax.axhline(1.0, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
        ax.set_xticks(range(-3, 4))
        ax.set_xlim(-3.3, 3.3)
        ax.set_ylim(0.35, 1.3)
        ax.set_title(f"{names}\n{run[0]}"
                     + (f" → {run[-1][5:]}" if len(run) > 1 else ""),
                     color=INK, fontsize=8.5, loc="left")
        tidy(ax)
    for ax in flat[len(runs):]:
        ax.set_visible(False)
    for col in range(cols):                    # the last VISIBLE row per column
        column = [axes[r][col] for r in range(rowsn) if axes[r][col].get_visible()]
        column[-1].set_xlabel("days from the storm's first day", color=MUTED,
                              fontsize=8)
    for row in axes:
        row[0].set_ylabel("crossings ÷ baseline", color=MUTED, fontsize=8.5)
    fig.legend(*flat[0].get_legend_handles_labels(), frameon=False, fontsize=8.5,
               labelcolor=MUTED, ncol=2, loc="upper right",
               bbox_to_anchor=(0.995, 1.0))
    fig.suptitle("Named storms: crossings against the line's own baseline · "
                 "shaded = the storm's calendar days · dashed = an ordinary day",
                 color=INK, fontsize=10.5, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.955 if rowsn > 2 else 0.92))
    fig.savefig(IMG / "ch03-storm.png", dpi=160, facecolor="white")
    return dropped


def chart_speed(spd, picks, control):
    """Chart 3 -- median speed made good per year, on the lines that changed ship.

    The last panel is the control: one ship, all six years, so the reader can
    see what "no replacement" looks like on the same axis — and see that it is
    not a flat line either.
    """
    fig, axes = plt.subplots(1, len(picks) + 1, figsize=(12.6, 3.6))
    for ax, line in zip(axes, picks + [control]):
        years = [y for y in YEARS if y in spd[line]]
        ys = [spd[line][y]["med_kn"] for y in years]
        colour = SLATE if line == control else FERRY
        ax.plot(range(len(years)), ys, color=colour, linewidth=2, marker="o",
                markersize=4)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels([str(y) for y in years], fontsize=7, rotation=45)
        lo, hi = min(ys), max(ys)
        pad = max(0.35, 0.35 * (hi - lo))
        ax.set_ylim(lo - pad, hi + 2.4 * pad)
        # The vessel names ride along the TOP of the panel, at the year the
        # name first appears, never on the line itself: on a 2.19 nm line the
        # step is 0.6 kn and a label pinned to the marker sits on the curve.
        seen, slot = None, 0
        for i, y in enumerate(years):
            name = spd[line][y]["modal_vessel"]
            if name != seen:
                ax.annotate(name, (i, hi + (2.0 - 0.45 * (slot % 2)) * pad),
                            xytext=(1, 0), textcoords="offset points",
                            color=colour, fontsize=7, ha="left", va="center",
                            annotation_clip=False)
                seen, slot = name, slot + 1
        nm = spd[line][years[-1]]["med_nm"]
        ax.set_title(f"{line}\n{nm:.2f} nm"
                     + ("  · control" if line == control else ""),
                     color=INK, fontsize=8.5, loc="left")
        tidy(ax)
    axes[0].set_ylabel("median speed made good, kn", color=MUTED, fontsize=8.5)
    fig.suptitle("A new ship is a step: median berth-to-berth speed per year, "
                 "on the lines where one vessel replaced another and the "
                 "distance did not move (within 3 %)",
                 color=INK, fontsize=10.5, x=0.006, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    fig.savefig(IMG / "ch03-speed.png", dpi=160, facecolor="white")


# ------------------------------------------------------------ numbers ----
def numbers(panel, unmatched, spd, faster, orc, tt, per_ly, runs, per_storm,
            island_lines, dropped, charted_speed, hid_line, hid_year,
            hid_vessels):
    """Every figure notes/ch03-findings.md quotes. Printed, never hand-typed."""
    orc_rows, worst_gap, at_22 = orc
    index = {(row["line"], row["day"]): row for row in panel}
    svc = services(panel)

    print("\n== the store, as sql/41 emits it ==")
    days = collections.defaultdict(set)
    for row in panel:
        days[row["year"]].add(row["day"])
    harbour = {row["line"] for row in panel if row["kind"] == "harbour"}
    print(f"line-days {len(panel)}, distinct local days "
          f"{len({row['day'] for row in panel})}, lines "
          f"{len({row['line'] for row in panel})}, island lines "
          f"{len(island_lines)} (the four big lines of chart 2 excluded, one of "
          "which sql/40 files as `island`: Køge – Rønne)")
    print("  " + "  ".join(f"{y}:{len(days[y])}d" for y in sorted(days))
          + "   (* 2022 and 2023 are winter windows, not years)")
    print(f"  kind = 'harbour', excluded from every pool and table below: "
          f"{len(harbour)} lines, "
          f"{sum(1 for row in panel if row['kind'] == 'harbour')} line-days — "
          + "; ".join(sorted(harbour)))
    print("  Københavns havnebus is in the panel as `domestic`, and sql/40's "
          "termini rule costs it 29 % of its crossings (a multi-stop harbour "
          "network whose OSM relations carry only the two extreme ends); it is "
          "quoted nowhere in this chapter.")

    print("\n== the oracle (sql/43): Svendborg – Ærøskøbing, July 2025 ==")
    print("day          oracle  table   gap   vessels (oracle/table)")
    for r in orc_rows:
        print(f"{r['day']}   {r['oracle']:5d} {r['table']:6d} {r['gap']:+5d}"
              f"      {r['oracle_vessels']} / {r['table_vessels']}")
    print(f"max |gap| {worst_gap} over 31 days (bound 1); the table reads 22 on "
          f"{at_22} of 31 days (bound 28); both sides see exactly 2 vessels on "
          "all 31 days (the assert a finder broke the 24 h bound past)")

    print("\n== the timetable check (sql/41 against data/context/ferry_timetable.csv) ==")
    print("observed = median crossings/day, July weekdays the fleet was heard "
          "on; expected = 2 x the operator's departures per direction")
    print(f"{'line':32s} {'2x tt':>6} {'2025':>7} {'2026':>7} {'2026/tt':>8}  operator")
    for rec in tt:
        exp = 2 * rec["departures"] if rec["departures"] else None
        o25, o26 = rec["observed"][2025], rec["observed"][2026]
        ratio = f"{o26 / exp:7.2f}" if exp and o26 is not None else "      -"
        print(f"{rec['line']:32s} {exp if exp else '-':>6} {fmt(o25):>7} "
              f"{fmt(o26):>7} {ratio}  {rec['operator']}")
    missing = [rec["route"] for rec in tt if rec["departures"] is None]
    print("no published departure count: " + "; ".join(missing)
          + " — the operators render the timetable client-side or publish a "
            "frequency rule instead (see the file's `note` column)")
    print("Ystad – Rønne reads '-': it has no July weekday on which its own "
          "fleet was heard at all. Its conventional tonnage's majority line is "
          "elsewhere and its fast ferries are not in `public_track`.")
    print("the same two lines' BASELINES, read off sql/41 rather than "
          "recomputed — one per day of the week, May-Sep, Monday first:")
    for line, expect in (("Svendborg – Ærøskøbing", 22), ("Branden – Fur", 144)):
        for year in (2025, 2026):
            base = [baseline_of(panel, line, year, "may-sep", d)
                    for d in range(1, 8)]
            med = statistics.median(base[:5])
            print(f"  {line:24s} {year}  " + " ".join(f"{b:3d}" for b in base)
                  + f"   Mon-Fri median {med:5.1f} against the timetable's "
                    f"{expect} ({100 * med / expect:5.1f} %)")
    print("  Grenaa – Anholt, the line the day-of-week key was added for "
          "(2025, Mon first):")
    for season in ("may-sep", "oct-apr"):
        base = [baseline_of(panel, "Grenaa – Anholt", 2025, season, d)
                for d in range(1, 8)]
        print(f"    {season}  " + " ".join(f"{b:3d}" for b in base)
              + "   (Wednesday 0: the line does not sail one)")

    print("\n== island lines: the summer timetable against the winter one ==")
    print("median crossings/day, loaded years pooled, days the fleet was heard on")
    print(f"{'line':32s} {'Jul':>6} {'Jan':>6} {'Jul/Jan':>8} {'wkday':>6} "
          f"{'Sun':>6} {'Sun/wkday':>10}")
    season_rows = []
    for line in sorted(island_lines):
        def med(pred):
            vals = [row["crossings"] for row in panel
                    if row["line"] == line and loaded(row)
                    and row["fleet_positions"] > 0 and pred(row)]
            return statistics.median(vals) if vals else None
        season_rows.append((
            line,
            med(lambda r: r["day"][5:7] == "07" and r["daytype"] == "weekday"),
            med(lambda r: r["day"][5:7] == "01" and r["daytype"] == "weekday"),
            med(lambda r: r["daytype"] == "weekday"),
            med(lambda r: r["daytype"] == "sun")))
    for line, jul, jan, wkd, sun in sorted(season_rows,
                                           key=lambda t: -(t[1] or 0)):
        r_s = f"{jul / jan:8.2f}" if jul and jan else "       -"
        r_w = f"{sun / wkd:10.2f}" if sun is not None and wkd else "         -"
        print(f"{line:32s} {fmt(jul):>6} {fmt(jan):>6} {r_s} {fmt(wkd):>6} "
              f"{fmt(sun):>6} {r_w}")
    flat_week = [line for line, jul, jan, wkd, sun in season_rows
                 if wkd and sun is not None and sun == wkd]
    print(f"island lines whose Sunday median equals their weekday median: "
          f"{len(flat_week)} of {len(season_rows)} — " + ", ".join(flat_week))
    for floor in (10, 20):
        jul = sum(1 for _, j, _, _, _ in season_rows if j is not None and j >= floor)
        jan = sum(1 for _, _, a, _, _ in season_rows if a is not None and a >= floor)
        print(f"island lines running >= {floor} crossings a day: {jul} in July, "
              f"{jan} in January (of {len(season_rows)})")

    print("\n== how a day with no crossing reads (sql/41's four coverage columns) ==")
    print("silent = the line's own fleet reported nothing · cannot tell = heard "
          "but no usable speed all day · lay still = heard, under way nowhere · "
          "moved, nothing matched = under way, no crossing on this line")
    print("a lay-still day whose baseline is 0 is the timetable — sql/41 keys "
          "the baseline on the DAY OF WEEK, so Grenaa – Anholt's Wednesday, on "
          "which it never sails, has a baseline of 0 and is an ordinary day. "
          "The cancellation column is the other kind: a line that normally "
          "sails that day of the week, and did not.")
    print(f"{'line':32s} {'days':>5} {'sailed':>7} "
          f"{'silent':>7} {'c/tell':>7} {'still/tt':>9} {'STILL, DUE':>11} "
          f"{'moved':>6} {'due %':>7}")
    agg = collections.defaultdict(collections.Counter)
    for (line, year), cell in per_ly.items():
        if line in island_lines and year in YEARS:
            agg[line].update(cell)
    for line in sorted(agg, key=lambda l: -agg[l]["lay still, scheduled"]
                       / agg[l]["days"]):
        c = agg[line]
        print(f"{line:32s} {c['days']:5d} "
              f"{c['sailed']:7d} {c['silent']:7d} "
              f"{c['cannot tell']:7d} {c['lay still, no baseline']:9d} "
              f"{c['lay still, scheduled']:11d} "
              f"{c['moved, nothing matched']:6d} "
              f"{100 * c['lay still, scheduled'] / c['days']:6.1f}")
    tot = collections.Counter()
    for (line, year), cell in per_ly.items():
        if line in island_lines and year in YEARS:
            tot.update(cell)
    print(f"\nall island lines, six loaded years: {tot['days']} line-days = "
          f"{tot['sailed']} sailed + {tot['silent']} silent + "
          f"{tot['cannot tell']} cannot tell + {tot['lay still']} lay still "
          f"({tot['lay still, scheduled']} of them on a day the line normally "
          f"sails, {tot['lay still, no baseline']} on a day it does not) + "
          f"{tot['moved, nothing matched']} moved-nothing-matched")
    sailed_unheard = sum(1 for row in panel if row["line"] in island_lines
                         and loaded(row) and row["crossings"] > 0
                         and row["fleet_positions"] == 0)
    print(f"and the other direction: {sailed_unheard} island line-days have "
          f"crossings and NO coverage at all — the own-majority fleet is not "
          "always the fleet that sailed (sql/41's header states the trade)")
    print("\nper year, all island lines pooled:")
    for year in YEARS + WINDOWS:
        cells = [c for (line, y), c in per_ly.items()
                 if line in island_lines and y == year]
        n = sum(c["days"] for c in cells)
        still = sum(c["lay still, scheduled"] for c in cells)
        print(f"  {year}{'*' if year in WINDOWS else ' '} line-days {n:6d}  "
              f"sailed {sum(c['sailed'] for c in cells):6d}  "
              f"silent {sum(c['silent'] for c in cells):5d}  "
              f"lay still on a day it normally sails {still:5d} "
              f"({100 * still / n:4.1f} %)  moved-nothing-matched "
              f"{sum(c['moved, nothing matched'] for c in cells):5d}")

    print("\n== the days the eight charted lifelines lay still ==")
    for line, _ in LIFELINES:
        still = [row for row in panel if row["line"] == line and loaded(row)
                 and zero_kind(row) == "lay still" and row["baseline"] > 0]
        total = sum(per_ly[(line, y)]["days"] for y in YEARS if (line, y) in per_ly)
        hid = [y for y in YEARS if hidden_share(hid_line, line, y) > HIDDEN_MARK]
        print(f"{line:32s} {len(still):4d} lay-still days on a day it "
              f"normally sails, of {total:5d} loaded"
              + (f"   [hidden fleet > {HIDDEN_MARK:.0%} in {hid}]" if hid else ""))
        for row in still[:12]:
            print(f"      {row['day']} {row['daytype']:7s} baseline "
                  f"{row['baseline']:4d}  positions {row['fleet_positions']:6d}  "
                  f"moving {row['fleet_moving']:5d}"
                  f"{'   STORM DAY' if row['is_storm_day'] else ''}")
        if len(still) > 12:
            print(f"      ... and {len(still) - 12} more")

    print("\n== runs of consecutive lay-still days: a ship out of service ==")
    runs_off = laid_up(panel, island_lines)
    for length, line, first, last in runs_off[:12]:
        print(f"  {length:3d} days  {first} → {last}  {line}")
    print(f"  ... {len(runs_off)} such runs in all, "
          f"{sum(n for n, _, _, _ in runs_off)} line-days")
    charted = {name for name, _ in LIFELINES}
    fano = [r for r in runs_off if r[1] == "Esbjerg – Nordby"]
    shown = 0
    for length, line, first, last in runs_off:
        if line in charted and line != "Esbjerg – Nordby" and shown < 12:
            print(f"  charted line: {length:3d} days  {first} → {last}  {line}")
            shown += 1
    print(f"  Esbjerg – Nordby has {len(fano)} runs of its own, "
          f"{sum(n for n, _, _, _ in fano)} line-days — two of its three "
          "ferries are invisible to `public_track` in every year (sql/44), so "
          "those are the days the VISIBLE ferry rested, not days Fanø had no "
          "ferry")

    print("\n== Hals – Egense, the case the coverage columns were rebuilt for ==")
    for row in panel:
        if row["line"] == "Hals – Egense" and row["day"][:7] == "2025-07" \
                and row["day"][8:10] <= "06":
            print(f"  {row['day']} crossings {row['crossings']:4d}  baseline "
                  f"{row['baseline']:4d}  positions {row['fleet_positions']:5d}  "
                  f"sog known {row['fleet_sog_known']:5d}  moving "
                  f"{row['fleet_moving']:5d}  vessels reporting "
                  f"{row['fleet_vessels']}  -> {zero_kind(row)}")

    print("\n== the hidden fleet (sql/44) ==")
    print("store-wide, over the union of every line's fleet:")
    print(f"{'year':6s} {'fleet':>6} {'visible days':>13} {'hidden days':>12} "
          f"{'share':>7} {'vessels with a hidden day':>26}")
    for year in sorted(hid_year):
        h = hid_year[year]
        print(f"{year:6d} {h['fleet_vessels']:6d} {h['visible_days']:13d} "
              f"{h['hidden_days']:12d} {h['hidden_share']:7.4f} "
              f"{h['hidden_vessels']:26d}")
    print("\nisland line-years with a hidden share above 20 % (chart 1 marks these):")
    for (line, year), h in sorted(hid_line.items()):
        if h["kind"] == "island" and h["hidden_share"] > HIDDEN_MARK:
            print(f"  {line:32s} {year}  fleet {h['fleet_vessels']}  visible "
                  f"{h['visible_days']:5d}  hidden {h['hidden_days']:5d}  "
                  f"share {h['hidden_share']:.4f}  hidden vessels "
                  f"{h['hidden_vessels']}")
    print("\nthe Danish vessels behind it, by hidden days (sql/44 block 3):")
    for v in hid_vessels[:16]:
        print(f"  {v['vessel']:22s} {v['year']}  {v['line']:32s} "
              f"{v['hidden_days']:4d} days filed as {v['dominant_hidden_type']}")
    fur = [v for v in hid_vessels if v["line"] == "Branden – Fur"]
    print("  Branden – Fur, every hidden vessel-year: "
          + "; ".join(f"{v['vessel']} {v['year']} {v['hidden_days']} d "
                      f"({v['dominant_hidden_type']})" for v in fur))
    print("\nthe eight charted lifelines, hidden share by year:")
    for line, island in LIFELINES:
        cells = [f"{y}:{hidden_share(hid_line, line, y):.2f}" for y in YEARS]
        print(f"  {line:32s} " + "  ".join(cells))

    print("\n== the storms ==")
    print("pooled crossings / baseline, offset in days from the storm's first "
          "calendar day (the storm itself is 0 .. n-1); a line-day is dropped "
          "when the line's fleet was not heard")
    print(f"{'storm':26s} {'days':24s} {'group':16s} " +
          " ".join(f"{o:+5d}" for o in range(-3, 4)) + "   lines on day 0")
    for names, run in runs:
        label = run[0] + (f" → {run[-1][5:]}" if len(run) > 1 else "")
        for group, gname in ((island_lines, "island"), (BIG, "big")):
            prof, _ = storm_profile(index, group, run)
            print(f"{names:26s} {label:24s} {gname + ' pooled':16s} " +
                  " ".join("    -" if v is None else f"{v:5.2f}"
                           for _, v, _, _ in prof)
                  + f"   {prof[3][2]}")
            print(f"{'':26s} {'':24s} {gname + ' mean/line':16s} " +
                  " ".join("    -" if m is None else f"{m:5.2f}"
                           for _, _, _, m in prof))
    print(f"line-days dropped for silence across chart 2: {dropped}")
    print(f"storms.csv rows with at least one loaded calendar day: "
          f"{len(per_storm)}, in {len(runs)} runs "
          f"({sum(len(d) for d in per_storm.values())} storm line-days flagged "
          f"over {len({d for ds in per_storm.values() for d in ds})} dates)")

    print("\nthe three deepest storms, line by line (crossings / baseline; "
          "'-' = not heard, or no baseline):")
    deep = ["Dagmar · Egon", "Malik", "Pia"]
    for names, run in runs:
        if names not in deep:
            continue
        span = [shift(run[0], o) for o in range(-1, len(run) + 1)]
        print(f"  {names} — days " + " ".join(d[5:] for d in span))
        for line in BIG + [name for name, _ in LIFELINES]:
            cells = []
            for day in span:
                row = index.get((line, day))
                if row is None or row["fleet_positions"] == 0 or row["baseline"] == 0:
                    cells.append("    -")
                else:
                    cells.append(f"{row['crossings'] / row['baseline']:5.2f}")
            print(f"    {line:32s} " + " ".join(cells))

    print("\nisland lines, the storm's own days against the six ordinary days "
          "in the same window:")
    worst = []
    for names, run in runs:
        prof, _ = storm_profile(index, island_lines, run)
        vals = [v for o, v, _, _ in prof if v is not None and 0 <= o < len(run)]
        base = [v for o, v, _, _ in prof
                if v is not None and (o < 0 or o >= len(run))]
        if vals and base:
            worst.append((min(vals) / (sum(base) / len(base)), names, run[0],
                          min(vals), sum(base) / len(base)))
    worst.sort()
    for ratio, names, day, low, around in worst:
        print(f"  {names:26s} {day}  storm-day low {low:.2f} against "
              f"{around:.2f} around it = {100 * (1 - ratio):5.1f} % below")

    print("\n== speed, and the ships behind it (sql/42) ==")
    print("every line whose modal vessel changed between two loaded years at a "
          "modal share >= 0.8, with med_nm stable to 3 %:")
    print(f"{'line':30s} {'kind':13s} years  {'from':18s} {'to':18s} "
          f"{'kn':>13} {'minutes':>10} {'Δ kn':>7}")
    for rep in replacements(spd):
        print(f"{rep['line']:30s} {rep['kind']:13s} {rep['y0']}→{rep['y1']} "
              f"{rep['v0']:18s} {rep['v1']:18s} "
              f"{rep['kn0']:5.2f}→{rep['kn1']:5.2f} "
              f"{rep['min0']:5d}→{rep['min1']:4d} {100 * rep['d_kn']:+6.1f} %")

    print("\nthe full per-year rows for the five charted lines, plus the ones "
          "the note discusses beside them:")
    for line in charted_speed + ["Svendborg – Ærøskøbing", "Hou – Tunø",
                                 "Esbjerg – Nordby", "Branden – Fur",
                                 "Grenaa – Anholt"]:
        for year in YEARS + WINDOWS:
            if year not in spd[line]:
                continue
            r = spd[line][year]
            print(f"  {line:26s} {year}{'*' if year in WINDOWS else ' '} "
                  f"{r['crossings']:6d} crossings  {r['vessels']} vessel(s)  "
                  f"{r['modal_vessel']:18s} share {r['modal_share']:.2f}  "
                  f"{r['med_kn']:6.2f} kn (max {r['max_kn']:5.2f})  sog "
                  f"{r['med_sog_kn']:5.2f}  {r['med_min']:3d} min (p10 "
                  f"{r['p10_min']:3d} p90 {r['p90_min']:3d})  "
                  f"{r['med_nm']:6.2f} nm")
        print()

    print("== what max_kn says about sql/40's 30 kn guard ==")
    danish_years = [r for line in spd for r in spd[line].values()
                    if r["kind"] in ("island", "domestic")]
    for floor in (15, 20, 25):
        print(f"  Danish line-years with max_kn above {floor} kn: "
              f"{sum(1 for r in danish_years if r['max_kn'] > floor)} of "
              f"{len(danish_years)}")
    for r in sorted(danish_years, key=lambda r: -r["max_kn"])[:4]:
        print(f"  {r['max_kn']:6.2f} kn fastest against a median of "
              f"{r['med_kn']:5.2f}  {r['line']:28s} {r['year']}")
    top = max((r for line in spd for r in spd[line].values()),
              key=lambda r: r["max_kn"])
    print(f"  the store-wide maximum is {top['max_kn']:.2f} kn ({top['line']} "
          f"{top['year']}, {top['kind']}), against sql/40's 30 kn guard. The "
          "guard was 40 until this column showed a 10.17 nm crossing recorded "
          "in 16 minutes; at 30 no Danish line-year reaches it and every "
          "figure this chapter quotes is a median anyway.")

    print("\n== speed made good above the vessel's own median sog (sql/42) ==")
    for row in faster:
        print(f"  {row['line']:34s} {row['year']}  made good {row['med_kn']:5.2f} kn "
              f"against a reported median sog of {row['med_sog_kn']:5.2f} kn, "
              f"{row['crossings']} crossings")
    print(f"  {len(faster)} rows of {sum(len(v) for v in spd.values())} — two "
          "medians over different populations, and thin ones")

    print("\n== the fastest and the slowest Danish lines, 2025 (sql/42) ==")
    print("  made good / sog = how much of the ship's own speed survives "
          "berth-to-berth")
    danish = [spd[line].get(2025) for line in spd]
    danish = [r for r in danish if r and r["crossings"] >= 200
              and r["kind"] in ("island", "domestic", "international")]
    danish.sort(key=lambda r: -r["med_kn"])
    for r in danish[:5] + danish[-5:]:
        print(f"  {r['med_kn']:6.2f} kn made good (sog {r['med_sog_kn']:5.2f}, "
              f"{100 * r['med_kn'] / r['med_sog_kn']:3.0f} %)  "
              f"{r['med_nm']:6.2f} nm  {r['med_min']:3d} min  {r['line']:32s} "
              f"{r['modal_vessel']}")
    for line in ("Grenaa – Anholt", "Branden – Fur"):
        r = spd[line][2025]
        print(f"  {r['med_kn']:6.2f} kn made good (sog {r['med_sog_kn']:5.2f}, "
              f"{100 * r['med_kn'] / r['med_sog_kn']:3.0f} %)  "
              f"{r['med_nm']:6.2f} nm  {r['med_min']:3d} min  {r['line']:32s} "
              f"{r['modal_vessel']}   (quoted in the note, not in the top or "
              "bottom five)")

    print("\n== what sql/40 could not match to a route (sql/41, second block) ==")
    print(f"{'year':6s} {'crossings':>10} {'unmatched <1 km':>16} "
          f"{'>=1 km':>8} {'share':>7} {'>=1 km share':>13} {'below floor':>12} "
          f"{'in block 1':>11}")
    agg2 = collections.Counter()
    for u in unmatched:
        print(f"{u['year']:6d} {u['crossings']:10d} {u['lt1km']:16d} "
              f"{u['ge1km']:8d} {u['share']:7.4f} {u['ge1km_share']:13.4f} "
              f"{u['below_floor']:12d} {u['in_first_block']:11d}")
        for k in ("crossings", "lt1km", "ge1km", "below_floor", "in_first_block"):
            agg2[k] += u[k]
    print(f"{'all':6s} {agg2['crossings']:10d} {agg2['lt1km']:16d} "
          f"{agg2['ge1km']:8d} "
          f"{(agg2['lt1km'] + agg2['ge1km']) / agg2['crossings']:7.4f} "
          f"{agg2['ge1km'] / agg2['crossings']:13.4f} {agg2['below_floor']:12d} "
          f"{agg2['in_first_block']:11d}")
    print(f"of {agg2['crossings']} crossings, {agg2['in_first_block']} carry a "
          f"line = {100 * agg2['in_first_block'] / agg2['crossings']:.1f} %; "
          f"the panel's own sum over service lines is "
          f"{sum(row['crossings'] for row in svc)} and over all kinds "
          f"{sum(row['crossings'] for row in panel)}")


def laid_up(panel, lines, minimum=3):
    """Maximal runs of >= `minimum` consecutive lay-still days, per line.

    A single lay-still day is weather or a breakdown. A RUN of them, with the
    fleet reporting from the berth the whole time, is a ship out of service —
    a docking or a refit. The chapter has to separate the two before it says
    anything about cancellation.
    """
    days = collections.defaultdict(list)
    for row in panel:
        if row["line"] in lines and zero_kind(row) == "lay still":
            days[row["line"]].append(row["day"])
    out = []
    for line, ds in days.items():
        cur = []
        for day in sorted(ds):
            if cur and days_between(cur[-1], day) == 1:
                cur.append(day)
            else:
                if len(cur) >= minimum:
                    out.append((len(cur), line, cur[0], cur[-1]))
                cur = [day]
        if len(cur) >= minimum:
            out.append((len(cur), line, cur[0], cur[-1]))
    out.sort(reverse=True)
    return out


def fmt(v):
    return "-" if v is None else f"{v:.0f}"


class Tee(io.StringIO):
    """stdout, recorded, so guard (e) can be run against the real output."""

    def write(self, s):
        sys.__stdout__.write(s)
        return super().write(s)


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    # One query at a time: the store lock is exclusive (docs/DECISIONS.md).
    panel, unmatched = daily()
    spd, faster = speed()
    orc = oracle()
    hid_line, hid_year, hid_vessels = hidden()

    # (7) The three files must be talking about the same set of lines. sql/42
    # drops a line-year with no crossing over a minute and sql/44 adds the
    # line-years a line was entirely hidden for, so the containment is
    # one-directional: 42 within 41 within 44. A line that appears in one and
    # not the next is a fold that stopped agreeing between the files, which is
    # exactly what the S8 review found when each file resolved its own labels.
    lines_41 = {row["line"] for row in panel}
    lines_42 = set(spd)
    lines_44 = {line for line, _ in hid_line}
    assert lines_42 <= lines_41, f"sql/42 has lines sql/41 lacks: {lines_42 - lines_41}"
    assert lines_41 <= lines_44, f"sql/41 has lines sql/44 lacks: {lines_41 - lines_44}"

    # (4) THE FOLD. Block 2 counts crossings straight off `ferry_crossing`;
    # block 1 is the zero-filled per-line-day panel. The panel can never hold
    # MORE than block 2 says carry a line, and it holds all but a named
    # remainder: sql/41's day domain drops local days whose UTC date has no
    # `ferry_day` row, which is 150 crossings on six days — 2016-01-01,
    # 2019-01-01, 2022-03-01, 2023-03-01, 2024-01-01 and 2026-08-27, the
    # spill-over at the edges of the loaded windows (sql/41's header, "TWO
    # DAY-BOUNDARY FACTS"). The bound is 200, not 150, because a loader that
    # adds a day changes the remainder and should not turn this file red; a
    # day domain that lost a real day moves it by thousands.
    # (The per-year split cannot be compared: block 2 keys the year on the UTC
    # date and block 1 on the local one.)
    panel_total = sum(row["crossings"] for row in panel)
    block2_total = sum(u["in_first_block"] for u in unmatched)
    assert 0 <= block2_total - panel_total <= 200, \
        (f"the panel holds {panel_total} crossings, sql/41's second block says "
         f"{block2_total} carry a line — a gap of "
         f"{block2_total - panel_total}, not the ~150 edge-day spill-over")
    for u in unmatched:
        # Every crossing of the year is in exactly one of the four buckets.
        assert (u["lt1km"] + u["ge1km"] + u["below_floor"] + u["in_first_block"]
                == u["crossings"]), \
            (f"{u['year']}: {u['lt1km']} + {u['ge1km']} + {u['below_floor']} + "
             f"{u['in_first_block']} != {u['crossings']}")
        # Measured 5.1-11.4 % a year. 15 % is a ceiling, not a target: past it
        # the route matcher has stopped being a matcher and the chapter's
        # counts are a sample of unknown size.
        assert u["share"] < 0.15, \
            f"{u['year']}: {u['share']:.1%} of crossings match no route"

    island_lines = sorted({row["line"] for row in panel
                           if row["kind"] == "island" and row["line"] not in BIG})
    for line in BIG:
        assert any(row["line"] == line for row in panel), f"sql/41 has no {line}"
    tt = timetable(panel)
    per_ly = per_line_year(panel, set(island_lines))
    runs, per_storm = storm_windows(panel)

    # (b) the plan's own Validate: the Ærø line against the 2026 timetable, in
    # 2026, because the timetable file is the 2026 one. 11 departures per
    # direction on a summer weekday = 22 crossings a day. The tolerance is +-2,
    # i.e. one round trip.
    aero = july_weekday_median(panel, "Svendborg – Ærøskøbing", 2026)
    expect = 2 * next(r["departures"] for r in tt
                      if r["route"] == "Svendborg – Ærøskøbing")
    assert expect == 22 and abs(aero - expect) <= 2, \
        f"Svendborg – Ærøskøbing July 2026: {aero} crossings/day against {expect}"
    # (c) Fur, the busiest and the shortest: 72 departures per direction a day
    # derived from the operator's frequency rule, so 144 crossings. 10 % is the
    # slack the rule itself carries (the evening sailings run only if someone
    # is waiting); the measured shortfall is about 5 %.
    fur = july_weekday_median(panel, "Branden – Fur", 2026)
    fur_expect = 2 * next(r["departures"] for r in tt if r["route"] == "Branden – Fur")
    assert fur_expect == 144 and abs(fur - fur_expect) / fur_expect < 0.10, \
        f"Branden – Fur July 2026: {fur} crossings/day against {fur_expect}"
    # (2) THE BASELINE AGAINST AN OUTSIDE NUMBER, read off the rows, one day of
    # the week at a time. The timetable is the only figure in this chapter that
    # does not come from the store, and the baseline is what every ratio in § 3
    # and § 4 divides by. Three rules make it and all three move this number:
    # quantileExactLow (quantileExact returns the UPPER middle and puts the
    # lower-middle ordinary day below its own baseline), signal days only
    # (silent days as zeros put Rønbjerg – Livø's 2015 winter baseline at 0
    # instead of 10), and the day-of-week key.
    aero_base = [baseline_of(panel, "Svendborg – Ærøskøbing", 2026, "may-sep", d)
                 for d in range(1, 6)]
    assert aero_base == [22] * 5, \
        (f"Svendborg – Ærøskøbing 2026 may-sep Mon-Fri baselines {aero_base}, "
         "not the timetable's 11 x 2 on every one")
    # Fur's rule-derived 144 is a frequency, not a departure list, so the
    # per-day baselines scatter: the median of the five is within 5 % and no
    # single day is more than 10 % off. A flat 5 % on every day fails on the
    # 136 that Friday reads, which is the timetable's own slack and not an
    # error.
    fur_base = [baseline_of(panel, "Branden – Fur", 2026, "may-sep", d)
                for d in range(1, 6)]
    assert abs(statistics.median(fur_base) - 144) / 144 < 0.05 \
        and max(abs(b - 144) for b in fur_base) / 144 < 0.10, \
        f"Branden – Fur 2026 may-sep Mon-Fri baselines {fur_base} against 2 x 72"
    # (1 of the new SQL) THE DAY-OF-WEEK KEY ITSELF, on the line it was
    # introduced for. Grenaa – Anholt sails Mon, Tue, Thu and Fri and NEVER a
    # Wednesday; under the old `daytype` key its weekday baseline was 2 and
    # every Wednesday in the archive read as a day the line should have sailed
    # and did not — 237 of them. Wednesday's baseline is now 0, Saturday's and
    # Sunday's too in winter, and the four sailing days still read 2. Pinned on
    # 2025 oct-apr, where the pattern holds in every loaded year; the summers
    # of 2018 and 2026 are the two in which the line does sail on a Wednesday.
    anholt = {d: baseline_of(panel, "Grenaa – Anholt", 2025, "oct-apr", d)
              for d in range(1, 8)}
    assert anholt == {1: 2, 2: 2, 3: 0, 4: 2, 5: 2, 6: 0, 7: 0}, \
        f"Grenaa – Anholt 2025 oct-apr baselines by day of week: {anholt}"
    # (8) The two Hals – Egense days the coverage rebuild was done for, read
    # off the rows instead of hand-carried into the note.
    hals = {row["day"]: row for row in panel if row["line"] == "Hals – Egense"}
    for day in ("2025-07-03", "2025-07-04"):
        assert zero_kind(hals[day]) == "lay still", \
            (f"Hals – Egense {day} reads {zero_kind(hals[day])}, not 'lay still' "
             f"— positions {hals[day]['fleet_positions']}, moving "
             f"{hals[day]['fleet_moving']}")

    chart_lifelines(panel, hid_line, per_ly)
    dropped = chart_storm(panel, runs, island_lines)
    picks = list(dict.fromkeys(r["line"] for r in replacements(spd)
                               if r["kind"] in ("island", "domestic")))[:4]
    assert "Søby – Fynshav" in picks, \
        f"the ELLEN step is not in the selection: {picks}"
    # The control: PRINSESSE ISABELLA has run Hou – Sælvig alone in all six
    # loaded years, so its panel is the metric's own noise floor. Asserted,
    # because a control that quietly changed ship is worse than no control.
    control = "Hou – Sælvig"
    control_names = {spd[control][y]["modal_vessel"] for y in YEARS}
    assert control_names == {"PRINSESSE ISABELLA"}, \
        f"the control line changed ship: {control_names}"
    # (7) The Ærø crossing takes 73-75 minutes and sql/40 cuts a session at a
    # 60-minute position gap, so a p90 anywhere near two hours means the
    # session guard stopped cutting and a berth stay is being counted as a
    # crossing. 120 is double the guard.
    for year in YEARS:
        p90 = spd["Svendborg – Ærøskøbing"][year]["p90_min"]
        assert p90 < 120, \
            f"Svendborg – Ærøskøbing {year}: p90 {p90} min — is the 60-minute " \
            "session split still there?"
    chart_speed(spd, picks, control)

    out = Tee()
    sys.stdout = out
    numbers(panel, unmatched, spd, faster, orc, tt, per_ly, runs, per_storm,
            island_lines, dropped, picks + [control], hid_line, hid_year,
            hid_vessels)
    sys.stdout = sys.__stdout__
    # (e) THE MMSI GUARD. CLAUDE.md forbids a private vessel's MMSI anywhere
    # near an output. It is a blunt instrument and it has to be: a 9-digit
    # integer is an MMSI, an OSM way id, or a coincidence, and this grep cannot
    # tell them apart — which is why sql/40 now fails its build rather than
    # falling back to an `osm_type:osm_id` line label, and why daily() checks
    # the line labels separately before this fires.
    hit = re.search(r"\b\d{9}\b", out.getvalue())
    assert hit is None, f"a 9-digit integer reached stdout: {hit.group(0)!r}"
    print(f"\nno 9-digit integer in {len(out.getvalue())} characters of output "
          "(the MMSI guard)")
    print(f"wrote {IMG}/ch03-lifelines.png, ch03-storm.png, ch03-speed.png",
          file=sys.stderr)
