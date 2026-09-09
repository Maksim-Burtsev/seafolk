-- S8 — chapter 03's biggest caveat, measured: THE FLEET THIS CHAPTER CANNOT
-- SEE. `public_track` holds a vessel only on the days its resolved ship type
-- is 'Passenger'. On every other day the same ferry is invisible to
-- sql/40-43 — no position, no stay, no crossing, and no gap in any coverage
-- column, because the coverage columns are also built from `public_track`.
-- Run: scripts/ch.sh sql/44_hidden_fleet.sql  (read-only; 0.6 s, 1 780 rows)
-- Reads `ferry_crossing` (sql/40) and `vessel_day` (sql/03_aggregate.sql).
--
-- THIS IS A LOAD-TIME FACT, NOT A BUG IN THIS CHAPTER. sql/03_aggregate.sql
-- resolves ONE identity per vessel-day (a vessel does not report one identity
-- per message; see the long note in sql/01_schema.sql) and fills
-- `public_track` from Class A vessels whose resolved ship_group is
-- 'passenger'. A ferry that reported 'Undefined' — or 'HSC', which
-- sql/03 maps to ship_group 'other' — for a whole year is simply not in
-- `public_track` for that year. Fixing it means re-aggregating 2.3 TB, not
-- editing a query. What this file does is MEASURE the hole so that every
-- number in the chapter can be read as the lower bound it is.
--
-- EVERY LINE-YEAR WITH hidden_days > 0 IS A LOWER BOUND. The crossings sql/41
-- counts for that line in that year are the crossings made on the days the
-- vessel happened to be filed as a passenger ship. Named cases, from the
-- per-vessel block below:
--   M/F FENJA and MENJA (Esbjerg - Nordby, Fano) are 'Undefined' in EVERY
--     year, 361-365 days each, and never reach `public_track` at all. The
--     Fano line's crossings come entirely from its other tonnage.
--   PRINSESSE ISABELLA is 'Undefined' 284 days of 2021, which is why Hou -
--     Saelvig (Samso) reads blank from March to September 2021.
--   ANHOLT is 'HSC' all 365 days of 2015.
--   SLEIPNER-FUR is 'Undefined' for 28 days of 2023 — a February gap, not a
--     storm window — which is the "second Fur ferry that is not in the
--     archive". It shows on Hvalpsund - Sundsore and Feggesund, the two lines
--     it made matched crossings on.
-- Store-wide, over the fleet defined below, the hidden share of vessel-days
-- runs 13.03 / 12.40 / 14.03 / 13.16 / 17.52 / 16.12 / 16.08 / 13.62 % for
-- 2015 / 2018 / 2021 / 2022 / 2023 / 2024 / 2025 / 2026 — these are the
-- figures the SECOND BLOCK of this file emits, not a hand-carried estimate.
-- 342-494 fleet vessels a year, 166-358 of them with at least one hidden day.
--
-- THE FLEET IS DEFINED OVER ALL YEARS, AND IT HAS TO BE. A vessel that is
-- hidden for a whole year makes no crossing that year, so a fleet defined
-- per year would define the hole out of existence — the vessel would not be
-- expected and its absence would not be counted. The fleet of a line is
-- therefore every MMSI that made at least one MATCHED crossing on that line in
-- ANY year, and it is held fixed across every year of the archive. The cost is
-- the mirror error: a vessel that genuinely joined the line in 2024 is counted
-- as hidden for 2015, so a line's early hidden_days are an OVER-estimate in
-- exactly the way its crossings are an under-estimate. Read `fleet_vessels`
-- next to `hidden_vessels` before quoting a share.
--
-- A vessel-day is HIDDEN when `vessel_day.ship_group != 'passenger'`, and
-- VISIBLE when it equals 'passenger'. A day on which the vessel reported
-- nothing at all has no `vessel_day` row and is neither: it is not in
-- visible_days, not in hidden_days, and not in the denominator. That is
-- deliberate — this file measures MISFILING, not silence. Silence is sql/41's
-- `fleet_positions`.
--
-- PRIVACY. `vessel_day` and `ferry_crossing` both hold MMSI and NEITHER IS
-- EMITTED. The third block names VESSELS, which CLAUDE.md allows: ferries and
-- commercial vessels are public and `public_track` is Class A passenger only.
-- The name comes from `ferry_crossing.name`, the modal AIS name sql/40
-- resolved per MMSI-year, taken over every year because a fully hidden year
-- has no name of its own.
--
-- Three blocks:
--   1. per (line, year)          for every line with a line label
--   2. per year, store-wide      over the union of every line's fleet
--   3. per (vessel, year, line)  for the DANISH lines only (kind island or
--                                domestic), where a hidden vessel is a hole in
--                                a lifeline and not in a contrast case

