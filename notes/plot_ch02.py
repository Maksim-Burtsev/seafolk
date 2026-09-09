#!/usr/bin/env python3
"""S7 chapter-02 charts: three PNGs into notes/img/, and the numbers behind them.

    uv run --project notes notes/plot_ch02.py

Same contract as notes/plot.py and notes/plot_ch01.py, whose helpers this file
imports: queries run through scripts/ch.sh against the `clickhouse local --path
data/ch` store, one at a time (the store lock is exclusive), there is no client
library, matplotlib is the one dependency, and every number the note quotes is
printed by numbers() below.

Chart 1 reproduces the geometry already prototyped in site/day-clocks.html:
midnight at the top, hours clockwise, radius linear in the hour's share of the
day, an inner hole, and a dashed reference circle at a flat day's 100/24 =
4.167 %. The site's constants are R_IN 20 / R_MAX 92 inside a 240-unit box with
13 % reaching the outer edge; matplotlib gets the same shape from set_rorigin.

2022 and 2023 hold 59 winter days each and are excluded from every chart and
every headline here; they appear in the printed numbers and in the note's
caveats only. sql/30 and sql/32 emit a `year` column and the filtering happens
in YEARS below; sql/31 pools the years and emits no `year`, so it drops the two
windows in SQL instead — same calendar, different place.
"""
import collections
import math
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot import IMG, INK, MUTED, GROUPS, label_ends, rows, tidy

YEARS = [2015, 2018, 2021, 2024, 2025, 2026]
SEASONS = ["May-Sep", "Oct-Apr"]
DAYTYPES = ["weekday", "sat", "sun"]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NIGHT = [22, 23, 0, 1, 2, 3, 4]            # sql/24's definition, reused verbatim
FLAT_DAY = 1 / 24                          # 4.167 % — a day with no rhythm
FLAT_WEEK = 1 / 168
# The four harbours drawn in chart 3. Marina names are public (the privacy rule
# is about vessels); `place` is the named marina nearest the cell centre, so it
# is a landmark for a ~5 km cell, not an inventory of it.
# THE LISTS ARE KEYED ON h3, NOT ON `place`: sql/31's header calls `place` a landmark and a
# REUSABLE LITERAL — every cell whose marinas are all unnamed in OSM comes back
# as 'unnamed marina cell'. Two such cells would collapse into one dict entry
# and one chart panel, silently and plausibly. The name rides along as a label
# and is asserted against the file, so a rename upstream fails loudly instead.
PORTS = [("608534686242701311", "Sønderborg Havn"),
         ("608531603630587903", "Marstal Lystbådehavn"),
         ("608531604905656319", "Vindebyøre Bro"),
         ("608533723196948479", "Helsingør Nordhavn")]
# Four of sql/31's ten cells are four adjacent cells in ONE harbour, Svendborg
# Sund, and their ring-1 neighbourhoods overlap. Their curves must never be
# added together; chart 3 draws exactly one of them.
SVENDBORG = [("608531604905656319", "Vindebyøre Bro"),
             ("608531604955987967", "Lystbådehavn Troense"),
             ("608531604939210751", "Vindeby Havn"),
             ("608531605241200639", "Rantzausminde Lystbådehavn")]
SVENDBORG_H3 = {h3 for h3, _ in SVENDBORG}
# The project bounding box, and one cell centre pinned to the literal
# sql/33_port_oracle.sql's header carries. lat/lon are printed and never
# computed with, so nothing else in this file would notice them swapped —
# h3ToGeo(h3).1/.2 the wrong way round puts every Danish harbour in the Somali
# basin and every number stays green. scripts/ch.sh pins the argument order;
# this is the assert that says the pin held.
BBOX = (53.0, 59.0, 3.0, 17.0)
PIN = ("608531604905656319", 55.0589, 10.6251)
LEISURE, FERRY = "leisure Class B", "ferry Class A"


# ---------------------------------------------------------------- sql/30 ----
def hour_profiles():
    """sql/30 -> {(year, season, group, mobile, daytype): {hour: share}} and msgs.

    share_of_day is normalised inside each (year, season, group, mobile,
    daytype) partition, so pooling daytypes or years means weighting each
    partition by its own moving_msgs — which reconstructs the message ratio
    exactly, not approximately.
    """
    share, msgs = collections.defaultdict(dict), collections.Counter()
    for year, season, group, mobile, daytype, lhour, days, mm, sh in \
            rows("30_hour_profiles.sql"):
        key = (int(year), season, group, mobile, daytype)
        share[key][int(lhour)] = float(sh)
        msgs[key] += int(mm)

    for key, prof in share.items():
        # A partition is a clock: 24 hours, and its shares are a distribution.
        # The literals are the calendar, not a measurement, and they are what
        # catches a GROUP BY that lost a column: pool two fleets into one
        # partition and the sum lands near 2.0, drop a fleet from the PARTITION
        # BY and it lands near 0.5. A "< 0.05" tolerance would pass both.
        # Observed: 24 hours everywhere, sums 0.99990 to 1.00010 (sql/30 rounds
        # share_of_day to 5 dp, so 24 roundings can move the sum by 1.2e-4).
        assert len(prof) == 24, f"{key}: {len(prof)} hours, not 24"
        assert abs(sum(prof.values()) - 1.0) < 1e-3, \
            f"{key}: shares sum to {sum(prof.values())}, not 1"
    return share, msgs


