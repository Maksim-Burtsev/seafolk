-- S9 check — the two claims chapter 04 leans on hardest, recounted.
-- Run: scripts/ch.sh sql/53_storm_oracle.sql  (read-only; 0.3 s, 8 + 8 rows)
-- Same discipline as sql/33_port_oracle.sql and sql/43_ferry_oracle.sql, and
-- for the reason in docs/STATUS.md § S4-redo: the S2 spatial test passed while
-- the whole store was mirrored into the Arabian Sea, because it checked one
-- expression against itself.
--
-- THE TWO BLOCKS ARE NOT EQUALLY INDEPENDENT, AND THE DIFFERENCE MATTERS.
-- Block 2 IS an oracle: it counts the Ærø crossings from raw `public_track`
-- positions and two hard-coded cell ids, and reads nothing sql/40 wrote.
-- Block 1 IS NOT. `moved_dist` is `uniqExactIf(mmsi, dist_nm >= 1)` over
-- `vessel_day` — the SAME expression on the SAME table as sql/52 block 1's
-- `moved`, and it cannot be anything else: THERE IS NO FISHING TRACK IN THE
-- STORE to recount from. `public_track` holds ferries and other public
-- vessels only, and the raw archive is deleted after aggregation (CLAUDE.md).
-- So block 1 is a CROSS-FILE CONSISTENCY CHECK, and here is exactly what each
-- of its columns is worth:
--   * `moved_msgs` vs `moved_dist` — two DEFINITIONS of "moved" over one
--     table. Real content, no independence: it says the collapse is not an
--     artefact of the threshold, not that the table is right.
--   * `msgs_gap` — the ONE genuinely independent number here. It compares
--     `vessel_day` with `h3_hourly`, two tables written by two separate
--     INSERTs in sql/03_aggregate.sql. If the loader lost or doubled messages
--     on one side, this is where it shows.
--   * `h3_moving_msgs` is also the number sql/50's hourly rows sum to for
--     this fleet and day (461 314 on 2023-12-20, Class A fishing), so a
--     consumer can pin sql/50's daily total HERE instead of re-summing 24
--     hourly rows on the other side of the chapter.
-- Calling block 1 an oracle would be the same mistake as the S2 spatial test.
-- It is a check that the chapter's headline collapse survives the definition
-- and that the two aggregate tables agree; nothing more.
--
-- ====================================================================
-- BLOCK 1 — PIA'S FISHING COLLAPSE, 2023-12-18 .. 12-25, recounted.
-- 8 columns: day, heard, moved_msgs, moved_dist, moved_gap,
--            vd_moving_msgs, h3_moving_msgs, msgs_gap
--
-- THREE ROUTES TO THE SAME COLLAPSE — two definitions and two tables, not two
-- independent sources; see the banner above:
--   moved_msgs      uniqExactIf(mmsi, moving_msgs > 0) — a vessel that sent
--                   ONE message over 0.5 kn all day counts as having moved.
--                   The loosest possible definition.
--   moved_dist      uniqExactIf(mmsi, dist_nm >= 1)    — sql/52 block 1's
--                   `moved`, replicated here from the same table.
--   moved_gap       moved_msgs - moved_dist >= 0 ALWAYS: dist_nm is summed
--                   over moving steps, so dist_nm >= 1 implies moving_msgs > 0.
--                   A NEGATIVE gap means the loader's two columns disagree
--                   about what moving is, which nothing else in this project
--                   would notice.
--   vd_moving_msgs  sum(moving_msgs) over the SAME vessel-days
--   h3_moving_msgs  sum(moving_msgs) over `h3_hourly` for the same day and
--                   fleet — sql/50's daily sum, emitted here as a column so
--                   it can be pinned directly (MEASURED: 488 984 / 585 761 /
--                   461 314 / 194 661 / 58 921 / 82 356 / 51 053 / 143 795
--                   for 12-18 .. 12-25). TWO DIFFERENT TABLES, written
--                   by two separate INSERTs in sql/03_aggregate.sql from the
--                   same `ais_clean` view; the one is per (cell, hour), the
--                   other per (vessel, day). msgs_gap must be 0, and is.
-- The collapse itself is a real number, not a definition: moved_dist falls
-- 72 -> 24 -> 11 over 12-20/21/22 while `heard` barely moves (320 -> 313 ->
-- 298), so the fleet is still being received and is simply not going out.
-- Whichever definition of "moved" the essay quotes, the shape has to survive.
--
-- The day key is toDate(ts) in UTC on both sides — `vessel_day.day` is a UTC
-- date (sql/01_schema.sql) and `h3_hourly.hour` is a UTC hour, so no timezone
-- conversion happens anywhere in this block, which is also the calendar-date
-- rule the storm window uses.
-- ====================================================================
WITH
toDate('2023-12-18') AS d0,
toDate('2023-12-25') AS d1,
vd AS (
    SELECT day,
           uniqExact(mmsi)                     AS heard,
           uniqExactIf(mmsi, moving_msgs > 0)  AS moved_msgs,
           uniqExactIf(mmsi, dist_nm >= 1)     AS moved_dist,
           sum(moving_msgs)                    AS vd_moving_msgs
    FROM vessel_day
    WHERE day BETWEEN d0 AND d1
      AND mobile = 'Class A' AND ship_group = 'fishing'
    GROUP BY day
),
h3 AS (
    SELECT toDate(hour) AS day, sum(moving_msgs) AS h3_moving_msgs
    FROM h3_hourly
    WHERE hour >= toDateTime(d0, 'UTC') AND hour < toDateTime(d1 + 1, 'UTC')
      AND mobile = 'Class A' AND ship_group = 'fishing'
    GROUP BY day
),
-- the day domain is the calendar, not either side's occupancy: a day on which
-- one side found nothing must still produce a row, or the check passes by
-- being absent.
days AS (
    SELECT d0 + number AS day FROM numbers(8)
)
SELECT d.day                                                AS day,
       v.heard                                              AS heard,
       v.moved_msgs                                         AS moved_msgs,
       v.moved_dist                                         AS moved_dist,
       toInt64(v.moved_msgs) - toInt64(v.moved_dist)        AS moved_gap,
       v.vd_moving_msgs                                     AS vd_moving_msgs,
       h.h3_moving_msgs                                     AS h3_moving_msgs,
       toInt64(v.vd_moving_msgs) - toInt64(h.h3_moving_msgs) AS msgs_gap
