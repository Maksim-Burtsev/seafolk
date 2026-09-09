-- S8 — chapter 03: crossings per ferry line per day, the baseline a day is
-- judged against, whether a named storm ran over it, and — the part that makes
-- the rest usable — whether the line's fleet was HEARD at all that day.
-- Run: scripts/ch.sh sql/41_ferry_daily.sql   (read-only; 0.7 s, 281 491 rows)
-- Reads `ferry_crossing`, `ferry_day`, `ferry_line` (all built by
-- sql/40_ferry_trips.sql) and `storm` (sql/04_context.sql). Writes nothing.
--
-- Columns of the FIRST block, one row per (LINE, local day):
--   line       the ferry service, resolved at BUILD TIME in sql/40 and stored
--              on the crossing. This file does not know what a route is: the
--              200-crossing floor and the OSM-object fold both live in sql/40
--              (`ferry_rl`), so `WHERE line != ''` is the whole of it. They
--              used to be a copy-paste of three CTEs in sql/41 and sql/42.
--   kind       island / domestic / international / foreign (see sql/40)
--   island     the island for kind = 'island', else ''
--   day        LOCAL date (Europe/Copenhagen) of the crossing's `dep`
--   year, season, dow                  the baseline's grouping keys
--   daytype    weekday / sat / sun — kept for consumers that want the coarse
--              split; it is NOT the baseline key any more, see below
--   crossings  crossings that departed on that local day, both directions
--   vessels    distinct vessels that made them
--   routes     how many OSM objects were folded into the line that day
--   baseline   MEDIAN crossings over the same (line, year, season, DAY OF
--              WEEK), counting SIGNAL DAYS ONLY — see below
--   missed     greatest(baseline - crossings, 0)
--   is_storm_day  1 if the day is a `storm` calendar date
--   fleet_positions, fleet_sog_known, fleet_moving, fleet_vessels_reporting
--              the coverage denominator. READ THESE BEFORE READING `missed`.
--
-- HOW TO READ A ZERO, which is the only reason the coverage columns exist:
--   crossings = 0 and fleet_positions = 0      SILENT. Nothing was heard from
--                                              this line's fleet. Not a
--                                              cancellation; not evidence.
--   fleet_positions > 0, fleet_sog_known = 0   CANNOT TELL. The vessel was
--                                              heard, its speed field was
--                                              empty all day, and sql/40 can
--                                              build neither a stay nor a
--                                              crossing out of that.
--   fleet_moving = 0                           THE FLEET LAY STILL. A real
--                                              cancellation, or a docking.
--   fleet_moving > 0 and crossings = 0         MOVED, NOTHING MATCHED. The
--                                              matcher or OSM, not the weather.
-- Those four are the whole vocabulary; a consumer that prints "cancelled"
-- without checking them is printing the receiver's bad day.
--
-- THE SECOND BLOCK, at the bottom, emits per year the share of crossings
-- sql/40 could NOT match to a route, SPLIT AT 1 km, plus the crossings that
-- matched a route below the 200-crossing floor. It is the honesty number for
-- sql/40's 100 m distance guard: an unmatched crossing under 1 km is most
-- likely a move inside one harbour that the nearest-endpoint rule correctly
-- refused, while an unmatched crossing over 1 km is a real passage on a line
-- OSM does not have. That block is the only place this file still looks at
-- `route_id` and `nm`.
--
-- WHY THE BASELINE IS OBSERVED AND NOT A TIMETABLE. Danish operator timetables
-- are not archived per year and this archive spans 2015 -> 2026; a hand-made
-- expected-departures table for every route x year x season would be invented
-- data, which CLAUDE.md forbids. The baseline is therefore the MEDIAN of what
-- this same line actually ran on comparable days: same line, same calendar
-- year (so a 2019 fleet change does not contaminate 2015), same season
-- (May-Sep against Oct-Apr — the summer timetable is a different timetable),
-- same daytype (weekday / sat / sun — Sunday sailings are fewer by design).
-- A median, not a mean, so a handful of storm days inside the group cannot
-- pull the thing they are being measured against down with them.
--
-- THE BASELINE IS KEYED ON THE DAY OF WEEK, NOT ON `daytype`. Pooling Monday
-- to Friday assumes a line sails every weekday, and the small Danish lines do
-- not. Grenaa - Anholt NEVER SAILS A WEDNESDAY — its day-of-week medians are
-- 2 / 2 / 0 / 2 / 2 — so a weekday baseline of 2 made every Wednesday of the
-- archive a day the line "lay still when it should have sailed": all 237 of
-- them. Frederikshavn - Hirsholmene (three days a week) contributed 167 more.
-- Those are not cancellations, they are the timetable. With the day of week as
-- the key, Wednesday's baseline is 0 and the day is ordinary.
-- The cost is smaller groups — a year x season x dow group is ~13 days in
-- Oct-Apr and ~22 in May-Sep instead of ~5x that — so a thin line's baseline
-- is now a median over a dozen days. `fleet_vessels_reporting` and the
-- crossing counts are there to be read before a single day is believed.
--
-- THE BASELINE COUNTS SIGNAL DAYS ONLY — days with fleet_positions > 0. It
-- used to include silent days as zeros, which is a median of the receiver and
-- not of the line: 310 baseline groups (10 422 line-days) move when the silent
-- days come out, and the extreme is Ronbjerg - Livo 2015 oct-apr, where 102 of
-- 140 weekdays are silent and the baseline reads 0 instead of 10. Every
-- consumer of `missed` already excludes silent days; the baseline now agrees
-- with them.
-- quantileExactLOW, not quantileExact: on an even-sized group ClickHouse's
-- quantileExact returns the UPPER of the two middle values, which puts the
-- lower-middle ORDINARY day below the baseline by construction. 525 groups are
-- even-sized here and the difference is 56 246 against 54 079 line-days with
-- missed > 0. Low is the honest side: a baseline no ordinary day falls short of.
--
-- `missed` is "fewer crossings than a comparable day that the fleet was heard
-- on", NOT "cancelled sailings". Nothing here proves a sailing did not happen.
--
-- THE COVERAGE DENOMINATOR IS BUILT FROM OWN-MAJORITY VESSELS. A vessel-year
-- belongs to the ONE line on which it made the most crossings that year, and
-- counts towards that line's coverage only. Sharing it out to every line it
-- ever touched credits a line with its neighbour's transponder: 450 of the 684
-- fleet memberships in 2025 are vessels in more than one line's fleet, 32-37 %
-- of a typical island line's coverage came from vessels whose majority line is
-- somewhere else, and recomputing on own-majority vessels alone moves the
-- island-line "cancelled" count from 1 853 to 1 549 line-days — Grenaa -
-- Anholt 24 of 48, Kleppen - Veno 51 of 53, Soby - Faaborg 71 of 111.
-- The cost is stated plainly: a relief vessel that spends most of a year
-- elsewhere contributes nothing to this line's coverage, so a line served only
-- by relief tonnage in some year reads silent. `fleet_vessels_reporting` is
-- there to show it.
--
-- `ferry_day` IS THE ONLY TABLE THIS FILE READS BESIDES `ferry_crossing`,
-- `ferry_line` AND `storm`. It replaced `vessel_day.msgs`, which could not
-- tell a receiver gap from a cancellation at all: a day whose speed field is
-- empty end to end has a perfectly normal message count, and 300 such
-- vessel-days (297 214 positions) put 258 island line-days on Havnso -
-- Sejero, Stigsnaes - Omo, Stigsnaes - Agerso and Havnso - Nekselo into the
-- "cancelled" column between 2021-09-30 and 2025-07-16.
--
-- TWO DAY-BOUNDARY FACTS, one fixed and one only stated:
--   FIXED. `ferry_day.day` is a UTC date. A local day whose UTC date was never
--   loaded has no coverage row at all and would read as silence on the
--   strength of the loader's calendar: 131 line-days on 2016-01-01,
--   2019-01-01, 2022-03-01, 2023-03-01, 2024-01-01 and 2026-08-27 held a few
--   spill-over crossings with fleet coverage 0. The day domain is therefore
--   restricted to local days whose UTC date HAS a `ferry_day` row.
--   NOT FIXED, ON PURPOSE. Inside the loaded range the two calendars still
--   differ by up to two hours: 2.09 % of crossings depart between 22:00 and
--   23:59 UTC and are keyed to a local day whose coverage figure is really the
--   previous UTC day's. That is fine for a denominator answering "was the
--   fleet heard today" and it is NOT fine for anything finer. Do not divide
--   crossings by these columns.
--
-- ZERO DAYS ARE ROWS. A day on which a line ran NOTHING is the whole point of
-- the storm chapter and it produces no crossing to group by, so the day domain
-- is built explicitly and the counts are LEFT JOINed onto it:
--   * covered days = local days that carry a crossing anywhere in the archive
--     AND whose UTC date is loaded. The archive is not continuous (2015 / 2018
--     / 2021 / 2024 / 2025 / 2026 are full-ish years, 2022 and 2023 are storm
--     windows only), so a calendar range would invent 3 000 empty days.
--   * per LINE and year, only the days between that line's FIRST and LAST
--     crossing of that year. Otherwise a line that opened in June reads as
--     five months of total cancellation.
-- join_use_nulls = 0 is pinned for the same reason as in sql/31 and sql/33:
-- under = 1 an unmatched left side comes back NULL and `greatest(baseline -
-- NULL, 0)` propagates the NULL into a row that looks like a normal zero.
--
-- PRIVACY: `ferry_crossing` and `ferry_day` both carry MMSI; nothing below
-- emits it, or any per-vessel figure. Ferries are public and may be named, but
-- this file emits line names — sql/42 and sql/44 do the vessels.

