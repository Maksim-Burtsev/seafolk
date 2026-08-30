-- S3 chart 3 — the shape of a day, per group, weekday vs Saturday.
-- Run: scripts/ch.sh sql/12_day_profile.sql
-- Columns: month, ship_group, mobile, daytype, lhour, moving_msgs, share_of_day
--   daytype: 'weekday' (Mon-Fri) | 'sat' | 'sun'
--   lhour:   hour of day in Europe/Copenhagen, 0-23
--
-- Same two caveats as sql/11_week_profile.sql, for the same reasons: activity is
-- `moving_msgs` because a distinct moving-vessel count is not recoverable from
-- h3_hourly's `vessels` state, and `share_of_day` normalises each group against
-- itself because Class A and Class B report at different rates. Only the SHAPE
-- of two curves may be compared, never their heights.
--
-- Local time is the whole point of this chart: the archive is UTC (S1) and
-- "when do people go out" is a question about the clock on the wall. The
-- conversion is DST-correct because it is done by timezone name, not by an
-- offset — July is UTC+2 and January UTC+1.
WITH
covered AS (
    SELECT toDate(toTimeZone(hour, 'Europe/Copenhagen')) AS lday
    FROM h3_hourly
    GROUP BY lday
    HAVING uniqExact(toHour(toTimeZone(hour, 'Europe/Copenhagen'))) = 24
),
local AS (
    SELECT toTimeZone(hour, 'Europe/Copenhagen') AS lt,
           ship_group, mobile, moving_msgs
    FROM h3_hourly
    WHERE toDate(toTimeZone(hour, 'Europe/Copenhagen')) IN (SELECT lday FROM covered)
)
SELECT
    toYYYYMM(lt)  AS month,
    ship_group,
    mobile,
    multiIf(toDayOfWeek(lt) = 6, 'sat', toDayOfWeek(lt) = 7, 'sun', 'weekday') AS daytype,
    toHour(lt)    AS lhour,
    sum(moving_msgs) AS moving_msgs,
    round(moving_msgs / sum(moving_msgs) OVER (PARTITION BY month, ship_group, mobile, daytype), 5) AS share_of_day
FROM local
GROUP BY month, ship_group, mobile, daytype, lhour
ORDER BY month, ship_group, mobile, daytype, lhour;