FROM days AS d
LEFT JOIN vd AS v ON v.day = d.day
LEFT JOIN h3 AS h ON h.day = d.day
ORDER BY day
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 2 — THE ÆRØ LIFELINE UNDER PIA, 2023-12-18 .. 12-25.
-- 5 columns: day, oracle_crossings, table_crossings, gap, oracle_vessels
--
-- TWO COUNTING ROUTES THAT SHARE NOTHING BUT TWO 64-BIT INTEGERS, exactly as
-- sql/43_ferry_oracle.sql does it for July 2025 — this block is that oracle
-- re-aimed at Pia's week, and the method below is sql/43's, copied on purpose:
--   ORACLE SIDE: raw `public_track` positions in the two hard-coded res-7
--   cells, ordered within a vessel; every time the cell of a position differs
--   from the cell of that vessel's previous in-cell position AND the two
--   sightings are at most 24 HOURS apart, that is one crossing, counted on the
--   day of the PREVIOUS position — the last sighting on the departure side.
--   It uses no `ferry_crossing`, no `ferry_stay`, no route matching, no line
--   label, no sessionisation and no MMSI: the two cells select the traffic.
--     608531604905656319  Svendborg ferry berth, geoToH3(55.058, 10.615, 7)
--     608531599906045951  Ærøskøbing,            geoToH3(54.892, 10.413, 7)
--   sql/43's header carries the provenance of both ids (they are the two
--   endpoints of OSM way 33847154 rounded to res 7) and recomputes them from
--   their literals every run, so the argument-order guard lives there and is
--   not duplicated here.
--   THE 24-HOUR BOUND is the one piece of judgement in the oracle: sql/43
--   measured what it is for — sail-training ships lying in Svendborg and
--   appearing in Ærøskøbing up to ten days later, which is not a crossing.
--   TABLE SIDE: rows of `ferry_crossing` with
--   line = 'Svendborg – Ærøskøbing' (EN DASH, U+2013, from
--   data/context/ferry_lines.csv). If the label were renamed or re-folded,
--   this side would go to zero while the oracle kept counting.
-- The two sides can legitimately differ, and sql/43's header lists why in
-- full (the cell is not the berth; different clocks for the same trip;
-- sql/40's 60-minute, 100 m and 30 kn guards; other Class A traffic through
-- both cells). MEASURED HERE: gap = 0 on all eight days.
--
-- THE DAY KEY IS UTC ON BOTH SIDES, which is this chapter's key (the storm
-- window is built from UTC calendar dates and sql/50 buckets departures by
-- toStartOfHour(dep) in UTC), and NOT sql/41_ferry_daily.sql's local
-- Europe/Copenhagen date. The two keys differ only for a crossing that
-- departs between 23:00 and 24:00 UTC — 2.09 % of all crossings in the store
-- (STATUS § S8), and MEASURED on this line in this week: 0 of 142. The Ærø
-- ferry's last departure is well before 23:00 UTC, so the choice of key
-- changes nothing here and the block spends its five columns on the counting
-- route instead.
-- Ferries and commercial vessels are public, so the line may be named here.
--
-- WHY THIS WEEK. Pia is 2023-12-21/22 and 2023-12 is fully loaded; the eight
-- days are the storm's own window at day grain (start_day - 3 .. end_day + 3),
-- the same eight days as block 1, so the two blocks can be read side by side.
-- MEASURED, this week: 20 / 20 / 20 / 16 / 18 / 18 / 14 / 16 crossings for
-- 12-18 .. 12-25 — 20 on an ordinary December day, 16 on Pia's first date
-- and 18 on its second. The timetable anchor is 22 a day in summer
-- (data/context/ferry_timetable.csv, 11 per direction).
--
-- PRIVACY: MMSI is a partition key inside the query; only counts are emitted.
-- ====================================================================
WITH
toDate('2023-12-18') AS d0,
toDate('2023-12-25') AS d1,
608531604905656319 AS cell_sv,
608531599906045951 AS cell_ae,
-- a day of run-up on each side so 12-18 has a real predecessor position
toDateTime('2023-12-17 00:00:00', 'UTC') AS win0,
toDateTime('2023-12-27 00:00:00', 'UTC') AS win1,
-- --- the oracle side: raw positions, two cell ids, nothing else -------
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
    SELECT toDate(prev_ts) AS day, count() AS crossings, uniqExact(mmsi) AS vessels
    FROM step
    WHERE cell != prev_cell
      AND dateDiff('hour', prev_ts, ts) <= 24
    GROUP BY day
    HAVING day BETWEEN d0 AND d1
),
-- --- the table side: what sql/40 wrote, on the same UTC days ----------
tbl AS (
    SELECT toDate(dep) AS day, count() AS crossings
    FROM ferry_crossing
    WHERE line = 'Svendborg – Ærøskøbing'
      AND dep >= toDateTime(d0, 'UTC') AND dep < toDateTime(d1 + 1, 'UTC')
    GROUP BY day
),
days AS (
    SELECT d0 + number AS day FROM numbers(8)
)
SELECT d.day                                       AS day,
       o.crossings                                 AS oracle_crossings,
       t.crossings                                 AS table_crossings,
       toInt64(o.crossings) - toInt64(t.crossings) AS gap,
       o.vessels                                   AS oracle_vessels
FROM days AS d
LEFT JOIN oracle AS o ON o.day = d.day
LEFT JOIN tbl    AS t ON t.day = d.day
ORDER BY day
-- join_use_nulls = 0: a day missing from either side must read as 0, not as
-- NULL, or `gap` is NULL and anything grepping for a non-zero calls it clean.
SETTINGS join_use_nulls = 0;
