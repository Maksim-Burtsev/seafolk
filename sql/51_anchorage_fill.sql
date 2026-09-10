-- S9 chart 2 — chapter 04: WHERE do the ships that stop go? Anchorage cells
-- found by a rule and confirmed by hand, and how full each one is hour by hour
-- around a named storm.
-- Run: scripts/ch.sh sql/51_anchorage_fill.sql
--      (read-only; 25.7 s, 758 + 1 + 38 534 rows; writes nothing)
-- Reads `h3_hourly`, the `land` dictionary (sql/04_context.sql),
-- `storm`, `vessel_day` (day list only) and the committed hand file
-- data/context/anchorages.csv.
--
-- THREE STATEMENTS:
--   1. the candidate cells, per (cell, year), with their hand label  [9 cols]
--   2. the guard: three throws over anchorages.csv and the rule      [1 col]
--   3. the storm profile, per (storm, anchorage, hour)               [8 cols]
-- A consumer separates them by row width, the way notes/plot_ch03.py separates
-- sql/44's three blocks.
--
-- ===================================================================
-- BLOCK 1 — THE RULE. A cell-year is an anchorage CANDIDATE when
--   * mobile = 'Class A' and ship_group IN ('cargo', 'other') — the fleets
--     that wait. Passenger ships keep a timetable and fishing boats go home;
--     'other' is where tugs, offshore support and the HSC misfile live
--     (sql/03 maps HSC -> other, docs/STATUS.md § S8).
--   * the cell is AT SEA: NOT dictHas('land', (lon, lat)). NOTE THE SWAP —
--     h3ToGeo returns (lat, lon) under scripts/ch.sh's pins and the polygon
--     dictionary takes (x, y) = (lon, lat). See sql/04_context.sql's banner:
--     getting it backwards does not error, it mirrors Denmark into the
--     Arabian Sea and answers 0 for every harbour.
--   * still share = 1 - moving_msgs / msgs >= 0.8 — four messages in five
--     come from a vessel under 0.5 kn.
--   * >= 50 distinct vessels in that year (uniqExactMerge over the year).
-- The vessel floor is the whole of the discrimination. Without it the same
-- still-share test returns individual BERTHS (2-5 vessels a year) by the
-- thousand: a quay is stiller than any anchorage.
--
-- MEASURED: the rule returns 758 cell-years over 2015-2026 and 143 DISTINCT
-- CELLS reach >= 100 vessels in at least one year. Those 143 are the rows of
-- data/context/anchorages.csv.
--
-- WHY A HAND LABEL AT ALL. The rule finds "a lot of ships sitting still at
-- sea", which is an anchorage, a shipyard basin, an offshore field, a lock
-- approach or a fairway where everybody waits. It cannot tell them apart and
-- neither can this query. anchorages.csv is labelling only — a name, the URL
-- it was read off, and a note. It carries NO NUMBERS: every number in this
-- file comes from the store.
--   note = ''                  a real anchorage, with a source
--   note = 'not an anchorage'  no anchorage source was found for this cell;
--                              the name says what the place geographically
--                              is. Block 3 EXCLUDES these.
-- The bar is a source, not an opinion. 74 of the 143 cells sit within 8 km of
-- an OSM `seamark:type=anchorage` / `anchor_berth` object (fetched from
-- Overpass over the project bbox: 274 objects) or of a published Danish
-- roadstead — Skagen Red and Ålbæk Bugt, which OSM does not carry at all —
-- and they hold 37 distinct anchorage names. The other 69 are named for what
-- they are (Lindø yard in Odense Fjord, the Fredericia oil terminal, Aarhus
-- harbour, Hirtshals, the Drogden channel, the Danish North Sea oil fields,
-- the Baltic south-east of Bornholm) and excluded.
-- THE 8 km BOUND is the object CENTRE to the cell CENTRE, and it sits in a
-- gap in the measured distance distribution: matches run ..., 6.5, 6.6, 7.1,
-- 7.1, then 8.4, 9.4, 9.6, 10.8, ... Four nearest matches inside the bound
-- were rejected by hand as not anchorages at all — two canoe landing points,
-- a mooring pile ('Dalben') and a small-craft berth, each tagged
-- seamark:type=anchor_berth. Two cells fall just outside it and are therefore
-- excluded although their nearest object is plausibly theirs: Varberg (8.4 km
-- from an object named 'V') and the Elbe off Stade (9.4 km). 'not an
-- anchorage' means "no anchorage source within the bound", and it is the
-- conservative direction: a cell there may well be an anchorage that no
-- source we found records.
--
-- ===================================================================
-- THERE IS DELIBERATELY NO MARINA TEST, AND HERE IS THE MEASUREMENT.
-- The obvious extra filter is `h3 NOT IN (SELECT h3 FROM marina)` — a marina
-- full of moored yachts passes a still-share test trivially. It was tried and
-- REMOVED, for two reasons.
-- First, it is redundant against this rule: the rule reads Class A CARGO and
-- 'other' only, and a cargo ship does not moor in a yacht marina. The marina
-- layer answers a question about leisure boats (it is S6/S7's layer) and this
-- is not one.
-- Second, it deletes Denmark's biggest anchorage. A res-7 cell is ~5 km2 and
-- Skagen's marina sits in the same cell as the Skagen roadstead: cell
-- 608533825823178751 (57.7158 N, 10.5877 E) holds 1 021 distinct Class A
-- cargo + other vessels in 2015, 1 158 in 2018 and 273 in 2025 at a still
-- share of 0.91-0.94, and the marina test removed every one of those
-- cell-years. Store-wide it removed 366 candidate cell-years over 87 cells,
-- of which 44 CELLS reach >= 100 vessels in some year — of 143 such cells,
-- so nearly a third of everything the rule finds, including the Port of
-- Copenhagen, Esbjerg, Hirtshals, Frederikshavn and the Limfjord.
-- WHAT REPLACES IT is the hand label: a marina cell that the rule surfaces is
-- either a real anchorage (Skagen Red) or a harbour, and the CSV says which.
-- ===================================================================
--
-- BLOCK 2 — THE GUARD, a separate statement so its messages can be constants,
-- the pattern sql/40_ferry_trips.sql uses for `lines_unmapped`. It re-runs
-- block 1's scan (TWO full scans of `h3_hourly` in this file, block 1's and
-- this one; block 3 prefilters on 143 cells and costs a fraction of one),
-- which is the price of failing loudly when the archive
-- grows a new anchorage and nobody labels it. Under 100 vessels a cell may go
-- unlabelled: it is then simply absent from block 3.
-- IT THROWS ON THREE THINGS, not one, because anchorages.csv is a hand file
-- with no machine source and each of the three is a SILENT wrong answer, not
-- an error:
--   1. a rule cell with >= 100 vessels in a year and no row in the CSV;
--   2. a DUPLICATE h3. Two rows for one cell with two different names make
--      block 3 count the same vessels under both names — MEASURED on a
--      mutated copy (one Skagen Red cell repeated as 'Skagen Red North'):
--      block 3 goes 38 534 -> 41 150 rows;
--   3. a `note` that is neither '' nor 'not an anchorage'. The exclusion in
--      block 3 is a string comparison, so 'Not an anchorage' or a trailing
--      space silently re-admits every excluded cell — MEASURED on a mutated
--      copy with the capital N on all 69 excluded rows: block 3 grows
--      38 534 -> 106 308 rows, i.e. the oil fields, the Lindø yard and every
--      harbour come back as "anchorages";
--   4. an h3 in the CSV that the rule never surfaced. A hand-typed cell is
--      otherwise profiled as an anchorage anyway — MEASURED: one bogus row
--      (Copenhagen city centre) adds 21 rows to block 3. Block 3 reads the
--      CSV directly for speed and RELIES ON THIS THROW for the cells it
--      profiles being the rule's. All 143 current rows are rule cells at sea.
-- scripts/test_context.sh asserts the same three, plus a URL in every
-- source_url, a non-empty name and h3IsValid/resolution 7 on every h3. The
-- guard is here as well so the SQL fails loudly when the test was not run.
--
-- BLOCK 3 — THE STORM PROFILE. Per (storm, anchorage NAME, hour):
--   present      uniqExactMerge(vessels) over Class A cargo + other in ALL
--                cells that carry that name — several res-7 cells make one
--                anchorage (Skagen Red is seven, Ålbæk Bugt three), and the
--                uniqExact states merge across them exactly, so a ship that
--                drifts from one cell to the next inside the hour is ONE
--                vessel, not two.
--                THE CSV MAY ONLY NAME AND EXCLUDE WHAT THE RULE FOUND, and
--                block 2 is what enforces it: it throws unless every h3 in
--                the CSV is a rule cell at sea, so a hand-typed cell cannot
--                conjure an anchorage out of an arbitrary square of water.
--                Block 3 then reads the CSV directly and prefilters
--                `h3_hourly` on those 143 cells. IT IS NOT A STANDALONE
--                STATEMENT: it is only sound with block 2 ahead of it in the
--                same run.
--   still_share  1 - moving_msgs / msgs in the same cells and hour
--   ref_present  `present` at the reference hour
-- Hours with nothing in `h3_hourly` produce no row (same rule as sql/50).
--
-- THE REFERENCE RULE AND THE WINDOW ARE sql/50_storm_window.sql's, and the
-- four CTEs `loaded`, `st`, `win`, `winr` below are a VERBATIM COPY of
-- sql/50's. They are duplicated on purpose — a ClickHouse local run cannot
-- import a CTE from another file and this project has no SQL templating — and
-- they must stay byte-identical: diff them before believing any change.
-- In one line each: Dagmar and Egon are one storm 'Dagmar·Egon'; the window
-- is [start_day 00:00 UTC - 72 h, end_day 24:00 UTC + 72 h) built from
-- calendar dates with NO timezone conversion; the reference is the same UTC
-- hour 14 days earlier, else 14 days later, else NULL. sql/50's header has
-- the reasoning, the measurements and which rule fired for which storm.
--
-- PRIVACY: every emitted number is a count over a whole fleet in a whole
-- hour, and `vessel_day` is read for its calendar days only. No MMSI, no
-- name, no track.

