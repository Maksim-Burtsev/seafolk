-- S3 chart 1 — the leisure season, day by day.
-- Run: scripts/ch.sh sql/10_season_daily.sql
-- Columns: day, mobile, present, active, active_7d
--
-- `present` is every leisure vessel that reported a position inside the Danish
-- bbox that day. `active` is those that actually moved. The distinction is not
-- cosmetic: on 2025-07-16, 1 457 of 4 554 leisure vessel-days (32 %) never
-- exceed 0.5 kn — a transponder left on in the marina is not a boat out
-- sailing, and the essay has to say which of the two it means.
--
-- This replaces the "minimum message count" S2 asked S3 to pick. A msgs >= N
-- filter was measured on 2025-07-16 and is the wrong lever: at N = 100 it drops
-- 19.2 % of vessels but only 0.72 % of the moving messages, and the median
-- dist_nm of what it drops is 0 at every N. It only ever removes boats that did
-- not move, so `moving_msgs > 0` says it directly. See docs/DECISIONS.md.
--
-- The 7-day mean is PARTITIONed by month because phase 0 loads three separate
-- months: ROWS BETWEEN 6 PRECEDING over the raw day order would drag January
-- into July across the hole. S6 does the real season-bounds query on a
-- continuous archive.
--
-- Both classes are reported. ship_group = 'leisure' is Sailing + Pleasure
-- regardless of Type of mobile, and a little over 100 of those are Class A
-- (large yachts, sail training ships). The private leisure fleet the project is
-- about is the Class B line.
SELECT
    day,
    mobile,
    uniqExact(mmsi)                    AS present,
    uniqExactIf(mmsi, moving_msgs > 0) AS active,
    round(avg(active) OVER (PARTITION BY mobile, toYYYYMM(day)
                            ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS active_7d
FROM vessel_day
WHERE ship_group = 'leisure'
GROUP BY day, mobile
ORDER BY mobile, day;
