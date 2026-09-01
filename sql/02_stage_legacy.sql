-- S4 — stage one archive file written in the PRE-2016-10 CSV dialect. Same
-- contract as sql/02_stage.sql: same target table, same column meanings, so
-- sql/03_aggregate.sql cannot tell which of the two ran.
--
--   2006-03 … 2016-09   no header row, ';' delimiter, decimal COMMA, 22 columns
--   2016-10 … today     header row,   ',' delimiter, decimal point, 22 or 26 columns
--
-- Probed by HTTP range read (first and last member of each): 2014-01, 2015-07,
-- 2016-01, 2016-07, 2016-08, 2016-09 are legacy; 2016-10, 2017-01, 2018-01,
-- 2021-01 and every daily file are modern. No month mixes the two. scripts/load.sh
-- does not trust that boundary as a date rule though — it reads the archive's
-- own first line, which costs 0.05 s even on a 17 GB monthly zip.
--
-- No header means positional parsing, so all 22 columns are declared in file
-- order and the 12 this project does not use are read as String and dropped.
-- The comma-decimal fields are staged as String and converted here; replaceAll
-- on a value with no comma is a no-op, so this is safe on either dialect.
--
-- The conversions THROW on a value that is not a number, and this is where the
-- two paths deliberately differ: sql/02_stage.sql leaves an empty Latitude to
-- the CSV reader, which yields 0.0 — the row lands at (0, 0) in the Gulf of
-- Guinea and disappears into rows_out_of_bbox. That is measured behaviour on
-- 909 loaded days, not a decision anyone would repeat, so the new path refuses
-- instead. Cost of refusing: one malformed coordinate aborts a whole monthly
-- load. 2015-07 has none in 364 402 400 rows, and 2006-2013 has never been read.
--
-- Column order is the whole risk of parsing by position, so scripts/test_load.sh
-- reads back one field from every column this file selects — a deliberate
-- misdeclaration of any of them turns an assert red.

SET format_csv_delimiter = ';';

TRUNCATE TABLE IF EXISTS ais_raw_stage;

INSERT INTO ais_raw_stage
SELECT
    parseDateTime(ts, '%d/%m/%Y %H:%i:%S', 'UTC')          AS ts,
    mmsi                                                   AS mmsi,
    mobile                                                 AS mobile,
    toFloat64(replaceAll(lat, ',', '.'))                   AS lat,
    toFloat64(replaceAll(lon, ',', '.'))                   AS lon,
    if(sog = '', -1, toFloat32(replaceAll(sog, ',', '.'))) AS sog,
    ship_type                                              AS ship_type,
    name                                                   AS name,
    ifNull(length, 0)                                      AS length,
    toUInt32OrZero(imo)                                    AS imo
FROM file({src:String}, CSV,
          'ts String, mobile String, mmsi UInt32, lat String, lon String,
           navstat String, rot String, sog String, cog String, heading String,
           imo String, callsign String, name String, ship_type String,
           cargo String, width String, length Nullable(UInt16), posfix String,
           draught String, dest String, eta String, source String')
LIMIT {lim:UInt64};
