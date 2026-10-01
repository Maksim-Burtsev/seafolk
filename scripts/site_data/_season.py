"""site/season.html — chapter one: a year under sail. Four charts, one dict.

Everything the page says about the private fleet is computed here, from the
query files chapter 01 already runs (notes/ch01-findings.md, findings 1-10).

    chart  what it says                            where the numbers come from
    S1     the peak has walked three weeks early   sql/20_season_bounds.sql
                                                   + sql/10_season_daily.sql (the profiles)
    S2     the summer week, day by day             sql/81_site_season.sql
    S3     a hundred days of a switched-on radio   sql/23_radius.sql
    S4     Silverrudder against a usual day        sql/22_regatta_spikes.sql
    prose  Friday starts late                      sql/21_weekend_effect.sql
    prose  the night is empty, and stays empty     sql/24_night.sql

sql/81 is the only new file: sql/21 measures the weekend as two buckets and the
page draws seven bars, so the same measure is cut by day of the week there.
Its weekday and weekend means are asserted against sql/21's below — the two
files must agree, and if one is ever edited the build says so rather than the
page drifting from the chapter.

PRIVACY. The fleet on this page is private (small boats), so every published
number is either a SHARE of tens of thousands of days, or a head count of
hundreds of boats:

  * S1 draws dates, one head count per year (the smallest is the busiest
    week of 2015, over a thousand boats) and each year's season as a SHARE of
    its own busiest week; the daily counts behind those shares are floored;
  * S2 draws a mean over 21-22 occurrences of a weekday; the smallest single
    day behind any bar is asserted below and runs in the hundreds;
  * S3 draws shares of a year's days, scaled to a hundred;
  * S4 is the only place where small counts could appear at all — it draws one
    harbour on one day. Every Silverrudder race day holds 47 boats or more and
    every day of its usual-day comparison holds at least 12, asserted below.
    The other regattas appear in the prose as ratios only, never as counts,
    because some of their quiet days hold fewer than five boats.

No radio ID, name, position or track of a private boat is read or written here.
"""
import datetime
import statistics

from . import YEARS, private_count, sp, typed
# The last year the store holds whole, which is the year the three single-year
# charts draw. 2026 stops on 26 August, in the middle of its own season.
NOW = 2025
# May to September, the sailing season this page's week and night numbers use.
SEASON_DAYS = 153

S20 = ("year days first_day last_day censored peak_7d peak_day start_25 end_25 "
       "len_25 start_50 end_50 len_50").split()
S20_INT = "year days len_25 len_50".split()
S81 = "year dow day_name days mean_moved min_moved ratio_to_weekday".split()
S81_INT = "year dow days min_moved".split()
S22 = ("name year place race_day dow race_vessels base_days base_mean base_min "
       "base_max ratio event_mean_ratio").split()
S22_INT = "year race_vessels base_days base_min base_max".split()
S23 = ("year days vessel_days share_idle moved_days p25 p50 p75 p90 p99 "
       "share_lt_5nm share_ge_30nm share_home_in_marina_cell "
       "share_home_near_marina").split()
S23_INT = "year days vessel_days moved_days".split()
S21 = "metric year season bucket n value ratio".split()
S24 = "year season fleet local_days moving_msgs night_msgs night_share".split()

MONTHS = ("January February March April May June July August September "
          "October November December").split()


def doy(day):
    """A date string -> its day of a COMMON year.

    The six years are drawn over one calendar, so a leap year must not shift
    August by a day against a common one; every date here is mapped onto 2001.
    Nothing on this page falls on 29 February — the season runs May to October.
    """
    d = datetime.date.fromisoformat(day)
    return datetime.date(2001, d.month, d.day).timetuple().tm_yday


def spell(day):
    """'2015-08-07' -> '7 August'."""
    d = datetime.date.fromisoformat(day)
    return f"{d.day} {MONTHS[d.month - 1]}"


def per100(shares):
    """Shares summing to 1 -> whole numbers summing to 100.

    The unit chart draws a hundred dots and they have to be a hundred, so the
    rounding is largest-remainder rather than six independent round() calls
    that add up to 99 in some years and 101 in others.
    """
    out = [int(s * 100) for s in shares]
    short = 100 - sum(out)
    order = sorted(range(len(shares)), key=lambda i: shares[i] * 100 - out[i],
                   reverse=True)
    for i in order[:short]:
        out[i] += 1
    return out


