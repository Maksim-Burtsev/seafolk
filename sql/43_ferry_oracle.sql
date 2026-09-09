-- S8 check — an EXTERNAL ORACLE for sql/40_ferry_trips.sql: recount the
-- Svendborg - Ærøskøbing crossings of July 2025 straight from `public_track`,
-- WITHOUT stays, without runs, without sessions, without route matching, and
-- emit that count next to `ferry_crossing`'s for the same local day so a
-- caller can assert |gap| <= 1 per day (measured max 0; see MEASURED below).
-- Run: scripts/ch.sh sql/43_ferry_oracle.sql  (read-only; 0.5 s, 31 rows)
-- Columns: day, oracle_crossings, table_crossings, gap (= oracle - table),
--          oracle_vessels, table_vessels
--
-- WHY AN ORACLE AND NOT A ROUND TRIP. docs/STATUS.md § S4-redo: the S2 spatial
-- test passed while the whole store was mirrored into the Arabian Sea, because
-- it checked one expression against itself. Same discipline as
-- sql/33_port_oracle.sql. THE TWO SIDES OF THIS FILE SHARE NOTHING BUT TWO
-- 64-BIT INTEGERS — the two hard-coded H3 res-7 cell ids below. In particular
-- the oracle side does NOT use:
--   * `ferry_stay`, `ferry_crossing`, `ferry_day`, `ferry_line`, or any other
--     table sql/40 writes;
--   * the stopped/under-way run-length encoding, the 60-minute session split,
--     the 100 m distance guard or the 30 kn guard;
--   * `ferry_route`, the endpoint extraction, the 1 500 m radius or the
--     h3kRing prefilter;
--   * a hard-coded MMSI. It reads EVERY Class A passenger vessel in the
--     archive and lets the two cells select the traffic.
-- If sql/40's sessionisation lost a crossing, or its route matcher put the Ærø
-- line's crossings on some other OSM object, this file would not follow it.
--
-- THE ORACLE'S DEFINITION OF A CROSSING, in full: take every position of every
-- Class A passenger vessel that falls in one of the two cells; order them by
-- time within the vessel; every time the cell of a position differs from the
-- cell of that vessel's previous in-cell position AND the two sightings are at
-- most 24 HOURS apart, that is one crossing, counted on the LOCAL day of the
-- PREVIOUS position — the last sighting on the departure side, which is the
-- oracle's analogue of `ferry_crossing.dep`. That is all. It cannot tell a
-- ferry from a yacht and does not try to.
-- THE 24-HOUR BOUND is the one piece of judgement in the oracle and it is
-- there because "next seen" alone is not a crossing on any reading: the first
-- build measured three +1 days in July 2025 and every one of them was a
-- sail-training ship (FULTON, JANTJE) lying in Svendborg and turning up in
-- AErOskObing ONE TO TEN DAYS LATER. A vessel that takes more than a day to
-- get 12 nm did not make the crossing this file is counting. The bound shares
-- nothing with sql/40, which has no such rule anywhere: its equivalent guards
-- are a 60-minute position gap, 100 m and 30 kn.
--
-- THE TWO CELLS, computed once from the two harbours and hard-coded here as
-- literals so this file does not depend on any coordinate the rest of the
-- project stores:
--   608531604905656319  Svendborg ferry berth, geoToH3(55.058, 10.615, 7)
--   608531599906045951  Ærøskøbing,            geoToH3(54.892, 10.413, 7)
-- Both were checked against the geometry sql/40 actually matches on: the two
-- endpoints of OSM way 33847154 in `ferry_route` are (10.6147914, 55.057768)
-- and (10.4127177, 54.8915321) — (lon, lat), the sql/04 order — and
-- geoToH3(55.057768, 10.6147914, 7) and geoToH3(54.8915321, 10.4127177, 7)
-- return exactly these two ids. The Svendborg one is also sql/33's cell, so a
-- mirrored store would break this file and sql/33 at once.
-- COORDINATE ORDER: geoToH3 takes (LAT, LON, res) under scripts/ch.sh's pins.
-- The `check_` columns at the bottom recompute both ids from the literals in
-- this comment every run, so a future ClickHouse that flips the argument order
-- again shows up as two changed numbers instead of as an empty result.
--
-- WHY WAY 33847154 IS THE ONLY ROUTE ON THE TABLE SIDE: it is the only object
-- in `ferry_route` (of 1 324) with one endpoint within 1 500 m of the
-- Svendborg berth AND another within 1 500 m of Ærøskøbing, so sql/40 has no
-- competing candidate to put these crossings on. Checked, 2026-09-09.
-- The table side deliberately keys on `route_type`/`route_id`, NOT on
-- `ferry_crossing.line`: `line` is the output of the fold and the floor that
-- sql/40 applies, and an oracle that shared those would stop being one.
--
-- WHY THE TWO SIDES CAN LEGITIMATELY DIFFER — read this before touching the
-- bound:
--   1. DIFFERENT CLOCKS FOR THE SAME TRIP. `dep` is the last second the vessel
--      was STOPPED at the Svendborg berth; the oracle's timestamp is the last
--      sighting anywhere inside the ~5 km res-7 cell, which is several minutes
--      later. A sailing that leaves near local midnight can therefore be filed
--      on different days by the two sides — one day reads +1, the next -1.
--   2. THE CELL IS NOT THE BERTH. A vessel that enters the Svendborg cell,
--      turns around WITHOUT EVER STOPPING and leaves for AErOskObing is a
--      crossing to the oracle and is not one to sql/40, which needs a stopped
--      run at both ends. (sql/40 has no minimum stay LENGTH any more — one
--      stopped position is a berth call — so this is now a narrower difference
--      than it was: the vessel has to never drop below 0.5 kn.)
--   3. GUARDS ONLY sql/40 HAS: a coverage gap > 60 min inside the passage ends
--      the session and the crossing with it; two berth centroids closer than
--      100 m are not a crossing; an implied speed over 30 kn is not a
--      crossing. And sql/40 drops positions with no speed field, where this
--      file keeps them — a cell transition needs a position, not a speed.
--   4. OTHER TRAFFIC, AND THE ORACLE HAS NO CLOCK OF ITS OWN. Any Class A
--      passenger vessel passing through both cells in sequence is a crossing
--      to the oracle, bounded only by the 24 h rule above.
--   5. A crossing that starts on 2025-06-30 and lands on 2025-07-01, or the
--      mirror at the end of the month, is filed by `dep`/previous-sighting on
--      the departure day, so the month edges are consistent on both sides —
--      but the oracle reads a wider UTC window on purpose (see `win`) so that
--      the first local day of July has a real predecessor position.
--
-- MEASURED, July 2025, against the current sql/40 (no stay threshold, 100 m
-- distance guard, nearest-endpoint route match, sog-less positions dropped;
-- and the 24 h bound on this side). Both sides read 22 crossings a day for the
-- whole month and ALL 31 DAYS AGREE EXACTLY: max |gap| = 0.
-- SO THE ASSERT BOUND IS |gap| <= 1 — the measured maximum plus one. The
-- margin is a full crossing on every day of the month; a red run means a real
-- change, not noise.
-- The two disagreements earlier builds had are both gone, and it is worth
-- recording what fixed each, because they were opposite failures:
--   * 07-04 / 07-09 / 07-15 read +1 with oracle_vessels = 3. Cause: FULTON,
--     JANTJE, FULTON — sail-training ships whose two in-cell sightings were
--     1 to 10 days apart. Fixed on the ORACLE side by the 24 h bound; sql/40
--     was right and this file was wrong.
--   * 07-30 read +2. Cause: sql/40's then 5-minute minimum stay. M/F MARSTAL
--     left AErOskObing at 04:30 UTC, was alongside in Svendborg from 05:57 to
--     06:00 — THREE minutes, sog 0 to 0.1 — and was back in AErOskObing at
--     07:17. Under a 5-minute rule that was not a stay, the out and back
--     collapsed into one AErOskObing-to-AErOskObing pair and the distance
--     guard deleted it: two real sailings, gone. Fixed on the SQL/40 side by
--     dropping the threshold; the oracle was right and sql/40 was wrong.
-- That is the oracle earning its keep in both directions in one month.
--
-- PRIVACY: MMSI is used inside the query as a partition key and nothing but
-- counts is emitted. Ferries are public, but no name is emitted here either —
-- this file is a check, not a chart.

