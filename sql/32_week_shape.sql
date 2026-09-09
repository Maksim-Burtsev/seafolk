-- S7 chart 3 — the 168-hour week: where in the week does each fleet actually move?
-- Run: scripts/ch.sh sql/32_week_shape.sql
-- Columns: year, season, ship_group, mobile, slot, slot_days, days_seen,
--          mean_moving, share_of_week
--   season: 'May-Sep' | 'Oct-Apr', from the LOCAL month
--   mobile: 'Class A' | 'Class B'
--   slot:   0 = Monday 00:00 … 167 = Sunday 23:00, in Europe/Copenhagen,
--           computed as (toDayOfWeek(lt) - 1) * 24 + toHour(lt)
--
-- This is sql/30_hour_profiles.sql's question asked at the other grain: sql/30
-- folds every Saturday onto one 24-hour clock, this file keeps the week open so
-- the Friday-evening ramp and the Sunday-evening return are visible as one
-- continuous curve instead of three separate day-shapes.
--
-- Activity is `moving_msgs`. h3_hourly's `vessels` is a uniqExact state over
-- every vessel in the cell-hour, moving or not, and a distinct *moving* vessel
-- count is NOT recoverable from it — the same constraint as sql/11, sql/12,
-- sql/24 and sql/30.
--
-- Class A and Class B report at completely different rates, so heights are not
-- comparable between fleets. `share_of_week` normalises each (year, season,
-- ship_group, mobile) week against itself: ONLY THE SHAPES may be compared.
--
-- AVERAGED PER OCCURRENCE OF THE SLOT, NEVER SUMMED (sql/11's rule). A season
-- holds 22 Mondays and 21 Tuesdays, or a year is cut short mid-week, and a raw
-- sum would draw that calendar accident as a weekly rhythm.
--
-- TWO DAY COLUMNS, AND ONLY ONE OF THEM IS THE DENOMINATOR.
--   slot_days  every covered local day in that (year, season) falling on the
--              slot's WEEKDAY — how many times the slot occurred at all. The
--              divisor of mean_moving.
--   days_seen  the covered local days on which this fleet actually produced a
--              row in that slot. Informative, never a divisor.
-- A covered day on which a fleet moved nowhere in Denmark is a TRUE ZERO, and it
-- cannot reach the group by itself because an empty cell-hour writes no
-- h3_hourly row. For the fleets with national traffic every hour the two columns
-- are equal and nothing moves; for the THIN pairs this file deliberately emits —
-- Class A leisure, Class B cargo — days_seen is well below slot_days and
-- dividing by it would inflate exactly the curves that are already fragile.
-- Both columns are emitted so the ratio is auditable, and the same convention is
-- used in sql/31_port_breathing.sql and sql/33_port_oracle.sql.
--   KNOWN AND SMALL, both of them at slot 146 (Sunday 02:00) and nowhere else,
--   because slot_days counts WEEKDAYS and one Sunday a year does not have 24
--   ordinary hours:
--     * fall-back Sunday — the local clock strikes 02 twice, so slot 146 takes
--       two UTC hours from one date while slot_days counts the date once, and
--       the mean is over-stated by that hour. Five such Sundays are in the store
--       (2015-10-25, 2018-10-28, 2021-10-31, 2024-10-27, 2025-10-26).
--     * spring-forward Sunday — there is no local 02 at all, so the slot really
--       occurred one time fewer than slot_days says and the mean is under-stated
--       by up to 1/29. Six such Sundays are in the store, the ones the repaired
--       coverage rule below adds back.
--   MEASURED: days_seen differs from slot_days on 61 of the 23 520 rows, always
--   by exactly 1. SIXTY of those are at slot 146 — six years x ten fleet pairs,
--   every one of them 'Oct-Apr' — and that regularity is the proof that what is
--   left there is the CALENDAR and not occupancy. The SIXTY-FIRST is not: slot
--   38 (Tuesday 14:00), 2024 'Oct-Apr', Class A leisure, a single thin fleet
--   that sent nothing anywhere in that hour on one day. It is the same
--   occupancy case sql/30's header records (107 days against 108) and it is why
--   this paragraph does not claim the shortfall is calendar-only. Neither case
--   is worth the special-casing it would cost; both are visible in the two day
--   columns, which is why both are emitted.
--
-- `year` IS EMITTED rather than aggregated away. 2022 and 2023 hold 59 winter
-- days each — a winter sample, not a year — and 2024 begins 2024-03-01, 2026
-- ends 2026-08-26. The plot script excludes 2022/2023; this file shows them.
--
-- COVERAGE, REPAIRED FOR DST — the same repaired `base` / `covered` / `local`
-- chain as sql/30_hour_profiles.sql and sql/31_port_breathing.sql, and it
-- differs on purpose from sql/11, sql/12 and sql/24. Those three keep a local
-- day when `uniqExact(toHour(local)) = 24`, which a 23-hour spring-forward
-- Sunday fails by construction, so they drop one Sunday in March in every year
-- (2015-03-29, 2018-03-25, 2021-03-28, 2024-03-31, 2025-03-30, 2026-03-29 —
-- six local days, measured). Here a local day is kept when its number of
-- DISTINCT UTC HOURS equals the number of hours the day really has,
-- dateDiff('hour', toStartOfDay(lt), toStartOfDay(lt) + INTERVAL 1 DAY), which
-- this machine's ClickHouse returns as 23 / 25 / 24 on a spring-forward /
-- fall-back / ordinary day. The count must be over UTC hours: `uniqExact(hour)`,
-- not `uniqExact(toHour(lt))`, because the local-hour count on a fall-back day
-- is 24 against an expected 25 and would drop the five autumn Sundays.
-- sql/11, sql/12 and sql/24 are NOT retrofitted — their numbers are quoted
-- verbatim in notes/ch01-findings.md; the measured cost of the difference is
-- at most 0.0010 on sql/24's night shares, all of it in 'Oct-Apr'.
--
-- The Sep-2015 duplication window is excluded in `base`, BEFORE the coverage
-- test, so its two edge days cannot survive as part-days (sql/24's ordering
-- rule). This file counts messages, which is the one quantity the duplication
-- moves.
WITH
base AS (
    SELECT hour,                                   -- UTC, kept for the coverage count
           toTimeZone(hour, 'Europe/Copenhagen') AS lt,
           mobile, ship_group, moving_msgs
    FROM h3_hourly
    WHERE NOT (hour >= toDateTime('2015-08-28 00:00:00', 'UTC')
           AND hour <  toDateTime('2015-10-01 00:00:00', 'UTC'))
),
covered AS (
    SELECT toDate(lt) AS lday
    FROM base
    GROUP BY lday
    HAVING uniqExact(hour) = dateDiff('hour', toStartOfDay(min(lt)),
                                              toStartOfDay(min(lt)) + INTERVAL 1 DAY)
),
-- the denominator: how many times each weekday occurs, covered, in each
-- (year, season). Independent of any fleet ever being seen on it.
slot_days AS (
    SELECT toYear(lday)                                        AS year,
           if(toMonth(lday) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr') AS season,
           toDayOfWeek(lday)                                   AS dow,
           count()                                             AS n_days
    FROM covered
    GROUP BY year, season, dow
),
local AS (
    SELECT lt,
           toYear(lt)                                            AS year,
           if(toMonth(lt) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr') AS season,
           toDayOfWeek(lt)                                       AS dow,
           mobile, ship_group, moving_msgs AS mm
    FROM base
    WHERE toDate(lt) IN (SELECT lday FROM covered)
)
SELECT
    l.year                                                AS year,
    l.season                                              AS season,
    l.ship_group                                          AS ship_group,
    l.mobile                                              AS mobile,
    (l.dow - 1) * 24 + toHour(l.lt)                       AS slot,
    max(d.n_days)                                         AS slot_days,
    uniqExact(toDate(l.lt))                               AS days_seen,
    round(sum(l.mm) / slot_days, 1)                       AS mean_moving,
    round(mean_moving / sum(mean_moving)
          OVER (PARTITION BY year, season, ship_group, mobile), 5) AS share_of_week
FROM local AS l
INNER JOIN slot_days AS d
        ON d.year = l.year AND d.season = l.season AND d.dow = l.dow
GROUP BY year, season, ship_group, mobile, slot
ORDER BY year, season DESC, ship_group, mobile, slot;
