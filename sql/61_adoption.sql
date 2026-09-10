-- S10 — the honesty layer, part 2: THE ADOPTION CURVE, AND WHAT IT IS MADE OF.
-- Run: scripts/ch.sh sql/61_adoption.sql
--      (read-only; four SELECTs, 14 + 21 + 5 + 6 rows.
--       Timing in "RUN TIME" at the foot of this header.)
-- Reads `vessel_day` and `h3_hourly`. Writes nothing.
--
-- Chapter 01's headline is that the Danish leisure fleet grew 3.7x in eleven
-- years. sql/60 asks whether the INSTRUMENT changed. This file asks what the
-- FLEET is made of: is the rise new boats, boats that stayed, or boats heard
-- once and never again — and does it survive being divided by the commercial
-- fleet that shares the same receivers.
--
-- PRIVACY, AND IT IS THE WHOLE DESIGN OF THIS FILE. `vessel_day` holds MMSI
-- (sql/01_schema.sql, INTERNAL ONLY). Every block below groups BY mmsi
-- internally — that is what a cohort and a retention share ARE — and NOT ONE
-- OF THEM EMITS ONE. Every emitted row is a count, a share or a median over
-- thousands of vessels, at the grain of a whole YEAR of the whole bbox. There
-- is no cell, no region, no position, no name, no callsign and no day-level
-- vessel list anywhere in the output. The one place a vessel property reaches
-- the output is `danish_share` / `german_share` in block 4, and those are the
-- aggregate share of a THREE-DIGIT flag prefix over 6-23 k vessels.
-- The smallest number this file can emit is a cohort cell in block 2; the
-- smallest one measured is 3 125 vessels, far above any k threshold.
-- A GREP FOR NINE-DIGIT INTEGERS OVER THIS FILE'S OUTPUT IS NOT ZERO, AND
-- THAT IS EXPECTED: block 4's `msgs` column (112 M - 393 M) passes nine
-- digits on all six rows, and nothing else in the file does. It is a sum of
-- message counts over a whole year of the whole bbox; it cannot be an MMSI,
-- and no expression anywhere in this file selects `mmsi` into a result. The
-- check that IS zero is the same grep over the SQL source, plus a reading of
-- the four SELECT lists.
--
-- ===================================================================
-- THE FIVE THINGS THIS FILE MEASURED:
--
-- 1. THE RISE SURVIVES BEING DIVIDED BY THE INSTRUMENT. On the common window
--    (see below), leisure Class B vessels per Class A vessel heard on >= 5
--    days: 0.609 (2015), 0.955 (2018), 1.488 (2021), 1.913 (2024), 1.985
--    (2025), 2.112 (2026) — 3.47x. The raw leisure count over the same window
--    is 6 137 -> 22 773, 3.71x. The two agree to within 7 %, so essentially
--    NONE of the eleven-year rise is the commercial fleet's receivers growing
--    with it. Denmark now hears two leisure boats for every commercial ship.
--
-- 2. YEARLY DISTINCT CLASS A IS A BROKEN DENOMINATOR AND THIS FILE EMITS BOTH.
--    Class A vessels heard in a whole year: 25 421 (2015), 27 909 (2018),
--    17 870 (2021), 17 512 (2024), 19 212 (2025), 16 100 (2026) — a fleet that
--    apparently shrank by a third between 2018 and 2021, which it did not.
--    WHAT IS MEASURED: vessels heard on exactly one day of the year number
--    8 428 (2015) and 9 527 (2018) against 3 195 (2021) and 2 822 (2024), and
--    7 617 of 2015's 8 428 sent THREE MESSAGES OR FEWER all year (median: one
--    message). That is the whole finding — a count of one-day, near-silent
--    MMSIs that collapses after 2018.
--    THE LIKELY READING, and it is a reading and not a measurement: an MMSI
--    that appears once and carries one message looks like a corrupted frame
--    decoded into a plausible number, i.e. an artefact of the era's decoding
--    rather than a ship. NOTHING IN THIS STORE CAN CONFIRM IT — the archive
--    keeps no checksum, no receiver and no raw sentence, so a real vessel that
--    passed the bbox once is indistinguishable from a garbled frame. What the
--    number is USED for needs only the measurement: a denominator that moves
--    with the count of one-day MMSIs is not a fleet size either way.
--    Class A heard on >= 5 days is stable — 13 056 / 13 909 / 12 540 / 12 527
--    / 13 748 / 11 696 — and is the denominator any ratio should use.
--    `class_a_vessels` and `class_a_vessels_5d` are both emitted so the reader
--    can see the artefact rather than take a corrected number on trust.
--    Class B has the same ghosts, milder: 796 -> 2 728 one-day vessels, about
--    a third of them at <= 3 messages (median 3-14 messages, so most one-day
--    Class B vessels are real boats that sailed once).
--
-- 3. A FIFTH OF EACH YEAR'S FLEET IS NEW AND AN EIGHTH IS ELEVEN YEARS OLD
--    (block 2). 2026's 26 223 Class B vessels break down by first loaded year
--    as 3 202 (2015) / 3 314 (2018) / 5 040 (2021) / 6 126 (2024) / 3 125
--    (2025) / 5 416 (2026): 20.7 % new this year, 12.2 % carried all the way
--    from 2015. The curve is not churn.
--
-- 4. RETENTION IS HIGH AND ROSE (block 3). Share of a year's Class B vessels
--    heard again in the NEXT loaded year: 0.650 (2015->2018), 0.602
--    (2018->2021), 0.648 (2021->2024) — all three-year gaps — and 0.763
--    (2024->2025), 0.758 (2025->2026) over one year. Leisure-only is the same
--    to two decimals (0.649 / 0.610 / 0.658 / 0.769 / 0.773). MIND THE GAP
--    COLUMN: a 0.65 across three years and a 0.76 across one are not the same
--    statistic and `gap_years` is emitted so nobody plots them as a series.
--
-- 5. CLASS B MESSAGE COUNTS STEP IN 2023 TOO, BY LESS (block 4). Messages
--    per Class B vessel-hour on the common window: 41.1 (2015), 39.5 (2018),
--    37.1 (2021), then 50.5 (2024), 50.1 (2025), 49.6 (2026) — +36 % across
--    the gap in which sql/60 block 6 measures the Class A message TAILS
--    doubling. Median messages per Class B vessel-DAY does NOT show it
--    (548 / 438 / 388 / 471 / 469 / 433), and neither does the Class A median
--    (sql/60 block 6): both of these are MEANS over a fleet whose tail grew.
--    CALL IT A STEP IN THE MESSAGE COUNT, NOT IN THE REPORTING RATE. sql/60
--    block 6 shows what it is: the archive stores some messages more than
--    once from 2023 on — Class A vessel-days above the physical 43 200/day
--    ceiling go from 0-0.06 % to 0.18-1.09 %, and Class B's p90 messages per
--    vessel-day goes 979-1 306 -> 1 500-1 527 while its median falls. Nothing
--    here says a transponder started reporting faster.
--    SO: Class B message counts are also not comparable across 2023. Class B
--    HEAD COUNTS are, which is what blocks 1-3 are built from.
-- ===================================================================
--
-- THE COMMON WINDOW, AND WHY EVERY YEAR IS ALSO REPORTED WHOLE. The store
-- holds full years for 2015, 2018, 2021 and 2025; 2024 starts 2024-03-01;
-- 2026 ends 2026-08-26; 2022 and 2023 hold storm months only (2022-01, -02;
-- 2023-02, -12). MARCH 1 - AUGUST 26 IS THE ONLY STRETCH COMMON TO ALL SIX
-- MAIN YEARS — 179 days in every one of them, leap year included, verified.
-- A leisure fleet is 32x bigger in July than in January (S3), so comparing a
-- full 2025 with ten months of 2024 would put a whole extra winter and autumn
-- into one side of the comparison. Block 1 emits BOTH windows with a `window`
-- column; blocks 2, 3 and 4 use the common window ONLY, and say so.
-- 2022 AND 2023 ARE EXCLUDED FROM BLOCKS 2, 3 AND 4 and are present in block 1
-- as `full_year` rows only, with `coverage` = 'storm months only (59 days)'.
-- They have NO row in the common window at all — they hold no day between
-- March 1 and August 26 — so the exclusion is what the data does, not a
-- filter, and their `full_year` numbers (2 151 and 2 372 Class B vessels)
-- are two winter months of a fleet that is 10-20 boats a day in winter (S9
-- finding 44). DO NOT PLOT THEM IN THE ADOPTION SERIES.
--
-- THE DUPLICATION WINDOW NEEDS NO MASK IN THIS FILE, and that is luck worth
-- writing down: the archive's 2015-08-28 -> 2015-09-30 duplication (sql/60
-- block 3, ~2.2-2.6x on Class A message counts) begins TWO DAYS AFTER the
-- common window ends. No block-2, -3 or -4 number touches it. Block 1's
-- `full_year` rows for 2015 do contain it, and block 1 emits no message
-- column at all — every one of its columns is a distinct-vessel count, and
-- uniqExact is structurally immune to duplicated messages.
--
-- THE GAPS ARE THE BIGGEST CAVEAT IN THIS FILE AND BLOCK 2 CANNOT FIX THEM.
-- 2016, 2017, 2019, 2020 and most of 2022 and 2023 are NOT LOADED. So:
--   * "first seen in 2018" means "NOT HEARD IN 2015 AND HEARD IN 2018". A boat
--     that arrived in 2016 is in the 2018 cohort. The cohort is a FIRST LOADED
--     YEAR, never a build year or a registration date, and the essay must say
--     so wherever it draws block 2.
--   * "retained 2015 -> 2018" is a three-year survival, "2024 -> 2025" a
--     one-year one. `gap_years` carries that.
--   * A vessel absent in 2018 and back in 2021 counts as retained by
--     `heard_any_later` and not by `retained_next`. Both are emitted.
--
-- WHAT IS NOT RECOVERABLE HERE:
--   * A BOAT is not recoverable, only a TRANSPONDER. An MMSI is reassigned
--     when a boat is sold and re-registered, and a new transponder in an old
--     boat is a new MMSI. Every "vessel" in this file is an MMSI heard in the
--     bbox, and the cohort/retention blocks measure transponder lifetimes.
--   * WHETHER A BOAT EXISTED BUT WAS SILENT is not in any table. Class B was
--     optional and is still not mandatory for Danish pleasure craft, so this
--     is adoption of AIS, not ownership of boats — the single largest reason
--     the 3.7x is not a count of new boats.
--   * MEDIAN MESSAGES PER ACTIVE HOUR PER VESSEL IS NOT RECOVERABLE. `vessel_day`
--     has no hourly detail and `h3_hourly` has no per-vessel detail — its
--     `vessels` is a uniqExact STATE over the cell-hour, so the MMSIs behind a
--     message count cannot be recovered from it, and no median over vessels of
--     a per-hour quantity exists anywhere in this store. WHAT BLOCK 4 EMITS
--     INSTEAD is a ratio of two exact store-wide totals: sum over hours of
--     (exact distinct Class B vessels heard anywhere in the bbox in that hour)
--     as the denominator, sum of msgs as the numerator. It is a FLEET MEAN per
--     vessel-hour, not a median and not a per-vessel figure, and its bias is
--     stated at block 4.
--
-- RUN TIME, /usr/bin/time -p on an APFS clone of the store (data/ch_a),
-- whole file in one run, output to /dev/null:
--   real 2.40  user 16.13  sys 1.98                          (budget: 60 s)