WITH
608531604905656319 AS cell_sv,
608531599906045951 AS cell_ae,
-- one local July, plus a day of run-up on each side in UTC so the first and
-- last local day are computed from a complete neighbourhood.
toDateTime('2025-06-30 00:00:00', 'UTC') AS win0,
toDateTime('2025-08-02 00:00:00', 'UTC') AS win1,
-- ---------------------------------------------------------------------------
-- THE ORACLE SIDE: raw positions, two cell ids, nothing else.
-- ---------------------------------------------------------------------------
pos AS (
    SELECT mmsi, ts, geoToH3(lat, lon, 7) AS cell
    FROM public_track
    WHERE ts >= win0 AND ts < win1
      AND geoToH3(lat, lon, 7) IN (cell_sv, cell_ae)
),
-- lagInFrame's third argument is the default for a partition's first row;
-- feeding it the row's own cell makes that row a non-transition, which is
-- correct — there is no previous sighting to have crossed from.
step AS (
    SELECT mmsi, ts, cell,
           lagInFrame(cell, 1, cell) OVER w AS prev_cell,
           lagInFrame(ts,   1, ts)   OVER w AS prev_ts
    FROM pos
    WINDOW w AS (PARTITION BY mmsi ORDER BY ts
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
oracle AS (
    SELECT toDate(toTimeZone(prev_ts, 'Europe/Copenhagen')) AS day,
           count()           AS crossings,
           uniqExact(mmsi)   AS vessels
    FROM step
    WHERE cell != prev_cell
      AND dateDiff('hour', prev_ts, ts) <= 24
    GROUP BY day
),
-- ---------------------------------------------------------------------------
-- THE TABLE SIDE: what sql/40 wrote, for the same line and the same local days.
-- ---------------------------------------------------------------------------
tbl AS (
    SELECT toDate(toTimeZone(dep, 'Europe/Copenhagen')) AS day,
           count()          AS crossings,
           uniqExact(mmsi)  AS vessels
    FROM ferry_crossing
    WHERE route_type = 'way' AND route_id = 33847154
    GROUP BY day
),
-- the day domain is the calendar, not either side's occupancy: a day on which
-- one side found nothing must still produce a row, or the check passes by
-- being absent.
days AS (
    SELECT toDate('2025-07-01') + number AS day FROM numbers(31)
)
SELECT d.day                                        AS day,
       o.crossings                                  AS oracle_crossings,
       t.crossings                                  AS table_crossings,
       toInt64(o.crossings) - toInt64(t.crossings)  AS gap,
       o.vessels                                    AS oracle_vessels,
       t.vessels                                    AS table_vessels,
       geoToH3(55.058, 10.615, 7)                   AS check_cell_sv,
       geoToH3(54.892, 10.413, 7)                   AS check_cell_ae
FROM days AS d
LEFT JOIN oracle AS o ON o.day = d.day
LEFT JOIN tbl    AS t ON t.day = d.day
ORDER BY day
-- join_use_nulls = 0: under = 1 a day missing from either side comes back NULL
-- and `gap` is NULL too, which reads as "no disagreement" to anything that
-- greps for a non-zero. Zero is the honest value and it fires the assert.
SETTINGS join_use_nulls = 0;