WITH
-- --- observed crossings per line-day --------------------------------
obs AS (
    SELECT line, kind, island,
           toDate(toTimeZone(dep, 'Europe/Copenhagen')) AS day,
           count()            AS crossings,
           uniqExact(mmsi)    AS vessels,
           uniqExact(route_id) AS routes
    FROM ferry_crossing
    WHERE line != ''
    GROUP BY line, kind, island, day
),
-- --- the coverage denominator ---------------------------------------
-- own-majority: one line per (vessel, year), the one it worked most.
-- tuple(c, line) breaks a tie on the line name so the table is reproducible.
per_line AS (
    SELECT mmsi, toYear(toTimeZone(dep, 'Europe/Copenhagen')) AS year, line,
           count() AS c
    FROM ferry_crossing
    WHERE line != ''
    GROUP BY mmsi, year, line
),
own AS (
    SELECT mmsi, year, argMax(line, tuple(c, line)) AS line
    FROM per_line GROUP BY mmsi, year
),
cover AS (
    SELECT o.line AS line, f.day AS day,
           sum(f.positions) AS fleet_positions,
           sum(f.sog_known) AS fleet_sog_known,
           sum(f.moving)    AS fleet_moving,
           count()          AS fleet_vessels_reporting
    FROM own AS o
    INNER JOIN ferry_day AS f ON f.mmsi = o.mmsi AND toYear(f.day) = o.year
    GROUP BY line, day
),
-- --- the day domain -------------------------------------------------
loaded AS (SELECT DISTINCT day FROM ferry_day),
cov AS (
    SELECT DISTINCT toDate(toTimeZone(dep, 'Europe/Copenhagen')) AS day
    FROM ferry_crossing
    WHERE line != ''
      AND toDate(toTimeZone(dep, 'Europe/Copenhagen')) IN (SELECT day FROM loaded)
),
span AS (
    SELECT line, kind, island, toYear(day) AS year, min(day) AS d0, max(day) AS d1
    FROM obs
    GROUP BY line, kind, island, year
),
-- CROSS JOIN, not a range join: ClickHouse has no non-equi JOIN, and this is
-- ~1 200 spans x ~2 100 days = 2.5 M candidate pairs, which costs nothing.
dom AS (
    SELECT s.line AS line, s.kind AS kind, s.island AS island,
           s.year AS year, cov.day AS day
    FROM span AS s CROSS JOIN cov
    WHERE cov.day >= s.d0 AND cov.day <= s.d1
),
-- --- storm days, as CALENDAR dates ----------------------------------
-- NO TIMEZONE CONVERSION. Every window in data/context/storms.csv is a whole
-- UTC day standing for a calendar date — `00:00:00` to `23:59:59` — so
-- toTimeZone('Europe/Copenhagen') pushes the end into the following local day
-- and widens every storm by one: 59 local days were flagged for 35 calendar
-- dates. The dates are read as dates. S9 MUST USE THIS SAME RULE.
storm_day AS (
    SELECT DISTINCT arrayJoin(arrayMap(
               i -> toDate(start_utc) + i,
               range(toUInt32(dateDiff('day', toDate(start_utc), toDate(end_utc))) + 1))) AS day
    FROM storm
),
-- --- the zero-filled panel ------------------------------------------
panel AS (
    SELECT d.line AS line, d.kind AS kind, d.island AS island,
           d.day AS day, d.year AS year,
           if(toMonth(d.day) BETWEEN 5 AND 9, 'may-sep', 'oct-apr') AS season,
           multiIf(toDayOfWeek(d.day) = 6, 'sat',
                   toDayOfWeek(d.day) = 7, 'sun', 'weekday')        AS daytype,
           toDayOfWeek(d.day)                                       AS dow,
           o.crossings AS crossings,
           o.vessels   AS vessels,
           o.routes    AS routes,
           c.fleet_positions          AS fleet_positions,
           c.fleet_sog_known          AS fleet_sog_known,
           c.fleet_moving             AS fleet_moving,
           c.fleet_vessels_reporting  AS fleet_vessels_reporting
    FROM dom AS d
    LEFT JOIN obs   AS o ON o.line = d.line AND o.day = d.day
    LEFT JOIN cover AS c ON c.line = d.line AND c.day = d.day
),
base AS (
    SELECT line, year, season, dow,
           quantileExactLow(0.5)(crossings) AS baseline
    FROM panel
    WHERE fleet_positions > 0
    GROUP BY line, year, season, dow
)
SELECT p.line                                AS line,
       p.kind                                AS kind,
       p.island                              AS island,
       p.day                                 AS day,
       p.year                                AS year,
       p.season                              AS season,
       p.daytype                             AS daytype,
       p.dow                                 AS dow,
       p.crossings                           AS crossings,
       p.vessels                             AS vessels,
       p.routes                              AS routes,
       toUInt32(b.baseline)                  AS baseline,
       greatest(toInt64(b.baseline) - toInt64(p.crossings), 0) AS missed,
       toUInt8(p.day IN (SELECT day FROM storm_day))           AS is_storm_day,
       p.fleet_positions                     AS fleet_positions,
       p.fleet_sog_known                     AS fleet_sog_known,
       p.fleet_moving                        AS fleet_moving,
       p.fleet_vessels_reporting             AS fleet_vessels_reporting
