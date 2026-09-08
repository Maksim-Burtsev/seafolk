-- S6 chart 2 — the weekend, and the Friday-evening departure.
-- Run: scripts/ch.sh sql/21_weekend_effect.sql
-- One long result set. Columns: metric, year, season, bucket, n, value, ratio
--
--   metric = 'weekend_effect'
--     bucket 'weekday' (Mon-Fri) | 'weekend' (Sat-Sun)
--     n      how many such days occurred in that year and season
--     value  mean number of DISTINCT Class B leisure vessels that moved on one
--            such day — averaged per OCCURRENCE of the day, never a raw sum: a
--            season holds a different number of Saturdays than of Tuesdays and
--            a sum would draw that calendar accident as a weekly rhythm.
--     ratio  weekend value / weekday value, repeated on both rows.
--
--   metric = 'late_start'
--     bucket 'Mon-Thu' | 'Fri' | 'Sat' | 'Sun', May-Sep only
--     n      Class B leisure vessel-days with moving_msgs > 0 in that bucket
--     value  share of those whose first_ts is after 15:00 Europe/Copenhagen
--     ratio  value / the 'Mon-Thu' value of the same year.
--
-- CAVEAT 1 — the weekday is taken from vessel_day.day, which is a UTC date.
-- Denmark is UTC+1/+2, so a "Saturday" here is the local window 01:00 Sat to
-- 01:00 Sun (02:00 in summer): the first one to two hours of local Saturday are
-- filed under Friday. That smear can only move activity that happens between
-- midnight and 02:00 local, which is the deadest part of the leisure day —
-- sql/24_night.sql measures exactly how much of the fleet's movement falls in
-- that window and is the bound on this error. A local-day version is not free:
-- vessel_day is built on UTC days (sql/03_aggregate.sql), so first_ts,
-- moving_msgs and dist_nm are all defined against the UTC day and re-cutting
-- the day would mean re-reading the raw archive, which is gone.
--
-- CAVEAT 2 — 'late_start' is a PROXY for "left after work", not a measurement
-- of it. What it says is: the first message of the vessel-day arrives after
-- 15:00 local. A Class B transponder is usually switched on when the boat
-- leaves and off when it is tied up, so a late first message usually means a
-- late departure — but a boat that sat all afternoon with the electronics on
-- and cast off at 19:00 counts as an early start, and a boat whose transponder
-- simply came back into receiver range counts as a late one. The honest
-- quantity, "the first hour in which the vessel moved", is not recoverable:
-- vessel_day keeps one first_ts per day and h3_hourly cannot separate a moving
-- vessel from a stationary one inside its uniqExact state.
--
-- Season labels are calendar-year slices: 'Oct-Apr' for year Y means Jan-Apr Y
-- plus Oct-Dec Y, two different winters, not one continuous one.
--
-- Partial years are kept and made visible through `n`: 2022 and 2023 hold 59
-- days each (winter only, so they have no 'May-Sep' row at all), 2024 starts
-- 2024-03-01 and 2026 ends 2026-08-26.
--
--
-- SHORT UTC DAYS ARE COUNTED WHOLE. Two of the 2 122 loaded days hold fewer than
-- 24 hours of h3_hourly — 2015-06-24 (21) and 2018-05-17 (20), receiver gaps in
-- the source — and this file counts them as ordinary days. No coverage filter is
-- applied on purpose: what is counted here is DISTINCT VESSELS (or vessel-days),
-- which a missing hour barely moves — a boat out sailing reports in the other
-- 20-odd hours too — and dropping 2 days in 2 122 would cost more in a special
-- case than it buys. sql/11, sql/12 and sql/24 do drop such days, because they
-- count messages by hour of the day, where a missing hour is a hole in the shape.
-- Message counts are not used, so the Sep-2015 duplication (docs/STATUS.md
-- § S4-tails) does not reach this query: it inflates msgs, not distinct-vessel
-- counts, and first_ts is a min over timestamps that duplication cannot move.
WITH
daily AS (
    SELECT toYear(day)                                  AS year,
           if(toMonth(day) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr') AS season,
           if(toDayOfWeek(day) >= 6, 'weekend', 'weekday')        AS bucket,
           day,
           uniqExactIf(mmsi, moving_msgs > 0)           AS moved
    FROM vessel_day
    WHERE mobile = 'Class B' AND ship_group = 'leisure'
    GROUP BY year, season, bucket, day
),
vdays AS (
    SELECT toYear(day) AS year,
           multiIf(toDayOfWeek(day) = 5, 'Fri',
                   toDayOfWeek(day) = 6, 'Sat',
                   toDayOfWeek(day) = 7, 'Sun', 'Mon-Thu') AS bucket,
           toHour(toTimeZone(first_ts, 'Europe/Copenhagen')) >= 15 AS late
    FROM vessel_day
    WHERE mobile = 'Class B' AND ship_group = 'leisure'
      AND moving_msgs > 0
      AND toMonth(day) BETWEEN 5 AND 9
)
SELECT * FROM
(
SELECT
    'weekend_effect' AS metric,
    year,
    season,
    bucket,
    toUInt64(count())     AS n,
    round(avg(moved), 1)  AS value,
    round(value / sumIf(value, bucket = 'weekday')
                    OVER (PARTITION BY year, season), 3) AS ratio
FROM daily
GROUP BY year, season, bucket

UNION ALL

SELECT
    'late_start' AS metric,
    year,
    'May-Sep'    AS season,
    bucket,
    toUInt64(count())     AS n,
    round(avg(late), 4)   AS value,
    round(value / sumIf(value, bucket = 'Mon-Thu')
                    OVER (PARTITION BY year), 3) AS ratio
FROM vdays
GROUP BY year, bucket
)
ORDER BY metric DESC, year, season DESC, bucket;
