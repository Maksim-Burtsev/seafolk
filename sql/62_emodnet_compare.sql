-- S10 check — our leisure density for JULY 2021 against an independent source.
-- Run: scripts/ch.sh sql/62_emodnet_compare.sql
--      (read-only; 200 + 200 + 2 + 40 + 4 rows; writes nothing.
--       Timing in "RUN TIME" at the foot of this header.)
-- Reads `h3_hourly` and the committed context file
-- data/context/emodnet_2021-07_leisure.tsv (built by notes/emodnet.py).
--
-- WHAT IS COMPARED. EMODnet Human Activities publishes monthly vessel density
-- on a 1 km EPSG:3035 grid, per AIS ship-type code; 04 is Sailing and 05 is
-- Pleasure Craft, and together they are the closest thing anybody else
-- publishes to this project's `ship_group = 'leisure'`. It is built from the
-- same underlying AIS, but by a different pipeline, a different receiver mix
-- and a different definition — so it is a cross-check on SHAPE, never a
-- second opinion on a level.
--
-- THE UNIT DOES NOT MATCH, AND IT CANNOT BE MADE TO.
--   EMODnet: draws a LINE between consecutive positions of one ship, cuts it
--   against the 1 km grid and sums the time each segment spends in each cell.
--   Hours per km2 per month. A ship crossing a cell in six minutes adds 0.1.
--   Ours:    `h3_hourly` counts PRESENCE. vessel_hours = sum over cell-hours
--   of uniqExactMerge(vessels) — a vessel that left one message in a cell in
--   an hour adds a whole 1, and a vessel that sat there all month adds 744.
--   The grid differs too: 1 km2 pixels against ~5 km2 H3 res-7 cells.
-- So the levels are NOT comparable and no ratio between them is quoted here.
-- THE RANK IS WHAT IS COMPARED: if the two sources disagree about WHERE the
-- leisure fleet is, that is a finding about our coverage. If they agree on the
-- order of the busiest cells while disagreeing on the numbers, the unit
-- mismatch is doing the disagreeing.
-- The res-5 block exists for the same reason: at ~250 km2 a cell is bigger
-- than the difference between the two griddings, so a rank correlation that
-- rises from res 7 to res 5 is the grid, not the fleet. MEASURED: Spearman
-- over the union goes 0.6427 (res 7) -> 0.6987 (res 5), so some of the res-7
-- disagreement is griddling and most of it is not.
--
-- WHAT THE MISMATCH LOOKS LIKE WHEN YOU LOOK AT ONE CELL. Res-7 cell
-- 608533867682332671 (57.3177 N, 11.1397 E, a harbour on Laeso: on land by the
-- `land` dictionary, one marina in it) is our 9th densest cell — 12 989
-- vessel-hours from 348 distinct Class B leisure vessels present in all 744
-- hours of the month, 2.9 % of their messages moving — and EMODnet gives it
-- 4.1 hours, rank 16 984. A boat that never moves draws no line, so EMODnet's
-- method cannot see a full marina and ours cannot see anything else. Neither
-- is wrong; they measure different things, which is why only the rank travels.
--
-- THE MONTH BOUNDARY IS THE UTC CALENDAR MONTH,
--   hour >= 2021-07-01 00:00 UTC and < 2021-08-01 00:00 UTC.
-- `h3_hourly.hour` is UTC (sql/01_schema.sql) and AIS timestamps are UTC, so
-- EMODnet's "monthly total" is presumed to be the same calendar month; the
-- dataset states no other convention. Denmark is UTC+2 in July, so a local
-- month would shift the window by two hours at each end — 2 h out of 744 — and
-- the choice is stated rather than measured because it cannot change a rank.
--
-- LEISURE IS BOTH CLASSES. `ship_group = 'leisure'` regardless of `mobile`,
-- because EMODnet's codes 04/05 do not distinguish Class A from Class B
-- either. MEASURED for this month: Class A is 121 642 of 2 981 367 leisure
-- vessel-hours, 4.1 %. The distinct-vessel counts merge the uniqExact states
-- across both classes, so a vessel that reported as both in one cell-hour
-- (10 % of vessels do, sql/01_schema.sql) is counted once.
--
-- PRIVACY — THE k >= 5 FLOOR. Every row that carries an h3 id or a coordinate
-- is floored: uniqExactMerge(vessels) over the whole month for that cell must
-- be >= 5 distinct leisure vessels. 21 059 of the 39 101 res-7 cells with any
-- leisure vessel-hours in July 2021 clear it; the rest are dropped from blocks
-- 1, 2 and 4 and never appear with their cell id.
-- The RANKS AND THE SUMMARY ARE COMPUTED OVER ALL CELLS, floored or not — a
-- rank number and a correlation disclose nothing about which cell held which
-- boat, and flooring the domain first would silently change what the ranks
-- mean. Block 3 emits counts, correlations and shares only: no cell ids.
--
-- FIVE STATEMENTS, separated by row width the way sql/51's are:
--   1. per-cell pairs at res 7, top 200 by EMODnet rank       [ 9 cols]
--   2. the same at res 5                                      [ 9 cols]
--   3. one summary row per resolution                         [13 cols]
--   4. the ten densest cells on each side, both resolutions   [10 cols]
--   5. the missed EMODnet hours split by zone, res 7          [ 5 cols]
-- Blocks 1 and 2 share a width; their first column is `res`, so a consumer
-- that concatenates them can still tell them apart.
-- The WITH block is repeated verbatim in all five statements. clickhouse-local
-- has no cross-statement scope and this file is READ-ONLY — it will not create
-- a table to share one. Each copy costs ~0.4 s of the total.
--
-- COORDINATE ORDER, again: under scripts/ch.sh's pins geoToH3 takes
-- (LAT, LON, res) and h3ToGeo returns (LAT, LON), so `.1` is lat and `.2` is
-- lon in block 4. See sql/04_context.sql's banner for what a swap costs.
-- The context file's own columns are (lon, lat) — GeoJSON order, as written by
-- notes/emodnet.py — and are bound BY POSITION in the file() schema below, so
-- the two orders meet in the geoToH3(lat, lon, …) call and nowhere else.
-- input_format_tsv_skip_first_lines = 17 skips the file's commented header,
-- and 17 IS ALSO ASSERTED — see the throwIf in block 1's WHERE. Left to the
-- parser alone only ONE of the two failures is loud: a header that GROWS
-- pushes a '#' line into Float64 parsing and throws, but a header that SHRINKS
-- is SILENT — skip-17 swallows the first data row and the comparison quietly
-- loses one pixel. The guard counts the lines that start with '#' (via
-- LineAsString, which the TSV settings do not touch) and throws either way.
-- The header carries NO BUILD DATE on purpose: notes/emodnet.py used to stamp
-- one, which made every rebuild a diff of a 5.7 MB blob and contradicted the
-- "two runs produce the same file" claim in its own docstring.
--
-- RUN TIME, /usr/bin/time -p on an APFS clone of the store (data/ch_a),
-- whole file in one run, output to /dev/null:
--   real 1.69  user 12.24  sys 1.22                          (budget: 60 s)