FROM panel AS p
LEFT JOIN base AS b
       ON b.line = p.line AND b.year = p.year
      AND b.season = p.season AND b.dow = p.dow
ORDER BY line, day
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- SECOND BLOCK — what the first block is silent about, per year.
--   unmatched_lt1km  crossings with no route, shorter than 1 km. sql/40's
--                    distance guard is only 100 m, so every harbour shuffle
--                    between 100 m and 1 km reaches the route matcher; the
--                    nearest-endpoint rule refuses it and it lands here. This
--                    is the price of catching Fur and Hals - Egense.
--   unmatched_ge1km  crossings with no route, 1 km or longer — a real passage
--                    on something OSM does not carry as a ferry route.
--   below_floor      matched, but on a route with < 200 crossings in the whole
--                    store, so sql/40 gave it no line and block one omits it.
--   in_first_block   what block one actually counts — ALMOST. `year` here is
--                    the LOCAL year of `dep`, the same key block one uses, so
--                    the two blocks agree on which year a crossing belongs to.
--                    They still differ by 150 crossings on 52 line-days,
--                    all of them on the six local days whose UTC date was
--                    never loaded and which block one therefore drops:
--                    2016-01-01 (19 crossings), 2019-01-01 (28), 2022-03-01
--                    (13), 2023-03-01 (42), 2024-01-01 (15), 2026-08-27 (33).
--                    A crossing there is real; the day has no coverage figure,
--                    so block one cannot say anything honest about it.
-- ====================================================================
SELECT toYear(toTimeZone(dep, 'Europe/Copenhagen'))       AS year,
       count()                                            AS crossings,
       countIf(route_id = 0 AND nm * 1852 <  1000)        AS unmatched_lt1km,
       countIf(route_id = 0 AND nm * 1852 >= 1000)        AS unmatched_ge1km,
       round(countIf(route_id = 0) / count(), 4)          AS unmatched_share,
       round(countIf(route_id = 0 AND nm * 1852 >= 1000) / count(), 4) AS unmatched_ge1km_share,
       countIf(route_id != 0 AND line = '')               AS below_floor,
       countIf(line != '')                                AS in_first_block
FROM ferry_crossing
GROUP BY year
ORDER BY year;