-- ====================================================================
-- BLOCK 1 — the adoption series, both windows. 14 rows (8 years full_year +
-- 6 years mar_aug), 13 columns:
--   year
--   window        'full_year' | 'mar_aug' (March 1 - August 26, 179 days)
--   coverage      what the store holds for that YEAR — not for the window.
--                 Read it before the numbers: 'full year', 'from 2024-03-01',
--                 'to 2026-08-26', 'storm months only (59 days)'. On a
--                 `mar_aug` row it still describes the year, so 2015 mar_aug
--                 reads 'full year' with loaded_days = 179; `loaded_days` is
--                 the window's own number and is the one to trust.
--   loaded_days   days of that year present in `vessel_day` within the window
--   class_b_vessels          uniqExact(mmsi), mobile = 'Class B'
--   class_b_leisure_vessels  the same, restricted to MMSIs that were filed
--                 `ship_group = 'leisure'` ON AT LEAST ONE DAY of the window.
--                 ship_group is resolved per VESSEL-DAY (sql/03_aggregate.sql)
--                 and a transponder can be 'Undefined' one day and 'Sailing'
--                 the next, so "ever leisure in the window" is the stable
--                 definition; "leisure every day" would count the same boat
--                 differently depending on how often it sailed.
--   class_a_vessels          uniqExact(mmsi), mobile = 'Class A'. GHOST-RIDDEN,
--                 see header point 2 — do not use as a denominator.
--   class_a_vessels_5d       the same, heard on >= 5 days of the window. THIS
--                 is the instrument.
--   leisure_per_class_a, leisure_per_class_a_5d   the same numerator over each
--                 of those two denominators. The second is the honest one.
--   class_b_5d    Class B MMSIs heard on >= 5 days of the window
--   class_b_1d    Class B MMSIs heard on EXACTLY 1 day. The transient tail:
--                 687 -> 2 679 across the common window, 9.2 % -> 10.2 % of
--                 the fleet, i.e. the tail grew WITH the fleet and not faster,
--                 which is why the headline is not a tail artefact.
--   class_a_1d    the same for Class A, and it is NOT stable: 5 554 / 6 370 /
--                 2 126 / 1 983 / 2 027 / 2 000 across the common window —
--                 header point 2, the ghost MMSIs, in one column.
-- ====================================================================
WITH
vy AS (
    -- one row per (window, year, mmsi, mobile). `mobile` is in the key, not
    -- aggregated away: a transponder that reports Class A on some days and
    -- Class B on others (sql/03_aggregate.sql resolves this per day, toward
    -- Class B) then contributes to both classes' counts for that year, which
    -- is the honest answer for a count of "vessels heard as Class B".
    SELECT 'mar_aug' AS window, toYear(day) AS year, mmsi, mobile,
           maxIf(1, ship_group = 'leisure') AS ever_leisure,
           count() AS ndays
    FROM vessel_day
    WHERE day BETWEEN makeDate(toYear(day), 3, 1) AND makeDate(toYear(day), 8, 26)
    GROUP BY window, year, mmsi, mobile
    UNION ALL
    SELECT 'full_year' AS window, toYear(day) AS year, mmsi, mobile,
           maxIf(1, ship_group = 'leisure') AS ever_leisure,
           count() AS ndays
    FROM vessel_day
    GROUP BY window, year, mmsi, mobile
),
ld AS (
    SELECT 'mar_aug' AS window, toYear(day) AS year, uniqExact(day) AS loaded_days
    FROM vessel_day
    WHERE day BETWEEN makeDate(toYear(day), 3, 1) AND makeDate(toYear(day), 8, 26)
    GROUP BY window, year
    UNION ALL
    SELECT 'full_year' AS window, toYear(day) AS year, uniqExact(day) AS loaded_days
    FROM vessel_day GROUP BY window, year
)
SELECT vy.year   AS year,
       vy.window AS window,
       multiIf(vy.year IN (2022, 2023), 'storm months only (59 days)',
               vy.year = 2024,          'from 2024-03-01',
               vy.year = 2026,          'to 2026-08-26',
                                        'full year')            AS coverage,
       ld.loaded_days                                           AS loaded_days,
       uniqExactIf(mmsi, mobile = 'Class B')                    AS class_b_vessels,
       uniqExactIf(mmsi, mobile = 'Class B' AND ever_leisure = 1) AS class_b_leisure_vessels,
       uniqExactIf(mmsi, mobile = 'Class A')                    AS class_a_vessels,
       uniqExactIf(mmsi, mobile = 'Class A' AND ndays >= 5)     AS class_a_vessels_5d,
       round(class_b_leisure_vessels / class_a_vessels,    4)   AS leisure_per_class_a,
       round(class_b_leisure_vessels / class_a_vessels_5d, 4)   AS leisure_per_class_a_5d,
       uniqExactIf(mmsi, mobile = 'Class B' AND ndays >= 5)     AS class_b_5d,
       uniqExactIf(mmsi, mobile = 'Class B' AND ndays  = 1)     AS class_b_1d,
       uniqExactIf(mmsi, mobile = 'Class A' AND ndays  = 1)     AS class_a_1d