-- ====================================================================
-- BLOCK 1 — PER-CELL PAIRS AT RES 7 (~5 km2), the 200 densest AMONG THE CELLS
-- THAT CLEAR k >= 5 — which is NOT the 200 EMODnet calls densest. The floor is
-- applied first and the limit second, so a cell EMODnet ranks in its true top
-- 200 but where we saw fewer than five leisure vessels is dropped and a cell
-- further down the list takes its place: 18 of EMODnet's true top 200 are
-- floored out here (23 at res 5) and the block reaches rank 225. Block 3's
-- `top200_floored_out` counts them; do not read this block as EMODnet's list.
-- 9 columns: res, h3, our_vessel_hours, our_vessels, emodnet_hours,
--            emodnet_sailing, emodnet_pleasure, rank_ours, rank_emodnet
-- rank 1 = densest. Both ranks are over the UNION of cells that either source
-- puts anything in, and rank() gives every tie the same number — so the
-- 12 697 res-7 cells where we have zero vessel-hours all read rank_ours =
-- 39 102 (1 758 cells have vessel-hours at res 5, so the tie there is 1 759).
-- A rank_ours in the tens of thousands means "we have nothing here", not
-- "we have a little".
-- emodnet_hours is code 04 + code 05, rounded to 0.1 h; the next two columns
-- are the same total split back into Sailing and Pleasure Craft, because a
-- cell that is all 04 and a cell that is all 05 are different places and only
-- EMODnet can tell us which — our `ship_group = 'leisure'` merges them.
-- ====================================================================
WITH
toDateTime('2021-07-01 00:00:00', 'UTC') AS t0,
toDateTime('2021-08-01 00:00:00', 'UTC') AS t1,
-- one row per (cell, hour): the head count in that hour, and the state kept so
-- the month's DISTINCT vessels can be merged per cell (and per res-5 parent)
-- instead of summed, which would count one boat once per hour it was seen.
cellhour AS (
    SELECT h3, hour,
           uniqExactMerge(vessels)      AS v,
           uniqExactMergeState(vessels) AS st
    FROM h3_hourly
    WHERE hour >= t0 AND hour < t1 AND ship_group = 'leisure'
    GROUP BY h3, hour
),
ours AS (
    SELECT 7 AS res, h3 AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
    UNION ALL
    SELECT 5 AS res, h3ToParent(h3, 5) AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
),
px AS (
    SELECT lon, lat, hs, hp
    FROM file('data/context/emodnet_2021-07_leisure.tsv', TSV,
              'lon Float64, lat Float64, hs Float64, hp Float64')
),
emo AS (
    SELECT 7 AS res, geoToH3(lat, lon, 7) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
    UNION ALL
    SELECT 5 AS res, geoToH3(lat, lon, 5) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
),
-- FULL join: a cell only one source knows about must survive, or the zero
-- shares in block 3 have nothing to count. With join_use_nulls = 0 the missing
-- side's key columns come back as 0, and 0 is not a legal h3 index nor a legal
-- resolution here, so greatest() picks the real value from whichever side has
-- one. (USING would be shorter and is not safe: which side's key survives a
-- FULL join is a version-dependent detail.)
pairs AS (
    SELECT greatest(o.res, e.res)   AS res,
           greatest(o.cell, e.cell) AS cell,
           o.vh                     AS our_vh,
           o.vessels                AS our_vessels,
           e.h_sail                 AS emo_sail,
           e.h_plea                 AS emo_plea,
           e.h_sail + e.h_plea      AS emo_hours
    FROM ours AS o FULL OUTER JOIN emo AS e ON o.res = e.res AND o.cell = e.cell
),
ranked AS (
    SELECT res, cell, our_vh, our_vessels, emo_sail, emo_plea, emo_hours,
           rank() OVER (PARTITION BY res ORDER BY our_vh    DESC) AS rank_ours,
           rank() OVER (PARTITION BY res ORDER BY emo_hours DESC) AS rank_emodnet
    FROM pairs
)
SELECT res, cell AS h3, our_vh AS our_vessel_hours, our_vessels,
       round(emo_hours, 1) AS emodnet_hours,
       round(emo_sail, 1)  AS emodnet_sailing,
       round(emo_plea, 1)  AS emodnet_pleasure,
       rank_ours, rank_emodnet
