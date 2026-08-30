-- S2 — the permanent schema. Idempotent: safe to run before every load.
-- Run with: scripts/ch.sh sql/01_schema.sql
--
-- Raw archive files are deleted right after they are aggregated (see
-- docs/DECISIONS.md, "stream-and-delete"), so anything not captured here is
-- lost until 2.3 TB is downloaded again. These tables are designed once.

-- One archive file at a time. Truncated by sql/02_stage.sql before every load,
-- so nothing here survives a run. Every CSV row is staged, including AtoN and
-- base stations and the lat=91 sentinel: the quality and scope filters are
-- applied in sql/03_aggregate.sql, which lets scripts/load.sh count what it
-- drops in one pass instead of re-reading the zip. S10 needs those counts.
CREATE TABLE IF NOT EXISTS ais_raw_stage
(
    ts        DateTime('UTC'),
    mmsi      UInt32,
    mobile    LowCardinality(String),
    lat       Float64,
    lon       Float64,
    sog       Float32,                 -- -1 where the CSV field is empty
    ship_type LowCardinality(String),
    name      String,
    length    UInt16,                  -- 0 where the CSV field is empty
    imo       UInt32                   -- 0 where the CSV says 'Unknown'
)
ENGINE = MergeTree
ORDER BY (mmsi, ts);

-- The single definition of "a row this project counts".
--   * mobile filter: 'Type of mobile' has eight values, only two are vessels.
--   * abs(lat) <= 90 is implied by the bbox and removes the lat=91 sentinel
--     (the only impossible coordinate in the archive — S1 finding 4).
--   * the bbox is a SCOPE decision, not a cleaning step: it drops real
--     southern-Baltic traffic (3.2 % of vessel rows on 2025-06-14 against
--     0.1 % on 2025-07-16). load_log.rows_out_of_bbox records how much, per
--     file, because S10 has to report it or a change in receiver reach will
--     read as a change in traffic.
--   * sog = -1 means the CSV field was empty; sog >= 100 is the AIS 102.3
--     "speed not available" sentinel (27-66 k rows/day). Neither is movement.
CREATE VIEW IF NOT EXISTS ais_rows AS
SELECT
    ts, toDate(ts) AS day, mmsi, mobile, lat, lon, sog, ship_type, name,
    length, imo,
    sog > 0.5 AND sog < 100 AS moving
FROM ais_raw_stage
WHERE mobile IN ('Class A', 'Class B')
  AND lat BETWEEN 53 AND 59
  AND lon BETWEEN 3 AND 17;