WITH
fleet AS (
    SELECT line, min(kind) AS kind, min(island) AS island, mmsi,
           argMax(name, tuple(c, name)) AS name
    FROM (
        SELECT line, kind, island, mmsi, name, count() AS c
        FROM ferry_crossing WHERE line != '' AND name != ''
        GROUP BY line, kind, island, mmsi, name
    )
    GROUP BY line, mmsi
),
-- one row per (fleet membership, day the vessel reported anything)
vd AS (
    SELECT day, mmsi, min(ship_group) AS ship_group
    FROM vessel_day
    WHERE mmsi IN (SELECT mmsi FROM fleet)
    GROUP BY day, mmsi
),
fd AS (
    SELECT f.line AS line, f.kind AS kind, f.island AS island,
           f.mmsi AS mmsi, f.name AS name,
           toYear(v.day) AS year,
           v.ship_group AS ship_group
    FROM fleet AS f INNER JOIN vd AS v ON v.mmsi = f.mmsi
)
SELECT line,
       min(kind)                                          AS kind,
       min(island)                                        AS island,
       year,
       uniqExact(mmsi)                                    AS fleet_vessels,
       countIf(ship_group  = 'passenger')                 AS visible_days,
       countIf(ship_group != 'passenger')                 AS hidden_days,
       round(countIf(ship_group != 'passenger') / count(), 4) AS hidden_share,
       uniqExactIf(mmsi, ship_group != 'passenger')       AS hidden_vessels
FROM fd
GROUP BY line, year
ORDER BY line, year;


-- ====================================================================
-- SECOND BLOCK — store-wide per year, over the union of every line's fleet.
-- A vessel in two lines' fleets is counted ONCE here (uniqExact on the
-- vessel-day), which the per-line block above does not do.
-- ====================================================================
WITH
fleet AS (
    SELECT DISTINCT mmsi FROM ferry_crossing WHERE line != ''
),
vd AS (
    SELECT day, mmsi, min(ship_group) AS ship_group
    FROM vessel_day
    WHERE mmsi IN (SELECT mmsi FROM fleet)
    GROUP BY day, mmsi
)
SELECT toYear(day)                                        AS year,
       uniqExact(mmsi)                                    AS fleet_vessels,
       countIf(ship_group  = 'passenger')                 AS visible_days,
       countIf(ship_group != 'passenger')                 AS hidden_days,
       round(countIf(ship_group != 'passenger') / count(), 4) AS hidden_share,
       uniqExactIf(mmsi, ship_group != 'passenger')       AS hidden_vessels
FROM vd
GROUP BY year
ORDER BY year;


-- ====================================================================
-- THIRD BLOCK — the Danish lines, vessel by vessel and year by year, so the
-- note can name the ship instead of quoting a percentage. Only rows with at
-- least one hidden day are emitted. `dominant_hidden_type` is the `ship_type`
-- the vessel spent most of its hidden days filed as — 'Undefined' for a vessel
-- whose static message never arrived, 'HSC' for a fast ferry (which sql/03
-- maps to ship_group 'other' and so keeps out of `public_track` entirely).
-- ====================================================================
WITH
fleet AS (
    SELECT line, min(kind) AS kind, min(island) AS island, mmsi,
           argMax(name, tuple(c, name)) AS name
    FROM (
        SELECT line, kind, island, mmsi, name, count() AS c
        FROM ferry_crossing
        WHERE line != '' AND kind IN ('island', 'domestic') AND name != ''
        GROUP BY line, kind, island, mmsi, name
    )
    GROUP BY line, mmsi
),
vd AS (
    SELECT day, mmsi, min(ship_group) AS ship_group, min(ship_type) AS ship_type
    FROM vessel_day
    WHERE mmsi IN (SELECT mmsi FROM fleet)
    GROUP BY day, mmsi
),
hid AS (
    SELECT f.line AS line, f.kind AS kind, f.island AS island, f.name AS name,
           toYear(v.day) AS year, v.ship_type AS ship_type, count() AS days
    FROM fleet AS f INNER JOIN vd AS v ON v.mmsi = f.mmsi
    WHERE v.ship_group != 'passenger'
    GROUP BY line, kind, island, name, year, ship_type
)
SELECT name                                          AS vessel,
       year,
       line,
       min(kind)                                     AS kind,
       min(island)                                   AS island,
       sum(days)                                     AS hidden_days,
       argMax(ship_type, tuple(days, ship_type))     AS dominant_hidden_type
FROM hid
GROUP BY vessel, year, line
ORDER BY hidden_days DESC, vessel, year, line;
