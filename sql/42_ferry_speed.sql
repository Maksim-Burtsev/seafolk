-- S8 — chapter 03: how fast each ferry line is, year by year, and which ship
-- was flying the flag that year. A vessel replacement is a step in BOTH
-- columns at once, which is what makes it readable as a replacement and not as
-- a bad summer: the line Søby – Fynshav (OSM way 171896489) is the reference
-- case, the battery ferry ELLEN.
-- Run: scripts/ch.sh sql/42_ferry_speed.sql   (read-only; 0.4 s, 1 248 rows)
-- Reads `ferry_crossing` (built by sql/40_ferry_trips.sql). Writes nothing —
-- and it no longer reads `ferry_line` either: the 200-crossing floor and the
-- OSM-object fold are resolved at build time into `ferry_crossing.line`, so
-- `WHERE line != ''` is the whole of it. They used to be a verbatim copy of
-- three CTEs shared with sql/41.
--
-- Columns, one row per (LINE, calendar year of `dep`):
--   line, kind, island   the service, not the OSM object; Helsingor -
--                        Helsingborg is seven OSM objects and one line. There
--                        is no fallback label any more — sql/40 fails the
--                        build if a route over the floor is unmapped.
--   year                 the calendar year of the LOCAL (Europe/Copenhagen)
--                        date of `dep`, the same key sql/41 uses. On UTC the
--                        two files disagreed about 144 crossings at the turn
--                        of the year.
--   crossings      crossings on that line that year, both directions
--   vessels        distinct vessels that made them
--   routes         OSM objects folded into the line that year
--   modal_vessel   the name most crossings that year were made by, and
--   modal_share    its share of them — 1.00 means one ship ran the whole line
--   med_kn         MEDIAN speed made good = nm / (minutes / 60) per crossing.
--                  Made good, berth centroid to berth centroid: it is lower
--                  than the ship's service speed by exactly the manoeuvring
--                  and the fact that the great circle is not the fairway. It
--                  is the right number for a YEAR-ON-YEAR comparison of the
--                  same line and the wrong number to compare against a
--                  brochure.
--   med_sog_kn     median of `ferry_crossing.med_sog` — the median of the
--                  vessel's own reported speeds while under way, which is
--                  higher than med_kn and moves for different reasons
--                  (a slower ship vs. a longer turnaround). Both are emitted
--                  so a step can be attributed.
--   med_min, p10_min, p90_min   crossing duration, and its spread. A new ship
--                  on an unchanged timetable usually shows first in p90.
--   max_kn         the fastest crossing of the line-year, same speed made
--                  good. It exists so sql/40's 30 kn guard has a consumer: if
--                  a line-year ever reads close to 40 the guard is shaping the
--                  data instead of catching a coverage hole, and the guard has
--                  to be re-argued before the number is quoted.
--   med_nm         distance, as a control: if med_nm moves too, the berths
--                  moved (or OSM's route did) and the speed step is an
--                  artefact, not a ship. On a line that folds several OSM
--                  objects this column also catches a mis-mapped route: two
--                  objects that are not the same service would show as a
--                  bimodal distance and a med_nm that jumps between years.
--
-- SAME 200-CROSSING FLOOR AS sql/41, on the ROUTE and applied before the fold
-- into lines. A median speed over four crossings is not a line's speed. The
-- floor is on the WHOLE STORE, not per year, so a line's thin years are still
-- emitted — the `crossings` column is there to be read before the speed is
-- believed.
--
-- The years in this archive are 2015 / 2018 / 2021 / 2024 / 2025 / 2026 in
-- full and 2022 / 2023 as storm windows only (a few weeks each). The 2022 and
-- 2023 rows are a winter sample of a summer-and-winter line and must not be
-- read as that year's average; `crossings` shows it immediately.
--
-- EVERY QUANTILE HERE IS THE *Exact* VARIANT. ClickHouse's plain `quantile`
-- and `median` are reservoir sampling driven by a random number generator:
-- two runs of this file over an unchanged table returned different medians,
-- which is not something a chapter can cite. `quantileExact` sorts the group.
-- The largest group here is a few hundred thousand crossings and the file
-- runs in under a second, so there is nothing to trade away.
--
-- PRIVACY: `public_track`, and therefore `ferry_crossing`, holds Class A
-- PASSENGER ships only — public vessels, which CLAUDE.md allows to be named.
-- `modal_vessel` is the only place in sql/41-43 where a vessel name is
-- emitted, and no MMSI is emitted anywhere.

WITH x AS (
    SELECT line, kind, island,
           toYear(toTimeZone(dep, 'Europe/Copenhagen')) AS year,
           route_id, mmsi, name, minutes, nm, med_sog
    FROM ferry_crossing
    WHERE line != ''
      AND minutes > 0                  -- a crossing that rounds to zero minutes
),                                     -- has no speed; 1-minute sampling floor
-- the modal vessel needs a count PER NAME, which is a finer grain than the
-- output, so it is its own aggregation and is joined back.
per_name AS (
    SELECT line, year, name, count() AS c
    FROM x GROUP BY line, year, name
),
modal AS (
    SELECT line, year, argMax(name, tuple(c, name)) AS modal_vessel,
           max(c) / sum(c) AS modal_share
    FROM per_name GROUP BY line, year
)
SELECT x.line                                              AS line,
       min(x.kind)                                         AS kind,
       min(x.island)                                       AS island,
       x.year                                              AS year,
       count()                                             AS crossings,
       uniqExact(x.mmsi)                                   AS vessels,
       uniqExact(x.route_id)                               AS routes,
       any(m.modal_vessel)                                 AS modal_vessel,
       round(any(m.modal_share), 3)                        AS modal_share,
       round(medianExact(x.nm / (x.minutes / 60.)), 2)     AS med_kn,
       round(max(x.nm / (x.minutes / 60.)), 2)             AS max_kn,
       round(medianExact(x.med_sog), 2)                    AS med_sog_kn,
       round(medianExact(x.minutes))                       AS med_min,
       round(quantileExact(0.1)(x.minutes))                AS p10_min,
       round(quantileExact(0.9)(x.minutes))                AS p90_min,
       round(medianExact(x.nm), 2)                         AS med_nm
FROM x
LEFT JOIN modal AS m ON m.line = x.line AND m.year = x.year
GROUP BY line, year
ORDER BY line, year
SETTINGS join_use_nulls = 0;
