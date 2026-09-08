-- S5 — the context layers every chapter joins against. Run with:
--   scripts/ch.sh sql/04_context.sql
-- after scripts/fetch_context.sh has filled data/context/.
--
-- Idempotent, by DROP ... SYNC + CREATE — the pattern scripts/load.sh uses and
-- for the same reason. CREATE OR REPLACE looks equivalent and is not: on an
-- Atomic database it renames the old table aside and defers the real drop by
-- database_atomic_delay_before_drop_table_sec (480 s). `clickhouse local` exits
-- long before that, no later process ever picks the work up, and the bytes stay
-- in data/ch/store forever with a stub in data/ch/metadata_dropped. Measured:
-- five runs of this file left 20 orphaned tables, ~5.5 MB a run, land_src the
-- bulk of it. SYNC makes the drop happen before the statement returns.
-- Paths are relative to the repo root; scripts/ch.sh cds there.
--
-- Who reads what:
--   marina       S6 (are the summer peaks harbour hours or sea hours?), S7
--                (marina density per H3 cell)
--   ferry_route  S8 (chapter 03 — the island ferries)
--   land         S6 (split "on land" harbour cell-hours from cell-hours at sea)
--   storm        S9 (chapter 04 — behaviour around a named storm)
--   regatta      S6 (the events behind a spike in the season curve)
--
-- ===================================================================
-- COORDINATE ORDER. Two conventions meet in this file and they disagree.
--   * H3, under scripts/ch.sh's pins: geoToH3(LAT, LON, 7), and
--     h3ToGeo(h) = (LAT, LON) — so .1 is lat, .2 is lon.
--   * ClickHouse geo types and the polygon dictionary: a point is (X, Y) =
--     (LON, LAT). `geom` below is stored in that order too.
-- Therefore every land lookup on an H3 cell must swap:
--
--     dictHas('land', (h3ToGeo(h3).2, h3ToGeo(h3).1))     -- (lon, lat)
--
-- Getting it backwards does not error. It mirrors the point across the
-- lat = lon diagonal — Copenhagen becomes a spot in the Arabian Sea, and
-- dictHas quietly answers 0 for every harbour in Denmark. That exact mistake
-- destroyed the whole store once; see docs/DECISIONS.md, 2026-09-03.
-- scripts/test_context.sh asserts both directions and range-checks every
-- coordinate this file stores, because a name swap inside the JSONExtract
-- tuple types below would otherwise be silent.
-- ===================================================================


-- --- marinas -------------------------------------------------------
-- OSM leisure=marina inside the project bbox, from Overpass `out center;`, so
-- a way or relation marina arrives as its centre point like a node does.
-- 475 of the 2 833 have no name — they are kept: an unnamed marina is still a
-- place a boat sits, and S7 counts places, not names.
-- The TSV header (@type @id name @lat @lon) is skipped by line count, because
-- those column names are not identifiers ClickHouse can bind to.
DROP TABLE IF EXISTS marina SYNC;
CREATE TABLE marina
(
    osm_type LowCardinality(String),
    osm_id   UInt64,
    name     String,
    lat      Float64,
    lon      Float64,
    h3       UInt64                    -- geoToH3(lat, lon, 7) — same grid as
                                       -- h3_hourly.h3, so the join is a plain
                                       -- equality. Oracle in test_context.sh.
)
ENGINE = MergeTree
ORDER BY (h3, osm_id);

INSERT INTO marina
SELECT osm_type, osm_id, name, lat, lon, geoToH3(lat, lon, 7)
FROM file('data/context/marinas.tsv', TSV,
          'osm_type String, osm_id UInt64, name String, lat Float64, lon Float64')
SETTINGS input_format_tsv_skip_first_lines = 1;