-- ====================================================================
-- BLOCK 1 — candidate cells by rule, with their hand label.
-- ====================================================================
WITH
cy AS (
    SELECT h3, toYear(hour) AS year,
           uniqExactMerge(vessels) AS vessels,
           sum(msgs)               AS msgs,
           sum(moving_msgs)        AS moving_msgs
    FROM h3_hourly
    WHERE mobile = 'Class A' AND ship_group IN ('cargo', 'other')
    GROUP BY h3, year
    HAVING vessels >= 50 AND msgs > 0 AND 1 - moving_msgs / msgs >= 0.8
),
lab AS (
    SELECT * FROM file('data/context/anchorages.csv', CSVWithNames,
        'h3 UInt64, name String, source_url String, note String')
    -- skip_unknown_fields = 1, unlike sql/04_context.sql's two hand files.
    -- The strict setting only bites while EVERY header column is read, and
    -- ClickHouse prunes `source_url` out of these three CTEs before the
    -- reader ever sees it — the file then refuses to open at all. The
    -- protection sql/04 gets from the setting is here provided by
    -- scripts/test_context.sh, which asserts this file's header VERBATIM (a
    -- renamed or dropped column is not "unknown", it is absent, and no input
    -- setting has ever caught that — sql/04's own note says so), and by the
    -- guard in block 2, which throws if `h3` stops parsing.
    SETTINGS input_format_skip_unknown_fields = 1,
             input_format_defaults_for_omitted_fields = 0
)
SELECT c.h3                                       AS h3,
       round(h3ToGeo(c.h3).1, 4)                  AS lat,   -- .1 = LAT (pinned)
       round(h3ToGeo(c.h3).2, 4)                  AS lon,   -- .2 = LON
       c.year                                     AS year,
       c.vessels                                  AS vessels,
       c.msgs                                     AS msgs,
       round(1 - c.moving_msgs / c.msgs, 4)       AS still_share,
       l.name                                     AS name,
       l.note                                     AS note
