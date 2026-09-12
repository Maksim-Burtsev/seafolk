-- S11 — the open dataset. Writes three Parquet products into dist/dataset/.
-- Run: scripts/export.sh          (which rm -rf's dist/dataset first, then
--                                  runs this file, then scripts/test_export.py)
--      scripts/ch.sh sql/70_export.sql   -- the queries ALONE. They overwrite
--        the files (TRUNCATE) but nothing verifies them, so dist/dataset is
--        then untested and scripts/publish.sh refuses it: the .tests-passed
--        marker is older than the files. Go through scripts/export.sh.
-- READ-ONLY against the store: reads `h3_hourly` (products a and b) and
-- `ferry_crossing` / `ferry_day` / `storm` (product c). Creates no table,
-- writes nothing into data/ch*.
--
-- WHAT IS WRITTEN
--   class_a_hourly_<year>.parquet   one file per LOADED year (2015, 2018,
--       2021, 2022, 2023, 2024, 2025, 2026). h3_hourly WHERE mobile =
--       'Class A' AND ship_group != 'leisure', res-7 cell x UTC hour x
--       ship_group. NO k FLOOR: a commercial Class A vessel is a public
--       transponder class (CLAUDE.md) and a one-vessel Class A cell-hour is a
--       ship that is required to broadcast.
--       CLASS A LEISURE IS EXCLUDED (2026-09-12, docs/DECISIONS.md). A pleasure
--       craft with a Class A transponder is a private boat with a better
--       radio: 337-467 such vessels a year, and 81-92 % of their cell-hours
--       hold a single vessel. They move to leisure_daily, under the floor.
--       Columns: h3 UInt64, hour DateTime (UTC), ship_group String,
--                msgs UInt64, vessels UInt64, moving_msgs UInt64,
--                mean_sog Nullable(Float64)
--   leisure_daily.parquet           the PRIVATE FLEET — every Class B
--       transponder OR any ship_group = 'leisure' whatever its class — res-5
--       parent cell x UTC DAY x ship_group, floored at vessels >= 5. Same
--       columns with `day Date` in place of `hour`. The OR is evaluated per
--       ROW, not per vessel: a vessel that reports Class B one day and Class A
--       another (28-958 a year) is under the floor on its Class B days
--       whatever its ship_group, and on its Class A days too when that group
--       is leisure (11-102 a year) — never unfloored as leisure.
--   ferry_daily.parquet             block 1 of sql/41_ferry_daily.sql, one row
--       per (named line, local day). Ferries are public and may be named.
--
-- PRIVACY, and this is the whole point of the file.
--   * `h3_hourly.vessels` is an AggregateFunction(uniqExact, UInt32) state
--     that keeps the hashed MMSI values themselves, which makes it a
--     membership oracle over Danish MMSIs (sql/01_schema.sql's PRIVACY note).
--     It is exported ONLY as uniqExactMerge(vessels), a plain number. THE
--     STATE COLUMN NEVER REACHES A FILE — no `SELECT *` appears below.
--   * `leisure_daily` is the ONLY private-fleet product. The res-7 HOURLY
--     layer is NEVER exported, at any k (docs/DECISIONS.md 2026-08-30):
--     measured over the whole store it would keep 7.2 % of cell-hours and
--     20.0 % of the moving messages under k >= 5 (its Class B part alone:
--     7.1 % and 20.8 %), so it is both unpublishable and useless.
--     Res 5 / daily keeps 23.60 % of cell-days and 82.03 % of the
--     moving messages (1 445 495 cell-days, 341 092 survive; 2026-09-12).
--   * No column named mmsi, name, callsign or imo is emitted anywhere here;
--     scripts/test_export.py re-checks that against the written files.
--
-- WHY GROUP BY AND NOT A PLAIN SELECT. h3_hourly is an AggregatingMergeTree:
-- its parts are merged in the background and there is no guarantee that one
-- (h3, hour, mobile, ship_group) key lives in exactly one part. A plain SELECT
-- would emit the same cell-hour twice with the counts split between the rows.
-- Every statement below therefore re-aggregates with sum() / uniqExactMerge().
-- (On the store as loaded the parts happen to be fully merged — raw count()
-- equals the grouped count for all eight years — which is exactly why this is
-- stated rather than trusted.)
--
-- WHY moving_msgs AND NOT moving_share. `moving_msgs / msgs` is one division
-- the reader can do; a share cannot be re-aggregated by a consumer who rolls
-- several cells or hours together, while two counts can. And `msgs` and
-- `moving_msgs` are NOT comparable across 2015-09 or across 2023 (findings
-- 58-59, docs/STATUS.md) — shipping the raw counts keeps that visible instead
-- of baking a ratio out of two numbers of different provenance.
--
-- mean_sog = sog_sum / moving_msgs is the mean speed MADE GOOD (sog_sum is
-- summed over moving messages only, sql/01_schema.sql) and is NULL, not 0,
-- where nothing moved in the cell.
--
-- TRUNCATE on INTO OUTFILE is supported by clickhouse local (checked on
-- 26.7.5.10) so this file overwrites rather than erroring — which is a
-- convenience, not a licence to run it on its own (see Run, above).
-- Paths are relative to the repo root, which is scripts/ch.sh's cwd.
--
-- RUN TIME, /usr/bin/time -p on an APFS clone of the store (data/ch_a):
--   real 51.43  user 364.15  sys 25.19        (the eight Class A years dominate)


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2015
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2015
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2015.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2018
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2018
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2018.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2021
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2021
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2021.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2022
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2022
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2022.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2023
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2023
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2023.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2024
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2024
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2024.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2025
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2025
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2025.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- CLASS A, RES 7, HOURLY — 2026
-- ====================================================================
SELECT h3,
       hour,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class A' AND ship_group != 'leisure' AND toYear(hour) = 2026
GROUP BY h3, hour, ship_group
ORDER BY hour, h3, ship_group
INTO OUTFILE 'dist/dataset/class_a_hourly_2026.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- THE PRIVATE FLEET (Class B OR ship_group = 'leisure'), RES 5, DAILY.
-- `vessels` is merged from the per-hour states over the WHOLE cell-day, never
-- summed: a boat seen in eight hours of a day is one vessel, and summing the
-- hourly head counts would inflate it eightfold and let a single-vessel
-- cell-day read as 8 and clear the floor.
-- HAVING vessels >= 5 is the privacy floor (CLAUDE.md); it is asserted again
-- on the written file by scripts/test_export.py.
-- The OR is what makes this the private fleet and not just Class B: a leisure
-- ship_group is private whatever transponder it carries, and no unfloored row
-- with ship_group = 'leisure' exists anywhere in the export.
-- ====================================================================
SELECT h3ToParent(h3, 5)           AS h3,
       toDate(hour)                AS day,
       CAST(ship_group AS String)  AS ship_group,
       sum(msgs)                   AS msgs,
       uniqExactMerge(vessels)     AS vessels,
       sum(moving_msgs)            AS moving_msgs,
       if(moving_msgs = 0, NULL, sum(sog_sum) / moving_msgs) AS mean_sog
FROM h3_hourly
WHERE mobile = 'Class B' OR ship_group = 'leisure'
GROUP BY h3, day, ship_group
HAVING vessels >= 5     -- `vessels` here is the ALIAS above, the merged count
ORDER BY day, h3, ship_group
INTO OUTFILE 'dist/dataset/leisure_daily.parquet' TRUNCATE FORMAT Parquet;


-- ====================================================================
-- FERRY LINES, DAILY — block 1 of sql/41_ferry_daily.sql, copied VERBATIM
-- (lines 149-266 of that file) with only the INTO OUTFILE clause added.
-- clickhouse local has no cross-statement scope and will not share a CTE
-- chain between files, so a copy is the only option — the same one S9 and S10
-- took. Diff against sql/41 block 1 when either changes:
--   diff <(sed -n '149,266p' sql/41_ferry_daily.sql) \
--        <(sed -n '/^-- FERRY LINES, DAILY/,$p' sql/70_export.sql | sed -n '/^WITH$/,/^SETTINGS/p' | sed '$d')
-- Ferries are public: this block emits line names and no MMSI (sql/41's own
-- privacy note applies unchanged).
-- ====================================================================
WITH
-- --- observed crossings per line-day --------------------------------
obs AS (
    SELECT line, kind, island,
           toDate(toTimeZone(dep, 'Europe/Copenhagen')) AS day,
           count()            AS crossings,
           uniqExact(mmsi)    AS vessels,
           uniqExact(route_id) AS routes
    FROM ferry_crossing
    WHERE line != ''
    GROUP BY line, kind, island, day
),
-- --- the coverage denominator ---------------------------------------
-- own-majority: one line per (vessel, year), the one it worked most.
-- tuple(c, line) breaks a tie on the line name so the table is reproducible.
per_line AS (
    SELECT mmsi, toYear(toTimeZone(dep, 'Europe/Copenhagen')) AS year, line,
           count() AS c
    FROM ferry_crossing
    WHERE line != ''
    GROUP BY mmsi, year, line
),
own AS (
    SELECT mmsi, year, argMax(line, tuple(c, line)) AS line
    FROM per_line GROUP BY mmsi, year
),
cover AS (
    SELECT o.line AS line, f.day AS day,
           sum(f.positions) AS fleet_positions,
           sum(f.sog_known) AS fleet_sog_known,
           sum(f.moving)    AS fleet_moving,
           count()          AS fleet_vessels_reporting
    FROM own AS o
    INNER JOIN ferry_day AS f ON f.mmsi = o.mmsi AND toYear(f.day) = o.year
    GROUP BY line, day
),
-- --- the day domain -------------------------------------------------
loaded AS (SELECT DISTINCT day FROM ferry_day),
cov AS (
    SELECT DISTINCT toDate(toTimeZone(dep, 'Europe/Copenhagen')) AS day
    FROM ferry_crossing
    WHERE line != ''
      AND toDate(toTimeZone(dep, 'Europe/Copenhagen')) IN (SELECT day FROM loaded)
),
span AS (
    SELECT line, kind, island, toYear(day) AS year, min(day) AS d0, max(day) AS d1
    FROM obs
    GROUP BY line, kind, island, year
),
-- CROSS JOIN, not a range join: ClickHouse has no non-equi JOIN, and this is
-- ~1 200 spans x ~2 100 days = 2.5 M candidate pairs, which costs nothing.
dom AS (
    SELECT s.line AS line, s.kind AS kind, s.island AS island,
           s.year AS year, cov.day AS day
    FROM span AS s CROSS JOIN cov
    WHERE cov.day >= s.d0 AND cov.day <= s.d1
),
-- --- storm days, as CALENDAR dates ----------------------------------
-- NO TIMEZONE CONVERSION. Every window in data/context/storms.csv is a whole
-- UTC day standing for a calendar date — `00:00:00` to `23:59:59` — so
-- toTimeZone('Europe/Copenhagen') pushes the end into the following local day
-- and widens every storm by one: 59 local days were flagged for 35 calendar
-- dates. The dates are read as dates. S9 MUST USE THIS SAME RULE.
storm_day AS (
    SELECT DISTINCT arrayJoin(arrayMap(
               i -> toDate(start_utc) + i,
               range(toUInt32(dateDiff('day', toDate(start_utc), toDate(end_utc))) + 1))) AS day
    FROM storm
),
-- --- the zero-filled panel ------------------------------------------
panel AS (
    SELECT d.line AS line, d.kind AS kind, d.island AS island,
           d.day AS day, d.year AS year,
           if(toMonth(d.day) BETWEEN 5 AND 9, 'may-sep', 'oct-apr') AS season,
           multiIf(toDayOfWeek(d.day) = 6, 'sat',
                   toDayOfWeek(d.day) = 7, 'sun', 'weekday')        AS daytype,
           toDayOfWeek(d.day)                                       AS dow,
           o.crossings AS crossings,
           o.vessels   AS vessels,
           o.routes    AS routes,
           c.fleet_positions          AS fleet_positions,
           c.fleet_sog_known          AS fleet_sog_known,
           c.fleet_moving             AS fleet_moving,
           c.fleet_vessels_reporting  AS fleet_vessels_reporting
    FROM dom AS d
    LEFT JOIN obs   AS o ON o.line = d.line AND o.day = d.day
    LEFT JOIN cover AS c ON c.line = d.line AND c.day = d.day
),
base AS (
    SELECT line, year, season, dow,
           quantileExactLow(0.5)(crossings) AS baseline
    FROM panel
    WHERE fleet_positions > 0
    GROUP BY line, year, season, dow
)
SELECT p.line                                AS line,
       p.kind                                AS kind,
       p.island                              AS island,
       p.day                                 AS day,
       p.year                                AS year,
       p.season                              AS season,
       p.daytype                             AS daytype,
       p.dow                                 AS dow,
       p.crossings                           AS crossings,
       p.vessels                             AS vessels,
       p.routes                              AS routes,
       toUInt32(b.baseline)                  AS baseline,
       greatest(toInt64(b.baseline) - toInt64(p.crossings), 0) AS missed,
       toUInt8(p.day IN (SELECT day FROM storm_day))           AS is_storm_day,
       p.fleet_positions                     AS fleet_positions,
       p.fleet_sog_known                     AS fleet_sog_known,
       p.fleet_moving                        AS fleet_moving,
       p.fleet_vessels_reporting             AS fleet_vessels_reporting
FROM panel AS p
LEFT JOIN base AS b
       ON b.line = p.line AND b.year = p.year
      AND b.season = p.season AND b.dow = p.dow
ORDER BY line, day
SETTINGS join_use_nulls = 0
INTO OUTFILE 'dist/dataset/ferry_daily.parquet' TRUNCATE FORMAT Parquet;