-- One resolved identity per vessel per day, filled by sql/03_aggregate.sql
-- before anything else reads ais_clean. Dropped with the raw stage.
--
-- This table exists because a vessel does NOT report one identity per day.
-- Measured inside the Danish bbox:
--   * Ship type varies within a vessel-day — position messages often say
--     'Undefined' while static messages carry the real type. On 2025-07-12,
--     of 4 884 Class B vessels 3 026 reported 'Undefined' AND something else,
--     so grouping on the per-message value put 2 950 vessels in two groups at
--     once and filed 96 156 leisure messages under 'other'. Of 298 Class A
--     vessels that ever say 'Passenger', 276 also say 'Undefined', and a
--     per-message filter dropped 1.93 % of their minutes from public_track.
--   * Type of mobile varies too: on 2025-01-15, 354 of 3 402 vessels (10.4 %)
--     reported BOTH 'Class A' and 'Class B'. That one is a privacy key, not a
--     grouping, so it is resolved in the safe direction — see below.
CREATE TABLE IF NOT EXISTS ais_vessel_stage
(
    day        Date,
    mmsi       UInt32,
    mobile     LowCardinality(String),
    ship_type  LowCardinality(String),
    ship_group LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY (day, mmsi);

-- What the three aggregate INSERTs read: countable rows carrying the identity
-- resolved for the whole vessel-day, so every table agrees on the grain.
-- `mobile` deliberately comes from the join, NOT from the row: the row-level
-- value is what would let one mislabelled message put a private vessel's
-- position into public_track.
-- The join is inner, and it cannot drop a row: ais_vessel_stage is built from
-- ais_rows itself. test_load.sh asserts that it does not.
CREATE VIEW IF NOT EXISTS ais_clean AS
SELECT
    r.ts AS ts, r.day AS day, r.mmsi AS mmsi,
    r.lat AS lat, r.lon AS lon, r.sog AS sog, r.name AS name,
    r.length AS length, r.imo AS imo, r.moving AS moving,
    v.mobile AS mobile, v.ship_type AS ship_type, v.ship_group AS ship_group
FROM ais_rows AS r
INNER JOIN ais_vessel_stage AS v ON r.day = v.day AND r.mmsi = v.mmsi;

-- The spatial grain everything downstream aggregates from. (Daily per-vessel
-- questions go to vessel_day; S3's leisure-season chart reads that, not this.)
--
-- PRIVACY: `vessels` is an exact uniqExact state, which keeps the hashed MMSI
-- values themselves — that is what makes it exact. Merging a guess into a
-- published state returns 1 for a hit and 2 for a miss, so a single-vessel
-- cell is a membership oracle over ~2 M Danish MMSIs (MID 219/220) and hands
-- back the boat. On 2025-07-16, 70.1 % of Class B cell-hours (59 027 of
-- 84 187) hold exactly one vessel. This is safe only because data/ch never
-- leaves the machine. **The state column itself must never cross an export
-- boundary — S11 exports uniqExactMerge(vessels) as a number, under k >= 5,
-- and never this column.**
--
-- `sog_sum` is summed over MOVING messages only, so sog_sum / moving_msgs is
-- the mean speed *made good*, not an average that counts a boat asleep at
-- anchor as sailing at 0 kn.
CREATE TABLE IF NOT EXISTS h3_hourly
(
    h3          UInt64,                -- geoToH3(lon, lat, 7) — note the argument order
    hour        DateTime('UTC'),
    mobile      LowCardinality(String),
    ship_group  LowCardinality(String),
    msgs        SimpleAggregateFunction(sum, UInt64),
    vessels     AggregateFunction(uniqExact, UInt32),
    moving_msgs SimpleAggregateFunction(sum, UInt64),
    sog_sum     SimpleAggregateFunction(sum, Float64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (h3, hour, mobile, ship_group);

-- INTERNAL ONLY. Holds MMSI for de-duplication and per-vessel-day statistics.
-- Never exported, never charted, never named in a commit — see CLAUDE.md.
-- `dist_nm` is distance covered *while moving*; see sql/03_aggregate.sql for
-- the four guards on each step.
CREATE TABLE IF NOT EXISTS vessel_day
(
    day         Date,
    mmsi        UInt32,
    mobile      LowCardinality(String),
    ship_type   LowCardinality(String),
    ship_group  LowCardinality(String),
    first_ts    DateTime('UTC'),
    last_ts     DateTime('UTC'),
    msgs        UInt32,
    moving_msgs UInt32,
    dist_nm     Float32,
    home_h3     UInt64,                -- H3 of the first position of the day
    length      UInt16,                -- max reported; 0 if never reported
    imo         UInt32                 -- 0 if never reported. The stable key to
                                       -- ship registries: 61 % of Class A
                                       -- passenger vessels carry it, 4 of 3 799
                                       -- Class B leisure ones do. Chapter 03
                                       -- joins on it; nothing else can, since
                                       -- names change and MMSI is reassigned.
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (day, mmsi);

-- Public vessels only: Class A passenger ships. Class B is excluded even when
-- it reports Ship type = 'Passenger' (86 such vessels on 2025-07-12) — the
-- privacy rule keys on Type of mobile, never on ship group. Downsampled to one
-- position per minute. Chapter 03 reads this.
CREATE TABLE IF NOT EXISTS public_track
(
    mmsi UInt32,
    ts   DateTime('UTC'),
    lat  Float64,
    lon  Float64,
    sog  Float32,
    name LowCardinality(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (mmsi, ts);

-- One row per successfully loaded archive file. The row-count columns are the
-- honesty layer: what the loader threw away and why. S10 turns them into the
-- per-day dropped share. rows_read = non_vessel + sentinel + out_of_bbox + kept.
CREATE TABLE IF NOT EXISTS load_log
(
    file              String,
    loaded_at         DateTime('UTC'),
    seconds           Float32,
    ts_min            DateTime('UTC'),
    ts_max            DateTime('UTC'),
    rows_read         UInt64,
    rows_non_vessel   UInt64,          -- AtoN, base stations, SAR, PIRB, MOB
    rows_sentinel     UInt64,          -- vessel rows at Latitude = 91
    rows_out_of_bbox  UInt64,          -- vessel rows with a real position outside Danish waters
    rows_kept         UInt64,
    rows_h3           UInt64,
    rows_vessel_day   UInt64,
    rows_public_track UInt64
)
ENGINE = MergeTree
ORDER BY (file, loaded_at);
