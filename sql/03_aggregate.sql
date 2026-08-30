-- S2 — turn the staged file into the three permanent tables.
-- Run with: scripts/ch.sh sql/03_aggregate.sql   (after sql/02_stage.sql)
--
-- All three read `ais_clean`, the view in sql/01_schema.sql, so they cannot
-- drift apart on which rows count or which group a vessel is in.
-- scripts/load.sh deletes the file's date range from all three tables before
-- running this, so re-running a file replaces its contribution.

-- 0. Resolve one identity per vessel-day, before ais_clean is readable.
--
-- Ship type: a vessel reports several values in a day — position messages
-- often say 'Undefined' while static messages carry the real type. Prefer any
-- classified value over 'Undefined', latest wins among those. Both fields come
-- from ONE argMax over a tuple, so they are read off the same row.
--
-- Type of mobile: 354 of 3 402 vessels on 2025-01-15 reported BOTH classes in
-- one day. This is the privacy key, so it is NOT resolved by majority or by
-- recency: a vessel that reports Class B even once is Class B for that day.
-- The asymmetry is the point — mislabelling a public ferry as private costs a
-- row in public_track, mislabelling a private boat as public publishes its
-- track. Only one of those is recoverable.
TRUNCATE TABLE ais_vessel_stage;

INSERT INTO ais_vessel_stage
SELECT
    day,
    mmsi,
    if(countIf(mobile = 'Class B') > 0, 'Class B', 'Class A')  AS safe_mobile,
    argMax((ship_type, grp), (ship_type != 'Undefined', ts)).1 AS best_type,
    argMax((ship_type, grp), (ship_type != 'Undefined', ts)).2 AS best_group
FROM (
    SELECT day, mmsi, ts, mobile, ship_type,
           multiIf(ship_type IN ('Sailing', 'Pleasure'), 'leisure',
                   ship_type = 'Passenger',             'passenger',
                   ship_type IN ('Cargo', 'Tanker'),    'cargo',
                   ship_type = 'Fishing',               'fishing',
                                                        'other') AS grp
    FROM ais_rows
)
GROUP BY day, mmsi;

-- 1. h3_hourly — the public grain: 5 km2 cell x hour x class x group.
INSERT INTO h3_hourly
SELECT
    geoToH3(lon, lat, 7)     AS h3,        -- (lon, lat), NOT (lat, lon); a swap
    toStartOfHour(ts)        AS hour,      -- is silent and lands the fleet in
    mobile,                                -- Kazakhstan. test_load.sh asserts it.
    ship_group,
    count()                  AS msgs,
    uniqExactState(mmsi)     AS vessels,
    countIf(moving)          AS moving_msgs,
    toFloat64(sumIf(sog, moving)) AS sog_sum
FROM ais_clean
GROUP BY h3, hour, mobile, ship_group;

-- 2. vessel_day — internal, holds MMSI. One row per vessel per day.
--
-- dist_nm is the distance covered WHILE MOVING. Each step between consecutive
-- positions is counted only if all four guards pass, and each guard is there
-- for a defect that is actually in the archive:
--   ts - pts BETWEEN 1 AND 3600  the first row of a window (lagInFrame returns
--                                1970 and (0, 0), so the step would be the
--                                distance from the Gulf of Guinea to Denmark),
--                                reception gaps, and duplicate same-second
--                                messages (division by zero).
--   implied speed <= 25.7 m/s    (50 kn) GPS teleports.
--   both ends moving             jitter at anchor: ~10 m a step over a day of
--                                3-minute reports is ~2.6 nm of fiction.
--   sog < 100 (via `moving`)     the 102.3 "not available" sentinel.
--
-- Measured on the full 2025-07-16, fleet total in nm — each guard earns its
-- place, and the first row is deliberately guarded twice:
--   all guards 185 591 | no anchor guard 189 634 (+2.2 %)
--   no time guard 194 392 (+4.7 %) | no teleport guard 195 042 (+5.1 %)
--   no guards at all 26 395 719 (142x — the phantom first step, every vessel)
INSERT INTO vessel_day
    (day, mmsi, mobile, ship_type, ship_group, first_ts, last_ts,
     msgs, moving_msgs, dist_nm, home_h3, length)
SELECT
    day,
    mmsi,
    -- all three are constant per (day, mmsi): resolved once in step 0
    any(mobile)                                 AS mobile,
    any(ship_type)                              AS best_type,
    any(ship_group)                             AS best_group,
    min(ts)                                     AS first_ts,
    max(ts)                                     AS last_ts,
    count()                                     AS msgs,
    countIf(moving)                             AS moving_msgs,
    sumIf(step_m, moving AND pmoving
                  AND ts - pts BETWEEN 1 AND 3600
                  AND step_m / (ts - pts) <= 25.7) / 1852 AS dist_nm,
    geoToH3(argMin(lon, ts), argMin(lat, ts), 7) AS home_h3,
    max(length)                                 AS length   -- static messages only
FROM (
    SELECT
        *,
        lagInFrame(ts)     OVER w                        AS pts,
        lagInFrame(moving) OVER w                        AS pmoving,
        geoDistance(lagInFrame(lon) OVER w, lagInFrame(lat) OVER w, lon, lat) AS step_m
    FROM ais_clean
    WINDOW w AS (PARTITION BY mmsi, day ORDER BY ts
                 ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
)
GROUP BY day, mmsi;

-- 3. public_track — Class A passenger ships only, one position per minute.
-- The mobile = 'Class A' filter is the privacy rule, not an optimisation:
-- Class B vessels reporting Ship type = 'Passenger' exist (2 164 rows in the
-- first 2 M rows of 2025-07-16 alone) and are private transponders.
-- ship_group here is the vessel-day value from step 0, not the per-message
-- one: filtering on the message dropped 1.93 % of ferry minutes entirely.
INSERT INTO public_track
SELECT
    mmsi,
    toStartOfMinute(ts) AS minute,
    argMin(lat, ts)     AS lat,
    argMin(lon, ts)     AS lon,
    argMin(sog, ts)     AS sog,
    argMax(name, ts)    AS name
FROM ais_clean
WHERE mobile = 'Class A' AND ship_group = 'passenger'
GROUP BY mmsi, minute;