def pooled_day(share, msgs, season, group, mobile,
               daytypes=DAYTYPES, years=YEARS):
    """The 24-hour curve for one fleet, pooled over daytypes and years."""
    tot, weight = collections.Counter(), 0
    for year in years:
        for daytype in daytypes:
            key = (year, season, group, mobile, daytype)
            if key not in share:
                continue
            weight += msgs[key]
            for hour, value in share[key].items():
                tot[hour] += value * msgs[key]
    assert weight, f"{season} {group} {mobile}: no rows to pool"
    return {hour: tot[hour] / weight for hour in range(24)}


def night_share(prof):
    return sum(prof[hour] for hour in NIGHT)


def check_fingerprints(share, msgs):
    """The bounds that catch a mis-read hour and a swapped fleet label."""
    for year in YEARS:
        prof = pooled_day(share, msgs, "May-Sep", "leisure", "Class B",
                          years=[year])
        peak = max(prof, key=prof.get)
        # Observed: the summer leisure peak is 12:00 in all six years, at
        # 11.5-11.9 % of the day. The floor is 11 because the store is UTC and
        # the local hour is the whole point: read `hour` as UTC instead of
        # Europe/Copenhagen and the summer peak (UTC+2) moves to 10:00, winter
        # (UTC+1) to 11:00. A floor of 10 would ADMIT the summer slip it claims
        # to catch; a `>= 6` floor would pass every version of the mistake.
        assert 11 <= peak <= 14, f"{year}: summer leisure peak at {peak}:00"
        # A flat day is 4.167 %. 8 % is nearly double it and still far below
        # the 11.5 % measured: it says "this fleet has a midday spike" without
        # asserting the spike's size. A `> 0.05` bound is satisfied by noise.
        assert prof[peak] > 0.08, f"{year}: summer leisure peak {prof[peak]}"

        # S6 finding 10, measured on sql/24: summer leisure night share
        # 4.27-4.79 %, ferries 17.72-23.22 %. The two windows do not touch, so
        # swapping the two fleet labels — the one mistake that would leave both
        # curves looking plausible — fails both asserts at once. Winter leisure
        # runs to 8.15 % and is deliberately out of scope here.
        lei = night_share(pooled_day(share, msgs, "May-Sep", "leisure", "Class B",
                                     years=[year]))
        fer = night_share(pooled_day(share, msgs, "May-Sep", "passenger", "Class A",
                                     years=[year]))
        assert 0.02 < lei < 0.08, f"{year}: summer leisure night share {lei}"
        assert 0.15 < fer < 0.30, f"{year}: summer ferry night share {fer}"


# ---------------------------------------------------------------- sql/32 ----
def week_shape():
    """sql/32 -> {(year, season, group, mobile): {slot: (mean, share, slot_days)}}.

    Returns the per-occurrence means as well as the shares: the Saturday /
    Sunday question in § 4 is about where a difference sits, and a difference
    of shares inside two different weeks is not a difference of anything.
    """
    week = collections.defaultdict(dict)
    mismatch = []
    covered = collections.Counter()
    for year, season, group, mobile, slot, slot_days, seen, mean, sh in \
            rows("32_week_shape.sql"):
        key = (int(year), season, group, mobile)
        week[key][int(slot)] = (float(mean), float(sh), int(slot_days))
        # slot_days is a property of the CALENDAR, the same for all 24 hours
        # of a weekday, so the 168 slots of one (year, season, fleet) sum to
        # 24 x that season's covered local days, and the years sum to the
        # archive's own constant.
        covered[(season, group, mobile)] += int(slot_days)
        if int(slot_days) != int(seen):
            mismatch.append((key, int(slot), int(slot_days) - int(seen)))

    for key, prof in week.items():
        # 168 slots and a distribution, for the same reason as sql/30 above.
        assert len(prof) == 168, f"{key}: {len(prof)} slots, not 168"
        total = sum(v[1] for v in prof.values())
        assert abs(total - 1.0) < 1e-3, f"{key}: shares sum to {total}, not 1"
    # THIS is the check that bites if slot_days regressed to occupancy — the
    # denominator bug this session already produced once, in sql/31. A reviewer
    # built that regression here and BOTH asserts below passed vacuously:
    # slot_days = days_seen makes `mismatch` EMPTY, and an empty list satisfies
    # `all(...)` and `len(...) < 100`. What the regression cannot fake is the
    # calendar: sum the slot_days of one slot per weekday over all seven
    # weekdays and all years and you have the number of covered local days,
    # which is a constant of the archive. Summing ALL 168 slots and not one
    # per weekday is deliberate: the occupancy regression differs from the
    # calendar only on the 61 slots of § "the calendar shortfall" below, none
    # of which is an hour-00 slot, so a one-slot-per-weekday sum would come
    # back 846/1 232 under the regression too (checked, it does).
    # 846 May-Sep is the same literal
    # sql/31 is pinned to; Oct-Apr is 1 232 and NOT sql/31's 1 116, because
    # sql/32 emits `year` and keeps the 116 storm-window days of 2022 and 2023
    # in its output for the caller to drop (YEARS above), while sql/31 pools
    # years and drops them in SQL.
    for key, total in covered.items():
        expect = 24 * (846 if key[0] == "May-Sep" else 1232)
        assert total == expect, \
            (f"{key}: slot_days sums to {total} over the 168 slots, not "
             f"{expect} = 24 x {expect // 24} covered local days")
    assert len(covered) == 20, f"{len(covered)} fleet pairs, not 20"
    # days_seen < slot_days is the CALENDAR (slot 146, Sunday 02:00, which the
    # spring-forward Sunday does not have) except where a thin fleet genuinely
    # missed a slot. These two do NOT guard the denominator — they bound the
    # shortfall between the calendar and the occupancy, so they catch a fleet
    # that vanished from the file, not a denominator that became the occupancy.
    # Observed: 61 rows of 23 520, always short by exactly 1; 60 of them at
    # slot 146, and one at slot 38 (2024 Oct-Apr, Class A leisure).
    assert all(gap == 1 for _, _, gap in mismatch), \
        f"days_seen short by more than 1: {[m for m in mismatch if m[2] != 1]}"
    assert len(mismatch) < 100, f"{len(mismatch)} slots with days_seen < slot_days"
    return week, mismatch


