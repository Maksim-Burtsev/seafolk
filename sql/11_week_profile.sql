-- S3 chart 2 — the weekday effect, per group.
-- Run: scripts/ch.sh sql/11_week_profile.sql
-- Columns: month, ship_group, mobile, dow, days, mean_moving, share_of_week
--   dow: 1 = Monday … 7 = Sunday, in Europe/Copenhagen.
--
-- Activity is `moving_msgs`, not distinct vessels: h3_hourly's `vessels` state
-- counts every vessel in a cell-hour whether it moved or not, and a distinct
-- *moving* vessel count is not recoverable from it. Class A and Class B report
-- at different rates, so the message counts are not comparable BETWEEN groups —
-- `share_of_week` normalises each group against itself, which is what a shape
-- comparison needs.
--
-- Averaged per OCCURRENCE of the weekday, never summed: a month holds four of
-- some weekdays and five of others, and a raw sum would draw that calendar
-- accident as a weekly rhythm.
--
-- Weekday is taken in local time. The archive is UTC (S1) and a Saturday is a
-- Saturday on shore, not in UTC.
WITH
-- UTC+1/+2 means the first local day of a loaded block is missing its first one
-- or two hours, and a straggler local day holds only those hours. Both would
-- bias an hour-of-day or weekday average. Keep local days whose 24 hours are all
-- present — self-adjusting, no hardcoded month edges.
covered AS (
    SELECT toDate(toTimeZone(hour, 'Europe/Copenhagen')) AS lday
    FROM h3_hourly
    GROUP BY lday
    HAVING uniqExact(toHour(toTimeZone(hour, 'Europe/Copenhagen'))) = 24
),
local AS (
    SELECT toDate(toTimeZone(hour, 'Europe/Copenhagen')) AS lday,
           ship_group, mobile, moving_msgs
    FROM h3_hourly
    WHERE toDate(toTimeZone(hour, 'Europe/Copenhagen')) IN (SELECT lday FROM covered)
)
SELECT
    toYYYYMM(lday)       AS month,
    ship_group,
    mobile,
    toDayOfWeek(lday)    AS dow,
    uniqExact(lday)      AS days,
    round(sum(moving_msgs) / days) AS mean_moving,
    round(mean_moving / sum(mean_moving) OVER (PARTITION BY month, ship_group, mobile), 4) AS share_of_week
FROM local
GROUP BY month, ship_group, mobile, dow
ORDER BY month, ship_group, mobile, dow;
