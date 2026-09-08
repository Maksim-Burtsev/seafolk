-- S6 chart 1 — where the leisure season starts and ends, per year.
-- Run: scripts/ch.sh sql/20_season_bounds.sql
-- Columns: year, days, first_day, last_day, censored,
--          peak_7d, peak_day,
--          start_25, end_25, len_25, start_50, end_50, len_50
--
-- The daily series is `distinct Class B leisure vessels that MOVED that day`
-- (moving_msgs > 0 — the S3 decision, see sql/10_season_daily.sql: a
-- transponder left on in the marina is not a boat out sailing). Counted from
-- vessel_day, which is the per-vessel-day grain; h3_hourly cannot answer it
-- because a distinct *moving* vessel count is not recoverable from its
-- uniqExact state.
--
-- The 7-day mean is TRAILING and continuous within the year — one partition per
-- year, not per month as sql/10_season_daily.sql had to do when only three
-- separate months were loaded. Verified before writing this file: every
-- calendar day inside each year's loaded range has at least one moved Class B
-- leisure vessel (min 12 vessels, on a January day in 2015), so the day rows are
-- contiguous and a ROWS window is a true 7-calendar-day window. The first six
-- days of each range are dropped from the bound search (`cnt = 7`) so a mean
-- taken over 1-6 days can never define a season edge.
--
-- Years with < 200 loaded days are excluded: 2022 and 2023 hold 59 days each,
-- both windows in winter, and a "season" computed from them would be an
-- artefact. The threshold is 200 and not 300 on purpose: 2026 holds 238 days
-- (Jan 1 - Aug 26), which covers the whole rise and the peak and is exactly the
-- right-censored case the `censored` column exists to label. 300 would have
-- dropped it silently.
--
-- `censored` is derived from the data, never from a year list: 'start' when the
-- first loaded day is after Jan 7 (2024 — the daily archive begins 2024-03-01),
-- 'end' when the last is before Dec 24 (2026 — the archive ends 2026-08-26).
-- A censored bound is a floor on the season length, not a measurement: 2026's
-- end_25 / end_50 are wherever the data stopped, and 2024's peak is real (July)
-- but its start_25 may be earlier than March.
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
-- Message counts are NOT used here, so the Sep-2015 upstream duplication
-- (docs/STATUS.md § S4-tails) does not touch this query: it inflates msgs by
-- ~2.3x for 2015-08-28..09-30 and leaves distinct-vessel counts untouched.
WITH
daily AS (
    SELECT toYear(day)                     AS year,
           day,
           uniqExactIf(mmsi, moving_msgs > 0) AS moved
    FROM vessel_day
    WHERE mobile = 'Class B' AND ship_group = 'leisure'
    GROUP BY year, day
),
full_years AS (
    SELECT year FROM daily GROUP BY year HAVING count() >= 200
),
smoothed AS (
    SELECT year, day, moved,
           avg(moved) OVER w AS m7,
           count()    OVER w AS cnt
    FROM daily
    WHERE year IN (SELECT year FROM full_years)
    WINDOW w AS (PARTITION BY year ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
),
peaks AS (
    SELECT year,
           count()                     AS days,
           min(day)                    AS first_day,
           max(day)                    AS last_day,
           maxIf(m7, cnt = 7)          AS peak_7d,
           argMaxIf(day, m7, cnt = 7)  AS peak_day
    FROM smoothed
    GROUP BY year
)
SELECT
    p.year                                        AS year,
    p.days                                        AS days,
    p.first_day                                   AS first_day,
    p.last_day                                    AS last_day,
    multiIf(p.first_day > makeDate(p.year, 1, 7)
                AND p.last_day < makeDate(p.year, 12, 24), 'start,end',
            p.first_day > makeDate(p.year, 1, 7),  'start',
            p.last_day  < makeDate(p.year, 12, 24), 'end',
                                                    '') AS censored,
    round(p.peak_7d, 1)                           AS peak_7d,
    p.peak_day                                    AS peak_day,
    minIf(s.day, s.cnt = 7 AND s.m7 >= 0.25 * p.peak_7d) AS start_25,
    maxIf(s.day, s.cnt = 7 AND s.m7 >= 0.25 * p.peak_7d) AS end_25,
    toInt32(end_25 - start_25) + 1                AS len_25,
    minIf(s.day, s.cnt = 7 AND s.m7 >= 0.50 * p.peak_7d) AS start_50,
    maxIf(s.day, s.cnt = 7 AND s.m7 >= 0.50 * p.peak_7d) AS end_50,
    toInt32(end_50 - start_50) + 1                AS len_50
FROM smoothed AS s
INNER JOIN peaks AS p ON s.year = p.year
GROUP BY p.year, p.days, p.first_day, p.last_day, p.peak_7d, p.peak_day
ORDER BY year;