FROM ranked
WHERE res = 7 AND our_vessels >= 5          -- the k floor
  -- THE HEADER GUARD, and it is here rather than in a comment because the
  -- silent direction is a SHRINKING header (see the file header). It costs one
  -- pass over the 5.7 MB context file, ~0.02 s, once per run of this file.
  AND NOT throwIf((SELECT countIf(startsWith(line, '#'))
                   FROM file('data/context/emodnet_2021-07_leisure.tsv', LineAsString)) != 17,
                  'data/context/emodnet_2021-07_leisure.tsv no longer has exactly 17 commented header lines: rebuild it with notes/emodnet.py, then set input_format_tsv_skip_first_lines and this guard to the new count in every statement of sql/62.')
ORDER BY rank_emodnet, h3
LIMIT 200
SETTINGS input_format_tsv_skip_first_lines = 17, join_use_nulls = 0;


-- ====================================================================
-- BLOCK 2 — THE SAME AT RES 5 (~250 km2). Identical query, `res = 5`.
-- A res-5 cell holds 49 res-7 cells, so the k floor is nearly free here and
-- the block is effectively the whole grid ordered by EMODnet.
-- 9 columns, same names.
-- ====================================================================
WITH
toDateTime('2021-07-01 00:00:00', 'UTC') AS t0,
toDateTime('2021-08-01 00:00:00', 'UTC') AS t1,
cellhour AS (
    SELECT h3, hour,
           uniqExactMerge(vessels)      AS v,
           uniqExactMergeState(vessels) AS st
    FROM h3_hourly
    WHERE hour >= t0 AND hour < t1 AND ship_group = 'leisure'
    GROUP BY h3, hour
),
ours AS (
    SELECT 7 AS res, h3 AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
    UNION ALL
    SELECT 5 AS res, h3ToParent(h3, 5) AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
),
px AS (
    SELECT lon, lat, hs, hp
    FROM file('data/context/emodnet_2021-07_leisure.tsv', TSV,
              'lon Float64, lat Float64, hs Float64, hp Float64')
),
emo AS (
    SELECT 7 AS res, geoToH3(lat, lon, 7) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
    UNION ALL
    SELECT 5 AS res, geoToH3(lat, lon, 5) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
),
pairs AS (
    SELECT greatest(o.res, e.res)   AS res,
           greatest(o.cell, e.cell) AS cell,
           o.vh                     AS our_vh,
           o.vessels                AS our_vessels,
           e.h_sail                 AS emo_sail,
           e.h_plea                 AS emo_plea,
           e.h_sail + e.h_plea      AS emo_hours
    FROM ours AS o FULL OUTER JOIN emo AS e ON o.res = e.res AND o.cell = e.cell
),
ranked AS (
    SELECT res, cell, our_vh, our_vessels, emo_sail, emo_plea, emo_hours,
           rank() OVER (PARTITION BY res ORDER BY our_vh    DESC) AS rank_ours,
           rank() OVER (PARTITION BY res ORDER BY emo_hours DESC) AS rank_emodnet
    FROM pairs
)
SELECT res, cell AS h3, our_vh AS our_vessel_hours, our_vessels,
       round(emo_hours, 1) AS emodnet_hours,
       round(emo_sail, 1)  AS emodnet_sailing,
       round(emo_plea, 1)  AS emodnet_pleasure,
       rank_ours, rank_emodnet
