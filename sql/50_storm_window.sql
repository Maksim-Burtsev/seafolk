-- S9 chart 1 — chapter 04: what each fleet does in the days around a named
-- storm, hour by hour, against the same hour a fortnight away.
-- Run: scripts/ch.sh sql/50_storm_window.sql  (read-only; 2.3 s, 26 160 rows)
-- Reads `h3_hourly`, `vessel_day` (day list only), `ferry_crossing` (built by
-- sql/40_ferry_trips.sql) and `storm` (sql/04_context.sql). Writes nothing.
--
-- Columns, one row per (storm, hour, mobile, ship_group):
--   storm             the DMI name; Dagmar and Egon are ONE storm, see below
--   start_day         toDate(start_utc) of the storm — the window's hour 0
--   hour              UTC hour
--   offset_h          dateDiff('hour', start_day 00:00 UTC, hour)
--   mobile            'Class A' | 'Class B'
--   ship_group        cargo | fishing | leisure | other | passenger
--   heard             uniqExactMerge(vessels) over ALL cells in that hour —
--                     distinct vessels of that (mobile, group) heard anywhere
--                     in the bbox. EXACT.
--   moving_msgs, msgs sums over all cells in that hour
--   ref_hour          the reference hour, or NULL (the rule is below)
--   ref_heard, ref_moving_msgs   the same two quantities at ref_hour
--   ratio_moving      moving_msgs / ref_moving_msgs, NULL when there is no
--                     reference hour, and NULL when the reference hour's
--                     moving_msgs is 0. MEASURED: the second case fires on
--                     RATIO_NULL_TOTAL rows and every one of them has ref_heard > 0 —
--                     it is never "the group is absent from the reference
--                     hour", it is always "the group is heard there and
--                     nothing in it moves" (thin fleets at night: Class B
--                     cargo, Class A leisure and the like).
--   ferry_crossings   DANISH ferry departures in that hour: `ferry_crossing`
--                     rows with toStartOfHour(dep) = hour AND kind IN
--                     ('island', 'domestic', 'international') — the lines
--                     with at least one Danish end. It is a property of the
--                     hour, not of a fleet, and it is emitted ONLY on the
--                     (Class A, passenger) row — every other row carries 0,
--                     and ref_ferry_crossings carries NULL there. Do not sum
--                     this column across groups.
--                     WHAT IS EXCLUDED, measured over the 528 940 crossings
--                     that fall in the hours this file scans:
--                       kind = 'foreign'  193 085 (36.5 %) — the Goteborg
--                         archipelago, the Nord-Ostsee-Kanal, Ruegen, the
--                         Baltic long-haul lines: neither end in Denmark, so
--                         a Danish storm is not their weather and pooling
--                         them made this column read as "the country's ferry
--                         service" while more than a third of it was not.
--                       kind = 'harbour'    3 479 (0.66 %) — sql/40's five
--                         intra-harbour objects, "a leg, not a service".
--                       line = '' (kind '') 39 547 (7.48 %) — crossings
--                         sql/40 could not match to any route, so their
--                         nationality is unknown.
--                     KEPT: island 133 213 (25.2 %), domestic 103 592
--                     (19.6 %), international 56 024 (10.6 %) = 292 829.
--                     `ferry_crossing.kind` comes from the committed hand
--                     file data/context/ferry_lines.csv (sql/40's header
--                     defines the five kinds); the same filter is applied to
--                     ref_ferry_crossings, so the ratio compares like with
--                     like.
--   ref_ferry_crossings  the same at ref_hour, on the (Class A, passenger)
--                     row only, NULL everywhere else.
--
-- THE WINDOW. Storm hour 0 is toDate(start_utc) at 00:00 UTC and the storm
-- ends at toDate(end_utc) 23:59; the window runs from 72 h before hour 0 to
-- 72 h after the end, so a three-day storm gets a longer window than a
-- one-day storm and offset_h runs -72 .. +95 for a one-day storm and
-- -72 .. +143 for Dagmar·Egon.
--
-- THE CALENDAR-DATE RULE, inherited from sql/41_ferry_daily.sql's header:
-- every row of storms.csv carries `date-only` in its note — DMI publishes the
-- DATE a storm crossed Denmark, and the 00:00:00/23:59:59 stamps in the CSV
-- are that date written as a day, not a measured hour. So the window is built
-- from toDate(start_utc) / toDate(end_utc) with NO timezone conversion. S8
-- measured what the alternative costs: converting the UTC stamps to
-- Europe/Copenhagen widened the storm windows by one local day and flagged 58
-- days for 35 calendar dates.
--
-- DAGMAR AND EGON ARE ONE EVENT. DMI lists Dagmar on 2015-01-09 and Egon on
-- 2015-01-10/11; they are adjacent, and a 72 h window around either contains
-- the other, so the two rows would double-count every hour between them under
-- two different names. They are merged into 'Dagmar·Egon', 2015-01-09 ->
-- 2015-01-11, exactly as S8 treats them (`notes/ch03-findings.md`, finding 33).
-- The merge is by NAME, so adding another storm to storms.csv changes nothing.
--
-- THE REFERENCE HOUR: the same UTC hour 14 days earlier — a fortnight keeps
-- the weekday and the time of day and stays inside the same season. If that
-- calendar DAY is not loaded, the reference is 14 days LATER; if neither day
-- is loaded the row is still emitted with ref_hour = NULL and ratio_moving =
-- NULL. A storm is never silently dropped for want of a reference.
--   "loaded" is `SELECT DISTINCT day FROM vessel_day`, not load_log's
--   ts_min/ts_max ranges. vessel_day answers the question actually being
--   asked — is there data for this calendar day — while a load_log range is
--   a property of an archive FILE (a monthly zip covers 28-31 days, and
--   sql/13's header records that its own toDate(ts_min) keying is unfixed).
--   The distinct-day scan is 0.3 s: `day` is the first ORDER BY key.
--
-- MEASURED, which rule fired for each of the 15 storms whose window touches a
-- loaded day (2 122 loaded days, 2015-01-01 -> 2026-08-26):
--   -14 d : Freja, Gorm, Helga (2015), Johanne, Knud (2018), Alfrida (2019),
--           Malik, Nora (2022), Pia (2023), Sif (2024), Floriane, Amy (2025),
--           Dave (2026)
--   +14 d : Dagmar·Egon — 2014-12-26 .. 2014-12-31 is not in the store at all
--           (the archive is loaded from 2015-01-01), so the whole window
--           references 2015-01-20 .. 2015-01-28.
--   BOTH  : Otto (2023-02-17/18). 2023 holds February and December only, so
--           the 24 hours of 2023-02-14 reference 2023-02-28 (+14, because
--           2023-01-31 is unloaded) and the other 168 hours reference
--           2023-02-01 .. 2023-02-07 (-14).
--   NONE  : no storm. Every emitted hour has a reference.
-- Eight storms (Allan, Bodil, Carl, Alexander, Urd, Ingolf, Laura, Rolf) have
-- no loaded day anywhere in their window and produce no rows at all.
-- ALFRIDA IS THREE DAYS OF WINDOW, NOT EIGHT: 2019 is entirely unloaded, so
-- only 2018-12-29/30/31 (offset_h -72 .. -1) survive. The storm itself is
-- unobserved. Read it as a run-up, not as a storm profile.
--
-- HOURS WITH NO DATA ARE ABSENT ROWS, NOT ZEROS. The window is not
-- zero-filled: a (hour, mobile, ship_group) with nothing in `h3_hourly`
-- produces no row. On an unloaded day that is the honest answer — a zero
-- would say the sea was empty.
-- WHAT THE CONSUMER ACTUALLY DOES WITH THAT is not zero-fill: notes/plot_ch04.py
-- asserts that every storm's offsets run DENSE from -72 to the storm's last
-- emitted offset and fails loudly on a hole, rather than papering over one.
-- Alfrida is the single storm whose series stops early (at -1, see below) and
-- it is dense up to there. So a hole in an emitted window is a bug in the
-- store or in this file, not a case to fill in; a consumer that wants a grid
-- across UNLOADED days must check the loaded-day list first.
--
-- TWO WINDOWS ARE NOT INDEPENDENT OF EACH OTHER, MEASURED over all 24 storms:
--   * GORM AND HELGA SHARE 48 HOURS. Gorm is 2015-11-29 and Helga 2015-12-04,
--     five days apart, so Gorm's +48 .. +95 (2015-12-01 00:00 -> 2015-12-02
--     23:00 UTC) are exactly Helga's -72 .. -25 — the same 48 hourly rows
--     emitted twice under two names. Nothing double-counts inside one storm's
--     panel, but a reader who pools storms pools those hours twice, and
--     "Helga's calm run-up" is partly "Gorm's recovery".
--   * NORA'S REFERENCE FALLS INSIDE MALIK'S WINDOW. Nora's first 48 window
--     hours reference 2022-02-01 00:00 -> 2022-02-02 23:00, and those 48
--     hours are Malik's +72 .. +119. Nora's -14 d baseline is therefore
--     Malik's aftermath, not a quiet fortnight, for the run-up part of its
--     panel.
--   These two are the only pairs: no other storm window overlaps another, and
--   no other storm's reference hour lands in another's window.
--
-- THE Sep-2015 DUPLICATION WINDOW NEEDS NO MASK HERE. sql/31/32 exclude
-- 2015-08-28 00:00 -> 2015-10-01 00:00 because upstream duplication moves
-- message counts. No storm window and no reference hour of any storm falls in
-- it: the nearest is Freja, window 2015-11-04 .. 2015-11-11, reference
-- 2015-10-21 .. 2015-10-28 — five clear weeks after the window closes. There
-- is therefore nothing to mask and no mask is applied. If a storm is ever
-- added to storms.csv between those dates, this file needs the exclusion.
--
-- WHY `heard` AND `moving_msgs` ARE TWO COLUMNS AND NOT ONE RATIO. A distinct
-- count of MOVING vessels per hour is NOT recoverable from `h3_hourly`:
-- `vessels` is a uniqExact state over every vessel present in the cell-hour,
-- moving or not, and no state of the moving subset was ever stored (the same
-- constraint sql/11, sql/12, sql/24 and sql/30 all state). So the hour grain
-- has an exact HEAD COUNT and a message-based MOVEMENT signal, and they are
-- kept apart. sql/52_who_stays.sql answers "how many vessels moved" exactly,
-- at the DAY grain, from `vessel_day`.
--
-- THE moving_msgs CAVEAT. A Class A ship reports a position every few
-- seconds, a Class B one every 30 s at best, and the reporting rate itself
-- rises with speed — so moving_msgs is NOT comparable between fleets, and its
-- absolute level is not a vessel count. `ratio_moving` divides a fleet by
-- ITSELF a fortnight away, which is the only comparison this column supports.
-- Compare ratios across fleets; never compare moving_msgs across fleets.
--
-- EVERY (mobile, ship_group) PAIR THAT EXISTS IS EMITTED, thin ones included
-- — Class A leisure, Class B cargo and the rest are the control that says a
-- collapse is a fleet's behaviour and not the receiver network's bad night.
-- `heard` stands next to every ratio so a thin combination reads as thin.
--
-- PRIVACY: nothing here is per-vessel. `vessel_day` is touched only for its
-- list of calendar days; every other column is a count over a whole fleet in
-- a whole hour. No MMSI, no name, no position leaves this file.