FROM vy INNER JOIN ld ON ld.window = vy.window AND ld.year = vy.year
GROUP BY year, window, coverage, loaded_days
ORDER BY window, year
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 2 — the first-seen cohort. 21 rows (the lower triangle of six years),
-- 5 columns:
--   year_heard         one of the six main years
--   cohort_first_seen  the FIRST of the six main years in which that MMSI was
--                      heard as Class B inside the common window
--   vessels            uniqExact(mmsi) in that cell
--   share_of_year      vessels / that year's total Class B in the window
--   years_since_first  year_heard - cohort_first_seen, in calendar years
--
-- READ THE HEADER'S GAP PARAGRAPH BEFORE PLOTTING THIS. 2016, 2017, 2019,
-- 2020, 2022 and 2023 are NOT in the store, so `cohort_first_seen` = 2018
-- means "not heard in 2015, heard in 2018" and nothing narrower. A stacked
-- area of `vessels` by cohort is the right chart; a caption calling 2018 a
-- cohort of new boats is wrong.
-- THE COHORT IS COMPUTED INSIDE THE COMMON WINDOW, not over the whole year, so
-- that it agrees with the counts it is a breakdown of. A vessel heard only in
-- (say) October 2015 and again in May 2018 is a 2018 cohort member here.
-- 2022 and 2023 cannot appear as a cohort: they hold no day of the window.
-- MEASURED: 2026's 26 223 vessels are 3 202 / 3 314 / 5 040 / 6 126 / 3 125 /
-- 5 416 by cohort 2015 / 2018 / 2021 / 2024 / 2025 / 2026.
-- ====================================================================
WITH
w AS (
    SELECT mmsi, toYear(day) AS year
    FROM vessel_day
    WHERE mobile = 'Class B'
      AND toYear(day) IN (2015, 2018, 2021, 2024, 2025, 2026)
      AND day BETWEEN makeDate(toYear(day), 3, 1) AND makeDate(toYear(day), 8, 26)
    GROUP BY mmsi, year
),
first_seen AS (
    SELECT mmsi, min(year) AS cohort FROM w GROUP BY mmsi
),
yr_total AS (
    SELECT year, uniqExact(mmsi) AS total FROM w GROUP BY year
)
SELECT w.year                                  AS year_heard,
       f.cohort                                AS cohort_first_seen,
       toUInt16(w.year - f.cohort)             AS years_since_first,
       uniqExact(w.mmsi)                       AS vessels,
       round(uniqExact(w.mmsi) / any(t.total), 4) AS share_of_year