FROM ranked
WHERE res = 5 AND our_vessels >= 5
ORDER BY rank_emodnet, h3
LIMIT 200
SETTINGS input_format_tsv_skip_first_lines = 17, join_use_nulls = 0;


-- ====================================================================
-- BLOCK 3 — THE SUMMARY, one row per resolution. NO CELL IDS, so it is
-- computed over every cell either source knows about, floored or not.
-- 13 columns:
--   res
--   n_both          cells where BOTH sources are > 0
--   n_emodnet_only  EMODnet has hours, we have no leisure vessel-hour
--   n_ours_only     we have vessel-hours, EMODnet has nothing
--   rankcorr_both   Spearman over the n_both cells — "given that both of us
--                   see this water, do we order it the same way?"
--   rankcorr_union  Spearman over every cell either sees. The honest number:
--                   it pays for the cells one side misses entirely.
--   pearson_log1p   corr(log1p(ours), log1p(emodnet)) over the union. Logs
--                   because both distributions are long-tailed by orders of
--                   magnitude; log1p because zeros are the point.
--   top10_overlap   how many of EMODnet's ten densest are in our ten densest
--   top25_overlap   the same at 25
--   top200_floored_out  how many of EMODnet's TRUE top 200 (rank_emodnet <=
--                   200 over the whole domain) carry fewer than 5 distinct
--                   leisure vessels of ours and are therefore NOT in block 1 /
--                   block 2, which take the 200 densest among the cells that
--                   clear the floor. 18 at res 7, 23 at res 5; the blocks
--                   reach rank 225 and 229 filling the gaps.
--   emo_hours_in_our_zero  share of ALL EMODnet leisure hours that falls in
--                   cells where we have zero leisure vessel-hours. This is a
--                   coverage number: water EMODnet sees boats in and we do not.
--   our_vh_in_emo_zero     the mirror: share of our vessel-hours in cells
--                   EMODnet gives no leisure hours at all.
--   n_union         every cell either source puts anything in (the domain of
--                   rankcorr_union, pearson_log1p and both shares)
-- rank() ties share a rank, so a tie straddling the tenth place can make an
-- overlap count read above 10; MEASURED here it does not.
--
-- MEASURED, and the two shares are NOT symmetric: at res 7, 10.26 % of
-- EMODnet's leisure hours sit in cells where we have nothing, against 0.62 %
-- the other way. The asymmetry is the bbox, not the fleet — BLOCK 5 SPLITS IT
-- BY ZONE and is the only place that split is computed. sql/01_schema.sql's
-- bbox is a scope decision that reaches water the Danish receiver network does
-- not; EMODnet's ranks 5, 7 and 8 at res 7 are Terschelling, Den Helder and
-- Västervik, where we hold 3, 2 and 0 vessel-hours. This is S10's honesty
-- layer with somebody else's numbers on it.
-- ====================================================================
WITH
toDateTime('2021-07-01 00:00:00', 'UTC') AS t0,
toDateTime('2021-08-01 00:00:00', 'UTC') AS t1,
cellhour AS (
    SELECT h3, hour,
           uniqExactMerge(vessels)      AS v,
           uniqExactMergeState(vessels) AS st
    FROM h3_hourly
    WHERE hour >= t0 AND hour < t1 AND ship_group = 'leisure'
    GROUP BY h3, hour
),
ours AS (
    SELECT 7 AS res, h3 AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
    UNION ALL
    SELECT 5 AS res, h3ToParent(h3, 5) AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
),
px AS (
    SELECT lon, lat, hs, hp
    FROM file('data/context/emodnet_2021-07_leisure.tsv', TSV,
              'lon Float64, lat Float64, hs Float64, hp Float64')
),
emo AS (
    SELECT 7 AS res, geoToH3(lat, lon, 7) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
    UNION ALL
    SELECT 5 AS res, geoToH3(lat, lon, 5) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
),
pairs AS (
    SELECT greatest(o.res, e.res)   AS res,
           greatest(o.cell, e.cell) AS cell,
           o.vh                     AS our_vh,
           o.vessels                AS our_vessels,
           e.h_sail                 AS emo_sail,
           e.h_plea                 AS emo_plea,
           e.h_sail + e.h_plea      AS emo_hours
    FROM ours AS o FULL OUTER JOIN emo AS e ON o.res = e.res AND o.cell = e.cell
),
ranked AS (
    SELECT res, cell, our_vh, our_vessels, emo_sail, emo_plea, emo_hours,
           rank() OVER (PARTITION BY res ORDER BY our_vh    DESC) AS rank_ours,
           rank() OVER (PARTITION BY res ORDER BY emo_hours DESC) AS rank_emodnet
    FROM pairs
)
SELECT
    res,
    countIf(our_vh > 0 AND emo_hours > 0)                        AS n_both,
    countIf(our_vh = 0 AND emo_hours > 0)                        AS n_emodnet_only,
    countIf(our_vh > 0 AND emo_hours = 0)                        AS n_ours_only,
    round(rankCorrIf(our_vh, emo_hours, our_vh > 0 AND emo_hours > 0), 4) AS rankcorr_both,
    round(rankCorr(our_vh, emo_hours), 4)                        AS rankcorr_union,
    round(corr(log1p(our_vh), log1p(emo_hours)), 4)              AS pearson_log1p,
    countIf(rank_emodnet <= 10 AND rank_ours <= 10)              AS top10_overlap,
    countIf(rank_emodnet <= 25 AND rank_ours <= 25)              AS top25_overlap,
    countIf(rank_emodnet <= 200 AND our_vessels < 5)              AS top200_floored_out,
    round(sumIf(emo_hours, our_vh = 0) / sum(emo_hours), 4)      AS emo_hours_in_our_zero,
    round(sumIf(our_vh, emo_hours = 0) / sum(our_vh), 4)         AS our_vh_in_emo_zero,
    count()                                                      AS n_union
