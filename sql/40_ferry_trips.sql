-- S8 — chapter 03's base layer. It BUILDS FOUR TABLES in the store:
--   ferry_stay      every berth call, from `public_track`
--   ferry_crossing  every move between two berth calls, carrying its LINE
--   ferry_day       per vessel-day position counts, the coverage denominator
--   ferry_line      the committed OSM-object -> line mapping
-- Everything sql/41–44 says about ferry lines is read off these four.
-- Run: scripts/ch.sh sql/40_ferry_trips.sql   (96-110 s, 11.6 GB peak RSS;
--                                              rebuilds all three from scratch)
--
-- This is the first file in the project that WRITES a derived table. It is
-- idempotent by DROP ... SYNC + CREATE + INSERT, the sql/04_context.sql
-- pattern, and for the same reason: CREATE OR REPLACE on an Atomic database
-- defers the real drop by 480 s, `clickhouse local` exits long before that and
-- the bytes stay in data/ch/store forever. SYNC drops before the statement
-- returns.
--
-- ===================================================================
-- COORDINATE ORDER, the trap this project has already paid for once
-- (docs/DECISIONS.md 2026-09-03). Under scripts/ch.sh's pins:
--   * geoToH3(LAT, LON, res)                 — lat first
--   * geoDistance(LON1, LAT1, LON2, LAT2)    — lon first, the geo-type order
--   * ferry_route.geom points are (LON, LAT) — see the banner in sql/04
-- A swap does not error, it mirrors Denmark into the Arabian Sea. sql/43
-- recomputes one line's crossings from two hard-coded cell ids as an external
-- check on all of it.
-- ===================================================================
--
-- WHAT A STAY AND A CROSSING ARE
--   run       a maximal run of consecutive positions of one MMSI with the same
--             stopped/under-way flag, cut additionally at every gap > 60 min.
--   stay      ANY maximal stopped run, of any length — one position is enough.
--             Centroid = mean of its positions.
--   crossing  the move between two CONSECUTIVE stays of the same MMSI inside
--             the same gap-free session, when the two centroids are > 100 m
--             apart. dep = the last second of the first stay, arr = the first
--             second of the second stay. Whether a route matches decides the
--             route columns, NOT whether the row exists — see ROUTE ASSIGNMENT.
--
-- stopped := sog < 0.5, over positions that HAVE a speed. A position whose
-- speed is missing is DROPPED before the run-length encoding rather than
-- guessed at: 725 916 of the 437 970 690 positions (0.17 %) carry sog = -1,
-- the loader's marker for an empty CSV speed field, and 690 carry the AIS
-- 102.3 "speed not available" sentinel (sql/01_schema.sql). Calling them under
-- way splits a berthed stay in two; calling them stopped plants a stay in
-- mid-channel. Dropping the row leaves a hole in TIME, which is what it
-- actually is, and the 60-minute session guard picks the hole up if it is long
-- enough to matter. A -1 inside a stay no longer splits that stay.
-- `ferry_day` counts those positions anyway, in `positions` but not in
-- `sog_known`, so sql/41 can tell "the receiver heard nothing" from "the
-- receiver heard a vessel with no speed field" — 300 vessel-days in this
-- archive are sog = -1 from end to end.
--
-- WHY THERE IS NO STAY THRESHOLD AT ALL. Every minimum tried here deleted
-- real sailings from the shortest lines and bought nothing on the long ones.
-- Crossings per day in July 2025, all other guards fixed (100 m, 60-min
-- session, and the then 40 kn speed guard — now 30 kn, which moves these by
-- ~0.02 %), at a 120 / 60 / 0-second stay threshold:
--   MJOELNER-FUR       63.2 / 108.4 / 136.0     timetable 144
--   EGENSE             72.1 /  88.6 /  92.8
--   M/F HALS EGENSE    24.2 /  26.7 /  27.9
--   AAROE              44.1 /  46.6 /  47.1
--   M/F FENJA          50.5 /  50.8 /  51.4
--   GROTTE             28.4 /  28.9 /  29.8
--   AEROESKOEBING      11.0 /  11.0 /  11.0
--   MARGRETE LAESOE     9.3 /   9.3 /   9.3
-- A THIRD of the Fur ferry's berth calls are shorter than two minutes, and on
-- every line whose crossing lasts more than a few minutes the threshold moves
-- nothing at all. The threshold was only ever a proxy for "this stop is a
-- berth, not a hiccup", and it is a bad one: the discrimination is done
-- properly by the 100 m distance guard and the route match below.
-- THE SPLIT-STAY HYPOTHESIS WAS TESTED BEFORE THE THRESHOLD WAS DROPPED, not
-- assumed away: of MJOELNER-FUR's 3 109 stopped runs of >= 2 min in July 2025,
-- every single one spans less than 100 m and not one straddles the sound. The
-- short stops are berth calls, not a crossing cut in half.
-- THE PRICE, MEASURED, AND IT IS NOT THE ONE THAT WAS EXPECTED. The feared
-- failure was a single slow position in mid-channel splitting a crossing in
-- two. That is not what happens. What happens is INTERMEDIATE PORT CALLS on
-- multi-stop lines: with no threshold, a two-minute call at an island on the
-- way now ends the crossing, and neither half matches a route whose OSM
-- geometry carries only the two EXTREME endpoints.
-- Whole store, 13 of 191 lines lose crossings, 11 678 in total against
-- 1 826 981 gained. Two lines carry 88 % of the loss and both are multi-stop:
--   Svendborg - Skaro - Drejo   12 534 -> 3 285   (-9 249, -74 %)
--   Kappeln - Schleimuende       1 738 ->   699   (-1 039, -60 %)
-- Traced to the position: 13 505 of the now-unmatched crossings berth at
-- 55.0084 N 10.4745 E, which is HJORTO — the island Hojestenefaergen calls at
-- between Svendborg and Drejo. OSM way 93308405 and relation 1356670 both end
-- at Svendborg and Drejo and carry no Hjorto endpoint, so Svendborg->Hjorto
-- and Hjorto->Drejo are two legs of a route that OSM says has two ends.
-- THIS IS AN OSM COVERAGE GAP, NOT A GUARD TO RETUNE: Faaborg - Lyo -
-- Avernako has the same shape and does NOT lose anything, because OSM carries
-- a separate way for each leg pair (36973884, 141509964, 141509969) as well
-- as the relation. The honest fix is per-leg geometry, not a threshold that
-- deletes a third of the Fur ferry to hide it.
-- `minutes` is kept in `ferry_stay` so a caller can re-impose any threshold it
-- wants after the fact.
--
-- THE THREE GUARDS, each with the number that justifies it (whole store):
--   1. gap > 60 min starts a new SESSION, and a crossing is only ever built
--      between two stays of the SAME session. Without it 5 750 573 pairs pass
--      the other two guards instead of 5 664 659 — the 85 914 extra ones have
--      a MEDIAN duration of 651 min and a p90 of 8 793 min (6.1 days). A
--      transponder switched off at the quay is not a crossing, and those rows
--      would otherwise be sql/42's minutes distribution.
--   2. centroid distance > 100 m — NOT 1 km, and this is the guard that was
--      wrong in the first build. A DISTANCE THRESHOLD CANNOT SEPARATE A
--      SAME-BERTH WARP FROM A SHORT CROSSING, because in Denmark the short
--      crossings are the lifelines. Fursund (Branden - Fur, 72 departures per
--      direction per day) is ~400 m wide: MJOELNER-FUR's 1 436 positions on
--      2025-07-10 span 56.8004-56.8037 N, 9.0217-9.0256 E. Hals - Egense is
--      the same (56.986-56.991 N, 10.303-10.305 E). Under a 1 km guard the Fur
--      ferry had SEVENTEEN crossings in the whole store.
--      Histogram of consecutive-stay centroid distances over 2025 — measured
--      at the 2-minute stay threshold this file no longer applies, so the
--      bins are a lower bound on today's counts, and the SHAPE is the point:
--          <  50 m  162 039  (13 min)      400- 500 m   21 960
--         50- 100 m   6 754               500- 700 m   26 422
--        100- 200 m  21 201               700-1000 m   51 546  (7 min)
--        200- 300 m  20 335              1000-1500 m   30 244
--        300- 400 m   2 264                >= 1500 m  429 429
--      There is no gap to cut at: 400 m - 1 km holds ~100 000 REAL short
--      crossings (Fur, Hals - Egense, Aaro 0.6 nm, Nordals 0.9 nm,
--      Gullmarsleden, Alvsnabbare). So the distance guard is set to the value
--      that only removes the degenerate bins (168 793 pairs under 100 m in
--      2025, median 13 min — a ferry shuffling along its own quay), and the
--      work of telling a crossing from a warp is given to the ROUTE MATCH,
--      which has the geometry to do it. Over the whole store: 7 187 875 stays
--      -> 6 827 749 consecutive same-session pairs -> 5 665 957 after the
--      100 m test (1 161 792 dropped, 17.0 %).
--   3. implied speed nm / hours <= 30 kn — lowered from 40 because sql/42's
--      max_kn showed the old bound being touched by ordinary lines rather
--      than by outliers: Hou - Saelvig read 38.15 kn in 2024, 2025 and 2026
--      (10.17 NM in 16 minutes), 12 Danish line-years sat above 30 kn and the
--      store maximum was 39.81 (Kragero - Tangane). NO PASSENGER SHIP IN
--      `public_track` MAKES 30 KN: the high-speed craft are absent by
--      construction (see the HSC note below) and the fastest median crossing
--      in the archive is Hirtshals - Kristiansand at 21.08 kn. A pair that
--      trips this bound is a stay whose centroid is the mean of positions on
--      both sides of a coverage hole, so the distance is real and the elapsed
--      time is not. 1 298 of the 5 665 957 pairs that clear the 100 m test
--      trip it (0.023 %), leaving 5 664 659; at the old 40 kn bound it was
--      1 096. See the counts printed at the end of this file.
--
-- IDENTITY. `name` is the MODAL trimmed name of that MMSI in that calendar
-- year, never the name on the row: raw AIS names carry bit-flipped garbage
-- (`ARMGRETE LAESOE` for ARNGRETE, `HALS EGENSQ "`, `AEROEXPRESSEN     B+`),
-- and a single corrupted message would otherwise fork one ferry into two.
-- Ferries and commercial vessels are PUBLIC and may be named (CLAUDE.md);
-- `public_track` holds Class A passenger ships only, so nothing private can
-- reach these tables.
-- PRIVACY: both tables carry MMSI, which is allowed — they live in data/ch and
-- never leave the machine, exactly like `vessel_day`. NO OUTPUT OF sql/41–43
-- CONTAINS AN MMSI; they emit route-level and vessel-count columns only.
--
-- ROUTE ASSIGNMENT is by GEOMETRY, not by tags: the OSM `from`/`to` tags are
-- empty on 1 049 of the 1 324 rows of `ferry_route` and 363 rows have no name
-- at all. The first and last point of every way in `geom` are the route's
-- endpoints — for a RELATION only its two TERMINI, see the endpoint rule in
-- the body. A
-- crossing matches a route when one berth is within 1 500 m of one endpoint
-- AND the other berth within 1 500 m of a DIFFERENT endpoint of the SAME
-- route; among the candidates the smallest summed distance wins, and that sum
-- is emitted as `end_dist_m` so sql/41 can show how tight the match is.
-- "A DIFFERENT ENDPOINT" MEANS THE NEAREST ONES DIFFER, not merely that two
-- distinct endpoints can be found within the radius. On a 400 m strait both
-- berths sit inside 1 500 m of both ends of the line, so the weaker test lets
-- a 200 m shuffle inside the Fur harbour match as a crossing at
-- d = 50 + 400 m. Computing each berth's NEAREST endpoint first and then
-- demanding the two differ rejects it: an intra-harbour move has one nearest
-- endpoint, not two. This is what carries the load now that the distance guard
-- is only 100 m, and it is why the unmatched share is higher than in the first
-- build — every 100 m-to-1 km harbour shuffle now reaches the matcher and
-- fails it. sql/41's second block splits the unmatched by distance so that
-- rise is visible as what it is.
-- Unmatched crossings are KEPT with route_type = '', route_id = 0,
-- route_name = '' — sql/41's second block reports their share per year.
-- The 1 500 m radius is prefiltered through h3kRing(cell_res7, 1) — without it
-- this is a 5.7 M x 4.6 k cross join. THE PREFILTER IS JUSTIFIED BY
-- MEASUREMENT, NOT BY GEOMETRY: an earlier version of this comment claimed
-- ring 1 covers at least 1.96 km around any point of the centre cell, and that
-- is wrong — a res-7 cell's own vertex is only ~1 215 m from the ring-2
-- boundary against an edge of ~1 406 m, so a 1 500 m match CAN in principle
-- sit outside ring 1. It does not here: re-running the match with
-- h3kRing(..., 2) gains a route for 0 of the 508 895 unmatched crossings.
-- Re-run that check if the radius, the resolution or the endpoint rule change.
-- Where the OSM name is empty the label falls back to `from` – `to` (73 of the
-- 363 nameless rows have both), else ''.
--
-- MEMORY. One window pass over all 437 970 690 positions, PARTITION BY mmsi
-- ORDER BY ts. The whole file is 96-110 s wall / 560 s user CPU at an 11.6 GB
-- max RSS, measured with /usr/bin/time -l on the full store, under
-- the 21.6 GB self-cap of clickhouse local on this 24 GB machine. It is
-- deliberately NOT split per year — a per-year loop would cut every stay and
-- crossing that straddles New Year at midnight, and the whole-table pass fits.
-- If a future load doubles the archive and this dies with
-- MEMORY_LIMIT_EXCEEDED, add `WHERE toYear(ts) = ...` and run the INSERT once
-- per year, accepting that split.
--
-- WHAT IS NOT HERE AND CANNOT BE: HIGH-SPEED CRAFT. `sql/03_aggregate.sql`
-- maps `ship_type = 'HSC'` to ship_group 'other', and `public_track` is filled
-- from ship_group 'passenger' only, so the 475 HSC vessels in the archive
-- (785 M messages) never reach this file. Those are Molslinjen's Express
-- ferries on Aarhus - Odden and Ronne - Ystad and Bornholm's fast ferries —
-- i.e. some of the busiest passenger lines in the country. It is a LOAD-TIME
-- fact: fixing it means re-aggregating the archive, not editing this file.
-- The visible symptom is Ronne - Ystad reading 414 crossings, all of them the
-- conventional ships (POVL ANKER, HAMMERSHUS, HAMMERODDE as relief) while the
-- fast ferries that carry most of the traffic are absent. Any statement this
-- chapter makes about a line served by HSC is a statement about its
-- conventional tonnage only. (docs/DECISIONS.md, written by the S8 session.)
--
-- ClickHouse forbids NESTED window functions, so every derived running value
-- is its own CTE — `chg` -> `seg` -> `idx` — the same chain the S8 probe used.