def pooled_week(week, season, group, mobile, years=YEARS):
    """The 168-hour week for one fleet, pooled over years.

    mean_moving is already a per-occurrence mean, so pooling means re-doing the
    division over the pooled occurrences: Σ(mean × slot_days) / Σslot_days.
    Summing the means instead would give a 118-day season the same weight as a
    153-day one.
    """
    tot, den = collections.Counter(), collections.Counter()
    for year in years:
        key = (year, season, group, mobile)
        if key not in week:
            continue
        for slot, (mean, _, slot_days) in week[key].items():
            tot[slot] += mean * slot_days
            den[slot] += slot_days
    tot = {slot: value / den[slot] for slot, value in tot.items()}
    total = sum(tot.values())
    assert total, f"{season} {group} {mobile}: no rows to pool"
    return {slot: tot[slot] / total for slot in range(168)}, tot


# ---------------------------------------------------------------- sql/31 ----
def ports():
    """sql/31 -> {(h3, fleet, season): {hour: row}}, with the port asserts.

    Keyed on h3 because `place` is a reusable literal — see PORTS above. `meta`
    carries the label, the marina count and the cell centre, one entry per h3.
    """
    out = collections.defaultdict(dict)
    meta = {}
    for (h3, place, n_marinas, lat, lon, fleet, season, lhour, season_days,
         days_seen, vessels_seen, present, appeared, from_ring, vanished,
         to_ring) in rows("31_port_breathing.sql"):
        row = dict(season_days=int(season_days), days_seen=int(days_seen),
                   vessels_seen=int(vessels_seen), present=float(present),
                   appeared=float(appeared), from_ring=float(from_ring),
                   vanished=float(vanished), to_ring=float(to_ring))
        out[(h3, fleet, season)][int(lhour)] = row
        meta[h3] = dict(place=place, n_marinas=int(n_marinas), lat=lat, lon=lon)

        # lat/lon are the CELL CENTRE and this file only ever prints them, so
        # h3ToGeo(h3).1 and .2 swapped would move every harbour into the Somali
        # basin and leave every other number in this run green. The bbox is
        # Denmark's; the pin is the one cell centre sql/33_port_oracle.sql's
        # header states independently, so a swap fails on both.
        assert BBOX[0] <= float(lat) <= BBOX[1] and BBOX[2] <= float(lon) <= BBOX[3], \
            f"{h3} {place}: cell centre {lat} N {lon} E is outside Denmark"
        if h3 == PIN[0]:
            assert (float(lat), float(lon)) == PIN[1:], \
                f"{h3}: cell centre {lat} / {lon}, not {PIN[1]} / {PIN[2]}"

        # Ring 1 is h3kRing(cell, 1), the SEVEN cells including the centre, so
        # A is a subset of Ring and the split of an appearance into "sailed in
        # from next door" and "switched on" cannot exceed the appearance. True
        # by construction — which is exactly why it is worth asserting: the way
        # to break it is to cross the two state sets (u2 with u3, own_st with
        # ring_st), and a crossed pair still returns plausible-looking numbers.
        # Observed: from_ring/appeared 0.00-0.64, to_ring/vanished 0.00-0.80.
        assert row["from_ring"] <= row["appeared"], \
            f"{place} {fleet} {season} {lhour}: arrived_from_ring > appeared"
        assert row["to_ring"] <= row["vanished"], \
            f"{place} {fleet} {season} {lhour}: left_to_ring > vanished"
        # season_days is every covered local day of that season, all years
        # pooled, and it is the divisor of every mean_* above. It is a property
        # of the CALENDAR, so it is the same number in all 480 rows of a
        # season. If it ever varies by cell, fleet or hour the denominator has
        # regressed to the occupancy-dependent one that was caught and fixed
        # once already in this session — which does not change a curve's level
        # uniformly, it destroys its shape (days_seen runs 7 to 846 inside one
        # curve). A range check would pass the regression; the exact literals
        # do not.
        # 1 116, not sql/32's 1 232: sql/31 pools the years and emits no
        # `year`, so it drops the 116 storm-window days of 2022 and 2023 in
        # SQL. See sql/31's header and week_shape() above.
        expect = 846 if season == "May-Sep" else 1116
        assert row["season_days"] == expect, \
            f"{place} {fleet} {season} {lhour}: season_days {season_days}"
        assert row["days_seen"] <= row["season_days"], \
            f"{place} {fleet} {season} {lhour}: days_seen > season_days"
        # CLAUDE.md's export rule, checked on every Class B row rather than on
        # the ones this note happens to quote: k >= 5 distinct vessels behind a
        # published cell. Observed minimum 12 (Vindeby Havn, Oct-Apr, 03:00);
        # the ferry rows go down to 0 and are public, which is why the rule is
        # applied by fleet and not to the file as a whole.
        assert fleet != LEISURE or row["vessels_seen"] >= 5, \
            f"{place} {season} {lhour}: k = {vessels_seen} < 5"

    assert len(meta) == 10, f"sql/31 returned {len(meta)} cells, not 10"
    for (h3, fleet, season), prof in out.items():
        place = meta[h3]["place"]
        assert len(prof) == 24, f"{place} {fleet} {season}: {len(prof)} hours"
        appeared = sum(r["appeared"] for r in prof.values())
        vanished = sum(r["vanished"] for r in prof.values())
        # Every boat that appears in a cell leaves it again, so the two sums
        # agree per (cell, fleet) up to the archive's own edges: sql/31's slot
        # domain contains the hour AFTER every occupied hour precisely so an
        # emptying harbour can record its departures. WHAT THIS BOUNDS IS THAT
        # EDGE RESIDUAL, and nothing more. It does NOT catch the LEFT -> INNER
        # JOIN swap that sql/31's header warns about: a reviewer made that swap
        # and all 40 curves still passed here — only `len(prof) == 24` fired,
        # and only because one thin ferry curve happened to lose an hour
        # entirely. The join contract is guarded where it lives, by sql/31's
        # own `SETTINGS join_use_nulls = 0` and by the oracle in numbers().
        # THE ADDITIVE TERM IS NOT SLACK: mean_appeared is rounded to 2 dp, so
        # 24 hours carry up to 0.12/day of rounding in each column and 0.24 in
        # the difference. Without it the near-empty ferry buckets — Lystbådehavn
        # Troense at 0.06 appearances a day, i.e. ~50 ferry-hours in 846 days —
        # fail on rounding alone. The 5 % term is what bites on every bucket
        # that carries a real number; observed 0.0000-0.0132 there.
        assert abs(appeared - vanished) < 0.05 * appeared + 0.24, \
            (f"{place} {fleet} {season}: appeared {appeared:.2f} vs vanished "
             f"{vanished:.2f}")
    return out, meta


