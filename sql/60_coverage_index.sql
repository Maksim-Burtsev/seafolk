-- S10 — the honesty layer, part 1: HOW MUCH OF THE CHANGE IS THE INSTRUMENT.
-- Run: scripts/ch.sh sql/60_coverage_index.sql
--      (read-only; nine SELECTs, 284 399 + 2 122 + 2 + 2 572 + 2 277 + 42 + 16
--       + 70 + 8 rows. Timing in "RUN TIME" at the foot of this header.)
-- Reads `h3_hourly`, `vessel_day` and `load_log`. Writes nothing.
--
-- CLASS A IS THE INSTRUMENT, NOT THE SUBJECT — the premise of the former
-- sql/13_coverage_daily.sql (S4's coverage query, removed in S10; block 2
-- below is the corrected version), taken to the grain where a receiver is
-- actually visible. A commercial fleet does not double between two Januaries
-- and does not follow the leisure season (S3: leisure moves 32x between
-- January and July, Class A barely moves), so a STEP in Class A numbers is a
-- step in RECEPTION. Chapter
-- 01's headline is a 3.7x rise in leisure transponders over eleven years; this
-- file is what lets the essay say how much of that is boats and how much is
-- the network that hears them.
--
-- WHAT IS NOT RECOVERABLE, AND NOTHING BELOW PRETENDS OTHERWISE:
--   * A RECEIVER'S IDENTITY IS NOT IN THE DATA AT ALL. The archive is a merged
--     national feed; no row says which base station heard it. A step in a
--     region is EVIDENCE that the network changed there, never a receiver
--     list, and this file names no station and locates none.
--   * DISTINCT MOVING VESSELS PER HOUR is not recoverable from `h3_hourly`:
--     `vessels` is a uniqExact state over everything present in the cell-hour,
--     moving or not, and no state of the moving subset was ever stored (the
--     constraint sql/11, sql/12, sql/24, sql/30 and sql/50 all carry). So
--     movement here is always a MESSAGE quantity and head counts are always
--     exact head counts, and the two are never divided into each other.
--   * A VESSEL HEARD BY NOBODY is not in any table, so nothing here can
--     measure the network's REACH — only how well it heard what it did hear.
--   * WHY A STEP HAPPENED is not in the store either. This file measures
--     steps; it does not explain them.
--
-- WHAT IS EXACT. `vessels` is a uniqExact state, so uniqExactMerge over any
-- set of cells and hours is the EXACT distinct-vessel count of that set — a
-- res-4 region-day in block 1, a whole hour of the bbox in block 5b. Merging
-- states is not an approximation and there is no sampling anywhere below.
-- EVERY MEDIAN IN THIS FILE IS `medianExact`, NOT `median`. ClickHouse's
-- `median` is `quantile`, which is approximate and whose answer depends on how
-- the rows were grouped: the first run of this file used it and block 3's
-- Class A factor came out 2.084 where the exact value is 2.199, and the
-- region filter kept 138 regions where the exact rule keeps 139. Thresholds
-- and published factors have to be reproducible, so every one is exact. The
-- inputs are small (a region-month has ~30 values, block 3 pools 172 k) and
-- the cost is not measurable.
--
-- PRIVACY. Class B appears in ONE grain only: STORE-WIDE (the whole bbox) per
-- day (block 2), per period (block 3) and per year/season (block 5). There is
-- no per-region and no per-cell Class B number in this file, by construction —
-- block 1 and block 4, the only spatial blocks, filter `mobile = 'Class A'` in
-- their innermost scan. No MMSI, name, callsign or position of any vessel is
-- emitted; `vessel_day` (which holds MMSI, sql/01_schema.sql) is read only
-- through uniqExact()/count()/medianExact() aggregates. The h3 ids that block
-- 1 and block 4 emit are 18-digit res-4 cell indexes covering ~1 800 km2 each,
-- not identifiers of anything that floats.
-- A GREP FOR NINE-DIGIT INTEGERS OVER THIS FILE'S OUTPUT IS NOT ZERO, AND
-- THAT IS EXPECTED: `rows_read` (up to 3.0e8 for a monthly file), `msgs`,
-- `moving_msgs`, `class_a_msgs`, `class_b_msgs`, `night_msgs` and
-- `vessel_hours` are counts that pass nine digits. None of them can be an
-- MMSI: no expression anywhere in this file selects `mmsi`, and every column
-- is either a date, an h3 index, a coordinate, a ratio or an aggregate over a
-- whole fleet. The mechanical check that IS zero here is
--   grep -cE '(^|[^0-9])[0-9]{9}([^0-9]|$)' on sql/60_coverage_index.sql itself
-- and a reading of the seven SELECT lists, which is what a reviewer should do.
--
-- ===================================================================
-- THE FOUR THINGS THIS FILE MEASURED, stated up front because every threshold
-- below was chosen from them and a reader should not have to re-derive them:
--
-- 1. THE Sep-2015 DUPLICATION IS REAL, STORE-WIDE, AND 2.2-2.6x ON CLASS A
--    (block 3). Class A msgs per vessel-day, median over DAYS of the daily
--    mean: 3 644 in the 30 days before, 9 950 inside 2015-08-28..2015-09-30,
--    4 153 in the 30 days after — 2.552x the pooled neighbours. On the median
--    over vessel-day ROWS it is 2.199x (1 948 / 4 684 / 2 312).
--    IT IS A CLEAN STEP, NOT A RAMP: daily Class A msgs per vessel is 4 347 on
--    2015-08-27 and 9 111 on 2015-08-28; 8 303 on 2015-09-30 and 2 618 on
--    2015-10-02. 2015-10-01 (5 143) is a partial tail day.
--    CLASS B IS INFLATED LESS: 1 096 against 570 / 658, i.e. 1.784x on the
--    daily-mean statistic and 1.468x on the vessel-day one — and THAT
--    COMPARISON IS CONFOUNDED BY SEASON, because a Class B vessel still heard
--    in October is a different, more active boat than the August fleet. Read
--    the Class A figure as the duplication's size. `vessels` and `dist_nm` are
--    structurally immune (docs/STATUS.md § S4-tails).
--    S10 MASKS IT WITH A FLAG, NOT BY REWRITING ANYTHING: `dup_window` in
--    blocks 1-2, `dup_month` in block 4, and sql/24's exclusion in block 5.
--
-- 2. THERE IS A SECOND CONTAMINATION, LARGER THAN Sep-2015 AND PERMANENT,
--    AND IT WAS NOT IN THE PLAN: THE CLASS A MESSAGE TAILS DOUBLE SOMEWHERE
--    BETWEEN 2022-03 AND 2023-11 AND STAY DOUBLED, WHILE THE MEDIAN DOES NOT
--    MOVE. It is a TAIL step, not a LEVEL step, and the tail goes where no
--    transponder can follow — so it is DUPLICATION, not better reception.
--    Block 6, `msgs` per Class A vessel-day, by loaded month:
--      p50   1 374 - 4 850 over all 69 months, seasonal, NO TREND. July reads
--            2 394 / 1 374 / 1 869 (2015 / 2018 / 2021) against 2 160 / 2 384
--            / 2 223 (2024 / 2025 / 2026); December 2 918 / 3 828 / 3 216
--            against 4 191 / 2 665 / 2 657. The typical Class A vessel-day is
--            the same size in 2026 as in 2015.
--      p90   8 749 - 9 428 in 37 of the 38 months of 2015, 2018, 2021 and
--            2022-01/02 (the exception is 2015-09 at 27 163, the duplication)
--            -> 11 877 in 2023-02 -> 16 261 - 19 607 in EVERY month from
--            2023-12 on. It doubles.
--      p99   14 156 - 16 980 -> 20 314 (2023-02) -> 31 633 - 44 041.
--      max   35 469 - 53 760 in 27 of those 36 clean months and 79 839 -
--            106 122 in the other nine -> 77 874 - 359 899 from 2023-12 on.
--    THE CEILING SETTLES WHAT KIND OF CHANGE IT IS. A Class A transponder
--    sends at most one position report every 2 s (ITU-R M.1371, autonomous
--    mode) = 43 200 a day, plus a few hundred static and voyage messages. A
--    vessel-day above 43 200 messages DID NOT HAPPEN: the archive holds the
--    same message more than once. Block 6's `share_over_cap` counts those
--    impossibilities and needs no baseline to be read against:
--      clean months before 2023   0 - 0.0612 % of Class A vessel-days
--      2023-12 onward             0.1796 - 1.0921 %, every month
--      2015-08 / 2015-09          0.3538 % / 2.1832 %  (point 1's window,
--                                 found by the ceiling with no date in the
--                                 query — which is what validates the test)
--    So sporadic duplication predates 2023 (2015-07 0.0383 %, 2018-01
--    0.0532 %) and 2023 makes it the archive's normal state. THE CAP IS A
--    LOOSE BOUND — no real ship holds the 2 s rate for 24 h — so
--    `share_over_cap` is a FLOOR on the duplication rate, never an estimate.
--    THE DATE, as tightly as this store can give it. 2022-02 is clean (p90
--    9 076, nothing over the cap); 2023-02 is HALFWAY (p90 11 877, +31 %, 13
--    over the cap); 2023-12 is fully stepped (p90 16 970, 147 over the cap);
--    2024-03 onward never comes back down. The step therefore BEGINS in
--    2022-03 .. 2023-02 and COMPLETES in 2023-03 .. 2023-11, and nothing
--    finer is available without loading those years. It is NOT the archive's
--    monthly -> daily file switch (that is 2024-03; the monthly 2023-12 zip is
--    already stepped).
--    CLASS B STEPS TOO, BY LESS. Block 6b: p90 msgs per Class B vessel-day
--    979 / 1 069 / 1 306 (2021 / 2018 / 2015) -> 1 500 - 1 527 (2024 / 2025 /
--    2026); by month 931 (2022-02) -> 1 445 (2023-02) -> 1 574 (2023-12), the
--    same bracket. sql/61 block 4 measures the same thing on a third
--    statistic (+36 % on messages per Class B vessel-HOUR).
--    WHAT THE MEANS IN THIS FILE ARE ACTUALLY SAYING, because a reader meets
--    them in block 2 and block 5b before reaching block 6:
--    `class_a_msgs_per_vessel_day` (block 2) is a MEAN, and a mean over a
--    doubling tail rises ~1.5x while the median stands still — 3 644 - 4 700
--    across 2015-2022 against 6.0 - 7.3 k from 2023-12 (median over DAYS of
--    that day's mean). Block 5b's Class A cargo messages per vessel-HOUR
--    (246 / 244 / 237 / 239 -> 346 -> 442 / 437 / 427) is the same mean over
--    the same duplicated tail. NEITHER IS A FLEET REPORTING MORE OFTEN.
--    CONSEQUENCE, and it is the whole reason this file exists: ANY MESSAGE
--    COUNT COMPARED ACROSS 2023 COMPARES TWO INSTRUMENTS, exactly as across
--    2015-09. HEAD COUNTS ARE IMMUNE: `vessels` is a uniqExact state and a
--    message stored twice is still one vessel. `dist_nm` IS IMMUNE FOR A
--    REASON WORTH STATING: sql/03_aggregate.sql counts a step only when
--    `ts - pts BETWEEN 1 AND 3600`, so a duplicate carrying the SAME second
--    contributes no distance, and one carrying a later second contributes the
--    metres the vessel actually moved. Point 3 measures that immunity instead
--    of arguing it.
-- 3. HEAD COUNTS DO NOT STEP WHERE MESSAGE COUNTS DO. Over the 9 568
--    region-month pairs that have a predecessor (block 4), the region's median
--    daily Class A vessel count moves by more than a third in 1 349 and its
--    message rate in 2 216. Broken down by `region_size` (the region's median
--    daily Class A vessels over the WHOLE store, a block 4 column), the
--    vessel-count flag rate is:
--      region_size <20      27 regions  1 840 pairs  33.9 % flagged
--      region_size 20-40    46 regions  3 174 pairs  18.0 %
--      region_size 40-80    34 regions  2 346 pairs   6.5 %
--      region_size 80-160   29 regions  2 001 pairs   0.05 %  (ONE pair)
--      region_size 160+      3 regions    207 pairs   0 %
--    So below ~80 vessels a day a "step" is counting noise, and above it there
--    is EXACTLY ONE in the whole store: 58.00 N 10.76 E — the Skagerrak, the
--    Skagen/Norway approach — at 2018-12 -> 2021-01, v_ratio 1.507. It is a
--    real level change and not a one-month blip; that region's monthly median
--    runs 63-95 across 2015 and 2018 and 107-130 from 2021-01 to 2026-08.
--    EVERY OTHER large-region flag in the store is a MESSAGE-rate flag, and
--    they cluster exactly where points 1 and 2 say they should — flagged
--    regions of size >= 80 per month: 2015-09 30, 2015-10 31 (the
--    duplication), 2023-12 14, 2023-02 5 (the 2023 step, seen from both
--    sides), 2021-01 5, 2024-09 6, 2024-10 8, and ones and twos elsewhere.
--    READ THAT AS THE ANSWER TO "did receivers appear?": on the evidence in
--    this store the Danish network's REACH (who is heard) shows no STEP — one,
--    in the Skagerrak — while the MESSAGE COUNT per vessel does, and points 1
--    and 2 have already shown that what moves there is DUPLICATION, not a
--    fleet reporting more often. "No step" is not "no change": see the drift
--    paragraph that closes this point.
--    SEASONALITY IS NOT WHAT MAKES THE SMALL REGIONS NOISY: normalising each
--    region's monthly median by the store-wide Class A median of that month
--    moves the vessel flag count from 1 349 to 1 292. The noise is
--    region-level, so no de-seasonalising is done and none would help.
--    THE STEP TABLE DOES NOT SEE A SLOW DRIFT, AND THERE ARE DRIFTS. A ratio
--    between one month and the previous one cannot flag a change that takes
--    eleven years, and over the twelve regions notes/plot_honesty.py charts
--    the 2015 -> 2026 yearly medians of the daily Class A head count run from
--    x0.82 to x1.16 once the flagged Skagerrak region (x1.57, the step above)
--    is set aside: west of Bornholm 148 -> 121, Bornholmsgat 146 -> 120 and
--    north of Rugen 137 -> 121, about -18 %, against the Fehmarn Belt
--    134 -> 156 and the Goteborg approach 205 -> 236, about +16 %. That is
--    TRAFFIC AND RECEPTION TOGETHER and this store cannot separate them; what
--    it can say is that no unflagged drift among the twelve leaves +-20 %.
--    notes/plot_honesty.py's numbers() prints all twelve.
--
-- 4. THE WINTER LEISURE NIGHT-SHARE STEP SURVIVES BOTH CONTROLS (block 5).
--    S6 finding 10 saw the Oct-Apr leisure night share go 0.041-0.055
--    (2015/2018) -> 0.070-0.082 (2021+). Measured here with two Class A
--    controls on the same local days, the same clock and the same exclusions:
--      Oct-Apr         2015    2018    2021    2024    2025    2026
--      leisure Class B 0.0547  0.0413  0.0769  0.0815  0.0784  0.0703
--      ferry   Class A 0.2041  0.1962  0.1818  0.1949  0.2002  0.1939
--      cargo   Class A 0.3006  0.3005  0.3008  0.3072  0.3107  0.3123
--    Cargo runs all night by nature and is the harder control: if the network
--    had started hearing the night better, cargo's night share would move. It
--    moves 0.3006 -> 0.3123, +3.9 % relative over eleven years, while leisure
--    moves +43 % against 2015 and +90 % against 2018. Block 5b puts a number
--    on the residual — Class A cargo messages per vessel-hour, night / day:
--    1.024 (2015), 1.017 (2018), 1.021 (2021), 1.031 (2022), 1.039 (2023),
--    1.083 (2024), 1.093 (2025), 1.108 (2026).
--    THAT ~8 % IS NOT NECESSARILY THE NETWORK, and block 5b carries its own
--    control: `vessel_hours` is a HEAD COUNT and immune to duplication, and
--    cargo's night/day vessel-hours are 0.4193 / 0.4218 / 0.4201 / 0.4092 /
--    0.4103 / 0.4231 / 0.4203 / 0.4216 for 2015 / 2018 / 2021 / 2022 / 2023 /
--    2024 / 2025 / 2026 — FLAT, and flat against 7/17 = 0.4118, the clock's
--    own share. The network hears the same fraction of the cargo fleet at
--    night in 2026 as in 2015. Only the MESSAGE rate moved, and it moved
--    exactly across the 2023 step of point 2. So the honest reading of the
--    residual is: no measurable change in night REACH, and a night/day
--    message ratio that is partly or wholly the post-2023 duplication being
--    slightly night-heavy. Either way it is 8 % against leisure's 43-90 %.
--    DO NOT READ THIS FILE AS A VERDICT: it emits the two controls next to the
--    subject and stops there.
-- ===================================================================
--
-- THE REGION GRAIN. `h3ToParent(h3, 4)` — res-4 cells, ~1 770 km2, ~22 km
-- edge, 458 of them in the bbox. Res 7 (the store's grain, ~5 km2) is far too
-- fine: a single vessel's route decides whether a cell has data at all. Res 4
-- is coarse enough that a region is a piece of sea with its own traffic and
-- fine enough that a change of network in the Kattegat does not average away
-- against the Great Belt. `h3ToGeo` returns (LAT, LON) under scripts/ch.sh's
-- `--h3togeo_lon_lat_result_order=0` pin — .1 IS LAT, .2 IS LON, verified for
-- this file on the Copenhagen oracle cell that scripts/test_context.sh uses:
--   h3ToGeo(608531686258376703) = (55.681968, 12.571018)  -- lat, lon
--   h3ToParent(that, 4) = 595020895127339007, centre (55.669425, 12.628192)
-- Getting it backwards does not error, it mirrors Denmark into the Arabian
-- Sea (docs/DECISIONS.md, 2026-09-03).
--
-- NO LAND/SEA LABEL. sql/51 labels res-7 cells with `dictHas('land', ...)` on
-- the cell centre. At res 4 that lookup is meaningless — a 1 770 km2 cell
-- spans coast, harbour and open water, and its centre answers for none of
-- them. The `land` dictionary is deliberately not joined here.
--
-- LOAD_LOG IS KEYED BY DAY RANGE, NOT BY toDate(ts_min). The former
-- sql/13_coverage_daily.sql — S4's coverage query, carried as an open question
-- since S4-tails and REMOVED IN S10 — keyed its LEFT JOIN on `toDate(ts_min)`,
-- which is right for a daily file and wrong for a monthly one: it attached a
-- whole month's drop counts to the 1st and left the other 27-30 days NULL. It
-- had no consumer left once this block existed, so it is deleted rather than
-- fixed twice; block 2 does the join correctly, by expanding each load_log row
-- into the days it covers:
--     toDate(ts_min) + arrayJoin(range(dateDiff('day', ts_min, ts_max) + 1))
-- MEASURED: 949 load_log rows expand to exactly 2 122 day rows, all distinct
-- (max 1 file per day), and every one of the 2 122 days in `vessel_day` has a
-- row — the ranges tile the loaded calendar with no gap and no overlap. The
-- `grain` column ('day' | 'month') says which kind of file a day's shares came
-- from: FOR A MONTHLY FILE THE SHARES ARE FILE-LEVEL, i.e. the same number is
-- repeated on all ~30 days and is that month's average, NOT that day's. 40
-- monthly files (2015, 2018, 2021 whole years; 2022-01, 2022-02, 2023-02,
-- 2023-12) and 909 daily files (2024-03-01 onward). Ranges of the shares:
--   grain=month  out_of_bbox 0.004-2.154 %  non_vessel 4.03-7.81 %  sentinel 0.281-0.728 %
--   grain=day    out_of_bbox 0    -6.278 %  non_vessel 5.52-11.34 % sentinel 0.044-0.982 %
-- The invariant rows_read = non_vessel + sentinel + out_of_bbox + kept holds
-- on all 949 rows (0 violations), and sum(rows_read) = 31 881 515 268 (31.9 G)
-- against sum(vessel_day.msgs) = sum(load_log.rows_kept) = 29 669 027 495 —
-- the two aggregate tables agree to the message.
--
-- WHY THE BLOCKS REPEAT THEIR CTEs. `clickhouse local` runs each statement on
-- its own; there is no cross-statement CTE and no templating (sql/50-52 hit
-- the same wall). Block 1, block 4 and block 4b therefore carry the same `d`
-- and `keep` CTEs — the ONE difference is that block 4's and 4b's `d` omits
-- `moving_msgs`, which neither uses; the grouping, the filter and the
-- `keep` rule are identical in all three. Block 5's `base`/`covered` CTEs are
-- COPIED FROM sql/24_night.sql with one change, stated at block 5. Diff them
-- before believing a change to any of them.
--
-- RUN TIME, /usr/bin/time -p on an APFS clone of the store (data/ch_a),
-- whole file in one run, output to /dev/null:
--   real 27.79  user 258.29  sys 11.07     (budget: 60 s)
-- Block 1 and the two step blocks are the cost: each is a full scan of the
-- Class A half of h3_hourly's 303 M rows, merging uniqExact states into
-- 284 399 region-days, and there is no way to share that scan between
-- statements.


-- ====================================================================
-- BLOCK 1 — the instrument, per region per day. One row per (day, region),
-- Class A only, 284 399 rows, 9 columns:
--   day             UTC calendar day
--   region          h3ToParent(h3, 4), an 18-digit res-4 cell index
--   lat, lon        the region CENTRE (h3ToGeo; .1 = lat, .2 = lon)
--   vessels         uniqExactMerge over every res-7 cell-hour of the region
--                   that day. EXACT distinct Class A vessels in the region.
--   msgs, moving_msgs   sums over the same rows
--   msgs_per_vessel msgs / vessels — a MEAN, so it carries both the reporting
--                   rate and the duplication of header points 1 and 2 and
--                   cannot separate them. Compare a
--                   region to ITSELF over time; the level differs between
--                   regions for reasons that have nothing to do with the
--                   network (a region of anchored ships reports slower than a
--                   region of ships at 14 kn).
--   dup_window      1 on 2015-08-28..2015-09-30. `msgs`, `moving_msgs` and
--                   `msgs_per_vessel` are ~2.2-2.6x inflated on those rows and
--                   `vessels` is not. Filter or mark; do not average across it.
--
-- WHICH REGIONS SURVIVE, AND WHY THAT RULE. 458 res-4 regions have data.
-- Kept: a region whose MEDIAN DAILY CLASS A VESSEL COUNT reaches 20 IN AT
-- LEAST ONE LOADED YEAR — 139 regions, 30 % of them, and the whole point of
-- the floor is that a region with three ships a day cannot show a step in
-- anything. The other thresholds were measured before this one was picked:
-- >= 10 keeps 230 regions, >= 50 keeps 64. "In at least one year" and not
-- "in every year" on purpose: a region that CROSSES the floor is exactly the
-- kind of change this file is looking for and must not be excluded by the
-- filter that looks for it.
-- The rule needs no day-coverage clause: over the 894 (region, year) pairs
-- that pass it, the region is present on 96-100 % of that year's loaded days
-- (5th percentile 0.962, median 1.000), so a region cannot pass on a handful
-- of freak days.
-- WHAT THE RULE DOES LET IN: 27 of the 139 have a WHOLE-STORE median below
-- 20 — bbox-fringe regions (lat 53.1-58.2, lon 4.2-17.0, the Dutch North Sea
-- and Baltic corners) that are heard well in some years and barely in others,
-- present on 1 824 of 2 122 days on average. They are kept on purpose (a
-- region that crosses the floor is the finding) and they are the noisiest
-- rows in block 4; `region_size` is how a consumer drops them.
-- HONEST LIMIT OF THE FLOOR: at 20-40 vessels a day the month-to-month vessel
-- median still swings past a third 23 % of the time (header point 3). Block 4
-- emits `region_size` so a consumer can raise the floor; block 1 keeps all 139
-- because a series is cheap to filter and impossible to un-filter.
-- ====================================================================
WITH
d AS (
    SELECT toDate(hour)        AS day,
           h3ToParent(h3, 4)   AS region,
           uniqExactMerge(vessels) AS vessels,
           sum(msgs)           AS msgs,
           sum(moving_msgs)    AS moving_msgs
    FROM h3_hourly
    WHERE mobile = 'Class A'
    GROUP BY day, region
),
keep AS (
    SELECT region
    FROM (SELECT region, toYear(day) AS y, medianExact(vessels) AS mv FROM d GROUP BY region, y)
    WHERE mv >= 20
    GROUP BY region
)
SELECT day,
       region,
       round(h3ToGeo(region).1, 4)              AS lat,   -- .1 = LAT (pinned)
       round(h3ToGeo(region).2, 4)              AS lon,   -- .2 = LON
       vessels,
       msgs,
       moving_msgs,
       round(msgs / vessels, 1)                 AS msgs_per_vessel,
       day BETWEEN '2015-08-28' AND '2015-09-30' AS dup_window
FROM d
WHERE region IN (SELECT region FROM keep)
ORDER BY region, day;


-- ====================================================================
-- BLOCK 2 — the store-wide daily reference. One row per loaded day, 2 122
-- rows, 14 columns. This is the former sql/13_coverage_daily.sql's job (that
-- file is removed in S10) done with the load_log join fixed and the honesty
-- columns it was missing.
--   day
--   class_a_vessels, class_b_vessels   uniqExact(mmsi) over `vessel_day`,
--        WHOLE BBOX. Source stated because there are two: the merged
--        uniqExact state in `h3_hourly` gives the same number, and
--        `vessel_day` is 8.8 M rows against 303 M. The CLASS B COUNT IS
--        STORE-WIDE AND ONLY STORE-WIDE — the privacy rule, see the header.
--   class_a_msgs, class_b_msgs         sum(msgs) over the same rows.
--        MEASURED: sum(vessel_day.msgs) = sum(h3_hourly.msgs) exactly, day by
--        day (checked on 2021-07-15: 13 125 382 both sides, difference 0), and
--        both equal sum(load_log.rows_kept) over the store.
--   class_b_per_class_a  class_b_vessels / class_a_vessels. The adoption
--        curve DIVIDED BY THE INSTRUMENT: if the whole rise were the receiver
--        network, this ratio would be flat, because a new receiver hears both
--        fleets. It is not flat — see sql/61 block 1.
--   class_a_msgs_per_vessel_day, class_b_msgs_per_vessel_day
--        class_?_msgs / class_?_vessels. THE DUPLICATION AND THE 2023 STEP ARE
--        BOTH VISIBLE HERE AS A NUMBER; that is what these two columns are for.
--   rows_read, pct_out_of_bbox, pct_non_vessel, pct_sentinel, grain
--        from `load_log`, joined by DAY RANGE (see header). On grain='month'
--        the four are the whole file's figures repeated on every day it covers.
--   dup_window  1 on 2015-08-28..2015-09-30.
-- ====================================================================
WITH
ll AS (
    -- one row per DAY a file covers, not one per file: a monthly zip covers
    -- ~30 days and the toDate(ts_min) keying of the former sql/13 filed them
    -- all under the 1st.
    SELECT toDate(ts_min)
             + arrayJoin(range(toUInt32(dateDiff('day', toDate(ts_min), toDate(ts_max))) + 1)) AS day,
           rows_read, rows_out_of_bbox, rows_non_vessel, rows_sentinel,
           if(dateDiff('day', toDate(ts_min), toDate(ts_max)) > 3, 'month', 'day') AS grain
    FROM load_log
),
v AS (
    SELECT day,
           uniqExactIf(mmsi, mobile = 'Class A') AS class_a_vessels,
           uniqExactIf(mmsi, mobile = 'Class B') AS class_b_vessels,
           sumIf(msgs,       mobile = 'Class A') AS class_a_msgs,
           sumIf(msgs,       mobile = 'Class B') AS class_b_msgs
    FROM vessel_day
    GROUP BY day
)
SELECT v.day                                          AS day,
       v.class_a_vessels                              AS class_a_vessels,
       v.class_b_vessels                              AS class_b_vessels,
       v.class_a_msgs                                 AS class_a_msgs,
       v.class_b_msgs                                 AS class_b_msgs,
       round(v.class_b_vessels / v.class_a_vessels, 4) AS class_b_per_class_a,
       round(v.class_a_msgs / v.class_a_vessels, 1)   AS class_a_msgs_per_vessel_day,
       round(v.class_b_msgs / v.class_b_vessels, 1)   AS class_b_msgs_per_vessel_day,
       l.rows_read                                    AS rows_read,
       round(100 * l.rows_out_of_bbox / l.rows_read, 3) AS pct_out_of_bbox,
       round(100 * l.rows_non_vessel  / l.rows_read, 3) AS pct_non_vessel,
       round(100 * l.rows_sentinel    / l.rows_read, 3) AS pct_sentinel,
       l.grain                                        AS grain,
       v.day BETWEEN '2015-08-28' AND '2015-09-30'    AS dup_window
FROM v INNER JOIN ll AS l USING (day)
ORDER BY day
-- INNER, not LEFT: every loaded day has exactly one load_log row (measured,
-- see header). An INNER join that silently drops a day would change the row
-- count from 2 122, which is the number this file's consumer asserts.
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 3 — the measured Sep-2015 inflation factor. ONE ROW PER CLASS —
-- 2 rows, 11 columns. The three periods are columns, not rows, so a reader
-- sees window / before / after and the factor on one line:
--   mobile                    'Class A' | 'Class B'
--   window_median_per_vd      median over the WINDOW's vessel-day rows of msgs
--   before_median_per_vd      the same over 2015-07-29..2015-08-27 (30 days)
--   after_median_per_vd       the same over 2015-10-01..2015-10-30 (30 days)
--   factor_vs_neighbours      window / mean(before, after) on that statistic
--   window_median_daily_mean, before_..., after_..., factor_daily_mean
--                             the same four on a SECOND statistic: the median
--                             over DAYS of that day's mean msgs per vessel-day.
-- TWO STATISTICS ON PURPOSE. A median over vessel-day rows is dominated by the
-- many small vessels; a median over days of the daily mean is dominated by the
-- big ones. The duplication should — and does — move both. Where they
-- disagree, the truth is "between 2.2 and 2.6 for Class A".
--
-- WHY THESE WINDOWS. 30 days each side, adjacent, no gap: long enough that one
-- storm does not set the number, short enough to stay in the same season. The
-- inflated window is 2015-08-28..2015-09-30 inclusive, 34 days, the range
-- docs/STATUS.md § S4-tails established and sql/24 already excludes.
-- 2015-10-01 IS IN THE 'after' PERIOD AND IS A PARTIAL TAIL DAY (daily Class A
-- msgs/vessel 5 143 against ~2 600-4 100 for the rest of that week and ~9-11 k
-- inside the window). It is deliberately NOT moved into the window: the window
-- is the published one, and leaving the tail in `after` makes the factor
-- CONSERVATIVE — it can only understate the step.
-- CLASS B'S FACTOR IS CONFOUNDED BY SEASON and the header says so; read the
-- Class A figure as the duplication's size.
-- ====================================================================
WITH
per_vd AS (
    SELECT multiIf(day BETWEEN '2015-08-28' AND '2015-09-30', 'window',
                   day <  '2015-08-28',                       'before',
                                                              'after') AS period,
           mobile, msgs
    FROM vessel_day
    WHERE day BETWEEN '2015-07-29' AND '2015-10-30'
),
per_day AS (
    SELECT multiIf(day BETWEEN '2015-08-28' AND '2015-09-30', 'window',
                   day <  '2015-08-28',                       'before',
                                                              'after') AS period,
           mobile, day, sum(msgs) / count() AS daily_mean
    FROM vessel_day
    WHERE day BETWEEN '2015-07-29' AND '2015-10-30'
    GROUP BY period, mobile, day
),
a AS (
    SELECT mobile,
           countIf(period = 'window')                 AS window_vessel_days,
           round(medianExactIf(msgs, period = 'window'), 1) AS window_median_per_vd,
           round(medianExactIf(msgs, period = 'before'), 1) AS before_median_per_vd,
           round(medianExactIf(msgs, period = 'after'),  1) AS after_median_per_vd
    FROM per_vd GROUP BY mobile
),
b AS (
    SELECT mobile,
           countIf(period = 'window')                       AS window_days,
           round(medianExactIf(daily_mean, period = 'window'), 1) AS window_median_daily_mean,
           round(medianExactIf(daily_mean, period = 'before'), 1) AS before_median_daily_mean,
           round(medianExactIf(daily_mean, period = 'after'),  1) AS after_median_daily_mean
    FROM per_day GROUP BY mobile
)
SELECT a.mobile                    AS mobile,
       b.window_days               AS window_days,
       a.window_vessel_days        AS window_vessel_days,
       a.window_median_per_vd      AS window_median_per_vd,
       a.before_median_per_vd      AS before_median_per_vd,
       a.after_median_per_vd       AS after_median_per_vd,
       round(a.window_median_per_vd / ((a.before_median_per_vd + a.after_median_per_vd) / 2), 3)
                                   AS factor_per_vd,
       b.window_median_daily_mean  AS window_median_daily_mean,
       b.before_median_daily_mean  AS before_median_daily_mean,
       b.after_median_daily_mean   AS after_median_daily_mean,
       round(b.window_median_daily_mean / ((b.before_median_daily_mean + b.after_median_daily_mean) / 2), 3)
                                   AS factor_daily_mean
FROM a INNER JOIN b USING (mobile)
ORDER BY mobile;


-- ====================================================================
-- BLOCK 4 — the step table: every region-month whose Class A level moved.
-- 2 572 rows, 17 columns. One row per (region, month) that is FLAGGED, where
-- flagged means either ratio outside [0.75, 1.3333] — a third either way,
-- symmetric in log (1/0.75 = 1.333).
--   region, lat, lon, region_size   region_size = the region's MEDIAN DAILY
--        Class A vessel count over the whole store. READ IT FIRST: below ~80
--        a vessel-count flag is noise (header point 3), and the emitted rows
--        are dominated by small regions because there are more of them.
--   mon, prev_mon, gap_months   THE PREVIOUS ROW IN THE REGION'S OWN MONTH
--        ORDER, not the previous calendar month. Loaded months are not
--        contiguous — 2015, 2018, 2021 whole; 2022-01/02; 2023-02; 2023-12;
--        2024-03 on — so `gap_months` is 1, 3, 10, 12, 25, ... and a
--        gap_months = 25 row is a 2015-12 -> 2018-01 comparison. IT IS EMITTED
--        AS SUCH so the reader sees it for what it is: two years of unloaded
--        archive between the two numbers, and nothing in this store can say
--        when in between the change happened.
--   med_vessels, prev_med_vessels, v_ratio        median over the month's days
--   med_msgs_per_vessel, prev_med_msgs_per_vessel, mpv_ratio   median over the
--        month's days of that day's msgs/vessels
--   flag_vessels, flag_msgs   WHICH of the two ratios put the row here, 0/1,
--        computed from THE SAME UNROUNDED EXPRESSIONS the WHERE below uses.
--        They exist so a consumer never has to re-derive the band from the
--        rounded `v_ratio` / `mpv_ratio`: 22 of these rows sit on the rounded
--        boundary and a Python `< 0.75 or > 1.3333` over the rounded column
--        answers differently for them. At least one of the two is 1 on every
--        emitted row, by construction.
--   dup_month  1 if the month overlaps 2015-08-28..2015-09-30, which is
--        2015-08 AND 2015-09 AND NOTHING ELSE — the rule cannot reach 2015-10
--        (measured: 0 rows), because the window ends on 09-30. 2015-10-01, the
--        partial tail day block 3 describes, is therefore NOT flagged here and
--        2015-10's rows carry dup_month = 0 while still holding one tail day.
--        Flagged rows ARE emitted — they are the loudest rows in the table and
--        they are the duplication, which is the point.
-- MEDIANS, not means: one receiver outage day should not create a step.
-- BASE RATE, so a flag is not mistaken for a finding — 9 568 region-month
-- pairs have a predecessor, 1 349 flag on vessels and 2 216 on messages, i.e.
-- 27 % of all pairs flag on something. See header point 3 for the
-- breakdown by region size, which is what makes the table readable.
-- SORTED BY SIZE OF THE STEP: greatest of the two log-magnitudes, descending,
-- so the biggest move in either metric is the first row.
-- ====================================================================
WITH
d AS (
    -- block 1's `d` without `moving_msgs`, which this block does not use.
    -- There is no cross-statement CTE in clickhouse local; diff the two
    -- before believing a change to either.
    SELECT toDate(hour)        AS day,
           h3ToParent(h3, 4)   AS region,
           uniqExactMerge(vessels) AS vessels,
           sum(msgs)           AS msgs
    FROM h3_hourly
    WHERE mobile = 'Class A'
    GROUP BY day, region
),
keep AS (
    SELECT region
    FROM (SELECT region, toYear(day) AS y, medianExact(vessels) AS mv FROM d GROUP BY region, y)
    WHERE mv >= 20
    GROUP BY region
),
dd AS (
    SELECT * FROM d WHERE region IN (SELECT region FROM keep)
),
sz AS (
    SELECT region, medianExact(vessels) AS region_size FROM dd GROUP BY region
),
rm AS (
    SELECT region, toStartOfMonth(day) AS mon,
           medianExact(vessels)       AS med_vessels,
           medianExact(msgs / vessels) AS med_mpv,
           count()               AS days_in_month,
           maxIf(1, day BETWEEN '2015-08-28' AND '2015-09-30') AS dup_month
    FROM dd GROUP BY region, mon
),
st AS (
    SELECT *,
           any(med_vessels) OVER w AS prev_v,
           any(med_mpv)     OVER w AS prev_m,
           any(mon)         OVER w AS prev_mon
    FROM rm
    WINDOW w AS (PARTITION BY region ORDER BY mon ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING)
)
SELECT st.region                        AS region,
       round(h3ToGeo(st.region).1, 4)   AS lat,
       round(h3ToGeo(st.region).2, 4)   AS lon,
       round(sz.region_size, 1)         AS region_size,
       st.mon                           AS mon,
       st.prev_mon                      AS prev_mon,
       toUInt16(dateDiff('month', st.prev_mon, st.mon)) AS gap_months,
       st.days_in_month                 AS days_in_month,
       round(st.med_vessels, 1)         AS med_vessels,
       round(st.prev_v, 1)              AS prev_med_vessels,
       round(st.med_vessels / st.prev_v, 3) AS v_ratio,
       round(st.med_mpv, 1)             AS med_msgs_per_vessel,
       round(st.prev_m, 1)              AS prev_med_msgs_per_vessel,
       round(st.med_mpv / st.prev_m, 3) AS mpv_ratio,
       -- the flags, from the UNROUNDED ratios — the same expressions as the
       -- WHERE, so "why is this row here" needs no second spelling of the rule
       toUInt8(st.med_vessels / st.prev_v < 0.75
            OR st.med_vessels / st.prev_v > 1.3333) AS flag_vessels,
       toUInt8(st.med_mpv / st.prev_m < 0.75
            OR st.med_mpv / st.prev_m > 1.3333)     AS flag_msgs,
       st.dup_month                     AS dup_month
FROM st INNER JOIN sz AS sz ON sz.region = st.region
-- prev_v > 0 is the "has a predecessor" test: the window function returns 0
-- for the region's first month, and 0 would make both ratios infinite.
-- the flags test the UNROUNDED ratios: `v_ratio`/`mpv_ratio` are rounded to
-- three decimals for the reader, and filtering on the rounded value moves the
-- boundary (a raw 0.7496 rounds to 0.750 and would stop being a step). 22 of
-- block 4's 2 572 rows sit in that band and filtering on the rounded value
-- would silently drop them.
WHERE st.prev_v > 0
  AND (   st.med_vessels / st.prev_v < 0.75 OR st.med_vessels / st.prev_v > 1.3333
       OR st.med_mpv     / st.prev_m < 0.75 OR st.med_mpv     / st.prev_m > 1.3333)
ORDER BY greatest(abs(log(st.med_vessels / st.prev_v)), abs(log(st.med_mpv / st.prev_m))) DESC
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 4b — the same table restricted to ADJACENT calendar months
-- (gap_months = 1), 2 277 rows, same 17 columns. This is the version to read
-- for "did something change between one month and the next"; block 4's
-- gap_months = 10, 12 and 25 rows are the only way this store can compare
-- across its unloaded years and they are a different question, so they are
-- separated rather than mixed in.
-- ====================================================================
WITH
d AS (
    SELECT toDate(hour) AS day, h3ToParent(h3, 4) AS region,
           uniqExactMerge(vessels) AS vessels, sum(msgs) AS msgs
    FROM h3_hourly WHERE mobile = 'Class A' GROUP BY day, region
),
keep AS (
    SELECT region FROM (SELECT region, toYear(day) AS y, medianExact(vessels) AS mv
                        FROM d GROUP BY region, y) WHERE mv >= 20 GROUP BY region
),
dd AS (SELECT * FROM d WHERE region IN (SELECT region FROM keep)),
sz AS (SELECT region, medianExact(vessels) AS region_size FROM dd GROUP BY region),
rm AS (
    SELECT region, toStartOfMonth(day) AS mon,
           medianExact(vessels) AS med_vessels, medianExact(msgs / vessels) AS med_mpv,
           count() AS days_in_month,
           maxIf(1, day BETWEEN '2015-08-28' AND '2015-09-30') AS dup_month
    FROM dd GROUP BY region, mon
),
st AS (
    SELECT *, any(med_vessels) OVER w AS prev_v, any(med_mpv) OVER w AS prev_m,
              any(mon) OVER w AS prev_mon
    FROM rm WINDOW w AS (PARTITION BY region ORDER BY mon ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING)
)
SELECT st.region AS region,
       round(h3ToGeo(st.region).1, 4) AS lat,
       round(h3ToGeo(st.region).2, 4) AS lon,
       round(sz.region_size, 1) AS region_size,
       st.mon AS mon, st.prev_mon AS prev_mon,
       toUInt16(dateDiff('month', st.prev_mon, st.mon)) AS gap_months,
       st.days_in_month AS days_in_month,
       round(st.med_vessels, 1) AS med_vessels,
       round(st.prev_v, 1) AS prev_med_vessels,
       round(st.med_vessels / st.prev_v, 3) AS v_ratio,
       round(st.med_mpv, 1) AS med_msgs_per_vessel,
       round(st.prev_m, 1) AS prev_med_msgs_per_vessel,
       round(st.med_mpv / st.prev_m, 3) AS mpv_ratio,
       toUInt8(st.med_vessels / st.prev_v < 0.75
            OR st.med_vessels / st.prev_v > 1.3333) AS flag_vessels,
       toUInt8(st.med_mpv / st.prev_m < 0.75
            OR st.med_mpv / st.prev_m > 1.3333)     AS flag_msgs,
       st.dup_month AS dup_month
FROM st INNER JOIN sz AS sz ON sz.region = st.region
-- unrounded ratios in the filter; see block 4.
WHERE st.prev_v > 0
  AND dateDiff('month', st.prev_mon, st.mon) = 1
  AND (   st.med_vessels / st.prev_v < 0.75 OR st.med_vessels / st.prev_v > 1.3333
       OR st.med_mpv     / st.prev_m < 0.75 OR st.med_mpv     / st.prev_m > 1.3333)
ORDER BY greatest(abs(log(st.med_vessels / st.prev_v)), abs(log(st.med_mpv / st.prev_m))) DESC
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 5 — S6 finding 10 with TWO controls. 42 rows, 7 columns:
--   year, season ('May-Sep' | 'Oct-Apr', from the LOCAL month), fleet,
--   local_days, moving_msgs, night_msgs, night_share
--   fleet: 'leisure Class B' (the SUBJECT)
--          'ferry Class A'   (control 1: sql/24's control, a timetable that
--                             runs into the night by design)
--          'cargo Class A'   (control 2, NEW HERE and the harder one: cargo
--                             runs all night by nature, so its night share is
--                             a property of the NETWORK almost entirely. If it
--                             moves across years, the receivers moved.)
--   night: local hour in 22, 23, 0, 1, 2, 3, 4.
--
-- THIS IS A COPY OF sql/24_night.sql's LOGIC, not an import — clickhouse local
-- has no way to include a file, and S9 set the precedent of copying a CTE and
-- saying so (sql/51 and sql/52 carry sql/50's window CTEs verbatim). THE ONE
-- CHANGE: the `local` CTE admits Class A `cargo` as a third fleet and the
-- fleet label is a three-way multiIf instead of a two-way if. Everything else
-- — the 2015-08-28..2015-10-01 UTC exclusion applied BEFORE the coverage test,
-- the `covered` full-24-local-hour test, the timezone-name conversion, the
-- season split, the night hours — is byte-for-byte sql/24. DIFF THE TWO
-- BEFORE BELIEVING A CHANGE TO EITHER. sql/24's header carries the reasoning
-- for every one of those decisions and is not repeated here.
--
-- READ `local_days` BEFORE ANY ROW. 2022 and 2023 hold 59 loaded days each and
-- have NO 'May-Sep' row at all; 2024 begins 2024-03-01; 2026 ends 2026-08-26;
-- 2015's 'May-Sep' covers 118 of 153 days because the duplication window takes
-- 34 of them. A 2022 or 2023 leisure night share (0.1835, 0.1944) is TWO
-- WINTER MONTHS of a fleet that is 10-20 boats a day in winter (S9 finding 44)
-- and is not comparable to a full Oct-Apr; the six main years are.
-- ====================================================================
WITH
base AS (
    SELECT toTimeZone(hour, 'Europe/Copenhagen') AS lt,
           mobile, ship_group, moving_msgs
    FROM h3_hourly
    WHERE NOT (hour >= toDateTime('2015-08-28 00:00:00', 'UTC')
           AND hour <  toDateTime('2015-10-01 00:00:00', 'UTC'))
),
covered AS (
    SELECT toDate(lt) AS lday
    FROM base
    GROUP BY lday
    HAVING uniqExact(toHour(lt)) = 24
),
local AS (
    SELECT lt,
           multiIf(mobile = 'Class B' AND ship_group = 'leisure',   'leisure Class B',
                   mobile = 'Class A' AND ship_group = 'passenger', 'ferry Class A',
                                                                    'cargo Class A') AS fleet,
           moving_msgs AS mm
    FROM base
    WHERE (   (mobile = 'Class B' AND ship_group = 'leisure')
           OR (mobile = 'Class A' AND ship_group IN ('passenger', 'cargo')))
      AND toDate(lt) IN (SELECT lday FROM covered)
)
SELECT toYear(lt)                                            AS year,
       if(toMonth(lt) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr') AS season,
       fleet,
       uniqExact(toDate(lt))                                 AS local_days,
       sum(mm)                                               AS moving_msgs,
       sumIf(mm, toHour(lt) IN (22, 23, 0, 1, 2, 3, 4))      AS night_msgs,
       round(night_msgs / moving_msgs, 4)                    AS night_share
FROM local
GROUP BY year, season, fleet
ORDER BY year, season DESC, fleet;


-- ====================================================================
-- BLOCK 5b — the message-count proxy the night shares need: Class A CARGO
-- messages per vessel-HOUR, night against day, by year. 16 rows, 6 columns:
--   year, part ('night' | 'day', same seven local hours as block 5)
--   vessel_hours  sum over hours of uniqExactMerge(vessels) for that hour,
--        WHOLE BBOX. Each term is the EXACT number of distinct Class A cargo
--        vessels heard anywhere in the bbox in that hour; summing those over
--        the hours of a year gives vessel-hours, which is the denominator a
--        per-vessel message count needs. This is the one place a merged state
--        buys something no other table has: `vessel_day` cannot say how many
--        vessels were present in a given HOUR.
--   msgs, msgs_per_vessel_hour, moving_msgs_per_vessel_hour
--
-- WHAT THIS IS AND IS NOT. It is a proxy for HOW WELL THE NETWORK HEARD a
-- vessel it was already hearing. It is NOT a proxy for reach (a vessel heard
-- by nobody contributes to neither numerator nor denominator, and no table in
-- this store can count it). BIAS, stated: a cargo ship reports faster when it
-- moves, so a year in which cargo spent more time under way reads as better
-- reception; `moving_msgs_per_vessel_hour` is emitted next to it so a consumer
-- can see the two move together, and they do.
-- The night/day RATIO is the number block 5 needs. It is the ratio of two
-- columns of the same year, so the 2023 duplication cancels out of it ONLY IF
-- the duplicated copies fall evenly over the clock — which this file cannot
-- check on the message columns. It CAN check it on `vessel_hours`, which is a
-- head count and immune: that ratio is flat across the step and the message
-- ratio is not (header point 4). Read the ~8 % as an upper bound on a night
-- reception change, not as a measurement of one.
-- MEASURED (msgs_per_vessel_hour night / day): 1.024, 1.017, 1.021 for 2015,
-- 2018, 2021; 1.031 (2022), 1.039 (2023), 1.083 (2024), 1.093 (2025), 1.108
-- (2026). 2022 is two winter months and 2023 is February plus December —
-- their `vessel_hours` says so.
-- Same exclusion and same `covered` local days as block 5, so the two blocks
-- describe the same hours.
-- ====================================================================
WITH
hb AS (
    SELECT hour, mobile, ship_group, msgs, moving_msgs, vessels
    FROM h3_hourly
    WHERE NOT (hour >= toDateTime('2015-08-28 00:00:00', 'UTC')
           AND hour <  toDateTime('2015-10-01 00:00:00', 'UTC'))
),
covered AS (
    SELECT toDate(toTimeZone(hour, 'Europe/Copenhagen')) AS lday
    FROM hb
    GROUP BY lday
    HAVING uniqExact(toHour(toTimeZone(hour, 'Europe/Copenhagen'))) = 24
),
ch AS (
    SELECT toTimeZone(hour, 'Europe/Copenhagen') AS lt,
           uniqExactMerge(vessels) AS vh,             -- EXACT, whole bbox, this hour
           sum(msgs)               AS h_msgs,
           sum(moving_msgs)        AS h_moving
    FROM hb
    WHERE mobile = 'Class A' AND ship_group = 'cargo'
      AND toDate(toTimeZone(hour, 'Europe/Copenhagen')) IN (SELECT lday FROM covered)
    GROUP BY lt
)
SELECT toYear(lt)                                                AS year,
       if(toHour(lt) IN (22, 23, 0, 1, 2, 3, 4), 'night', 'day') AS part,
       sum(vh)                                                   AS vessel_hours,
       sum(h_msgs)                                               AS msgs,
       round(sum(h_msgs)   / sum(vh), 1)                         AS msgs_per_vessel_hour,
       round(sum(h_moving) / sum(vh), 1)                         AS moving_msgs_per_vessel_hour
FROM ch
GROUP BY year, part
ORDER BY year, part;


-- ====================================================================
-- BLOCK 6 — THE CEILING TEST: the DISTRIBUTION of Class A messages per
-- vessel-day, per loaded month. 70 rows, 12 columns:
--   mon             the loaded month (every one, 2015-01 .. 2026-08)
--   loaded_days     days of that month in `vessel_day` (28-31; the store
--                   holds no partial month except 2024-03 onward's calendar)
--   vessel_days     rows of `vessel_day`, Class A, that month
--   median_msgs, mean_msgs, p90_msgs, p99_msgs, max_msgs
--                   medianExact / avg / quantileExact(0.9) / quantileExact
--                   (0.99) / max of `msgs` over those rows. EXACT quantiles,
--                   like every other quantile in this file.
--   vd_over_cap     vessel-days with msgs > 43 200
--   share_over_cap  vd_over_cap / vessel_days
--   max_over_cap_x  max_msgs / 43 200 — the worst vessel-day of the month in
--                   units of the physical ceiling. 1.0 is the ceiling itself;
--                   8.33 (2024-11) is eight copies of a saturated day.
--   dup_month       1 on 2015-08 and 2015-09, the duplication window's months
--
-- WHY 43 200 IS A CEILING AND NOT A THRESHOLD. A Class A transponder's fastest
-- autonomous position-report rate is one report every 2 s (ITU-R M.1371, class
-- A autonomous mode; 2 s applies to a vessel changing course above 23 kn, 10 s
-- is the ordinary under-way rate). 86 400 / 2 = 43 200 reports in a day, plus a
-- few hundred static and voyage messages. A vessel-day above that did not
-- happen: the same message is in the archive more than once. This is a
-- PHYSICAL bound, so `share_over_cap` needs no baseline year to be read
-- against — it is a count of impossibilities.
-- The BOUND IS LOOSE, deliberately: a real ship at 43 200 messages a day would
-- have to hold the 2 s rate for all 24 hours. Nothing does. So the true
-- duplication rate is higher than `share_over_cap` and this column is a floor
-- on it, never an estimate of it.
--
-- WHY THE MEDIAN AND THE TAIL ARE BOTH EMITTED: they disagree, and the
-- disagreement is the whole finding (header point 2). A mean over vessel-days
-- — which is what block 2's `class_a_msgs_per_vessel_day` and block 5b's
-- messages per vessel-hour both are — moves with the tail and reads as "the
-- fleet reports 1.5x more often". The median says the typical Class A
-- vessel-day did not change at all.
-- ====================================================================
SELECT toStartOfMonth(day)                          AS mon,
       uniqExact(day)                               AS loaded_days,
       count()                                      AS vessel_days,
       round(medianExact(msgs), 1)                  AS median_msgs,
       round(avg(msgs), 1)                          AS mean_msgs,
       round(quantileExact(0.90)(msgs), 1)          AS p90_msgs,
       round(quantileExact(0.99)(msgs), 1)          AS p99_msgs,
       max(msgs)                                    AS max_msgs,
       countIf(msgs > 43200)                        AS vd_over_cap,
       round(countIf(msgs > 43200) / count(), 5)    AS share_over_cap,
       round(max(msgs) / 43200, 2)                  AS max_over_cap_x,
       toUInt8(toStartOfMonth(day) IN ('2015-08-01', '2015-09-01')) AS dup_month
FROM vessel_day
WHERE mobile = 'Class A'
GROUP BY mon
ORDER BY mon;


-- ====================================================================
-- BLOCK 6b — THE SAME FOR CLASS B, per YEAR. 8 rows, 10 columns: year,
-- loaded_days, vessel_days, median_msgs, mean_msgs, p90_msgs, p99_msgs,
-- max_msgs, vd_over_cap, share_over_cap.
-- PER YEAR AND NOT PER MONTH because the point here is a yes/no — does the
-- other fleet show the same tail step — and a Class B winter month is 10-20
-- boats a day (S9 finding 44). 2015's row CONTAINS the duplication window's 34
-- days and 2022 / 2023 are two winter months each; read `loaded_days`.
--
-- THE CLASS B CAP IS 17 280 AND IT IS A LOOSE UPPER BOUND, NOT A CEILING.
-- Class B SO (self-organising, the 5 W type) reports at most every 5 s when
-- moving faster than 2 kn — 86 400 / 5 = 17 280 — while Class B CS (carrier
-- sense, the 2 W type most leisure boats carry) reports every 30 s at best,
-- i.e. 2 880 a day. The archive does not say which type a vessel carries, so
-- the cap is set at the more generous of the two and a CS boat is allowed
-- six times its own physical rate before it counts. `share_over_cap` for Class
-- B is therefore a much weaker instrument than Class A's, and the tail
-- quantiles are what carry the finding here.
-- ====================================================================
SELECT toYear(day)                                  AS year,
       uniqExact(day)                               AS loaded_days,
       count()                                      AS vessel_days,
       round(medianExact(msgs), 1)                  AS median_msgs,
       round(avg(msgs), 1)                          AS mean_msgs,
       round(quantileExact(0.90)(msgs), 1)          AS p90_msgs,
       round(quantileExact(0.99)(msgs), 1)          AS p99_msgs,
       max(msgs)                                    AS max_msgs,
       countIf(msgs > 17280)                        AS vd_over_cap,
       round(countIf(msgs > 17280) / count(), 5)    AS share_over_cap
FROM vessel_day
WHERE mobile = 'Class B'
GROUP BY year
ORDER BY year;
