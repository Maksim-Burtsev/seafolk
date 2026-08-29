-- S1 — first look at the raw archive. Read-only: queries the CSV *inside* the
-- downloaded zips via ClickHouse's archive syntax, so nothing is unpacked to
-- disk. Run with: scripts/ch.sh sql/00_peek.sql
--
-- Files expected in data/raw (see scripts/fetch.sh):
--   aisdk-2025-07-12  July Saturday      aisdk-2025-07-16  July Wednesday
--   aisdk-2025-01-15  January Wednesday  aisdk-2025-06-14  Sjaelland Rundt
--
-- The 26 CSV columns are matched by header name; each query declares only the
-- ones it needs and skips the rest (input_format_skip_unknown_fields=1).

SET input_format_skip_unknown_fields = 1;

SELECT '=== 1. size and Class B presence, per day ===';

SELECT
    _file                                                        AS file,
    count()                                                      AS msgs,
    uniqExact(MMSI)                                              AS vessels,
    uniqExactIf(MMSI, `Type of mobile` = 'Class A')              AS class_a,
    uniqExactIf(MMSI, `Type of mobile` = 'Class B')              AS class_b,
    round(100 * class_b / (class_a + class_b), 1)                AS class_b_pct
FROM file('data/raw/aisdk-2025-*.zip :: *.csv', CSVWithNames,
          '`# Timestamp` String, `Type of mobile` String, MMSI UInt32')
GROUP BY file
ORDER BY file;

SELECT '=== 2. Ship type by mobile class, July Saturday (distinct vessels) ===';

SELECT
    `Ship type`                                     AS ship_type,
    uniqExactIf(MMSI, `Type of mobile` = 'Class A') AS class_a,
    uniqExactIf(MMSI, `Type of mobile` = 'Class B') AS class_b,
    count()                                         AS msgs
FROM file('data/raw/aisdk-2025-07-12.zip :: *.csv', CSVWithNames,
          '`Type of mobile` String, MMSI UInt32, `Ship type` String')
GROUP BY ship_type
ORDER BY class_b + class_a DESC
LIMIT 20;

SELECT '=== 3. the leisure fleet (Sailing + Pleasure), summer vs winter ===';

SELECT
    _file                                                AS file,
    uniqExactIf(MMSI, `Ship type` = 'Sailing')           AS sailing,
    uniqExactIf(MMSI, `Ship type` = 'Pleasure')          AS pleasure,
    uniqExact(MMSI)                                      AS leisure_total,
    countIf(SOG > 0.5)                                   AS moving_msgs
FROM file('data/raw/aisdk-2025-*.zip :: *.csv', CSVWithNames,
          'MMSI UInt32, `Type of mobile` String, `Ship type` String, SOG Nullable(Float32)')
WHERE `Type of mobile` = 'Class B' AND `Ship type` IN ('Sailing', 'Pleasure')
GROUP BY file
ORDER BY file;

SELECT '=== 4. coordinates: sentinels, bounds, decimal separator ===';

SELECT
    _file                                                       AS file,
    count()                                                     AS msgs,
    countIf(Latitude = 91 OR Longitude = 181)                   AS sentinel_91_181,
    countIf(abs(Latitude) > 90 OR abs(Longitude) > 180)         AS impossible,
    countIf(Latitude BETWEEN 53 AND 59 AND Longitude BETWEEN 3 AND 17) AS in_danish_bbox,
    round(minIf(Latitude, abs(Latitude) <= 90), 4)              AS lat_min,
    round(maxIf(Latitude, abs(Latitude) <= 90), 4)              AS lat_max,
    round(minIf(Longitude, abs(Longitude) <= 180), 4)           AS lon_min,
    round(maxIf(Longitude, abs(Longitude) <= 180), 4)           AS lon_max
FROM file('data/raw/aisdk-2025-*.zip :: *.csv', CSVWithNames,
          'MMSI UInt32, Latitude Float64, Longitude Float64')
GROUP BY file
ORDER BY file;

SELECT '=== 5. timestamp: explicit DD/MM/YYYY parse vs best-effort ===';

SELECT
    _file                                                          AS file,
    count()                                                        AS msgs,
    countIf(strict IS NULL)                                        AS strict_parse_failed,
    countIf(best IS NULL)                                          AS best_effort_failed,
    countIf(strict != best)                                        AS the_two_disagree,
    min(strict)                                                    AS ts_min,
    max(strict)                                                    AS ts_max
FROM (
    SELECT _file,
        parseDateTimeOrNull(`# Timestamp`, '%d/%m/%Y %H:%i:%S', 'UTC') AS strict,
        parseDateTimeBestEffortOrNull(`# Timestamp`, 'UTC')            AS best
    FROM file('data/raw/aisdk-2025-*.zip :: *.csv', CSVWithNames,
              '`# Timestamp` String, MMSI UInt32')
)
GROUP BY file
ORDER BY file;

SELECT '=== 6. timezone probe: island ferries, first/last moving hour in the file clock ===';
-- Ferry timetables are written in local time and keep the same local first
-- departure all year. If the file clock shifted with DST it would be local
-- time; a constant +1 h in January means the file clock is UTC.

SELECT
    Name                        AS ferry,
    maxIf(h, day = '01-15')     AS jan_last,
    minIf(h, day = '01-15')     AS jan_first,
    minIf(h, day = '07-12')     AS jul_first,
    maxIf(h, day = '07-12')     AS jul_last,
    jan_first - jul_first       AS winter_shift_hours
FROM (
    SELECT
        Name,
        substring(_file, 12, 5)                            AS day,
        toUInt8(substring(`# Timestamp`, 12, 2))           AS h,
        count()                                            AS c
    FROM file('data/raw/aisdk-2025-{01-15,07-12}.zip :: *.csv', CSVWithNames,
              '`# Timestamp` String, Name String, SOG Nullable(Float32)')
    WHERE SOG > 3 AND Name IN ('PRINSESSE ISABELLA', 'AEROESKOEBING', 'ELLEN')
    GROUP BY Name, day, h
    HAVING c > 20
)
GROUP BY ferry
ORDER BY ferry;
