"""site/pulse.html — the sea by the hour. Three charts, one dict.

    chart  what it says                            where the numbers come from
    P1     four fleets, four clocks                sql/30_hour_profiles.sql
    P2     the sailing week against the cargo week sql/32_week_shape.sql
    P3     one marina, hour by hour                sql/31_port_breathing.sql
    prose  Sunday is the sharpest sailing day      sql/30
    prose  each fleet's biggest hour of the week   sql/32
    prose  fishing changes its clock, cargo does not  sql/30
    prose  most arrivals never sailed in           sql/31

Every curve is pooled over the six years the store holds whole or nearly so and
over May-Sep, the months a leisure fleet exists in. 2022 and 2023 are 59 winter
days each and are dropped: sql/30 and sql/32 emit a `year` to drop them by,
sql/31 pools the years and drops them in SQL itself.

ONLY SHAPES, NEVER HEIGHTS. A small boat's radio speaks a fraction as often as
a big ship's, so a sailing curve and a cargo curve cannot share an axis as
levels. Every curve here is a share of its own fleet's own day or week —
sql/30's `share_of_day` and sql/32's `share_of_week`, which are normalised
inside the fleet's own partition — and the page says so in plain words.

PRIVACY. The private fleet appears at two grains and no others: a share of its
own day or week, pooled over the whole country (P1, P2), and one marina cell's
hourly arrivals and departures (P3). P3 is the one that needs the k >= 5 rule
and it is checked here rather than assumed: sql/31 emits `vessels_seen` for
exactly this, every drawn hour is asserted against it below, and the lowest of
the twenty-four reaches the page as `small_boats_min` so the build's own guard
sees it too. No radio ID, name, position or track of a private boat is read or
written here; the cell is named by the public marina sql/31 labels it with and
never any finer.
"""
from collections import Counter, defaultdict

from . import YEARS, private_count, sp

# The four fleets, in the order the dials are drawn: the one with a day first,
# then the three that keep going. `sailing` is the reader's word for the
# private fleet; the schema's own word never reaches the page. That rename is
# exactly why the head counts here go through `private_count` where they are
# read — the driver's guard can only see a key name, and this module's names
# are the reader's.
FLEETS = [("sailing", "leisure", "Class B"), ("ferries", "passenger", "Class A"),
          ("cargo", "cargo", "Class A"), ("fishing", "fishing", "Class A")]
DAYTYPES = ["weekday", "sat", "sun"]
NIGHT = [22, 23, 0, 1, 2, 3, 4]          # sql/24's night, reused verbatim
DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
       "Sunday"]
FLAT_DAY = 100 / 24                      # 4.167 % — a day with no rhythm
FLAT_WEEK = 100 / 168
WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten"]

# The harbour P3 draws: the busiest leisure cell of sql/31's ten, and one that
# stands alone. Four of the ten are four adjacent cells in Svendborg Sund whose
# neighbourhoods overlap, so a boat hopping between two of them is an arrival
# for one and a departure for the other; drawing one of those four would need
# that whole caveat in a caption. This one needs none.
# The name is asserted against the query, not trusted: `place` is the named
# marina nearest the cell centre and a rename upstream would silently move the
# chart to another harbour.
PORT = "Sønderborg Havn"