-- ===================================================================
-- A CRASH LEAVES THE PREVIOUS COMPLETE TABLES, OR NONE.
-- Every table is built under a `__build` name and the four are swapped into
-- place by ONE `RENAME TABLE` at the end. This is not tidiness. `clickhouse
-- local` does not roll an INSERT back: a killed INSERT leaves the parts it had
-- already written (demonstrated on a throwaway store — 1 048 576 rows of a
-- table whose INSERT threw), and the statements after it never run. Building
-- in place therefore left a COMPLETE `ferry_stay`, a PARTIAL `ferry_crossing`
-- missing whole vessels, and the scratch tables — and sql/41 read that without
-- an error and answered. With the swap, a death anywhere before the RENAME
-- leaves the previous generation intact and untouched; the leftover `__build`
-- and scratch tables are dropped at the START of the next run, below.
-- ===================================================================
DROP TABLE IF EXISTS ferry_stay__build SYNC;
DROP TABLE IF EXISTS ferry_crossing__build SYNC;
DROP TABLE IF EXISTS ferry_line__build SYNC;
DROP TABLE IF EXISTS ferry_day__build SYNC;
-- Scratch. Dropped at the bottom too; they exist because the alternative is a
-- second window pass over 438 M positions.
DROP TABLE IF EXISTS ferry_run SYNC;
DROP TABLE IF EXISTS ferry_name SYNC;
DROP TABLE IF EXISTS ferry_xing SYNC;
DROP TABLE IF EXISTS ferry_rl SYNC;


