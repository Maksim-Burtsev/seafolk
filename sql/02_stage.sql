-- S2 — stage one archive file. Called by scripts/load.sh and, with a small
-- {lim}, by scripts/test_load.sh, so the test exercises the real statement.
--
--   scripts/ch.sh sql/02_stage.sql --param_src 'data/raw/aisdk-2025-07-16.zip :: *.csv' \
--                                  --param_lim 18446744073709551615
--
-- {lim} is a row cap, not a flag: ClickHouse reads LIMIT 0 as "zero rows", so
-- "no limit" is UInt64 max, which scripts/load.sh passes by default.
--
-- ClickHouse reads the CSV inside the zip; nothing is unpacked to disk.
-- Timestamps are parsed with an explicit %d/%m/%Y mask rather than best_effort:
-- 12/07/2025 is ambiguous and a silent month/day swap would be invisible.
-- parseDateTime (not ...OrNull) throws on a bad value — S1 measured zero
-- failures in 87.6 M rows, so a failure here is news, not noise.

SET input_format_skip_unknown_fields = 1;

TRUNCATE TABLE IF EXISTS ais_raw_stage;

INSERT INTO ais_raw_stage
SELECT
    parseDateTime(`# Timestamp`, '%d/%m/%Y %H:%i:%S', 'UTC') AS ts,
    MMSI                                                     AS mmsi,
    `Type of mobile`                                         AS mobile,
    Latitude                                                 AS lat,
    Longitude                                                AS lon,
    ifNull(SOG, -1)                                          AS sog,
    `Ship type`                                              AS ship_type,
    Name                                                     AS name,
    ifNull(Length, 0)                                        AS length
FROM file({src:String}, CSVWithNames,
          '`# Timestamp` String, `Type of mobile` String, MMSI UInt32,
           Latitude Float64, Longitude Float64, SOG Nullable(Float32),
           Name String, `Ship type` String, Length Nullable(UInt16)')
LIMIT {lim:UInt64};