def check_k(ports_data, h3, season, hours=range(24)):
    """k >= 5 on every Class B bucket this note quotes, checked not trusted.

    CLAUDE.md's export rule is k >= 5 distinct vessels per published cell.
    sql/31 emits vessels_seen so the rule is checkable downstream; nothing here
    may quote a leisure bucket without checking it, and the ferry buckets — some
    of which are one vessel — are public and quoted only where they are not.
    """
    prof = ports_data[(h3, LEISURE, season)]
    low = [(h, prof[h]["vessels_seen"]) for h in hours if prof[h]["vessels_seen"] < 5]
    assert not low, f"{h3} {season}: Class B buckets under k=5: {low}"
    return min(prof[h]["vessels_seen"] for h in hours)


# ------------------------------------------------------- the cross-check ----
def night_crosscheck(share, msgs):
    """sql/30's night share against sql/24's own, per year and season.

    Two independently written queries over one store, deliberately differing in
    one respect: sql/30 repairs the coverage rule for daylight saving and
    sql/24 does not, so sql/30 sees six spring-forward Sundays that sql/24
    drops. Anything bigger than that difference is a bug in one of them.
    """
    out = []
    for year, season, fleet, local_days, mm, nm, sh in rows("24_night.sql"):
        group, mobile = ("leisure", "Class B") if fleet == LEISURE else \
                        ("passenger", "Class A")
        mine = night_share(pooled_day(share, msgs, season, group, mobile,
                                      years=[int(year)]))
        out.append((int(year), season, fleet, mine, float(sh), int(local_days)))
    return sorted(out)


def weekday_vessels():
    """sql/10 -> mean distinct leisure vessels that MOVED, by weekday.

    The § 4 question is S3's, and S3 asked it in distinct vessels. sql/32
    answers it in moving messages; this reads the other metric from the query
    S3 itself used, so the two can be put side by side. Returns
    {(year, month or None, weekday): mean}. UTC days, no coverage filter —
    sql/10's own convention, stated in the note.
    """
    import datetime
    buckets = collections.defaultdict(list)
    for day, mobile, present, active, _ in rows("10_season_daily.sql"):
        if mobile != "Class B":
            continue
        assert int(active) <= int(present), f"{day}: active > present"
        date = datetime.date.fromisoformat(day)
        buckets[(date.year, date.month, date.weekday())].append(int(active))
    return buckets


def weekday_mean(buckets, year, weekday, months):
    vals = [v for month in months for v in buckets.get((year, month, weekday), [])]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------- charts ----
# site/day-clocks.html: R_IN 20, R_MAX 92 in a 240 box, PEAK 13 % at the rim.
# A polar axis with rorigin = -PEAK * R_IN / (R_MAX - R_IN) has the same hole.
PEAK_PCT = 13.0
R_ORIGIN = -PEAK_PCT * 20 / (92 - 20)


