-- S6 chart 4 — how far a leisure boat actually goes, and how close to home.
-- Run: scripts/ch.sh sql/23_radius.sql
-- Columns: year, days, vessel_days, share_idle, moved_days,
--          p25, p50, p75, p90, p99, share_lt_5nm, share_ge_30nm,
--          share_home_in_marina_cell, share_home_near_marina
--
-- One row per calendar year, Class B leisure only. `days` is the number of
-- calendar days the archive holds for that year, so a partial year is visible
-- rather than silently comparable: 2022 and 2023 hold 59 days each (winter
-- only — read their numbers as a winter sample, not as a year), 2024 starts
-- 2024-03-01, 2026 ends 2026-08-26.
--
--   share_idle    share of vessel-days with moving_msgs = 0 — a transponder
--                 that reported all day without the boat ever exceeding 0.5 kn.
--                 The S3 decision (docs/DECISIONS.md): this is the marina, not
--                 a trip, and it is a third of the summer fleet.
--   p25..p99      quantiles of dist_nm over MOVED vessel-days only (idle days
--                 are all 0 and would drag every quantile down). dist_nm is
--                 distance made good while moving, with the four guards in
--                 sql/03_aggregate.sql; quantilesExact, not the sampling
--                 quantile, so the numbers are reproducible byte for byte.
--   share_lt_5nm  moved vessel-days under 5 nm — an afternoon in the bay.
--   share_ge_30nm moved vessel-days of 30 nm or more — a real crossing.
--   share_home_in_marina_cell
--                 share of ALL vessel-days (idle included) whose home_h3 — the
--                 res-7 cell of the FIRST position of the day — is EXACTLY the
--                 res-7 cell of some marina (ring 0, ~5 km²). This is the
--                 column to read. Its ring-1 sibling below turned out to be
--                 saturated — 92 % in every year — because at res 7 a marina
--                 plus its six neighbours is ~15 km across and the union of
--                 2 833 of those covers most of the Danish coast, so the
--                 measure stopped separating anything.
--   share_home_near_marina
--                 the same share over h3kRing(marina.h3, 1) — the marina cell
--                 plus its six neighbours. Kept for continuity and as the
--                 evidence that ring 1 is the wrong radius; do not quote it as
--                 "started the day at a marina". `land` is deliberately NOT
--                 used for either column: Natural Earth 10 m generalises the
--                 coast ~1 km inland and reads 28 % of marina cell centres as
--                 water (docs/STATUS.md § S5).
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
-- vessel_day is a ReplacingMergeTree, so a double-loaded file could in
-- principle leave two rows for one (day, mmsi) and bias every count here.
-- Checked before writing this file: count() = uniqExact(day, mmsi) =
-- 8 843 467, exact, so no FINAL is needed and none is paid for.
--
-- Message counts are not used, so the Sep-2015 duplication (docs/STATUS.md
-- § S4-tails) does not reach this query. It inflates msgs; moving_msgs > 0 is a
-- yes/no that duplication cannot flip, and dist_nm drops same-second duplicate
-- steps by its >= 1 s guard.
--
-- PRIVACY: vessel_day holds MMSI. Nothing below groups by it or emits it —
-- every output row is a whole-year aggregate over thousands of vessel-days.
WITH
-- every marina cell and its six neighbours, built once (2 833 marinas)
marina_ring AS (
    SELECT DISTINCT arrayJoin(h3kRing(h3, 1)) AS h3 FROM marina
),
marina_cell AS (
    SELECT DISTINCT h3 FROM marina
),
vd AS (
    SELECT toYear(day)  AS year,
           day,
           moving_msgs > 0 AS moved,
           dist_nm,
           home_h3 IN (SELECT h3 FROM marina_cell) AS in_marina,
           home_h3 IN (SELECT h3 FROM marina_ring) AS near_marina
    FROM vessel_day
    WHERE mobile = 'Class B' AND ship_group = 'leisure'
)
SELECT
    year,
    days,
    vessel_days,
    round(share_idle, 4)                    AS share_idle,
    moved_days,
    round(q[1], 2)                          AS p25,
    round(q[2], 2)                          AS p50,
    round(q[3], 2)                          AS p75,
    round(q[4], 2)                          AS p90,
    round(q[5], 2)                          AS p99,
    round(lt5  / moved_days, 4)             AS share_lt_5nm,
    round(ge30 / moved_days, 4)             AS share_ge_30nm,
    round(inmarina, 4)                      AS share_home_in_marina_cell,
    round(near, 4)                          AS share_home_near_marina
FROM
(
    SELECT
        year,
        uniqExact(day)                  AS days,
        count()                         AS vessel_days,
        1 - avg(moved)                  AS share_idle,
        countIf(moved)                  AS moved_days,
        quantilesExactIf(0.25, 0.50, 0.75, 0.90, 0.99)(dist_nm, moved) AS q,
        countIf(moved AND dist_nm <  5)  AS lt5,
        countIf(moved AND dist_nm >= 30) AS ge30,
        avg(in_marina)                  AS inmarina,
        avg(near_marina)                AS near
    FROM vd
    GROUP BY year
)
ORDER BY year;
