-- S4 — the daily coverage reference: how much of what changes day to day is
-- the sea, and how much is the receivers.
-- Run: scripts/ch.sh sql/13_coverage_daily.sql
-- Columns: day, class_a_vessels, class_a_vessels_7d, class_a_msgs,
--          class_b_vessels, rows_read, pct_out_of_bbox, pct_non_vessel
--
-- Class A is the instrument, not the subject. A commercial fleet does not
-- change size with the weather or the season the way the leisure fleet does
-- (S3: leisure moves 32x between January and July, Class A barely moves), so a
-- step in class_a_vessels is a step in *reception*, not in traffic. S10 turns
-- this into the essay's honesty paragraph; S4 only has to make it queryable.
--
-- pct_out_of_bbox is the second half of the same question and comes from
-- load_log, not from the aggregates — by the time a row is in h3_hourly it has
-- already passed the bbox filter. It ranged from 55 rows to 4.70 % across S3's
-- 92 days, a swing that would read as a change in traffic if it were not
-- reported. See docs/DECISIONS.md, 2026-08-29 (S1).
--
-- The 7-day mean is partitioned by month so it does not average across the
-- holes an incomplete archive leaves; drop the PARTITION BY once the daily era
-- is loaded end to end.
SELECT
    v.day                                       AS day,
    v.class_a_vessels                           AS class_a_vessels,
    round(avg(v.class_a_vessels) OVER (PARTITION BY toYYYYMM(v.day)
          ORDER BY v.day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS class_a_vessels_7d,
    v.class_a_msgs                              AS class_a_msgs,
    v.class_b_vessels                           AS class_b_vessels,
    l.rows_read                                 AS rows_read,
    round(100 * l.rows_out_of_bbox / l.rows_read, 3) AS pct_out_of_bbox,
    round(100 * l.rows_non_vessel  / l.rows_read, 2) AS pct_non_vessel
FROM (
    SELECT day,
           uniqExactIf(mmsi, mobile = 'Class A') AS class_a_vessels,
           sumIf(msgs,       mobile = 'Class A') AS class_a_msgs,
           uniqExactIf(mmsi, mobile = 'Class B') AS class_b_vessels
    FROM vessel_day
    GROUP BY day
) AS v
LEFT JOIN (
    -- one row per loaded day; a monthly file would cover many, so take the
    -- file's own range rather than assuming one file is one day
    SELECT toDate(ts_min) AS day, any(rows_read) AS rows_read,
           any(rows_out_of_bbox) AS rows_out_of_bbox, any(rows_non_vessel) AS rows_non_vessel
    FROM load_log GROUP BY day
) AS l USING (day)
ORDER BY day;