FROM w
INNER JOIN first_seen AS f USING (mmsi)
INNER JOIN yr_total   AS t ON t.year = w.year
GROUP BY year_heard, cohort_first_seen, years_since_first
ORDER BY year_heard, cohort_first_seen
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 3 — retention between consecutive LOADED main years. 5 rows, 9 cols:
--   year_from, year_to, gap_years    THE GAP IS NOT 1 FOR THE FIRST THREE
--                    ROWS. 2015->2018 and 2018->2021 and 2021->2024 are
--                    three-year survivals because 2016-17, 2019-20 and 2022-23
--                    are unloaded; 2024->2025 and 2025->2026 are one-year
--                    ones. A chart that draws these five as a series without
--                    the gap is wrong, which is why the column is third.
--   vessels_from             Class B MMSIs in year_from's common window
--   retained_next            share of those heard again in year_to
--   leisure_from             of those, the ones ever filed leisure in
--                            year_from's window
--   retained_next_leisure    share of THOSE heard again in year_to AND filed
--                            leisure there too — a stricter test than
--                            `retained_next`, since a boat can come back
--                            filed 'Undefined'
--   heard_any_later          share of year_from's vessels heard in ANY later
--                            main year, not only the next one. For 2025 this
--                            equals `retained_next` by construction (2026 is
--                            the last loaded year) and the row says so via
--                            gap_years = 1 and year_to = 2026.
-- MEASURED: 0.6495 / 0.6016 / 0.6484 over three years, 0.7632 / 0.7584 over
-- one. Leisure-only: 0.6489 / 0.6097 / 0.6580 / 0.7694 / 0.7732.
-- WHAT RETENTION IS NOT: it is not a survival rate of boats. An MMSI stops
-- appearing when the transponder is switched off, the boat is sold and
-- re-registered, or the owner sails elsewhere that summer — and the store
-- cannot tell those apart (see the header's "not recoverable").
-- ====================================================================
WITH
w AS (
    SELECT mmsi, toYear(day) AS year, maxIf(1, ship_group = 'leisure') AS ever_leisure
    FROM vessel_day
    WHERE mobile = 'Class B'
      AND toYear(day) IN (2015, 2018, 2021, 2024, 2025, 2026)
      AND day BETWEEN makeDate(toYear(day), 3, 1) AND makeDate(toYear(day), 8, 26)
    GROUP BY mmsi, year
),
-- one row per MMSI carrying the set of years it was heard in, and the subset
-- of those in which it was ever filed leisure. Arrays, because ClickHouse has
-- no correlated IN subquery and a self-join per pair would scan `w` ten times.
seen AS (
    SELECT mmsi,
           groupUniqArray(year) AS years,
           groupUniqArrayIf(year, ever_leisure = 1) AS leisure_years
    FROM w GROUP BY mmsi
),
pairs AS (
    SELECT arrayJoin([(2015, 2018), (2018, 2021), (2021, 2024),
                      (2024, 2025), (2025, 2026)]) AS p
)
SELECT p.1                                              AS year_from,
       p.2                                              AS year_to,
       toUInt16(p.2 - p.1)                              AS gap_years,
       countIf(has(years, p.1))                         AS vessels_from,
       countIf(has(years, p.1) AND has(years, p.2))     AS vessels_next,
       round(countIf(has(years, p.1) AND has(years, p.2))
             / countIf(has(years, p.1)), 4)             AS retained_next,
       countIf(has(leisure_years, p.1))                 AS leisure_from,
       round(countIf(has(leisure_years, p.1) AND has(leisure_years, p.2))
             / countIf(has(leisure_years, p.1)), 4)     AS retained_next_leisure,
       round(countIf(has(years, p.1) AND arrayExists(x -> x > p.1, years))
             / countIf(has(years, p.1)), 4)             AS heard_any_later
FROM seen CROSS JOIN pairs
GROUP BY year_from, year_to, gap_years
ORDER BY year_from;


-- ====================================================================
-- BLOCK 4 — Class B message counts and flag shares, common window
-- only. 6 rows (the six main years), 10 columns:
--   year
--   vessel_days                      rows in `vessel_day`, Class B, in window
--   median_msgs_per_vessel_day       medianExact(msgs) over those rows
--   vessel_hours                     sum over UTC hours of the EXACT count of
--        distinct Class B vessels heard anywhere in the bbox in that hour
--        (uniqExactMerge over every res-7 cell of the hour). Exact.
--   msgs                             sum(msgs) over the same hours
--   msgs_per_vessel_hour             msgs / vessel_hours
--   vessel_days_moving               rows with dist_nm > 0
--   median_dist_nm_moving            medianExact(dist_nm) over THOSE rows
--   danish_share                     share of the window's distinct Class B
--        MMSIs whose first three digits (the MID) are 219 or 220 — Denmark
--   german_share                     the same for MID 211 or 218 — Germany
--
-- WHAT `msgs_per_vessel_hour` IS, AND ITS BIAS. It is a ratio of two exact
-- store-wide totals, NOT a per-vessel statistic and NOT a median: a vessel
-- heard for 200 hours contributes 200 times as much to both sides as one heard
-- for one hour, so the figure describes the fleet's messages per hour-at-sea
-- and is dominated by the boats that sail most. That is the right bias for a
-- RECEPTION question (it is a property of the network and the transponders,
-- not of who owns them) and the wrong one for "what does a typical boat do".
-- A true median over vessels of messages per active hour IS NOT RECOVERABLE
-- from this store — see the header. The vessel-DAY median next to it has the
-- opposite bias (every vessel-day counts once, a day at the mooring included),
-- and the two disagreeing is informative: the vessel-hour MEAN steps in 2023
-- and the vessel-day MEDIAN does not, which is the signature of a tail that
-- grew rather than a fleet that reports faster (sql/60 block 6, header
-- point 2).
-- MEASURED, msgs_per_vessel_hour: 41.1 / 39.5 / 37.1 / 50.5 / 50.1 / 49.6 for
-- 2015 / 2018 / 2021 / 2024 / 2025 / 2026.
--
-- MID = intDiv(mmsi, 1000000), the Maritime Identification Digits, the flag
-- state of the registration — a COUNTRY CODE, and the only vessel attribute in
-- this file, emitted as a share over thousands of vessels and never per
-- vessel. Denmark is 219 and 220. GERMANY IS THE BIGGER GROUP AND IT SURPRISED
-- THIS SESSION: on 2025's whole-year Class B fleet the top MIDs by distinct
-- vessel are 211 Germany 8 079, 219 Denmark 6 277, 265 Sweden 3 549, 244
-- Netherlands 1 651, 257 Norway 1 484 — so `german_share` is emitted next to
-- `danish_share` rather than leaving the reader with a 0.18-0.26 "Danish
-- share" and no idea what the rest is. The bbox (lat 53-59, lon 3-17) reaches
-- Kiel, Flensburg, Ruegen and the Dutch Wadden, so this is the fleet in the
-- box, not the fleet of Denmark.
-- ====================================================================
WITH
vd AS (
    SELECT toYear(day) AS year, mmsi, msgs, dist_nm
    FROM vessel_day
    WHERE mobile = 'Class B'
      AND toYear(day) IN (2015, 2018, 2021, 2024, 2025, 2026)
      AND day BETWEEN makeDate(toYear(day), 3, 1) AND makeDate(toYear(day), 8, 26)
),
per_year_vd AS (
    SELECT year,
           count()                                   AS vessel_days,
           round(medianExact(msgs), 1)               AS median_msgs_per_vessel_day,
           countIf(dist_nm > 0)                      AS vessel_days_moving,
           round(medianExactIf(dist_nm, dist_nm > 0), 2) AS median_dist_nm_moving,
           round(uniqExactIf(mmsi, intDiv(mmsi, 1000000) IN (219, 220)) / uniqExact(mmsi), 4) AS danish_share,
           round(uniqExactIf(mmsi, intDiv(mmsi, 1000000) IN (211, 218)) / uniqExact(mmsi), 4) AS german_share
    FROM vd GROUP BY year
),
-- the hourly side has to be aggregated per HOUR first: uniqExactMerge over the
-- cells of one hour is the exact number of vessels present in that hour, and
-- summing those over a year gives vessel-hours. Merging straight to the year
-- would give distinct vessels in the YEAR, which is a different quantity.
per_hour AS (
    SELECT toYear(hour) AS year, hour,
           uniqExactMerge(vessels) AS vh,
           sum(msgs)               AS h_msgs
    FROM h3_hourly
    WHERE mobile = 'Class B'
      AND toYear(hour) IN (2015, 2018, 2021, 2024, 2025, 2026)
      AND toDate(hour) BETWEEN makeDate(toYear(hour), 3, 1) AND makeDate(toYear(hour), 8, 26)
    GROUP BY year, hour
),
per_year_hr AS (
    SELECT year, sum(vh) AS vessel_hours, sum(h_msgs) AS msgs,
           round(sum(h_msgs) / sum(vh), 1) AS msgs_per_vessel_hour
    FROM per_hour GROUP BY year
)
SELECT v.year                          AS year,
       v.vessel_days                   AS vessel_days,
       v.median_msgs_per_vessel_day    AS median_msgs_per_vessel_day,
       h.vessel_hours                  AS vessel_hours,
       h.msgs                          AS msgs,
       h.msgs_per_vessel_hour          AS msgs_per_vessel_hour,
       v.vessel_days_moving            AS vessel_days_moving,
       v.median_dist_nm_moving         AS median_dist_nm_moving,
       v.danish_share                  AS danish_share,
       v.german_share                  AS german_share
FROM per_year_vd AS v INNER JOIN per_year_hr AS h USING (year)
ORDER BY year
SETTINGS join_use_nulls = 0;