def chart_fingerprint(share, msgs):
    """Chart 1 -- the 24-hour dial per fleet, summer against winter."""
    fig, axes = plt.subplots(1, len(GROUPS), figsize=(11, 3.6),
                             subplot_kw=dict(projection="polar"))
    width = math.radians(15 - 1.8)          # the site's 15 deg wedge, gapped
    ring = [math.radians(a) for a in range(0, 361, 3)]
    for ax, (group, mobile, label, colour) in zip(axes, GROUPS):
        summer = pooled_day(share, msgs, "May-Sep", group, mobile)
        winter = pooled_day(share, msgs, "Oct-Apr", group, mobile)
        theta = [math.radians(15 * h) for h in range(24)]
        ax.bar(theta, [min(100 * summer[h], PEAK_PCT) for h in range(24)],
               width=width, color=colour, linewidth=0, zorder=2)
        closed = theta + [theta[0]]
        ax.plot(closed, [min(100 * winter[h % 24], PEAK_PCT) for h in range(25)],
                color=INK, linewidth=1.0, linestyle=(0, (3, 2)), zorder=3)
        ax.plot(ring, [100 * FLAT_DAY] * len(ring), color="#a8b8bc",
                linewidth=0.9, linestyle=(0, (2, 3)), zorder=1)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rorigin(R_ORIGIN)
        ax.set_ylim(0, PEAK_PCT)
        ax.set_xticks([math.radians(15 * h) for h in (0, 6, 12, 18)])
        ax.set_xticklabels(["00", "06", "12", "18"], color=MUTED, fontsize=8)
        ax.set_yticks([])
        ax.grid(False)
        ax.spines["polar"].set_visible(False)
        ax.tick_params(pad=-3)
        peak = max(summer, key=summer.get)
        ax.set_title(f"{label}\n{peak:02d}:00 · {100*summer[peak]:.1f} % · "
                     f"night {100*night_share(summer):.0f} %",
                     color=INK, fontsize=9.5, pad=12)
    fig.suptitle("The shape of a day, six summers — bars = May–Sep, "
                 "dashed = Oct–Apr, thin circle = a flat day (4.17 %)",
                 color=INK, fontsize=11, x=0.008, ha="left")
    fig.tight_layout(rect=(0, -0.02, 1, 0.92))
    fig.savefig(IMG / "ch02-fingerprint.png", dpi=160, facecolor="white")


def chart_week(week):
    """Chart 2 -- the 168-hour week per fleet, summer against winter."""
    fig, axes = plt.subplots(len(GROUPS), 1, figsize=(11, 7.6), sharex=True)
    for ax, (group, mobile, label, colour) in zip(axes, GROUPS):
        ends = []
        for season, style, alpha in (("May-Sep", "solid", 1.0),
                                     ("Oct-Apr", (0, (3, 2)), 0.55)):
            prof, _ = pooled_week(week, season, group, mobile)
            ys = [100 * prof[s] for s in range(168)]
            ax.plot(range(168), ys, color=colour, linewidth=1.6,
                    linestyle=style, alpha=alpha)
            ends.append((ys[-1], season, colour))
        ax.axhline(100 * FLAT_WEEK, color=MUTED, linewidth=0.9,
                   linestyle=(0, (4, 3)))
        for boundary in range(24, 168, 24):
            ax.axvline(boundary, color="#d8d7d2", linewidth=0.8)
        ax.set_xlim(0, 167)
        ax.set_ylim(0, None)
        # after set_ylim, never before: label_ends reads the finished y-axis to
        # decide how far apart two labels have to be.
        label_ends(ax, 167, ends, gap_frac=0.10)
        ax.set_title(label, color=INK, fontsize=10, loc="left")
        tidy(ax)
        ax.grid(axis="y", linewidth=0)
    axes[-1].set_xticks([24 * d + 12 for d in range(7)])
    axes[-1].set_xticklabels(DOW)
    axes[-1].set_xlabel("hour of the week, Europe/Copenhagen "
                        "(dashed rule = a flat week, 0.60 %)",
                        color=MUTED, fontsize=8)
    axes[len(GROUPS) // 2].set_ylabel("% of the week's movement",
                                      color=MUTED, fontsize=9)
    fig.suptitle("Where in the week does each fleet move? "
                 "Six years pooled, per-occurrence means",
                 color=INK, fontsize=12, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 0.94, 0.96))
    fig.savefig(IMG / "ch02-week.png", dpi=160, facecolor="white")