-- --- ferry_line: OSM objects -> the LINE a reader knows ------------
-- One physical service is several OSM objects: Helsingor - Helsingborg is
-- SEVEN of them (three relations for the two directions plus four ways),
-- Rodby - Puttgarden four, Faaborg - Lyo - Avernako four. Grouping the chapter
-- by route_id would rank one line three times and split its traffic three
-- ways. `data/context/ferry_lines.csv` is the hand-made mapping — COMMITTED,
-- like storms.csv and regattas.csv, because it has no machine source — from
-- every route with >= 200 crossings to a line label, a kind and, for the
-- Danish small-island lifelines, the island.
-- FIVE KINDS:
--   island         a Danish small-island lifeline
--   domestic       a Danish line that is not an island lifeline
--   international  exactly one end in Denmark
--   foreign        neither end in Denmark — the Goteborg archipelago, the
--                  Nord-Ostsee-Kanal ferries, the Wadden Sea, Ruegen, the
--                  Baltic long-haul lines. Kept because they are in the bbox
--                  and they are the contrast.
--   harbour        NOT A SERVICE. An OSM ferry object that is an intra-harbour
--                  leg: both of its ends are berths in the same port, so every
--                  crossing it matches is a ferry moving between quays. FIVE
--                  of them clear the 200-crossing floor and each gets its OWN
--                  line label rather than being folded into the service whose
--                  name OSM gave it:
--                    way 24329730    30 984 crossings, median 0.058 NM
--                    way 1085653368     956 crossings, median 0.089 NM
--                    way 1085653369     225 crossings, median 0.185 NM
--                    way 1094196406     690 crossings, ALL under 1 km
--                    way 1090884525     205 crossings, ALL under 1 km
--                  Folded in, the first three put ~32 000 sub-1 km shuffles
--                  into Ockero - Groto and way 1094196406 put 690 into a
--                  93 NM Swinoujscie - Ystad. (Way 474600164 was suspected of
--                  the first and is NOT guilty — 77 of its 42 479 crossings
--                  are under 1 km and its median is 0.83 NM, so it stays with
--                  the service.) They are EMITTED by
--                  sql/41, 42 and 44 like any other line, carrying
--                  kind = 'harbour'; a consumer that wants services filters
--                  them out. Nothing is deleted, because the crossings are
--                  real ship movements — they are just not sailings.
--                  The `note` column of those three rows says which line each
--                  would otherwise pollute.
-- Two entries deviate from the rule and say so in their `note`: ROmO - Sylt is
-- filed domestic although it is DK-DE, and the Bornholm lines to Ystad and
-- Sassnitz are filed island because the line is a Bornholm lifeline whichever
-- flag the far quay flies.
-- THERE IS NO FALLBACK LABEL ANY MORE. A route that clears the floor and has
-- no row here gets line = '' and the build FAILS at the throwIf below. The old
-- `osm_type:osm_id` fallback was worse than useless: it put a 9-digit OSM id
-- into a text column, which is indistinguishable from an MMSI to the privacy
-- grep that guards every output of this chapter.
-- Rows for routes BELOW the floor are kept on purpose — they cost one
-- unmatched LEFT JOIN row each and they make the mapping survive a change to
-- a guard in this file, since which of several identical-geometry objects wins
-- a crossing is decided by the tie-break in `best` below.
-- Strict parse settings, the sql/04_context.sql reasoning: a renamed header
-- column must be an error, not a silently defaulted column.
-- scripts/test_context.sh asserts the header of this file verbatim.
CREATE TABLE ferry_line__build
(
    line     String,
    kind     LowCardinality(String),
    island   String,
    osm_type LowCardinality(String),
    osm_id   UInt64,
    note     String
)
ENGINE = MergeTree
ORDER BY (osm_type, osm_id);