# ------------------------------------------------------------------- S1 ----
def season(ch):
    """sql/20 -> one row per year: the season's span, and its busiest week.

    `start_25`/`end_25` are the days the year's own 7-day mean first and last
    stand above a quarter of its peak — the outer edge of the season, which
    finding 1 shows is nearly fixed. `peak_day` is the top of that mean, which
    finding 2 shows is not.

    `cut_start` / `cut_end` say whether a bound IS the edge of the loaded days
    rather than a day the archive watched the fleet cross. sql/20's `censored`
    column is coarser than the chart needs: it flags 2024 because the year has
    no January, but 2024's season still starts on 8 May, two months inside the
    loaded range, so that bound is a measurement and the bar should not be
    marked. 2026's end is the archive's own last day and is a floor.
    """
    rows = [typed(S20, r, S20_INT) for r in ch("20_season_bounds.sql")]
    assert [r["year"] for r in rows] == YEARS, "sql/20 no longer returns the six years"
    out = []
    for r in rows:
        assert r["len_25"] >= r["len_50"], f"{r['year']}: the core is wider than the season"
        out.append({
            "year": r["year"],
            "start": doy(r["start_25"]), "start_label": spell(r["start_25"]),
            "end": doy(r["end_25"]), "end_label": spell(r["end_25"]),
            "len": r["len_25"], "core": r["len_50"],
            "peak": doy(r["peak_day"]), "peak_label": spell(r["peak_day"]),
            "small_boats_peak": private_count(
                round(r["peak_7d"]), f"sql/20 {r['year']}: its busiest week"),
            # a bound that sits on the first or last loaded day is where the
            # ARCHIVE stopped, not where the season did
            "cut_start": r["start_25"] == r["first_day"],
            "cut_end": r["end_25"] == r["last_day"],
        })
    by_year = {r["year"]: r for r in rows}
    return {"rows": out, "guide": out[0]["peak"],
            "profile": profiles(ch, by_year)}, by_year


# The stretch of the calendar S1's profiles draw: 1 April to 31 October.
PROFILE = (91, 304)


def profiles(ch, bounds):
    """sql/10 -> each year's season as a coastline: the trailing 7-day mean of
    boats out, as a per cent of that year's own busiest week.

    The mean is sql/20's own (trailing, seven calendar days, per year), so the
    profile's summit IS sql/20's peak_day and it crosses a quarter of the
    summit on sql/20's start_25 and end_25 — both asserted, because the chart
    draws the season as the land above that quarter and the prose quotes
    sql/20's lengths for it.
    """
    per_year = {}
    for day, mobile, _present, active, _m7 in ch("10_season_daily.sql"):
        if mobile == "Class B" and int(day[:4]) in YEARS:
            per_year.setdefault(int(day[:4]), []).append((day, int(active)))
    out = {}
    for year in YEARS:
        rows = sorted(per_year[year])
        days = [datetime.date.fromisoformat(d) for d, _ in rows]
        assert all((b - a).days == 1 for a, b in zip(days, days[1:])), \
            f"sql/10 {year}: a hole in the loaded days, the 7-day mean would span it"
        vals = [private_count(v, f"sql/10 {d}: small boats that moved") for d, v in rows]
        b = bounds[year]
        rows_d = [d for d, _ in rows]
        m7 = {d: sum(vals[i - 6:i + 1]) / 7 for i, d in enumerate(rows_d) if i >= 6}
        top = max(m7, key=m7.get)
        assert top == b["peak_day"] and abs(m7[top] - b["peak_7d"]) < .1, \
            f"sql/10 {year}: summit {top} is not sql/20's {b['peak_day']}"
        above = [d for d in rows_d if d in m7 and m7[d] >= .25 * m7[top]]
        assert (above[0], above[-1]) == (b["start_25"], b["end_25"]), \
            f"sql/10 {year}: the quarter-line crossings disagree with sql/20"
        out[str(year)] = [[doy(d), round(100 * m7[d] / m7[top], 1)] for d in rows_d
                          if d in m7 and PROFILE[0] <= doy(d) <= PROFILE[1]]
    return out