def clock(hour):
    """13 -> 'one in the afternoon'. The page says hours in words, because a
    figure like 17:00 in a sentence is a number a reader has to decode and
    docs/SITE.md § Voice does not allow one that was not computed."""
    if hour == 0:
        return "midnight"
    if hour == 12:
        return "noon"
    words = ["twelve", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven"]
    part = ("in the morning" if hour < 12 else
            "in the afternoon" if hour < 18 else "in the evening")
    return f"{words[hour % 12]} {part}"


# ------------------------------------------------------------------- P1 ----
def hour_rows(ch):
    """sql/30 -> {(year, season, group, mobile, daytype): {hour: share}}, days.

    `share_of_day` is normalised inside each of those partitions, so pooling
    daytypes or years means WEIGHTING EACH PARTITION, and the weight is the
    number of days it covers — sql/30's `local_days` — not the messages in it.

    Messages were the weight until this was fixed, and message magnitudes are
    not comparable across the store: the archive keeps some of them twice from
    2023 on and again in 2015-09 (dataset card § Known biases 1 and 2). A
    pooled clock weighted by messages therefore leans towards whichever years
    are inflated. Days are days. sql/32's week has always been pooled this way
    (`slot_days`), and now the two agree.

    `local_days` is emitted per hour of the partition and the ten fleet pairs
    disagree in exactly one bucket out of 1 008 (sql/30's header measures it),
    so the partition's weight is the largest of its twenty-four — one number
    per partition, which is what a weighted average of distributions needs.
    """
    share, days = defaultdict(dict), Counter()
    for (year, season, group, mobile, daytype, lhour, ldays, _mm, sh) in \
            ch("30_hour_profiles.sql"):
        key = (int(year), season, group, mobile, daytype)
        share[key][int(lhour)] = float(sh)
        days[key] = max(days[key], int(ldays))
    return share, days


def day_curve(share, days, season, group, mobile, daytypes=DAYTYPES,
              years=YEARS):
    """One fleet's 24-hour clock, as percentages of its own day."""
    tot, weight = Counter(), 0
    for year in years:
        for daytype in daytypes:
            key = (year, season, group, mobile, daytype)
            if key not in share:
                continue
            weight += days[key]
            for hour, value in share[key].items():
                tot[hour] += value * days[key]
    assert weight, f"{season} {group} {mobile}: no rows to pool"
    curve = [round(100 * tot[hour] / weight, 2) for hour in range(24)]
    # A clock is a distribution over 24 hours. The literals are the calendar,
    # not a measurement: pool two fleets into one partition and this lands near
    # 200, drop a daytype from the partition and it lands near 50.
    assert len(curve) == 24 and abs(sum(curve) - 100) < 0.2, \
        f"{season} {group} {mobile}: the clock sums to {sum(curve)}, not 100"
    return curve


def night(curve):
    return sum(curve[hour] for hour in NIGHT)


def spread(a, b):
    """How much of a fleet's day would have to move to another hour to turn one
    season's clock into the other's. Half the sum of the differences — the
    measure chapter 02 quotes for finding 22."""
    return 0.5 * sum(abs(x - y) for x, y in zip(a, b))


# ------------------------------------------------------------------- P2 ----
def week_curves(ch):
    """sql/32 -> {(year, season, group, mobile): {slot: (mean, slot_days)}}.

    `mean_moving` is already a per-occurrence mean, so pooling the years means
    redoing the division over the pooled occurrences rather than averaging the
    means: a 118-day season would otherwise weigh the same as a 153-day one.
    """
    week = defaultdict(dict)
    for (year, season, group, mobile, slot, slot_days, _seen, mean, _sh) in \
            ch("32_week_shape.sql"):
        week[(int(year), season, group, mobile)][int(slot)] = \
            (float(mean), int(slot_days))
    return week


def week_curve(week, season, group, mobile, years=YEARS):
    """One fleet's 168-hour week, as percentages of its own week."""
    tot, den = Counter(), Counter()
    for year in years:
        key = (year, season, group, mobile)
        for slot, (mean, slot_days) in week.get(key, {}).items():
            tot[slot] += mean * slot_days
            den[slot] += slot_days
    assert len(tot) == 168, f"{season} {group} {mobile}: {len(tot)} slots"
    pooled = [tot[slot] / den[slot] for slot in range(168)]
    total = sum(pooled)
    curve = [round(100 * v / total, 3) for v in pooled]
    assert abs(sum(curve) - 100) < 0.2, \
        f"{season} {group} {mobile}: the week sums to {sum(curve)}, not 100"
    return curve


def day_shares(curve):
    return [sum(curve[24 * d:24 * d + 24]) for d in range(7)]


# ------------------------------------------------------------------- P3 ----
def harbour(ch):
    """sql/31 -> the drawn cell's summer day, and the range over all ten cells.

    Rows are keyed on the cell id inside this function and the id never leaves
    it: the page names the marina and nothing finer.
    """
    cells, places = defaultdict(dict), {}
    for (h3, place, _n_marinas, _lat, _lon, fleet, season, lhour, _season_days,
         _days_seen, vessels_seen, present, appeared, from_ring, vanished,
         to_ring) in ch("31_port_breathing.sql"):
        if fleet != "leisure Class B" or season != "May-Sep":
            continue
        places[h3] = place
        cells[h3][int(lhour)] = {
            "k": int(vessels_seen), "present": float(present),
            "appeared": float(appeared), "from_ring": float(from_ring),
            "vanished": float(vanished), "to_ring": float(to_ring)}

    assert len(cells) == 10, f"sql/31 returned {len(cells)} cells, not 10"
    drawn = [h3 for h3, name in places.items() if name == PORT]
    assert len(drawn) == 1, \
        f"sql/31 no longer labels exactly one cell {PORT!r}: {sorted(places.values())}"
    prof = cells[drawn[0]]

    # CLAUDE.md's export rule, on every hour that reaches the page rather than
    # on the ones the prose happens to quote. sql/31 emits vessels_seen so this
    # is checkable at all; without the check the rule would live in a comment.
    for h in range(24):
        private_count(prof[h]["k"], f"{PORT} at {h:02d}:00 (sql/31 vessels_seen)")

    # how much of an "arrival" was a boat that was already nearby an hour
    # earlier, over the whole day, in each of the ten cells. The rest had no
    # trace within about fifteen kilometres — finding 19.
    nowhere = []
    for h3, cell in cells.items():
        appeared = sum(cell[h]["appeared"] for h in range(24))
        ring = sum(cell[h]["from_ring"] for h in range(24))
        nowhere.append(100 * (1 - ring / appeared))
    floors = [100 * min(cell[h]["present"] for h in range(24))
              / max(cell[h]["present"] for h in range(24))
              for cell in cells.values()]
    return prof, nowhere, floors


# ------------------------------------------------------------------ page ----
def build(ch):
    share, days = hour_rows(ch)
    week = week_curves(ch)
    prof, nowhere, floors = harbour(ch)

    clocks = {name: day_curve(share, days, "May-Sep", group, mobile)
              for name, group, mobile in FLEETS}
    winter = {name: day_curve(share, days, "Oct-Apr", group, mobile)
              for name, group, mobile in FLEETS}
    weeks = {name: week_curve(week, "May-Sep", group, mobile)
             for name, group, mobile in FLEETS}

    # The page's whole first claim, asserted rather than trusted: the store is
    # UTC and the local hour is the point. Read the hour column as UTC and the
    # summer peak moves to 10:00 — a plausible clock, a wrong one.
    peak = max(range(24), key=lambda h: clocks["sailing"][h])
    assert peak == 12, f"the summer sailing peak is at {peak}:00, not noon"
    assert clocks["sailing"][peak] > 8, \
        f"the summer sailing peak is {clocks['sailing'][peak]} % of the day"

    sun = day_curve(share, days, "May-Sep", "leisure", "Class B", ["sun"])
    sat = day_curve(share, days, "May-Sep", "leisure", "Class B", ["sat"])
    wdy = day_curve(share, days, "May-Sep", "leisure", "Class B", ["weekday"])

    tops = {name: max(range(168), key=lambda s: curve[s])
            for name, curve in weeks.items()}
    sail_days = day_shares(weeks["sailing"])
    fish_days = day_shares(weeks["fishing"])

    app = [prof[h]["appeared"] for h in range(24)]
    van = [prof[h]["vanished"] for h in range(24)]
    ring = [prof[h]["from_ring"] for h in range(24)]
    morning = range(8, 13)

    return {
        "clocks": clocks,
        "week": {name: weeks[name] for name in ("sailing", "cargo")},
        "harbour": {
            "place": PORT,
            "appeared": app, "from_ring": ring,
            "vanished": van, "to_ring": [prof[h]["to_ring"] for h in range(24)],
        },
        "n": {
            # P1 — the four clocks
            "flat_hour": f"{FLAT_DAY:.1f}",
            "sailing_peak": clock(peak),
            "sailing_peak_share": f"{clocks['sailing'][peak]:.1f}",
            "sailing_peak_x": f"{clocks['sailing'][peak] / FLAT_DAY:.1f}",
            "sailing_low": f"{min(clocks['sailing']):.1f}",
            "sailing_low_hour": clock(clocks["sailing"].index(min(clocks["sailing"]))),
            "sailing_night": f"{night(clocks['sailing']):.1f}",
            "cargo_low": f"{min(clocks['cargo']):.1f}",
            "cargo_high": f"{max(clocks['cargo']):.1f}",
            "ferries_night": f"{night(clocks['ferries']):.0f}",
            "ferries_peak": clock(clocks["ferries"].index(max(clocks["ferries"]))),
            # the two counts the prose spells out as words: the years the store
            # holds whole enough to pool, and sql/31's ten marina cells.
            "summers": WORDS[len(YEARS)],
            "cells": WORDS[10],
            # P1 prose — Sunday against Saturday
            "sun_peak": f"{max(sun):.1f}",
            "sat_peak": f"{max(sat):.1f}",
            "weekday_peak": f"{max(wdy):.1f}",
            "sun_night": f"{night(sun):.1f}",
            "sat_night": f"{night(sat):.1f}",
            "sun_evening": f"{sum(sun[18:22]):.1f}",
            "weekday_evening": f"{sum(wdy[18:22]):.1f}",
            # P1 prose — the seasons
            "fishing_move": f"{spread(clocks['fishing'], winter['fishing']):.0f}",
            "cargo_move": f"{spread(clocks['cargo'], winter['cargo']):.0f}",
            "fishing_night_summer": f"{night(clocks['fishing']):.0f}",
            "fishing_night_winter": f"{night(winter['fishing']):.0f}",
            "fishing_peak_summer": clock(clocks["fishing"].index(max(clocks["fishing"]))),
            "fishing_peak_winter": clock(winter["fishing"].index(max(winter["fishing"]))),
            "sailing_peak_winter_share": f"{max(winter['sailing']):.1f}",
            # P2 — the week
            "flat_week": f"{FLAT_WEEK:.1f}",
            "week_top": f"{weeks['sailing'][tops['sailing']]:.1f}",
            "week_top_day": DOW[tops["sailing"] // 24],
            "week_top_hour": clock(tops["sailing"] % 24),
            "week_top_x": f"{weeks['sailing'][tops['sailing']] / FLAT_WEEK:.1f}",
            "ferries_top": f"{DOW[tops['ferries'] // 24]} at "
                           f"{clock(tops['ferries'] % 24)}",
            "cargo_top": f"{DOW[tops['cargo'] // 24]} at "
                         f"{clock(tops['cargo'] % 24)}",
            "fishing_top": f"{DOW[tops['fishing'] // 24]} at "
                           f"{clock(tops['fishing'] % 24)}",
            "sailing_weekend": f"{sail_days[5] + sail_days[6]:.0f}",
            "flat_weekend": f"{200 / 7:.0f}",
            "cargo_week_low": f"{min(weeks['cargo']):.2f}",
            "cargo_week_high": f"{max(weeks['cargo']):.2f}",
            "fishing_sat": f"{fish_days[5]:.0f}",
            "fishing_tue": f"{fish_days[1]:.0f}",
            # P3 — the harbour
            "port_in": f"{sum(app):.0f}",
            "port_out": f"{sum(van):.0f}",
            "port_in_peak": clock(max(range(24), key=lambda h: app[h])),
            "port_out_peak": clock(max(range(24), key=lambda h: van[h])),
            "port_nowhere": f"{100 * (1 - sum(ring[h] for h in morning) / sum(app[h] for h in morning)):.0f}",
            "port_nowhere_low": f"{min(nowhere):.0f}",
            "port_nowhere_high": f"{max(nowhere):.0f}",
            "port_floor_low": f"{min(floors):.0f}",
            "port_floor_high": f"{max(floors):.0f}",
            "small_boats_min": sp(private_count(
                min(prof[h]["k"] for h in range(24)), f"{PORT}'s quietest hour")),
        },
    }