def chart_port(ports_data, meta):
    """Chart 3 -- a harbour breathing: appearances up, departures down."""
    blue = GROUPS[0][3]
    orange = GROUPS[1][3]
    fig, axes = plt.subplots(2, len(PORTS), figsize=(11, 5.2), sharex=True)
    for col, (h3, place) in enumerate(PORTS):
        for row, (fleet, colour) in enumerate(((LEISURE, blue), (FERRY, orange))):
            ax = axes[row][col]
            prof = ports_data[(h3, fleet, "May-Sep")]
            up = [prof[h]["appeared"] for h in range(24)]
            down = [-prof[h]["vanished"] for h in range(24)]
            ax.bar(range(24), up, width=0.82, color=colour, alpha=0.35, linewidth=0)
            ax.bar(range(24), down, width=0.82, color=colour, alpha=0.35, linewidth=0)
            # the darker core is the half that was next door an hour earlier;
            # the pale remainder switched on, or came from beyond one ring.
            ax.bar(range(24), [prof[h]["from_ring"] for h in range(24)],
                   width=0.82, color=colour, linewidth=0)
            ax.bar(range(24), [-prof[h]["to_ring"] for h in range(24)],
                   width=0.82, color=colour, linewidth=0)
            ax.axhline(0, color=MUTED, linewidth=0.8)
            ax.set_xticks(range(0, 24, 6))
            ax.set_xlim(-0.6, 23.6)
            # A symmetric y-axis, and the daily total spelled out: without it a
            # panel holding 0.7 ferry arrivals a day is autoscaled into looking
            # exactly like one holding 15, which is the ferry control's whole
            # point (three of these ten cells have no ferry line at all).
            span = 1.12 * max(max(up), -min(down))
            ax.set_ylim(-span, span)
            ax.annotate(f"{sum(up):.1f} in / {-sum(down):.1f} out per day",
                        (0.03, 0.96), xycoords="axes fraction", color=MUTED,
                        fontsize=7.5, va="top")
            tidy(ax)
            ax.grid(axis="y", linewidth=0)
            if row == 0:
                title = place + (" · Svendborg Sund" if h3 in SVENDBORG_H3 else "")
                ax.set_title(title, color=INK, fontsize=9.5, loc="left")
            if col == 0:
                ax.set_ylabel(("leisure Class B" if row == 0 else "ferry Class A")
                              + "\nvessels per day", color=MUTED, fontsize=8.5)
        axes[1][col].set_xlabel("hour, Europe/Copenhagen", color=MUTED, fontsize=8)
    fig.suptitle("A harbour breathing, May–Sep: arrivals up, departures down · "
                 "solid = came from (left to) the next cell, pale = appeared "
                 "(vanished) out of nowhere",
                 color=INK, fontsize=10.5, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(IMG / "ch02-port.png", dpi=160, facecolor="white")


# --------------------------------------------------------------- numbers ----
def numbers(share, msgs, week, mismatch, ports_data, meta, cross, buckets):
    """Every figure notes/ch02-findings.md quotes. Printed, never hand-typed."""
    print("\n== the four fingerprints, six years pooled (sql/30) ==")
    print("fleet          season   peak  that hour   night 22-05   "
          "flat day = 4.17 %/h, 29.17 %/night")
    for group, mobile, label, _ in GROUPS:
        for season in SEASONS:
            prof = pooled_day(share, msgs, season, group, mobile)
            peak = max(prof, key=prof.get)
            trough = min(prof, key=prof.get)
            print(f"{label:9s} {mobile}  {season:8s} {peak:02d}:00 "
                  f"{100*prof[peak]:6.2f} %   {100*night_share(prof):6.2f} %   "
                  f"trough {trough:02d}:00 {100*prof[trough]:5.2f} %   "
                  f"peak/flat {prof[peak]/FLAT_DAY:4.2f}x  "
                  f"night/flat {night_share(prof)/(7/24):4.2f}x")

    print("\n== the same, year by year (sql/30) ==")
    for group, mobile, label, _ in GROUPS:
        for season in SEASONS:
            cells = []
            for year in YEARS:
                prof = pooled_day(share, msgs, season, group, mobile, years=[year])
                peak = max(prof, key=prof.get)
                cells.append(f"{year} {peak:02d}:00/{100*prof[peak]:4.1f}/"
                             f"{100*night_share(prof):4.1f}")
            print(f"{label:9s} {season:8s} " + "  ".join(cells))
    print("(year peak:hour / peak share % / night share %)")

    print("\n== the leisure peak hour, by year, season and daytype (sql/30) ==")
    for season in SEASONS:
        for year in YEARS:
            cells = []
            for daytype in DAYTYPES:
                prof = pooled_day(share, msgs, season, "leisure", "Class B",
                                  daytypes=[daytype], years=[year])
                peak = max(prof, key=prof.get)
                cells.append(f"{daytype:7s} {peak:02d}:00 {100*prof[peak]:5.2f} %")
            print(f"{season:8s} {year}  " + "   ".join(cells))

    print("\n== weekday / Saturday / Sunday, May-Sep, six years (sql/30) ==")
    for group, mobile, label, _ in GROUPS:
        for daytype in DAYTYPES:
            prof = pooled_day(share, msgs, "May-Sep", group, mobile,
                              daytypes=[daytype])
            peak = max(prof, key=prof.get)
            morning = sum(prof[h] for h in range(6, 12))
            afternoon = sum(prof[h] for h in range(12, 18))
            evening = sum(prof[h] for h in range(18, 22))
            print(f"{label:9s} {daytype:7s} peak {peak:02d}:00 "
                  f"{100*prof[peak]:5.2f} %  night {100*night_share(prof):5.2f} %  "
                  f"06-11 {100*morning:5.2f} %  12-17 {100*afternoon:5.2f} %  "
                  f"18-21 {100*evening:5.2f} %")

    print("\n== summer against winter: how much the shape moves (sql/30) ==")
    for group, mobile, label, _ in GROUPS:
        summer = pooled_day(share, msgs, "May-Sep", group, mobile)
        winter = pooled_day(share, msgs, "Oct-Apr", group, mobile)
        tv = 0.5 * sum(abs(summer[h] - winter[h]) for h in range(24))
        print(f"{label:9s} total variation summer vs winter {100*tv:5.2f} pp   "
              f"peak {max(summer, key=summer.get):02d}:00 -> "
              f"{max(winter, key=winter.get):02d}:00   "
              f"night {100*night_share(summer):5.2f} % -> "
              f"{100*night_share(winter):5.2f} %")

    print("\n== the 168-hour week: where the maximum sits (sql/32) ==")
    for group, mobile, label, _ in GROUPS:
        for season in SEASONS:
            prof, _ = pooled_week(week, season, group, mobile)
            top = max(prof, key=prof.get)
            days = [sum(prof[24 * d + h] for h in range(24)) for d in range(7)]
            print(f"{label:9s} {season:8s} max slot {top:3d} = {DOW[top//24]} "
                  f"{top%24:02d}:00 ({100*prof[top]:4.2f} % of the week, "
                  f"flat = 0.60 %)   day shares " +
                  " ".join(f"{DOW[d]} {100*days[d]:4.1f}" for d in range(7)))

    print("\n== Saturday against Sunday, leisure, May-Sep (sql/32) ==")
    for year in YEARS:
        prof, _ = pooled_week(week, "May-Sep", "leisure", "Class B", years=[year])
        sat = sum(prof[120 + h] for h in range(24))
        sun = sum(prof[144 + h] for h in range(24))
        print(f"{year}  sat {100*sat:5.2f} %  sun {100*sun:5.2f} %  "
              f"sun - sat {100*(sun-sat):+5.2f} pp")
    prof, means = pooled_week(week, "May-Sep", "leisure", "Class B")
    sat = [means[120 + h] for h in range(24)]
    sun = [means[144 + h] for h in range(24)]
    print("hour   Saturday   Sunday    Sunday - Saturday "
          "(mean moving messages per occurrence, six years)")
    for h in range(24):
        print(f" {h:02d}  {sat[h]:9.0f} {sun[h]:9.0f}  {sun[h]-sat[h]:+10.0f}")
    early = sum(sun[h] - sat[h] for h in range(0, 14))
    late = sum(sun[h] - sat[h] for h in range(14, 24))
    print(f"tot  {sum(sat):9.0f} {sum(sun):9.0f}  {sum(sun)-sum(sat):+10.0f}"
          f"   ({100*(sum(sun)/sum(sat)-1):+.1f} %)")
    print(f"  00-13 {early:+.0f}   14-23 {late:+.0f}   "
          f"10-13 {sum(sun[h]-sat[h] for h in range(10,14)):+.0f}   "
          f"18-23 {sum(sun[h]-sat[h] for h in range(18,24)):+.0f}")

    print("\n== Saturday against Sunday, the other metric: distinct leisure "
          "vessels that moved (sql/10) ==")
    for year in YEARS:
        may_sep = [weekday_mean(buckets, year, d, range(5, 10)) for d in range(7)]
        jul = [weekday_mean(buckets, year, d, [7]) for d in range(7)]
        print(f"{year}  May-Sep " +
              " ".join(f"{DOW[d]} {may_sep[d]:6.0f}" for d in range(7)) +
              f"  sun/sat {may_sep[6]/may_sep[5]:5.3f}")
        print(f"      July    " +
              " ".join(f"{DOW[d]} {jul[d]:6.0f}" for d in range(7)) +
              f"  sun/sat {jul[6]/jul[5]:5.3f}")

    print("\n== port breathing, May-Sep, ten cells (sql/31) ==")
    days = {season: next(iter(prof.values()))["season_days"]
            for (h3, fleet, season), prof in ports_data.items()}
    print("denominator: " + ", ".join(f"{season} {n} covered local days"
                                      for season, n in sorted(days.items()))
          + " (all years pooled)")
    print("place                       fleet             app/day  van/day  "
          "peak_app peak_van  from_ring  present max / min      k")
    for (h3, fleet, season), prof in sorted(
            ports_data.items(), key=lambda kv: (meta[kv[0][0]]["place"], kv[0][1])):
        if season != "May-Sep":
            continue
        place = meta[h3]["place"]
        appeared = sum(prof[h]["appeared"] for h in range(24))
        vanished = sum(prof[h]["vanished"] for h in range(24))
        from_ring = sum(prof[h]["from_ring"] for h in range(24))
        peak_app = max(range(24), key=lambda h: prof[h]["appeared"])
        peak_van = max(range(24), key=lambda h: prof[h]["vanished"])
        hi = max(range(24), key=lambda h: prof[h]["present"])
        lo = min(range(24), key=lambda h: prof[h]["present"])
        k = min(prof[h]["vessels_seen"] for h in range(24))
        print(f"{place:27s} {fleet:16s} {appeared:7.2f} {vanished:8.2f}  "
              f"  {peak_app:02d}:00    {peak_van:02d}:00   "
              f"{100*from_ring/appeared if appeared else 0:5.1f} %  "
              f"{prof[hi]['present']:5.1f} at {hi:02d} / {prof[lo]['present']:4.1f} "
              f"at {lo:02d} = {100*prof[lo]['present']/prof[hi]['present']:4.0f} % "
              f"of the peak  {k:6d}")

    print("\n== the four Svendborg Sund cells are ONE harbour — never added "
          "together (sql/31) ==")
    for h3, place in SVENDBORG:
        m = meta[h3]
        assert m["place"] == place, f"{h3}: sql/31 calls it {m['place']}, not {place}"
        prof = ports_data[(h3, LEISURE, "May-Sep")]
        print(f"{place:27s} h3 {h3}  {m['n_marinas']} marina(s)  "
              f"{m['lat']} N {m['lon']} E  "
              f"{sum(prof[h]['appeared'] for h in range(24)):6.2f} leisure "
              f"appearances/day")

    print("\n== the morning appearance: switched on, or sailed in? "
          "(sql/31, May-Sep) ==")
    for h3, place in PORTS:
        assert meta[h3]["place"] == place, \
            f"{h3}: sql/31 calls it {meta[h3]['place']}, not {place}"
        for fleet in (LEISURE, FERRY):
            prof = ports_data[(h3, fleet, "May-Sep")]
            morning = range(8, 13)
            app = sum(prof[h]["appeared"] for h in morning)
            ring = sum(prof[h]["from_ring"] for h in morning)
            print(f"{place:27s} {fleet:16s} 08-12: {app:6.2f} appearances/day, "
                  f"{ring:5.2f} from the ring = {100*ring/app if app else 0:4.1f} %, "
                  f"{100*(1-ring/app) if app else 0:4.1f} % out of nowhere")

    print("\n== winter against summer in the harbours (sql/31) ==")
    for h3, place in PORTS:
        summer = ports_data[(h3, LEISURE, "May-Sep")]
        winter = ports_data[(h3, LEISURE, "Oct-Apr")]
        s = sum(summer[h]["appeared"] for h in range(24))
        w = sum(winter[h]["appeared"] for h in range(24))
        print(f"{place:27s} leisure appearances/day  May-Sep {s:6.2f}  "
              f"Oct-Apr {w:5.2f}  = {s/w:5.1f}x   k(summer) "
              f"{check_k(ports_data, h3, 'May-Sep')}  k(winter) "
              f"{check_k(ports_data, h3, 'Oct-Apr')}")

    print("\n== cross-source: sql/30's night share against sql/24's own ==")
    print("(independent queries; sql/30 repairs the DST coverage rule, sql/24 "
          "does not)")
    worst = max(cross, key=lambda r: abs(r[3] - r[4]))
    for year, season, fleet, mine, theirs, days in cross:
        flag = "  <- worst" if (year, season, fleet) == worst[:3] else ""
        print(f"{year} {season:8s} {fleet:16s} sql/30 {100*mine:6.3f} %   "
              f"sql/24 {100*theirs:6.3f} %   diff {100*(mine-theirs):+6.3f} pp"
              f"   ({days} local days){flag}")
    print(f"worst disagreement {abs(worst[3]-worst[4]):.4f} on {worst[0]} "
          f"{worst[1]} {worst[2]}; May-Sep rows agree to "
          f"{max(abs(r[3]-r[4]) for r in cross if r[1] == 'May-Sep'):.4f}")

    print("\n== the calendar shortfall in sql/32 (days_seen < slot_days) ==")
    by_slot = collections.Counter(slot for _, slot, _ in mismatch)
    print(f"{len(mismatch)} rows of 23 520, every one short by exactly 1: " +
          ", ".join(f"slot {slot} ({DOW[slot//24]} {slot%24:02d}:00) x{n}"
                    for slot, n in by_slot.most_common()))
    for key, slot, gap in mismatch:
        if slot != 146:
            print(f"  not slot 146: {key} slot {slot} "
                  f"({DOW[slot//24]} {slot%24:02d}:00), short by {gap}")

    print("\n== the oracle (sql/33): one cell, 2025-07, Class A passenger ==")
    oracle = [[int(v) for v in r[1:]] for r in rows("33_port_oracle.sql")]
    days = oracle[0][1]
    assert all(r[1] == days == 31 for r in oracle), "sql/33: window_days moved"
    assert len(oracle) == 24, f"sql/33: {len(oracle)} local hours, not 24"
    # sql/33 emits the two answers side by side, both as RAW MONTH SUMS: five
    # columns computed from raw MMSI sets in `public_track` and five computed
    # with sql/31's inclusion–exclusion over aggregate states. Comparing them
    # is the whole point of the file, and until this assert existed nothing
    # compared them — the totals were printed next to a hand-typed string.
    #
    # WHAT THE BOUND IS FOR. 5 is headroom for the vessel-hours the 1-minute
    # sample misses (measured gaps today: 2, 1, 1, 0, 0 on a present total of
    # 1 646) and it sits two orders of magnitude below what a broken union
    # produces: cross the u1 offset-1 row from the own-cell state to the ring
    # state — one token in sql/31 — and its leisure appearances/day go up to
    # 15.9x wrong (Vindeby Havn 29.43 -> 467.14) while sql/31's OWN balance
    # assert stays green on all 20 pairs, because it telescopes i_own away and
    # cannot see it. Measured with the same break applied to the state side of
    # sql/33: appeared 502 -> 509, vanished 501 -> 508, left_to_ring 8 -> 15
    # against an unmoved oracle. This cell is a ferry cell whose ring is barely
    # wider than itself, so the break shows here as 6-8, not as the hundreds it
    # shows in a leisure harbour — 5 is chosen to sit under that, not under the
    # leisure blow-up.
    names = ["present", "appeared", "arrived_from_ring", "vanished",
             "left_to_ring"]
    print("month totals, raw sums over the 744-hour window:")
    print(f"{'':22s} {'oracle (raw MMSI sets)':>22s} "
          f"{'sql/31 algebra (states)':>24s}   gap")
    for i, name in enumerate(names):
        raw = sum(r[4 + i] for r in oracle)
        state = sum(r[9 + i] for r in oracle)
        print(f"  {name:20s} {raw:22d} {state:24d}   {raw - state:+d}")
        assert abs(raw - state) <= 5, \
            (f"sql/33: {name} {raw} from raw positions against {state} from "
             f"sql/31's algebra — the two sources are {abs(raw - state)} apart, "
             f"which is more than a 1-minute sampling gap can explain")
    hours_agreeing = sum(all(r[4 + i] == r[9 + i] for i in range(5))
                         for r in oracle)
    print(f"  {hours_agreeing} of the 24 local hours agree exactly on all five")


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    share, msgs = hour_profiles()
    check_fingerprints(share, msgs)
    week, mismatch = week_shape()
    ports_data, meta = ports()
    for h3, _ in PORTS:
        for season in SEASONS:
            check_k(ports_data, h3, season)
    cross = night_crosscheck(share, msgs)
    # The one number this file may not compute for itself: the two queries are
    # independent, and the DST repair is the only difference they are allowed
    # to have. Task A measured the cost at 0.0010, all of it in Oct-Apr.
    assert max(abs(mine - theirs) for _, _, _, mine, theirs, _ in cross) < 0.002, \
        "sql/30 and sql/24 disagree by more than the DST repair explains"
    buckets = weekday_vessels()
    chart_fingerprint(share, msgs)
    chart_week(week)
    chart_port(ports_data, meta)
    numbers(share, msgs, week, mismatch, ports_data, meta, cross, buckets)
    print(f"\nwrote {IMG}/ch02-fingerprint.png, ch02-week.png, ch02-port.png",
          file=sys.stderr)