# ------------------------------------------------------------------- S2 ----
def week(ch, ratio21):
    """sql/81 -> the seven days of a summer week in the last whole year.

    `mean_moved` is averaged per occurrence of the weekday, never summed: a
    season holds 22 Saturdays and 21 Thursdays and a sum would draw that
    calendar accident as a rhythm. The weekday line the bars are read against
    is the Mon-Fri mean, weighted by occurrences, which is exactly what
    sql/21_weekend_effect.sql calls `weekday` — asserted here, because the page
    and the chapter must not drift apart.
    """
    rows = [typed(S81, r, S81_INT) for r in ch("81_site_season.sql")]
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)

    # a year whose May-Sep is whole, read off the day counts rather than a list
    full = [y for y, rs in by_year.items() if sum(r["days"] for r in rs) == SEASON_DAYS]
    assert NOW in full, f"{NOW} no longer holds a whole May-September"

    mean = lambda rs: (sum(r["mean_moved"] * r["days"] for r in rs)  # noqa: E731
                       / sum(r["days"] for r in rs))
    ratios = {}
    for y, rs in by_year.items():
        assert len(rs) == 7, f"{y}: {len(rs)} days of the week"
        # the bars are means over 21-22 occurrences of a weekday; the floor
        # goes on the SMALLEST single day behind any of them, because that is
        # the day a mean could be hiding.
        for r in rs:
            private_count(r["min_moved"],
                          f"sql/81 {y} {r['day_name']}: its quietest day")
        ratios[y] = mean([r for r in rs if r["dow"] >= 6]) / mean(rs[:5])

    days, weekday = by_year[NOW], mean(by_year[NOW][:5])
    for bucket, value in (("weekday", weekday),
                          ("weekend", mean(days[5:]))):
        assert abs(ratio21[(NOW, bucket)] - value) < 0.05, \
            f"sql/81 and sql/21 disagree on the {NOW} {bucket}: " \
            f"{value:.1f} against {ratio21[(NOW, bucket)]}"

    return {"year": NOW, "weekday": round(weekday, 1),
            # what the chart's annotation says, so that it cannot drift from
            # the headline: both are this one number
            "more": round(100 * (ratios[NOW] - 1)),
            "days": [{"name": r["day_name"], "short": r["day_name"][:3],
                      "small_boats": private_count(
                          round(r["mean_moved"]),
                          f"sql/81 {NOW} {r['day_name']}: boats out"),
                      "ratio": r["ratio_to_weekday"],
                      "days": r["days"]} for r in days]}, ratios, full


# ------------------------------------------------------------------- S3 ----
GROUPS = [("stayed", "never left the berth"),
          ("short", "went out, under five miles"),
          ("mid", "five to thirty miles"),
          ("long", "more than thirty miles")]


def hundred(ch):
    """sql/23 -> a hundred days of a small boat with its radio on.

    `share_idle` is of ALL days (a day the boat never exceeded half a knot);
    the distance shares in sql/23 are of the MOVED days only, so they are
    rescaled here onto the same hundred. That is the whole arithmetic of the
    chart, and it is here rather than in the page so that the four numbers a
    reader counts are the four numbers the build printed.
    """
    rows = {r["year"]: r for r in
            (typed(S23, r, S23_INT) for r in ch("23_radius.sql"))}
    y = rows[NOW]
    moved = 1 - y["share_idle"]
    mid = 1 - y["share_lt_5nm"] - y["share_ge_30nm"]
    assert mid > 0, "the distance bands overlap"
    counts = per100([y["share_idle"], moved * y["share_lt_5nm"],
                     moved * mid, moved * y["share_ge_30nm"]])
    return {"year": NOW,
            "groups": [{"key": k, "label": label, "share": n}
                       for (k, label), n in zip(GROUPS, counts)]}, rows