FROM cy AS c
LEFT JOIN lab AS l ON l.h3 = c.h3
WHERE NOT dictHas('land', (h3ToGeo(c.h3).2, h3ToGeo(c.h3).1))
ORDER BY name, h3, year
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 2 — the guard. Mirrors sql/40's `lines_unmapped` throw.
-- ONE SCAN, FOUR CHECKS. The rule cells and the CSV are folded into one row
-- per h3 (`per_h3` below) and every throw is a countIf over that, so
-- `h3_hourly` is read ONCE here — a version that put each check in its own
-- scalar subquery read it twice and cost the file 20 seconds.
-- Four throwIf in ONE statement, so the block stays one column wide and the
-- consumer's width-based split keeps working. `+` and not `or`: no
-- short-circuit, so all four are evaluated and the first offence throws.
-- ====================================================================
WITH
cy AS (
    SELECT h3, toYear(hour) AS year,
           uniqExactMerge(vessels) AS vessels,
           sum(msgs)               AS msgs,
           sum(moving_msgs)        AS moving_msgs
    FROM h3_hourly
    WHERE mobile = 'Class A' AND ship_group IN ('cargo', 'other')
    GROUP BY h3, year
    HAVING vessels >= 50 AND msgs > 0 AND 1 - moving_msgs / msgs >= 0.8
),
-- block 1's cell-years collapsed to cells, at sea, with their best year
rule_cells AS (
    SELECT h3, max(vessels) AS vessels
    FROM cy
    WHERE NOT dictHas('land', (h3ToGeo(h3).2, h3ToGeo(h3).1))
    GROUP BY h3
),
lab AS (
    SELECT * FROM file('data/context/anchorages.csv', CSVWithNames,
        'h3 UInt64, name String, source_url String, note String')
    -- skip_unknown_fields = 1, unlike sql/04_context.sql's two hand files.
    -- The strict setting only bites while EVERY header column is read, and
    -- ClickHouse prunes `source_url` out of these CTEs before the reader ever
    -- sees it — the file then refuses to open at all. The protection sql/04
    -- gets from the setting is here provided by scripts/test_context.sh,
    -- which asserts this file's header VERBATIM (a renamed or dropped column
    -- is not "unknown", it is absent, and no input setting has ever caught
    -- that — sql/04's own note says so), and by the throws below, which fire
    -- if `h3` stops parsing.
    SETTINGS input_format_skip_unknown_fields = 1,
             input_format_defaults_for_omitted_fields = 0
),
per_h3 AS (
    SELECT h3,
           max(rule_vessels) AS rule_vessels,
           max(is_rule)      AS is_rule,
           sum(is_csv)       AS csv_rows,
           max(bad_note)     AS bad_note
    FROM (
        SELECT h3, vessels AS rule_vessels,
               toUInt8(1) AS is_rule, toUInt8(0) AS is_csv, toUInt8(0) AS bad_note
        FROM rule_cells
        UNION ALL
        SELECT h3, toUInt64(0) AS rule_vessels,
               toUInt8(0) AS is_rule, toUInt8(1) AS is_csv,
               toUInt8(note NOT IN ('', 'not an anchorage')) AS bad_note
        FROM lab
    )
    GROUP BY h3
)
SELECT throwIf(countIf(is_rule = 1 AND rule_vessels >= 100 AND csv_rows = 0) > 0,
               'sql/51: an anchorage-rule cell with >= 100 distinct vessels in a year has no row in data/context/anchorages.csv. Decode it with h3ToGeo (.1 = lat, .2 = lon), find out what the place is, and add a row — name it and set note = ''not an anchorage'' if no anchorage source exists for it.')
     + throwIf(countIf(csv_rows > 1) > 0,
               'sql/51: data/context/anchorages.csv has a duplicate h3. One cell may carry one name only — two rows for one cell count the same vessels under two anchorages in block 3.')
     + throwIf(countIf(bad_note > 0) > 0,
               'sql/51: data/context/anchorages.csv has a note that is neither '''' nor ''not an anchorage''. Block 3 excludes by exact string, so ''Not an anchorage'' or a trailing space silently re-admits every excluded cell.')
     + throwIf(countIf(csv_rows > 0 AND is_rule = 0) > 0,
               'sql/51: data/context/anchorages.csv holds an h3 that this rule never surfaced — a mistyped or stale cell. Block 3 trusts this guard and reads the CSV directly, so such a row would silently profile a cell the rule never found.')
       = 0 AS anchorages_csv_is_sound
FROM per_h3;


-- ====================================================================
-- BLOCK 3 — how full each labelled anchorage is, hour by hour, around each
-- storm, against the same hour a fortnight away.
-- ====================================================================
WITH
-- --- verbatim from sql/50_storm_window.sql ---------------------------
loaded AS (
    SELECT DISTINCT day FROM vessel_day
),
st AS (
    SELECT if(name IN ('Dagmar', 'Egon'), 'Dagmar·Egon', name) AS storm,
           min(toDate(start_utc)) AS start_day,
           max(toDate(end_utc))   AS end_day
    FROM storm
    GROUP BY storm
),
-- one row per storm-hour: [start_day 00:00 - 72 h, end_day 24:00 + 72 h)
win AS (
    SELECT storm, start_day,
           toDateTime(start_day, 'UTC') - INTERVAL 72 HOUR
             + INTERVAL arrayJoin(range(toUInt32(dateDiff('hour',
                   toDateTime(start_day, 'UTC')   - INTERVAL 72 HOUR,
                   toDateTime(end_day + 1, 'UTC') + INTERVAL 72 HOUR)))) HOUR AS hour
    FROM st
),
winr AS (
    SELECT storm, start_day, hour,
           toInt32(dateDiff('hour', toDateTime(start_day, 'UTC'), hour)) AS offset_h,
           multiIf(toDate(hour - INTERVAL 14 DAY) IN (SELECT day FROM loaded),
                       toNullable(hour - INTERVAL 14 DAY),
                   toDate(hour + INTERVAL 14 DAY) IN (SELECT day FROM loaded),
                       toNullable(hour + INTERVAL 14 DAY),
                   NULL) AS ref_hour
    FROM win
),
-- the hours h3_hourly has to be scanned for: the windows and their references.
-- Without this the aggregate below reads all 96 months of the store.
hrs AS (
    SELECT DISTINCT hour FROM (
        SELECT hour FROM winr
        UNION ALL
        SELECT assumeNotNull(ref_hour) AS hour FROM winr WHERE ref_hour IS NOT NULL
    )
),
-- --- end of the verbatim copy ---------------------------------------
-- Block 3 TRUSTS BLOCK 2, which has already run in this file: the guard
-- throws unless every h3 in the CSV is a rule cell at sea, every note is one
-- of the two allowed strings and no h3 appears twice. So the CSV can be read
-- straight here, and `h3_hourly` is prefiltered on `h3` — the table's FIRST
-- ORDER BY key — which turns this from a full scan into 143 cells' worth of
-- granules. RUNNING BLOCK 3 ON ITS OWN IS NOT SUPPORTED: without the guard
-- ahead of it, a mistyped cell in the hand file becomes an anchorage.
anch AS (
    SELECT h3, name FROM file('data/context/anchorages.csv', CSVWithNames,
        'h3 UInt64, name String, source_url String, note String')
    WHERE note = ''          -- 'not an anchorage' is the only other value
    SETTINGS input_format_skip_unknown_fields = 1,
             input_format_defaults_for_omitted_fields = 0
),
occ AS (
    SELECT a.name AS name, h.hour AS hour,
           uniqExactMerge(h.vessels) AS present,
           sum(h.msgs)               AS msgs,
           sum(h.moving_msgs)        AS moving_msgs
    FROM h3_hourly AS h
    INNER JOIN anch AS a ON a.h3 = h.h3
    WHERE h.h3 IN (SELECT h3 FROM anch)   -- prunes on the primary key
      AND h.hour IN (SELECT hour FROM hrs)
      AND h.mobile = 'Class A' AND h.ship_group IN ('cargo', 'other')
    GROUP BY name, hour
)
SELECT w.storm    AS storm,
       o.name     AS name,
       w.hour     AS hour,
       w.offset_h AS offset_h,
       o.present  AS present,
       if(o.msgs = 0, NULL, toNullable(round(1 - o.moving_msgs / o.msgs, 4))) AS still_share,
       w.ref_hour AS ref_hour,
       if(w.ref_hour IS NULL, NULL, toNullable(r.present)) AS ref_present
FROM winr AS w
INNER JOIN occ AS o ON o.hour = w.hour
LEFT  JOIN occ AS r ON r.hour = assumeNotNull(w.ref_hour) AND r.name = o.name
ORDER BY storm, name, hour
SETTINGS join_use_nulls = 0;