FROM ranked
GROUP BY res
ORDER BY res DESC
SETTINGS input_format_tsv_skip_first_lines = 17, join_use_nulls = 0;


-- ====================================================================
-- BLOCK 4 — THE TEN DENSEST CELLS ON EACH SIDE, both resolutions, with the
-- cell CENTRE and the rank the other source gives the same cell.
-- 10 columns: res, side, h3, lat, lon, our_vessel_hours, our_vessels,
--             emodnet_hours, rank_ours, rank_emodnet
--   side = 'ours'    the ten our vessel-hours call densest
--   side = 'emodnet' the ten EMODnet's hours call densest
-- FLOORED AT k >= 5 ON BOTH SIDES, including EMODnet's — the row carries an
-- h3 id and a coordinate, and the floor is on emitting the CELL, not on whose
-- number chose it. So "EMODnet's ten densest" means "the ten densest among
-- cells where we saw at least five leisure vessels in the month". The ranks in
-- the last two columns are the unfloored ones from block 1/2's domain, so a
-- gap in them is where a floored-out cell sat.
-- lat/lon are the H3 cell centre, NOT a vessel position: h3ToGeo returns
-- (lat, lon) under scripts/ch.sh's pins, hence .1 and .2 in that order.
-- The essay names these places; this file does not.
-- ====================================================================
WITH
toDateTime('2021-07-01 00:00:00', 'UTC') AS t0,
toDateTime('2021-08-01 00:00:00', 'UTC') AS t1,
cellhour AS (
    SELECT h3, hour,
           uniqExactMerge(vessels)      AS v,
           uniqExactMergeState(vessels) AS st
    FROM h3_hourly
    WHERE hour >= t0 AND hour < t1 AND ship_group = 'leisure'
    GROUP BY h3, hour
),
ours AS (
    SELECT 7 AS res, h3 AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
    UNION ALL
    SELECT 5 AS res, h3ToParent(h3, 5) AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
),
px AS (
    SELECT lon, lat, hs, hp
    FROM file('data/context/emodnet_2021-07_leisure.tsv', TSV,
              'lon Float64, lat Float64, hs Float64, hp Float64')
),
emo AS (
    SELECT 7 AS res, geoToH3(lat, lon, 7) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
    UNION ALL
    SELECT 5 AS res, geoToH3(lat, lon, 5) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
),
pairs AS (
    SELECT greatest(o.res, e.res)   AS res,
           greatest(o.cell, e.cell) AS cell,
           o.vh                     AS our_vh,
           o.vessels                AS our_vessels,
           e.h_sail                 AS emo_sail,
           e.h_plea                 AS emo_plea,
           e.h_sail + e.h_plea      AS emo_hours
    FROM ours AS o FULL OUTER JOIN emo AS e ON o.res = e.res AND o.cell = e.cell
),
ranked AS (
    SELECT res, cell, our_vh, our_vessels, emo_sail, emo_plea, emo_hours,
           rank() OVER (PARTITION BY res ORDER BY our_vh    DESC) AS rank_ours,
           rank() OVER (PARTITION BY res ORDER BY emo_hours DESC) AS rank_emodnet
    FROM pairs
),
floored AS (SELECT * FROM ranked WHERE our_vessels >= 5),
picked AS (
    SELECT *, 'ours' AS side,
           row_number() OVER (PARTITION BY res ORDER BY our_vh DESC, cell) AS n
    FROM floored
    UNION ALL
    SELECT *, 'emodnet' AS side,
           row_number() OVER (PARTITION BY res ORDER BY emo_hours DESC, cell) AS n
    FROM floored
)
SELECT res, side, cell AS h3,
       round(h3ToGeo(cell).1, 4)  AS lat,        -- .1 is LAT under the pins
       round(h3ToGeo(cell).2, 4)  AS lon,
       our_vh AS our_vessel_hours, our_vessels,
       round(emo_hours, 1) AS emodnet_hours,
       rank_ours, rank_emodnet