-- --- ferry routes --------------------------------------------------
-- One row per OSM object tagged route=ferry: a relation whose member ways
-- carry the geometry, OR a bare way that carries it directly. Both shapes are
-- real and both are needed — in Danish waters most island ferries are a single
-- tagged way, and relation["route"="ferry"] alone returns 326 objects in this
-- bbox with not one Ærø route among them. Svendborg–Ærøskøbing, which S8
-- validates against, is way 33847154.
-- osm_type is part of the identity: OSM ids are per-type, so a way and a
-- relation may share a number.
--
-- geom holds one entry per way — a relation's route is several ways and they
-- are NOT concatenated here, because their order and direction in the relation
-- are not guaranteed and stitching them wrongly draws a ferry through land.
-- S8 draws them as separate segments.
-- POINTS ARE (LON, LAT), the ClickHouse geo order — not the (lat, lon) that
-- geoToH3 takes two definitions above. The named tuple in the JSONExtract type
-- below is what picks the order: it binds by key, not by position, so swapping
-- the two names silently stores mirrored coordinates. test_context.sh
-- range-checks every stored point for exactly that.
DROP TABLE IF EXISTS ferry_route SYNC;
CREATE TABLE ferry_route
(
    osm_type LowCardinality(String),
    osm_id   UInt64,
    name     String,
    from     String,                   -- `from`/`to` are the OSM tag names and
    to       String,                   -- need no quoting as ClickHouse columns
    operator String,
    geom     Array(Array(Tuple(Float64, Float64)))   -- [way][point] = (lon, lat)
)
ENGINE = MergeTree
ORDER BY (osm_type, osm_id);

INSERT INTO ferry_route
SELECT
    JSONExtractString(el, 'type')             AS osm_type,
    JSONExtractUInt(el, 'id')                 AS osm_id,
    JSONExtractString(el, 'tags', 'name')     AS name,
    JSONExtractString(el, 'tags', 'from')     AS from,
    JSONExtractString(el, 'tags', 'to')       AS to,
    JSONExtractString(el, 'tags', 'operator') AS operator,
    arrayFilter(g -> length(g) > 0,
        if(osm_type = 'way',
           [JSONExtract(el, 'geometry', 'Array(Tuple(lon Float64, lat Float64))')],
           arrayMap(m -> JSONExtract(m, 'geometry', 'Array(Tuple(lon Float64, lat Float64))'),
                    -- Route LEGS only. A ferry relation also carries its two
                    -- piers as member ways with role platform /
                    -- platform_entry_only / platform_exit_only — 101 of them
                    -- here — and those are quay outlines, not the crossing. Fed
                    -- into geom they draw a box on the harbour wall at each end
                    -- of every line. The kept roles are the ones public_transport
                    -- v2 gives a leg: unset, route, forward, backward,
                    -- alternative. 38 relations lose at least one member this
                    -- way; none is left with nothing to draw.
                    arrayFilter(m -> JSONExtractString(m, 'type') = 'way'
                                 AND JSONExtractString(m, 'role') IN
                                     ('', 'route', 'forward', 'backward', 'alternative'),
                                JSONExtractArrayRaw(el, 'members'))))) AS geom
FROM
(
    SELECT arrayJoin(JSONExtractArrayRaw(json, 'elements')) AS el
    FROM file('data/context/ferry_routes.json', JSONAsString)
)
-- Drops the three route relations whose members carry no geometry, and the
-- three route=ferry nodes (a terminal, not a line). A row with no line is
-- nothing S8 can draw; test_context.sh asserts none survives.
WHERE length(geom) > 0;


-- --- land ----------------------------------------------------------
-- Natural Earth 10 m land polygons, pinned to release v5.1.2 in
-- scripts/fetch_context.sh. 11 features, each a MultiPolygon holding thousands
-- of rings — the file is grouped by scalerank, not one feature per landmass.
-- Rings are already (lon, lat) in GeoJSON, which is the order the dictionary
-- wants, so nothing is swapped on the way in.
--
-- NOTE ON PRECISION: at 10 m scale the coastline is generalised by up to about
-- a kilometre. Rådhuspladsen in Copenhagen (12.5683, 55.6761) reads as sea in
-- this dataset — confirmed independently with shapely against the same file.
-- This layer answers "harbour-ish or open water", never "which side of the
-- quay"; do not assert on a point close to a shore.
--
-- The dictionary is dropped before land_src because it depends on it.
DROP DICTIONARY IF EXISTS land SYNC;
DROP TABLE IF EXISTS land_src SYNC;
CREATE TABLE land_src
(
    id    UInt32,
    shape MultiPolygon                 -- = Array(Array(Array(Tuple(Float64, Float64))))
)
ENGINE = MergeTree
ORDER BY id;

