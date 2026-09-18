-- site/season.html chart S2 — the summer week, one row per day of the week.
-- Run: scripts/ch.sh sql/81_site_season.sql
-- Columns: year, dow, day_name, days, mean_moved, min_moved, ratio_to_weekday
--
-- sql/21_weekend_effect.sql already measures the weekend, but only as two
-- buckets (Mon-Fri against Sat-Sun). The chapter page draws seven bars, so the
-- same measure is cut by day of the week here rather than by bucket. Nothing
-- else about it changes:
--
--   * the fleet is `mobile = 'Class B' AND ship_group = 'leisure'`;
--   * a vessel counts on a day only if it MOVED that day (moving_msgs > 0 —
--     the S3 decision in docs/DECISIONS.md: a transponder left on at the
--     pontoon is not a boat out sailing);
--   * `mean_moved` is averaged per OCCURRENCE of the weekday, never a raw sum:
--     a season holds a different number of Saturdays than of Tuesdays and a sum
--     would draw that calendar accident as a weekly rhythm;
--   * May-Sep only, because the winter week is a different animal (sql/21:
--     the winter weekend ratio runs 1.03-1.88 and is collapsing).
--
-- `ratio_to_weekday` is this weekday's mean over the year's Mon-Fri mean,
-- weighted by the number of occurrences — i.e. exactly sql/21's `weekday`
-- value for the same year and season, so the two files must agree: pooling
-- Sat and Sun here reproduces sql/21's weekend ratio (2025: 1.292).
--
-- `min_moved` is the smallest single-day count behind a bar. It exists for the
-- site's privacy gate: every published private-fleet number counts at least
-- five boats, and this column is the evidence that the bars are nowhere near
-- that floor (the minimum over all six years is in the hundreds).
--
-- CAVEAT — the weekday comes from vessel_day.day, which is a UTC date, so a
-- "Saturday" is the local window 01:00 Sat to 01:00 Sun (02:00 in summer) and
-- the first one to two local hours of each day are filed under the previous
-- weekday. sql/24_night.sql bounds the error: everything between 22:00 and
-- 05:00 local is 4.3-4.8 % of summer leisure movement in total, and the
-- misfilable slice is the 00:00-02:00 part of it. A local-day version would
-- mean re-cutting vessel_day, which is built on UTC days from raw archive
-- files that have been deleted.
--
-- Partial years stay in and are made visible through `days`: 2024 begins
-- 2024-03-01 (its May-Sep is whole), 2026 ends 2026-08-26 (its May-Sep is not,
-- and September is the quietest of the five months, so 2026's means read
-- high). 2022 and 2023 hold 59 winter days each and have no May-Sep row at all.
--
--
-- SHORT UTC DAYS ARE COUNTED WHOLE. Two of the 2 122 loaded days hold fewer than
-- 24 hours of h3_hourly — 2015-06-24 (21) and 2018-05-17 (20), receiver gaps in
-- the source — and this file counts them as ordinary days, like sql/20-sql/23.
-- What is counted is DISTINCT VESSELS, which a missing hour barely moves: a boat
-- out sailing reports in the other 20-odd hours too. Message counts are not
-- used, so the Sep-2015 upstream duplication (docs/STATUS.md § S4-tails) cannot
-- reach this query either — it inflates msgs, and moving_msgs > 0 is a yes/no
-- that a duplicated message cannot flip.
--
-- PRIVACY: vessel_day holds MMSI. Nothing below groups by it or emits it —
-- every output row is a mean over 44 to 66 whole days of the fleet.
WITH
daily AS (
    SELECT toYear(day)                        AS year,
           toDayOfWeek(day)                   AS dow,
           day,
           uniqExactIf(mmsi, moving_msgs > 0) AS moved
    FROM vessel_day
    WHERE mobile = 'Class B' AND ship_group = 'leisure'
      AND toMonth(day) BETWEEN 5 AND 9
    GROUP BY year, dow, day
)
SELECT
    year,
    dow,
    ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
     'Friday', 'Saturday', 'Sunday'][dow]  AS day_name,
    toUInt64(count())                      AS days,
    round(avg(moved), 1)                   AS mean_moved,
    min(moved)                             AS min_moved,
    round(mean_moved
          / (sumIf(mean_moved * days, dow <= 5) OVER (PARTITION BY year)
             / sumIf(days, dow <= 5) OVER (PARTITION BY year)), 3) AS ratio_to_weekday
FROM daily
GROUP BY year, dow
ORDER BY year, dow;