# ------------------------------------------------------------------- S4 ----
def race(ch):
    """sql/22 -> Silverrudder: race day against the same weekday a fortnight
    either side, and what the other Danish regattas do instead.

    The region is the start harbour's cell and two rings, ~20 km across — the
    gathering, not the course (sql/22's header, and finding 6: a race that
    finishes elsewhere is invisible to it after the start).

    Every count published from this chart is checked here: the race day, the
    mean of the usual days, and the SMALLEST of those usual days. The other
    regattas are quoted only as ratios, because some of their quiet days hold
    two or three boats.
    """
    rows = [typed(S22, r, S22_INT) for r in ch("22_regatta_spikes.sql")]
    events = {}
    for r in rows:
        events.setdefault((r["name"], r["year"]), []).append(r)
    for days in events.values():
        days.sort(key=lambda r: r["race_day"])

    silver = [days[0] for (name, _), days in sorted(events.items())
              if name == "Silverrudder"]
    out = []
    for r in silver:
        assert len(events[("Silverrudder", r["year"])]) == 1, "Silverrudder is one day"
        assert r["base_days"] == 4, f"Silverrudder {r['year']}: {r['base_days']} usual days"
        where = f"Silverrudder {r['year']}"
        out.append({"year": r["year"], "date": spell(r["race_day"]),
                    "weekday": ["Monday", "Tuesday", "Wednesday", "Thursday",
                                "Friday", "Saturday", "Sunday"][int(r["dow"]) - 1],
                    "small_boats_race": private_count(r["race_vessels"],
                                                      f"{where}: race day"),
                    "small_boats_usual": private_count(round(r["base_mean"]),
                                                       f"{where}: a usual day"),
                    "usual_low": private_count(r["base_min"],
                                               f"{where}: its quietest usual day"),
                    "usual_high": private_count(r["base_max"],
                                                f"{where}: its busiest usual day"),
                    "times": round(r["ratio"], 1)})

    # the other Danish events, as ratios: the last day of a multi-day race is
    # the quiet one (finding 6), and none of them grows the way Silverrudder does
    multi = [days for (name, _), days in events.items()
             if name not in ("Silverrudder", "Kieler Woche") and len(days) > 1]
    others = [days[0]["event_mean_ratio"] for (name, _), days in events.items()
              if name not in ("Silverrudder", "Kieler Woche")]
    return {"place": "Svendborg", "rows": out}, {
        "events": len(multi),
        "first": statistics.mean(d[0]["ratio"] for d in multi),
        "last": statistics.mean(d[-1]["ratio"] for d in multi),
        "quiet_last": sum(1 for d in multi
                          if d[-1]["ratio"] == min(x["ratio"] for x in d)),
        "lo": min(others), "hi": max(others)}


# ----------------------------------------------------------------- prose ----
def friday(ch):
    """sql/21 -> the weekend means the week chart is checked against, and the
    share of a day's boats whose radio first speaks after 15:00 local.

    The late start is an INDIRECT measure and the page says so in a sentence:
    it is the first message of the day, not the moment the lines came off.
    """
    late, ratio = {}, {}
    for row in ch("21_weekend_effect.sql"):
        r = typed(S21, row)
        if r["metric"] == "late_start":
            late[(int(r["year"]), r["bucket"])] = r["value"]
        elif r["season"] == "May-Sep":
            ratio[(int(r["year"]), r["bucket"])] = r["value"]
    return late, ratio


def night(ch):
    """sql/24 -> the share of summer movement that happens between 22:00 and
    05:00 local, for the small boats and for the ferries that are its control.
    """
    out = {}
    for row in ch("24_night.sql"):
        r = typed(S24, row)
        if r["season"] == "May-Sep":
            out[(int(r["year"]), r["fleet"].split()[0])] = r["night_share"]
    return out