INSERT INTO ferry_line__build
SELECT * FROM file('data/context/ferry_lines.csv', CSVWithNames,
    'line String, kind String, island String, osm_type String, osm_id UInt64, note String')
SETTINGS input_format_skip_unknown_fields = 0,
         input_format_defaults_for_omitted_fields = 0;


-- --- scratch: the modal name per MMSI-year -------------------------
-- Empty names are excluded from the vote, not counted as a candidate; a vessel
-- that never reports a name in a year simply has no row here and comes out of
-- the LEFT JOINs below as ''.
CREATE TABLE ferry_name (mmsi UInt32, year UInt16, name String)
ENGINE = MergeTree ORDER BY (mmsi, year);

INSERT INTO ferry_name
WITH nc AS (
    SELECT mmsi, toYear(ts) AS year, trim(BOTH ' ' FROM name) AS nm, count() AS c
    FROM public_track
    WHERE nm != ''
    GROUP BY mmsi, year, nm
)
-- tuple(c, nm), not c: two names with the same message count would otherwise
-- be broken arbitrarily and the table would not rebuild to the same bytes.
SELECT mmsi, year, argMax(nm, tuple(c, nm)) FROM nc GROUP BY mmsi, year;


-- --- ferry_day: the coverage denominator ---------------------------
-- One row per (vessel, UTC day) over the WHOLE of `public_track`, counted
-- before any speed filter. sql/41 turns it into the answer to "did this line's
-- fleet report at all today", which is the difference between a cancellation
-- and a receiver gap.
-- It exists because sql/41 used to read `vessel_day.msgs` and that number
-- cannot tell the two apart: a day whose speed field is empty from end to end
-- has a perfectly normal message count. 300 vessel-days in this archive are
-- ENTIRELY sog = -1 (297 214 positions), and under the old coverage column
-- they produced no stay, no crossing and full coverage — 258 island line-days
-- on Havnso - Sejero, Stigsnaes - Omo, Stigsnaes - Agerso and Havnso - Nekselo
-- read as cancellations, from 2021-09-30 to 2025-07-16.
--   positions  every row in public_track that day
--   sog_known  those with a usable speed: 0 <= sog < 100. sog = -1 is the
--              loader's empty-field marker and 102.3 is the AIS "speed not
--              available" sentinel (sql/01_schema.sql).
--   moving     those with 1 <= sog < 100. One knot, not 0.5: this column is
--              read as "was the fleet under way at all", and a berthed ferry
--              reports 0.1-0.9 kn all day.
--   name       the modal name of that vessel in that calendar year, so the
--              table can be read without joining anything.
-- PRIVACY: it holds MMSI, like `ferry_stay` and `ferry_crossing` and for the
-- same reason — it lives in data/ch and never leaves the machine. sql/41 emits
-- only sums over a set of vessels.
CREATE TABLE ferry_day__build
(
    mmsi      UInt32,
    day       Date,                    -- UTC. See sql/41 on the local-day skew.
    positions UInt32,
    sog_known UInt32,
    moving    UInt32,
    name      String
)
ENGINE = MergeTree
ORDER BY (mmsi, day);