INSERT INTO land_src
SELECT
    toUInt32(idx) AS id,
    if(JSONExtractString(feats[idx], 'geometry', 'type') = 'Polygon',
       -- a Polygon is one level shallower than a MultiPolygon; wrap it
       [JSONExtract(feats[idx], 'geometry', 'coordinates',
                    'Array(Array(Tuple(Float64, Float64)))')],
       JSONExtract(feats[idx], 'geometry', 'coordinates', 'MultiPolygon')) AS shape
FROM
(
    SELECT JSONExtractArrayRaw(json, 'features') AS feats
    FROM file('data/context/ne_10m_land.geojson', JSONAsString)
)
ARRAY JOIN arrayEnumerate(feats) AS idx;

-- The lookup used by every "is this cell a harbour or open water" question.
-- LIFETIME(0) = never auto-reload; the DROP above is what rebuilds it.
-- STORE_POLYGON_KEY_COLUMN keeps the polygons so dictHas can answer
-- point-in-polygon.
--
-- POLYGON_INDEX_EACH, not the default POLYGON (= POLYGON_INDEX_CELL). Every
-- `clickhouse local` process reloads this dictionary from scratch on first use,
-- so its build cost is paid by every single query that touches it. Measured on
-- the same 116 289 H3 cell centres, identical answers from all three layouts:
--   POLYGON / POLYGON_INDEX_CELL   16.4 s, 150 MB
--   POLYGON_INDEX_EACH              3.5 s,  82 MB
-- CALL IT AS dictHas('land', (lon, lat)). See the banner at the top.
CREATE DICTIONARY land
(
    id    UInt32,
    shape MultiPolygon
)
PRIMARY KEY shape
SOURCE(CLICKHOUSE(TABLE 'land_src'))
LIFETIME(0)
LAYOUT(POLYGON_INDEX_EACH(STORE_POLYGON_KEY_COLUMN 1));


-- --- storms and regattas -------------------------------------------
-- Hand-collected and COMMITTED (see .gitignore) — they are the only context
-- with no machine source. Every row carries the URL it was read off, because a
-- named storm's start hour is an editorial choice and the essay has to be able
-- to show whose.
--
-- Both INSERTs are deliberately strict, because a hand-edited file is the one
-- input here that WILL eventually be wrong:
--   date_time_input_format = 'basic'      — best_effort silently accepts
--       '05/12/2013 12:00:00' and guesses which half is the month. The archive
--       loader refuses to guess (sql/02_stage.sql) and neither does this.
--   input_format_skip_unknown_fields = 0  — a renamed or added header column is
--       an error instead of a column quietly filled with 1970-01-01.
--   input_format_defaults_for_omitted_fields = 0 — no DEFAULT expressions.
-- A column that is simply MISSING from the header is still not caught by any
-- setting (it is not "unknown", just absent), so test_context.sh asserts the
-- header line of both files verbatim. And note that skip_unknown_fields = 0
-- only works while every column is actually read: `SELECT count() FROM
-- file(…)` prunes the column list to nothing and then every header name is
-- "unknown". These INSERTs select *, which is why they are fine.
DROP TABLE IF EXISTS storm SYNC;
CREATE TABLE storm
(
    name       String,
    start_utc  DateTime('UTC'),
    end_utc    DateTime('UTC'),
    source_url String,
    note       String
)
ENGINE = MergeTree
ORDER BY start_utc;

INSERT INTO storm
SELECT * FROM file('data/context/storms.csv', CSVWithNames,
    'name String, start_utc DateTime(\'UTC\'), end_utc DateTime(\'UTC\'),
     source_url String, note String')
SETTINGS date_time_input_format = 'basic',
         input_format_skip_unknown_fields = 0,
         input_format_defaults_for_omitted_fields = 0;

DROP TABLE IF EXISTS regatta SYNC;
CREATE TABLE regatta
(
    name       String,
    year       UInt16,
    start_date Date,
    end_date   Date,
    place      String,
    lat        Float64,
    lon        Float64,
    source_url String
)
ENGINE = MergeTree
ORDER BY (year, start_date);

INSERT INTO regatta
SELECT * FROM file('data/context/regattas.csv', CSVWithNames,
    'name String, year UInt16, start_date Date, end_date Date,
     place String, lat Float64, lon Float64, source_url String')
SETTINGS date_time_input_format = 'basic',
         input_format_skip_unknown_fields = 0,
         input_format_defaults_for_omitted_fields = 0;