FROM picked
WHERE n <= 10
ORDER BY res DESC, side, n
SETTINGS input_format_tsv_skip_first_lines = 17, join_use_nulls = 0;

-- ====================================================================
-- BLOCK 5 — WHERE THE MISSED EMODnet HOURS ARE. Block 3 says 10.26 % of
-- EMODnet's res-7 leisure hours fall in cells we have nothing in; this block
-- says which water that is. One row per zone, 4 rows, 5 columns:
--   zone                        the zone label, see the rule below
--   emodnet_hours               EMODnet leisure hours in the zone
--   emodnet_hours_in_our_zero   of those, the ones in cells where our leisure
--                               vessel-hours are 0
--   share_missed                the second divided by the first
--   n_cells                     res-7 cells either source puts anything in.
--                               The four sum to block 3's n_union (51 798).
-- RES 7 ONLY. NO CELL ID AND NO COORDINATE IS EMITTED — a zone is a quarter of
-- the bbox and every column is a sum over thousands of cells, so this block
-- runs on the unfloored domain for the same reason block 3 does.
--
-- THE ZONE RULE. The zone is decided by the RES-7 CELL CENTRE (h3ToGeo; .1 is
-- lat and .2 is lon under scripts/ch.sh's pins), and the tests are applied in
-- this order, FIRST MATCH WINS — that is how the overlaps are resolved, and it
-- makes the four zones a PARTITION of the bbox with no cell in two of them:
--   1. lon <  7      'west of lon 7'      the Dutch/German Wadden and the North
--                                         Sea corner north of it
--   2. lon >= 13.5   'east of lon 13.5'   the Swedish east coast and the open
--                                         Baltic (Vastervik, Norrkoping)
--   3. lat <  54.5   'south of 54.5 N'    the German Bight and the German
--                                         Baltic coast, lon 7 .. 13.5
--   4. otherwise     'Danish core'        lon 7 .. 13.5, lat >= 54.5
-- The bbox itself (lat 53-59, lon 3-17) is sql/01_schema.sql's.
--
-- MEASURED, and this is the sentence the essay quotes: the share of EMODnet's
-- leisure hours we have no vessel-hour for is 61.19 % west of lon 7, 32.96 %
-- east of lon 13.5, 7.13 % south of 54.5 N and 1.12 % in the Danish core. The
-- asymmetry of block 3's two shares is a SCOPE decision — the bbox reaches
-- water the Danish receiver network does not — and not a reception finding.
-- BEFORE S10's design review this split was a literal in this header (3.0 /
-- 13.3 / 33 / 53) that no query in the repo produced; two of those four
-- numbers do not reproduce under any zone rule, and this block replaces them.
-- ====================================================================
WITH
toDateTime('2021-07-01 00:00:00', 'UTC') AS t0,
toDateTime('2021-08-01 00:00:00', 'UTC') AS t1,
cellhour AS (
    SELECT h3, hour,
           uniqExactMerge(vessels)      AS v,
           uniqExactMergeState(vessels) AS st
    FROM h3_hourly
    WHERE hour >= t0 AND hour < t1 AND ship_group = 'leisure'
    GROUP BY h3, hour
),
ours AS (
    SELECT 7 AS res, h3 AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
    UNION ALL
    SELECT 5 AS res, h3ToParent(h3, 5) AS cell, sum(v) AS vh, uniqExactMerge(st) AS vessels
    FROM cellhour GROUP BY cell
),
px AS (
    SELECT lon, lat, hs, hp
    FROM file('data/context/emodnet_2021-07_leisure.tsv', TSV,
              'lon Float64, lat Float64, hs Float64, hp Float64')
),
emo AS (
    SELECT 7 AS res, geoToH3(lat, lon, 7) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
    UNION ALL
    SELECT 5 AS res, geoToH3(lat, lon, 5) AS cell, sum(hs) AS h_sail, sum(hp) AS h_plea
    FROM px GROUP BY cell
),
pairs AS (
    SELECT greatest(o.res, e.res)   AS res,
           greatest(o.cell, e.cell) AS cell,
           o.vh                     AS our_vh,
           o.vessels                AS our_vessels,
           e.h_sail                 AS emo_sail,
           e.h_plea                 AS emo_plea,
           e.h_sail + e.h_plea      AS emo_hours
    FROM ours AS o FULL OUTER JOIN emo AS e ON o.res = e.res AND o.cell = e.cell
),
ranked AS (
    SELECT res, cell, our_vh, our_vessels, emo_sail, emo_plea, emo_hours,
           rank() OVER (PARTITION BY res ORDER BY our_vh    DESC) AS rank_ours,
           rank() OVER (PARTITION BY res ORDER BY emo_hours DESC) AS rank_emodnet
    FROM pairs
)
SELECT
    multiIf(h3ToGeo(cell).2 <  7,    'west of lon 7',
            h3ToGeo(cell).2 >= 13.5, 'east of lon 13.5',
            h3ToGeo(cell).1 <  54.5, 'south of 54.5 N',
                                     'Danish core')          AS zone,
    round(sum(emo_hours), 1)                                 AS emodnet_hours,
    round(sumIf(emo_hours, our_vh = 0), 1)                   AS emodnet_hours_in_our_zero,
    round(sumIf(emo_hours, our_vh = 0) / sum(emo_hours), 4)  AS share_missed,
    count()                                                  AS n_cells
FROM ranked
WHERE res = 7
GROUP BY zone
ORDER BY share_missed DESC
SETTINGS input_format_tsv_skip_first_lines = 17, join_use_nulls = 0;