INSERT INTO ferry_day__build
SELECT p.mmsi AS mmsi, toDate(p.ts) AS day,
       count()                                        AS positions,
       countIf(p.sog >= 0 AND p.sog < 100)            AS sog_known,
       countIf(p.sog >= 1 AND p.sog < 100)            AS moving,
       any(nm.name)                                   AS name
FROM public_track AS p
LEFT JOIN ferry_name AS nm ON nm.mmsi = p.mmsi AND nm.year = toYear(p.ts)
GROUP BY mmsi, day
SETTINGS join_use_nulls = 0;


-- --- scratch: every run, stopped or under way ----------------------
-- `sog_q` is a quantile STATE, not a number, because a crossing's med_sog is
-- the median over the positions between two stays and those positions live in
-- one UNDER-WAY run — with no stay threshold, runs alternate strictly
-- stopped/under-way inside a session, so a crossing is exactly one moving run.
-- Merging the states is still how the median is obtained without joining
-- 438 M positions back onto the runs.
-- quantileDETERMINISTIC, not quantile: ClickHouse's plain `quantile` is
-- reservoir sampling off a random number generator, so med_sog — and every
-- number sql/42 derives from it — came out different on every rebuild of
-- identical input. The determinator is the position's timestamp, which makes
-- the sample a function of the data. Same accuracy, same state size.
CREATE TABLE ferry_run
(
    mmsi    UInt32,
    sess    UInt32,                    -- gap-free session index within the MMSI
    t0      DateTime('UTC'),
    t1      DateTime('UTC'),
    stopped UInt8,
    lat     Float64,
    lon     Float64,
    n       UInt32,
    sog_q   AggregateFunction(quantileDeterministic(0.5), Float32, UInt64)
)
ENGINE = MergeTree
ORDER BY (mmsi, sess, t0);