WITH
-- the calendar days the store actually holds
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
agg AS (
    SELECT hour, mobile, ship_group,
           uniqExactMerge(vessels) AS heard,
           sum(moving_msgs)        AS moving_msgs,
           sum(msgs)               AS msgs
    FROM h3_hourly
    WHERE hour IN (SELECT hour FROM hrs)
    GROUP BY hour, mobile, ship_group
),
fc AS (
    SELECT toStartOfHour(dep) AS hour, count() AS crossings
    FROM ferry_crossing
    WHERE toStartOfHour(dep) IN (SELECT hour FROM hrs)
      -- the lines with a Danish end. See the column note in the header for
      -- what this drops and how much of it.
      AND kind IN ('island', 'domestic', 'international')
    GROUP BY hour
)
SELECT w.storm     AS storm,
       w.start_day AS start_day,
       w.hour      AS hour,
       w.offset_h  AS offset_h,
       a.mobile    AS mobile,
       a.ship_group AS ship_group,
       a.heard       AS heard,
       a.moving_msgs AS moving_msgs,
       a.msgs        AS msgs,
       w.ref_hour    AS ref_hour,
       if(w.ref_hour IS NULL, NULL, toNullable(r.heard))       AS ref_heard,
       if(w.ref_hour IS NULL, NULL, toNullable(r.moving_msgs)) AS ref_moving_msgs,
       if(w.ref_hour IS NULL OR r.moving_msgs = 0, NULL,
          toNullable(round(a.moving_msgs / r.moving_msgs, 4)))  AS ratio_moving,
       if(a.mobile = 'Class A' AND a.ship_group = 'passenger', f.crossings, 0) AS ferry_crossings,
       if(a.mobile = 'Class A' AND a.ship_group = 'passenger' AND w.ref_hour IS NOT NULL,
          toNullable(rf.crossings), NULL)                       AS ref_ferry_crossings
FROM winr AS w
INNER JOIN agg AS a  ON a.hour  = w.hour
LEFT  JOIN agg AS r  ON r.hour  = assumeNotNull(w.ref_hour)
                    AND r.mobile = a.mobile AND r.ship_group = a.ship_group
LEFT  JOIN fc  AS f  ON f.hour  = w.hour
LEFT  JOIN fc  AS rf ON rf.hour = assumeNotNull(w.ref_hour)
ORDER BY storm, mobile, ship_group, hour
-- join_use_nulls = 0: a missing reference row must read as 0 messages, which
-- the ratio expression turns into NULL. Under = 1 it would arrive as NULL and
-- the arithmetic would silently propagate it instead of the explicit guard.
SETTINGS join_use_nulls = 0;
