-- S7 chart 1 — what shape does each fleet's day have, and does it change with
-- the season, the weekday and the year?
-- Run: scripts/ch.sh sql/30_hour_profiles.sql
-- Columns: year, season, ship_group, mobile, daytype, lhour, local_days,
--          moving_msgs, share_of_day
--   season:  'May-Sep' | 'Oct-Apr', from the LOCAL month
--   mobile:  'Class A' | 'Class B'
--   daytype: 'weekday' (Mon-Fri) | 'sat' | 'sun', from the LOCAL weekday
--   lhour:   hour of day in Europe/Copenhagen, 0-23
--
-- Activity is `moving_msgs`, not distinct vessels: h3_hourly's `vessels` is a
-- uniqExact state that counts every vessel in the cell-hour whether it moved or
-- not, and a distinct *moving* vessel count is NOT recoverable from it (the same
-- constraint as sql/11_week_profile.sql, sql/12_day_profile.sql and
-- sql/24_night.sql).
--
-- Class A and Class B report at completely different rates — a Class A ship
-- sends a position every few seconds, a Class B one every 30 s at best — so the
-- message counts are not comparable BETWEEN fleets. `share_of_day` normalises
-- each (year, season, ship_group, mobile, daytype) curve against itself: ONLY
-- THE SHAPES may be compared, never the heights.
--
-- EVERY (ship_group, mobile) pair is emitted, including the thin ones — Class A
-- leisure, Class B cargo and the rest exist in the store and are the control
-- that says a shape is a fleet's habit and not the receiver network's. Nothing
-- is filtered out; `moving_msgs` stands next to `share_of_day` precisely so a
-- thin combination reads as thin instead of as a noisy curve of equal weight.
--
-- year, season, daytype and lhour are ALL taken from `lt`, the local timestamp,
-- never from the UTC date: a Saturday is a Saturday on shore. The conversion is
-- by timezone NAME, so it is DST-correct (July UTC+2, January UTC+1).
--
-- COVERAGE, REPAIRED FOR DST — this differs on purpose from sql/11, sql/12 and
-- sql/24. Those three keep a local day when `uniqExact(toHour(local)) = 24`. A
-- spring-forward Sunday has only 23 local hours by construction, so that rule
-- drops it in EVERY year: 2015-03-29, 2018-03-25, 2021-03-28, 2024-03-31,
-- 2025-03-30, 2026-03-29 — six local days, measured. S6 left that standing and
-- asked S7 to decide; the decision is to repair it here. A local day is kept
-- when the number of DISTINCT UTC HOURS it contains equals the number of hours
-- the day actually has:
--     dateDiff('hour', toStartOfDay(lt), toStartOfDay(lt) + INTERVAL 1 DAY)
-- which this machine's ClickHouse returns as 23 on 2015-03-29 and 2018-03-25,
-- 25 on 2015-10-25, and 24 on 2015-06-24 and 2026-07-01.
-- It must count `uniqExact(hour)` in UTC, NOT `uniqExact(toHour(lt))`: on a
-- fall-back day the local clock strikes 02 twice, so the local-hour count is 24
-- against an expected 25 and the repaired rule would have thrown away the five
-- autumn Sundays it was supposed to keep (2015-10-25, 2018-10-28, 2021-10-31,
-- 2024-10-27, 2025-10-26 — all measured at local_h 24, utc_h 25).
-- sql/11, sql/12 and sql/24 are deliberately NOT retrofitted: their numbers are
-- quoted verbatim in notes/ch01-findings.md. The cost of the difference was
-- measured — sql/24's night shares move by at most 0.0010 (2026 Oct-Apr
-- leisure, 0.0703 -> 0.0693) and every May-Sep row is unchanged, because the
-- day this repair adds back is always a Sunday in March.
--
-- The other reason `covered` exists at all is unchanged from sql/11: the
-- archive is cut on UTC boundaries, so the first local day of a loaded block is
-- missing its first one or two hours and a straggler local day holds only
-- those. Both would bias an hour-of-day curve.
--
-- ORDER MATTERS, as in sql/24: the Sep-2015 exclusion is applied in `base`,
-- BEFORE the coverage test, and both `covered` and `local` read that one CTE.
-- The archive duplicates 2015-08-28 .. 2015-09-30 upstream (~2.3x on messages,
-- docs/STATUS.md § S4-tails) and this file counts messages, so the window goes.
-- Filtering after the test would let the two edge days through holding only the
-- hours the exclusion did not remove.
--
-- `local_days` is the coverage column: 2022 and 2023 hold 59 winter days each
-- and have no 'May-Sep' row at all, 2024 begins 2024-03-01, 2026 ends
-- 2026-08-26. Partial coverage is shown, not filtered away.
--
-- READ `local_days` AS "days this fleet was seen", not "days covered". A fleet
-- that sent nothing anywhere in an hour writes no h3_hourly row and drops out of
-- the count. Nothing here divides by it — `share_of_day` is a ratio of message
-- counts inside the partition — so no number in this file is affected, unlike
-- sql/31 and sql/32 where the same quantity IS a divisor and is therefore split
-- into `season_days` / `slot_days` (the divisor) and `days_seen`. Measured: over
-- the 1 008 (year, season, daytype, lhour) buckets the ten fleet pairs disagree
-- in exactly ONE — 2024 Oct-Apr weekday 14:00, Class A leisure 107 against 108
-- for the other nine.
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
local AS (
    SELECT lt, mobile, ship_group, moving_msgs AS mm
    FROM base
    WHERE toDate(lt) IN (SELECT lday FROM covered)
)
SELECT
    toYear(lt)                                            AS year,
    if(toMonth(lt) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr') AS season,
    ship_group,
    mobile,
    multiIf(toDayOfWeek(lt) = 6, 'sat', toDayOfWeek(lt) = 7, 'sun', 'weekday') AS daytype,
    toHour(lt)                                            AS lhour,
    uniqExact(toDate(lt))                                 AS local_days,
    sum(mm)                                               AS moving_msgs,
    round(moving_msgs / sum(moving_msgs)
          OVER (PARTITION BY year, season, ship_group, mobile, daytype), 5) AS share_of_day
FROM local
GROUP BY year, season, ship_group, mobile, daytype, lhour
ORDER BY year, season DESC, ship_group, mobile, daytype, lhour;