INSERT INTO ferry_run
WITH
-- POSITIONS WITH NO SPEED ARE NOT EVIDENCE OF ANYTHING AND ARE DROPPED HERE.
-- sog = -1 is an empty CSV field; treating it as under way (what this file did
-- before) split a berthed stay in two, and treating it as stopped would plant
-- a stay in mid-channel. Dropping the row leaves a hole in time instead, which
-- is what it is; if the hole is longer than an hour the session guard below
-- picks it up. 725 916 of 437 970 690 positions (0.17 %). A -1 inside a stay
-- no longer splits that stay.
pts AS (
    SELECT mmsi, ts, lat, lon, sog, sog < 0.5 AS stopped
    FROM public_track
    WHERE sog >= 0
),
-- c = the stopped flag flipped, g = a coverage gap longer than an hour.
-- lagInFrame's third argument is the DEFAULT for the first row of a partition;
-- feeding it the row's own value makes the first row a non-change, which is
-- what a run boundary at the start of a partition already is.
chg AS (
    SELECT mmsi, ts, lat, lon, sog, stopped,
           stopped != lagInFrame(stopped, 1, stopped) OVER w              AS c,
           dateDiff('second', lagInFrame(ts, 1, ts) OVER w, ts) > 3600    AS g
    FROM pts
    WINDOW w AS (PARTITION BY mmsi ORDER BY ts
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
seg AS (
    SELECT mmsi, ts, lat, lon, sog, stopped,
           sum(g)                     OVER w AS sess,
           sum(toUInt8(c OR g))       OVER w AS seg_id
    FROM chg
    WINDOW w AS (PARTITION BY mmsi ORDER BY ts
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT mmsi, sess, min(ts), max(ts), any(stopped),
       avg(lat), avg(lon), count(),
       quantileDeterministicState(0.5)(sog, toUInt64(ts))
FROM seg
GROUP BY mmsi, sess, seg_id;


-- --- ferry_stay ----------------------------------------------------
-- h3_8, not the project's usual res 7: a res-7 cell (~5 km across) holds both
-- ends of the shortest crossings in this archive, so at res 7 a berth is not a
-- place. Res 8 is ~0.46 km edge, which separates two quays in one harbour.
-- Route matching below still prefilters on res 7 — that is a lookup grid, not
-- an identity.
CREATE TABLE ferry_stay__build
(
    mmsi    UInt32,
    name    String,
    t0      DateTime('UTC'),
    t1      DateTime('UTC'),
    minutes UInt32,
    lat     Float64,
    lon     Float64,
    h3_8    UInt64                     -- geoToH3(lat, lon, 8), (lat, lon) order
)
ENGINE = MergeTree
ORDER BY (mmsi, t0);

INSERT INTO ferry_stay__build
SELECT r.mmsi, nm.name, r.t0, r.t1,
       dateDiff('minute', r.t0, r.t1) AS minutes,
       r.lat, r.lon, geoToH3(r.lat, r.lon, 8)
FROM ferry_run AS r
LEFT JOIN ferry_name AS nm ON nm.mmsi = r.mmsi AND nm.year = toYear(r.t0)
WHERE r.stopped
SETTINGS join_use_nulls = 0;


-- --- scratch: the crossings, before they know their line -----------
-- Two stages, because the 200-crossing floor is a property of the finished
-- table: the crossings have to exist before a route can be counted, and the
-- line label depends on that count.
CREATE TABLE ferry_xing
(
    mmsi        UInt32,
    name        String,
    dep         DateTime('UTC'),
    arr         DateTime('UTC'),
    minutes     UInt32,
    nm          Float32,
    lat_a       Float64,
    lon_a       Float64,
    lat_b       Float64,
    lon_b       Float64,
    h3_a        UInt64,
    h3_b        UInt64,
    med_sog     Float32,
    route_type  LowCardinality(String),
    route_id    UInt64,
    route_name  String,
    end_dist_m  Float32
)
ENGINE = MergeTree
ORDER BY (mmsi, dep);

INSERT INTO ferry_xing
WITH
-- k = how many stays this MMSI has completed in this session up to and
-- including this run. A stay run carries its OWN index; the under-way run that
-- follows it carries the same k, which is what pairs a crossing's speed
-- samples with its departure stay.
idx AS (
    SELECT mmsi, sess, t0, t1, lat, lon, sog_q, stopped AS is_stay,
           sum(stopped) OVER
               (PARTITION BY mmsi, sess ORDER BY t0
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS k
    FROM ferry_run
),
-- consecutive stays, paired. leadInFrame past the last stay of a session
-- returns the zero default, and `arr > dep` drops that row — which is exactly
-- the guard that stops a crossing from spanning a coverage gap.
pair AS (
    SELECT mmsi, sess, k, t1 AS dep, lat AS lat_a, lon AS lon_a,
           leadInFrame(t0)  OVER w AS arr,
           leadInFrame(lat) OVER w AS lat_b,
           leadInFrame(lon) OVER w AS lon_b
    FROM idx
    WHERE is_stay
    WINDOW w AS (PARTITION BY mmsi, sess ORDER BY k
                 ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING)
),
-- the speed samples of the move. Runs alternate stopped/under-way inside a
-- session by construction, so every paired stay has exactly one under-way run
-- after it and this INNER JOIN drops nothing.
spd AS (
    SELECT mmsi, sess, k, quantileDeterministicMerge(0.5)(sog_q) AS med_sog
    FROM idx WHERE NOT is_stay
    GROUP BY mmsi, sess, k
),
x AS (
    SELECT p.mmsi AS mmsi, p.dep AS dep, p.arr AS arr,
           p.lat_a AS lat_a, p.lon_a AS lon_a, p.lat_b AS lat_b, p.lon_b AS lon_b,
           s.med_sog AS med_sog,
           geoDistance(p.lon_a, p.lat_a, p.lon_b, p.lat_b) AS metres,
           geoToH3(p.lat_a, p.lon_a, 7) AS cell_a,
           geoToH3(p.lat_b, p.lon_b, 7) AS cell_b
    FROM pair AS p
    INNER JOIN spd AS s ON p.mmsi = s.mmsi AND p.sess = s.sess AND p.k = s.k
    WHERE p.arr > p.dep
      AND metres > 100
      AND (metres / 1852) / (dateDiff('second', p.dep, p.arr) / 3600.) <= 30
),
-- --- the route endpoints -------------------------------------------
-- A BARE WAY has two endpoints, its first and last point, and that is that.
-- A RELATION does not: `geom` holds one entry per MEMBER WAY (sql/04 refuses
-- to stitch them, because their order and direction in the relation are not
-- guaranteed and a wrong stitch draws a ferry through land), so taking every
-- member way's two ends gives the line's two TERMINI *and* every junction
-- between consecutive member ways. Two junction points 200 m apart are two
-- different "endpoints" of the same route, and a harbour shuffle inside one
-- quay then matched as a crossing of the whole line: Ockero - Groto had
-- 31 159 of 111 794 crossings under 1 km, Alvsnabben 18 719 of 120 836,
-- Swinoujscie - Ystad 925 of 4 903 on a 93 NM line (p05 0.12 NM),
-- Frederikshavn - Goteborg 196 of 13 035.
-- The fix is the definition of a terminus: a way end that NO OTHER member way
-- of the same relation ends within 50 m of. A junction is where two member
-- ways meet, so it appears twice and is dropped; a terminus appears once and
-- survives. Bare ways are untouched by the rule.
ends AS (
    SELECT osm_type, osm_id,
           if(name != '', name,
              if(from != '' AND to != '', concat(from, ' - ', to), '')) AS rname,
           arrayFlatten(arrayMap(i -> [(i, geom[i][ 1].1, geom[i][ 1].2),
                                       (i, geom[i][-1].1, geom[i][-1].2)],
                                 arrayEnumerate(geom))) AS raw,
           arrayDistinct(arrayMap(z -> (z.2, z.3),
               arrayFilter(v -> osm_type = 'way'
                             OR NOT arrayExists(u -> u.1 != v.1
                                    AND geoDistance(v.2, v.3, u.2, u.3) <= 50, raw),
                           raw))) AS pts
    FROM ferry_route
),
ep AS (
    SELECT osm_type, osm_id, rname,
           arrayJoin(arrayZip(arrayEnumerate(pts), pts)) AS e,
           e.1   AS ekey,
           e.2.1 AS elon,              -- geom points are (LON, LAT)
           e.2.2 AS elat
    FROM ends
),
-- The 1 500 m radius is prefiltered through h3kRing(cell_res7, 1) so this is
-- not a 5.7 M x 4.6 k cross join. The prefilter is justified BY MEASUREMENT,
-- not by geometry: a res-7 cell's own vertex is only ~1 215 m from the ring-2
-- boundary (edge ~1 406 m), so ring 1 does NOT provably cover 1 500 m from
-- every point of the centre cell. Re-run with h3kRing(..., 2) and compare:
-- 0 of the 469 935 unmatched crossings gain a match. Keep the check if the
-- radius or the resolution ever changes.
ring AS (
    SELECT osm_type, osm_id, rname, ekey, elon, elat,
           arrayJoin(h3kRing(geoToH3(elat, elon, 7), 1)) AS cell
    FROM ep
),
ca AS (
    SELECT x.mmsi AS mmsi, x.dep AS dep, r.osm_type AS ot, r.osm_id AS oid,
           r.rname AS rname, r.ekey AS ekey,
           geoDistance(x.lon_a, x.lat_a, r.elon, r.elat) AS d
    FROM x INNER JOIN ring AS r ON x.cell_a = r.cell
),
cb AS (
    SELECT x.mmsi AS mmsi, x.dep AS dep, r.osm_type AS ot, r.osm_id AS oid,
           r.ekey AS ekey,
           geoDistance(x.lon_b, x.lat_b, r.elon, r.elat) AS d
    FROM x INNER JOIN ring AS r ON x.cell_b = r.cell
),
-- THE NEAREST endpoint of this route to this berth, chosen BEFORE the 1 500 m
-- test and not after it. That order is the anti-warp rule: on a 400 m strait
-- both berths are inside 1 500 m of BOTH endpoints, so a test that merely
-- asks for two different endpoints out of the candidate set can pair a 200 m
-- shuffle inside one harbour with the far end of the line. Nearest-first
-- cannot: a move that stays in one harbour has the SAME nearest endpoint at
-- both ends and is rejected.
-- The output names differ from the input names on purpose: ClickHouse inlines
-- CTEs, and a column called `d` that is defined as min(d) reads back as an
-- aggregate inside an aggregate one level up (ILLEGAL_AGGREGATION).
na AS (
    SELECT mmsi, dep, ot, oid, any(rname) AS rname_a,
           argMin(ekey, tuple(d, ekey)) AS ekey_a, min(d) AS dist_a
    FROM ca GROUP BY mmsi, dep, ot, oid
),
nb AS (
    SELECT mmsi, dep, ot, oid, argMin(ekey, tuple(d, ekey)) AS ekey_b, min(d) AS dist_b
    FROM cb GROUP BY mmsi, dep, ot, oid
),
-- EVERY argMin HERE CARRIES A TIE-BREAKER IN ITS SORT KEY, and it is not
-- cosmetic. OSM holds the same physical line several times over — relation
-- 20202075 and way 1476699074 have IDENTICAL endpoints on Helsingor -
-- Helsingborg — so `min(dist_a + dist_b)` is an exact tie and a bare argMin
-- picks whichever row the aggregator saw first. Two runs then assign the same
-- crossing to different OSM objects, marginal routes cross the 200-crossing
-- floor in one run and not the other, and sql/41 emits a different number of
-- rows each time (measured: 250 622 and 251 585 from two consecutive builds of
-- identical input). Sorting on (distance, id) makes the choice a property of
-- the data.
best AS (
    SELECT na.mmsi AS mmsi, na.dep AS dep,
           argMin(tuple(na.ot, na.oid, na.rname_a),
                  tuple(na.dist_a + nb.dist_b, na.oid, na.ot)) AS r,
           min(na.dist_a + nb.dist_b) AS end_dist_m
    FROM na INNER JOIN nb
        ON na.mmsi = nb.mmsi AND na.dep = nb.dep AND na.ot = nb.ot AND na.oid = nb.oid
    WHERE na.ekey_a != nb.ekey_b        -- the two berths' NEAREST ends differ
      AND na.dist_a <= 1500 AND nb.dist_b <= 1500
    GROUP BY mmsi, dep
)
SELECT x.mmsi, nm.name, x.dep, x.arr,
       dateDiff('minute', x.dep, x.arr) AS minutes,
       x.metres / 1852                  AS nm,
       x.lat_a, x.lon_a, x.lat_b, x.lon_b,
       geoToH3(x.lat_a, x.lon_a, 8), geoToH3(x.lat_b, x.lon_b, 8),
       x.med_sog,
       tupleElement(b.r, 1), tupleElement(b.r, 2), tupleElement(b.r, 3), b.end_dist_m
FROM x
LEFT JOIN best       AS b  ON b.mmsi  = x.mmsi AND b.dep  = x.dep
LEFT JOIN ferry_name AS nm ON nm.mmsi = x.mmsi AND nm.year = toYear(x.dep)
-- join_use_nulls = 0 is load-bearing on BOTH left joins: under = 1 an
-- unmatched crossing comes back with NULL route columns and a NULL name, the
-- INSERT then fails on the non-nullable columns instead of writing the ''/0
-- sentinel this file promises. Same pin as sql/31 and sql/33.
SETTINGS join_use_nulls = 0;


-- --- scratch: route -> line, the floor resolved once ---------------
-- THE FOLD AND THE FLOOR LIVE HERE AND NOWHERE ELSE. They used to be a
-- verbatim copy of the same three CTEs in sql/41 and sql/42, and sql/44 would
-- have been a third; a floor changed in one file and not the others is a
-- silent disagreement between two charts of the same chapter. Now
-- `ferry_crossing.line` is written once and every query file is
-- `WHERE line != '' GROUP BY line`.
CREATE TABLE ferry_rl
(
    route_type LowCardinality(String),
    route_id   UInt64,
    line       String,
    kind       LowCardinality(String),
    island     String
)
ENGINE = MergeTree
ORDER BY (route_type, route_id);

INSERT INTO ferry_rl
SELECT e.route_type, e.route_id, l.line, l.kind, l.island
FROM (
    SELECT route_type, route_id
    FROM ferry_xing
    WHERE route_id != 0
    GROUP BY route_type, route_id
    HAVING count() >= 200
) AS e
LEFT JOIN ferry_line__build AS l
       ON l.osm_id = e.route_id AND l.osm_type = e.route_type
SETTINGS join_use_nulls = 0;

-- THE BUILD STOPS HERE IF THE MAPPING HAS A HOLE. A route that clears the
-- floor with no `ferry_line` row would silently vanish from every chart in the
-- chapter, because sql/41/42/44 all filter on `line != ''`. The old fallback
-- hid exactly that: 30 routes were reaching the charts under an OSM name or an
-- `osm_type:osm_id` string, and one service (Swinoujscie - Ystad) was two
-- lines because a second OSM object fell back to the hyphenated OSM spelling.
-- This runs BEFORE the RENAME, so a hole leaves the previous tables in place.
-- Two statements, because throwIf's message has to be a CONSTANT: the first
-- names the offenders, the second stops the build.
SELECT 'UNMAPPED ROUTE — add it to data/context/ferry_lines.csv' AS problem,
       route_type, route_id
FROM ferry_rl WHERE line = ''
ORDER BY route_type, route_id;

SELECT throwIf(count() > 0,
               'sql/40: a route with >= 200 crossings has no row in data/context/ferry_lines.csv. They are listed by the SELECT immediately above. Add them and re-run. The store still holds the PREVIOUS complete ferry_stay / ferry_crossing / ferry_day / ferry_line: this check runs before the RENAME.')
       AS ferry_line_covers_every_eligible_route
FROM ferry_rl WHERE line = '';


-- --- ferry_crossing ------------------------------------------------
CREATE TABLE ferry_crossing__build
(
    mmsi        UInt32,
    name        String,
    dep         DateTime('UTC'),
    arr         DateTime('UTC'),
    minutes     UInt32,
    nm          Float32,               -- great-circle between the two centroids
    lat_a       Float64,
    lon_a       Float64,
    lat_b       Float64,
    lon_b       Float64,
    h3_a        UInt64,
    h3_b        UInt64,
    med_sog     Float32,               -- median sog of the positions in between
    route_type  LowCardinality(String),-- '' when unmatched
    route_id    UInt64,                -- 0 when unmatched
    route_name  String,                -- '' when unmatched or unnamed in OSM
    end_dist_m  Float32,               -- berth-to-endpoint distances, summed
    line        String,                -- '' when unmatched OR below the floor
    kind        LowCardinality(String),
    island      String
)
ENGINE = MergeTree
ORDER BY (line, dep, mmsi);

INSERT INTO ferry_crossing__build
SELECT x.*, rl.line, rl.kind, rl.island
FROM ferry_xing AS x
LEFT JOIN ferry_rl AS rl
       ON rl.route_id = x.route_id AND rl.route_type = x.route_type
SETTINGS join_use_nulls = 0;


-- --- the swap ------------------------------------------------------
DROP TABLE IF EXISTS ferry_stay SYNC;
DROP TABLE IF EXISTS ferry_crossing SYNC;
DROP TABLE IF EXISTS ferry_line SYNC;
DROP TABLE IF EXISTS ferry_day SYNC;
RENAME TABLE ferry_stay__build     TO ferry_stay,
             ferry_crossing__build TO ferry_crossing,
             ferry_line__build     TO ferry_line,
             ferry_day__build      TO ferry_day;

DROP TABLE IF EXISTS ferry_run SYNC;
DROP TABLE IF EXISTS ferry_name SYNC;
DROP TABLE IF EXISTS ferry_xing SYNC;
DROP TABLE IF EXISTS ferry_rl SYNC;


-- What was built. Printed every run so a rebuild that silently loses half the
-- archive is visible without a second query. `lines_unmapped` must be 0 — the
-- throwIf above cannot fire after the RENAME, so this is the receipt.
-- The hidden-fleet share is NOT here: it is sql/44's whole subject.
SELECT * FROM
(
              SELECT 'ferry_stay' AS tbl, count() AS rows, uniqExact(mmsi) AS vessels,
                     min(t0) AS first_ts, max(t1) AS last_ts
              FROM ferry_stay
    UNION ALL SELECT 'ferry_crossing', count(), uniqExact(mmsi), min(dep), max(arr)
              FROM ferry_crossing
    UNION ALL SELECT 'ferry_day', count(), uniqExact(mmsi),
                     toDateTime(min(day), 'UTC'), toDateTime(max(day), 'UTC')
              FROM ferry_day
)
ORDER BY tbl;

-- The guards, as counts, so a rebuild that quietly changes one is visible.
SELECT count()                                        AS crossings,
       countIf(route_id = 0)                          AS unmatched,
       round(countIf(route_id = 0) / count(), 4)      AS unmatched_share,
       countIf(route_id = 0 AND nm * 1852 < 1000)     AS unmatched_under_1km,
       countIf(route_id != 0 AND line = '')           AS below_floor,
       uniqExactIf(route_id, route_id != 0)           AS routes_matched
FROM ferry_crossing;

SELECT count()                                  AS ferry_line_rows,
       uniqExact(line)                          AS distinct_lines,
       uniqExactIf(island, kind = 'island')     AS islands,
       (SELECT countIf(line = '') FROM
            (SELECT route_type, route_id, min(line) AS line
             FROM ferry_crossing WHERE route_id != 0
             GROUP BY route_type, route_id HAVING count() >= 200)) AS lines_unmapped
FROM ferry_line;
