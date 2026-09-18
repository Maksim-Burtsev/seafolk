-- S12a chart I3 — which country's boats these are, year by year.
-- Run: scripts/ch.sh sql/80_site_flags.sql  (read-only; 2.4 s, 36 rows)
-- Reads `vessel_day`. Writes nothing.
-- Columns: year, flag, share
--
-- WHY THIS IS NOT IN sql/61_adoption.sql, WHERE IT BELONGS. sql/61 block 4
-- already emits `danish_share` and `german_share` over exactly this population,
-- and the obvious move is to widen that block. It cannot be widened: sql/61
-- puts four result sets on one stdout and its consumers tell them apart BY
-- COLUMN COUNT — notes/plot_honesty.py asserts `set(widths) == {13, 5, 9, 10}`
-- and dies on anything else. Adding three columns to block 4, or adding a fifth
-- block, breaks a committed S10 tool whose output notes/honesty.md quotes.
-- So the site's version lives here, and the two files must agree: this file's
-- Denmark and Germany shares are the same numbers sql/61 block 4 emits, over
-- the same window and the same fleet, and scripts/site_data/index.py asserts
-- that they match before either reaches a chart.
--
-- THE POPULATION is sql/61 block 4's, to the row: distinct Class B
-- transponders heard between 1 March and 26 August of one of the six main
-- years. The common window exists because the archive does not cover the six
-- years equally — the daily files begin 2024-03-01 and the store ends
-- 2026-08-26 — so a full-year count would compare a year with three quarters
-- of one. 2022 and 2023 are storm months only and have no day in the window.
--
-- THE FLAG is read off the MID, the first three digits of the radio ID, which
-- is the flag state of the REGISTRATION and not where the boat sails. The
-- allocation is the ITU's; the six groups below are the ones with more than a
-- thousand transponders in this box in any loaded year, measured before this
-- file was written (2026: 211 Germany 8 470, 219 Denmark 6 376, 265 Sweden
-- 3 738, 244 Netherlands 1 706, 257 Norway 1 622, 258 Norway 870, 218 Germany
-- 793, 261 Poland 625). Every other prefix — Poland, the UK, Finland, Belgium
-- and the long tail — falls into 'everyone else' rather than being named, so
-- the shares always sum to 1 and nothing is quietly dropped.
--
-- THE BOX IS NOT DENMARK. It is lat 53-59, lon 3-17, which reaches Kiel,
-- Flensburg, Rügen and the Dutch Wadden. That is why Germany leads, and it is
-- a fact about the bounding box at least as much as about the fleet.
--
-- PRIVACY. A SHARE OVER THOUSANDS OF VESSELS, AND NOTHING ELSE. No count is
-- emitted, no MMSI, no name, no position, no per-cell or per-day grain; the
-- smallest group here is a whole country's fleet in a whole summer. The
-- `uniqExact(mmsi)` states never leave this query.
WITH
vd AS (
    SELECT toYear(day)              AS year,
           intDiv(mmsi, 1000000)    AS mid,
           mmsi
    FROM vessel_day
    WHERE mobile = 'Class B'
      AND toYear(day) IN (2015, 2018, 2021, 2024, 2025, 2026)
      AND day BETWEEN makeDate(toYear(day), 3, 1) AND makeDate(toYear(day), 8, 26)
),
tagged AS (
    SELECT year, mmsi,
           multiIf(mid IN (211, 218),           'German',
                   mid IN (219, 220),           'Danish',
                   mid IN (265, 266),           'Swedish',
                   mid IN (244, 245, 246),      'Dutch',
                   mid IN (257, 258, 259),      'Norwegian',
                                                'everyone else') AS flag
    FROM vd
),
total AS (
    SELECT year, uniqExact(mmsi) AS vessels FROM tagged GROUP BY year
)
SELECT t.year                                        AS year,
       t.flag                                        AS flag,
       round(uniqExact(t.mmsi) / any(a.vessels), 4)  AS share
FROM tagged AS t
INNER JOIN total AS a ON a.year = t.year
GROUP BY t.year, t.flag
ORDER BY year, share DESC;
