-- S6 chart 5 — how much of the movement happens at night.
-- Run: scripts/ch.sh sql/24_night.sql
-- Columns: year, season, fleet, local_days, moving_msgs, night_msgs, night_share
--   season: 'May-Sep' | 'Oct-Apr', from the LOCAL month
--   fleet:  'leisure Class B' | 'ferry Class A' (the control)
--   night:  local hour in 22, 23, 0, 1, 2, 3, 4
--
-- Activity is `moving_msgs`, not distinct vessels: h3_hourly's `vessels` is a
-- uniqExact state that counts every vessel in the cell-hour whether it moved or
-- not, and a distinct *moving* vessel count is not recoverable from it (same
-- constraint as sql/11_week_profile.sql and sql/12_day_profile.sql).
--
-- Class A passenger ships are the CONTROL, not a comparison of levels. The two
-- fleets report at completely different rates, so only the SHAPE may be read:
-- a ferry timetable runs into the night by design, a leisure boat does not, and
-- if both night shares moved together across years the cause would be the
-- receiver network, not people's behaviour.
--
-- WHY THIS FILE EXISTS BEYOND ITS OWN CHART: it is the error bound on
-- sql/21_weekend_effect.sql. That query takes the weekday from a UTC date, so
-- the first one to two local hours of each day are filed under the previous
-- weekday. `night_share` here — and in particular the 00:00-02:00 part of it —
-- says how much fleet movement can possibly be misfiled that way.
--
-- Local time is by timezone NAME, so it is DST-correct: July is UTC+2 and
-- January UTC+1. Year and month are taken from the local timestamp too, so a
-- row is filed under the calendar its hour belongs to on shore.
--
-- TWO EXCLUSIONS, both about message counts, which is the one quantity in the
-- store that is not robust:
--   1. 2015-08-28 00:00 UTC .. 2015-10-01 00:00 UTC is dropped. The archive
--      itself duplicates that window upstream — msgs per leisure vessel-day
--      averages 7 512 against 2 600-3 700 either side, ~2.3x inflated, and the
--      elevation crosses three separate zip files so it is in the source rows,
--      not in the loader (docs/STATUS.md § S4-tails). Duplicated messages carry
--      the original hour, so the inflation is not spread evenly across the
--      clock and would move 2015's night share by an unknown amount. The window
--      removes local 2015-08-28 .. 2015-09-30, i.e. 34 of the 153 May-Sep days;
--      2015-06-24 goes as well under rule 2 (a 21-hour receiver gap), so 2015's
--      'May-Sep' row covers 118 of its 153 days and its 'Oct-Apr' row 209 of 212
--      (2015-10-01 by rule 1, then 2015-01-01 at 23 hours — the first local day
--      of the loaded block — and 2015-03-29, the DST Sunday, by rule 2).
--   2. Local days that are not fully covered are dropped, the same `covered`
--      CTE as sql/11_week_profile.sql: the archive is cut on UTC boundaries, so
--      the first local day of a loaded block is missing its first one or two
--      hours and a straggler local day holds only those hours. Those are night
--      hours, which is exactly what this file counts. KNOWN COST, inherited from
--      sql/11 and not fixed here: the spring-forward Sunday has 23 local hours by
--      construction, so `covered` drops it in every single year (2015-03-29,
--      2018-03-25, ...). It is one Sunday in March out of a season, it falls in
--      'Oct-Apr', and the alternative — a per-day expected-hour count — is more
--      machinery than the answer is worth.
--
-- `local_days` is reported so the two exclusions stay visible: 2022 and 2023
-- hold 59 days each and have no 'May-Sep' row at all, 2024 begins 2024-03-01,
-- 2026 ends 2026-08-26.
WITH
-- ORDER MATTERS: exclusion 1 is applied HERE, before the coverage test, and both
-- `covered` and `local` read from this one CTE. Filtering after the test would
-- let the two edge days of the excluded window through with the hours the
-- exclusion did not remove — local 2015-08-28 kept 2 hours, both of them night,
-- and local 2015-10-01 kept 22 — which is precisely the kind of part-day this
-- file must not count.
base AS (
    SELECT toTimeZone(hour, 'Europe/Copenhagen') AS lt,
           mobile, ship_group, moving_msgs
    FROM h3_hourly
    WHERE NOT (hour >= toDateTime('2015-08-28 00:00:00', 'UTC')
           AND hour <  toDateTime('2015-10-01 00:00:00', 'UTC'))
),
covered AS (
    SELECT toDate(lt) AS lday
    FROM base
    GROUP BY lday
    HAVING uniqExact(toHour(lt)) = 24
),
local AS (
    SELECT lt,
           if(mobile = 'Class B', 'leisure Class B', 'ferry Class A') AS fleet,
           moving_msgs AS mm      -- renamed: the output column below is an
                                  -- aggregate of the same name
    FROM base
    WHERE (   (mobile = 'Class B' AND ship_group = 'leisure')
           OR (mobile = 'Class A' AND ship_group = 'passenger'))
      AND toDate(lt) IN (SELECT lday FROM covered)
)
SELECT
    toYear(lt)                                                AS year,
    if(toMonth(lt) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr')     AS season,
    fleet,
    uniqExact(toDate(lt))                                     AS local_days,
    sum(mm)                                                   AS moving_msgs,
    sumIf(mm, toHour(lt) IN (22, 23, 0, 1, 2, 3, 4))          AS night_msgs,
    round(night_msgs / moving_msgs, 4)                        AS night_share
FROM local
GROUP BY year, season, fleet
ORDER BY year, season DESC, fleet;