# ------------------------------------------------------------------ page ----
def build(ch):
    late, ratio21 = friday(ch)
    charts = {}
    charts["season"], bounds = season(ch)
    charts["week"], weekend, full_season = week(ch, ratio21)
    charts["hundred"], radius = hundred(ch)
    charts["race"], other_races = race(ch)
    nights = night(ch)

    whole = [y for y, r in bounds.items() if not r["censored"]]
    pct = lambda x: f"{100 * x:.0f}"                                # noqa: E731
    first, last = charts["season"]["rows"][0], charts["season"]["rows"][-1]
    hund = {g["key"]: g["share"] for g in charts["hundred"]["groups"]}
    silver = {r["year"]: r for r in charts["race"]["rows"]}
    # the weekend has been flat since 2018 and was higher in 2015 (finding 3),
    # so the range the page quotes is taken over the whole seasons after it
    steady = [weekend[y] for y in full_season if y > 2015]

    charts["n"] = {
        # S1 — the season and its peak
        "season_len_lo": str(min(bounds[y]["len_25"] for y in whole)),
        "season_len_hi": str(max(bounds[y]["len_25"] for y in whole)),
        "core_len_lo": str(min(bounds[y]["len_50"] for y in whole)),
        "core_len_hi": str(max(bounds[y]["len_50"] for y in whole)),
        "peak_first": first["peak_label"],
        "peak_last": last["peak_label"],
        "peak_shift": str(first["peak"] - last["peak"]),
        "fleet_growth": f"{bounds[NOW]['peak_7d'] / bounds[2015]['peak_7d']:.1f}",
        # S2 — the week
        "weekday_boats": sp(charts["week"]["weekday"]),
        "saturday_boats": sp(charts["week"]["days"][5]["small_boats"]),
        "weekend_more": f"{100 * (weekend[NOW] - 1):.0f}",
        "weekend_lo": f"{100 * (min(steady) - 1):.0f}",
        "weekend_hi": f"{100 * (max(steady) - 1):.0f}",
        "weekend_2015": f"{100 * (weekend[2015] - 1):.0f}",
        "late_friday": pct(late[(NOW, "Fri")]),
        "late_midweek": pct(late[(NOW, "Mon-Thu")]),
        "late_saturday": pct(late[(NOW, "Sat")]),
        "friday_edge_2015": f"{100 * (late[(2015, 'Fri')] / late[(2015, 'Mon-Thu')] - 1):.0f}",
        "friday_edge_now": f"{100 * (late[(NOW, 'Fri')] / late[(NOW, 'Mon-Thu')] - 1):.0f}",
        # S3 — a hundred days
        "stayed": str(hund["stayed"]),
        "went_far": str(hund["long"]),
        "idle_lo": pct(min(radius[y]["share_idle"] for y in YEARS)),
        "idle_hi": pct(max(radius[y]["share_idle"] for y in YEARS)),
        "trip_half": f"{radius[NOW]['p50']:.0f}",
        "trip_2015": f"{radius[2015]['p50']:.1f}",
        "trip_2021": f"{radius[2021]['p50']:.1f}",
        "marina": pct(radius[NOW]["share_home_in_marina_cell"]),
        "marina_lo": pct(min(radius[y]["share_home_in_marina_cell"] for y in YEARS)),
        "marina_hi": pct(max(radius[y]["share_home_in_marina_cell"] for y in YEARS)),
        # S4 — the race
        "race_times_first": f"{silver[2015]['times']:.1f}",
        "race_times_best": f"{max(r['times'] for r in silver.values()):.1f}",
        "race_boats": sp(silver[NOW]["small_boats_race"]),
        "race_usual": sp(silver[NOW]["small_boats_usual"]),
        "race_quiet_lo": str(min(r["usual_low"] for r in silver.values())),
        "race_quiet_hi": str(max(r["usual_high"] for r in silver.values())),
        "others_lo": f"{other_races['lo']:.1f}",
        "others_hi": f"{other_races['hi']:.1f}",
        "multi_events": str(other_races["events"]),
        "multi_quiet_last": str(other_races["quiet_last"]),
        "multi_first": f"{other_races['first']:.1f}",
        "multi_last": f"{other_races['last']:.1f}",
        # the night
        "night_now": f"{100 * nights[(NOW, 'leisure')]:.1f}",
        "night_lo": f"{100 * min(nights[(y, 'leisure')] for y in YEARS):.1f}",
        "night_hi": f"{100 * max(nights[(y, 'leisure')] for y in YEARS):.1f}",
        "night_ferry": pct(nights[(NOW, "ferry")]),
    }
    return charts
