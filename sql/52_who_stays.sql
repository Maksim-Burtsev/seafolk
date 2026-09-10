-- S9 chart 3 — chapter 04: WHO stops. The exact count of vessels that moved
-- at all, per fleet per day around each named storm, and the same on the
-- storm's derived peak hour.
-- Run: scripts/ch.sh sql/52_who_stays.sql
--      (read-only; 3.2 s, 1 090 + 140 + 146 rows)
-- Reads `vessel_day`, `h3_hourly` and `storm` (sql/04_context.sql).
-- Writes nothing.
--
-- WHY THIS FILE EXISTS NEXT TO sql/50. sql/50's hourly signal is
-- `moving_msgs`, a MESSAGE count: it has the right shape and the wrong unit,
-- because AIS reporting rates differ between classes and rise with speed. A
-- distinct count of MOVING vessels per hour is not recoverable from
-- `h3_hourly` at all (`vessels` is a uniqExact state over everything present).
-- `vessel_day` has it exactly, once a day: one row per vessel per day with
-- `dist_nm`, the distance covered while moving. So the honest answer to "how
-- many boats stayed in" is a DAY number, and this file is where it lives.
--
-- THE PASSENGER GROUP IS NOT THE FERRY FLEET, AND `other` IS PART OF IT.
-- A vessel's ship_group is resolved per DAY from what it broadcast that day
-- (sql/03_aggregate.sql), and ferries misfile themselves: of the Class A
-- vessels that ever appear in `ferry_crossing`, some are filed 'other' or
-- 'cargo' on any given day, and the proportion MOVES between a storm day and
-- its reference day. So `share_moved` for `passenger` is a share of a fleet
-- whose membership changed, and the `other` group inherits the ferries that
-- left it. BLOCK 3 measures exactly that, per storm and per reference day; read
-- it before quoting a passenger or `other` number from block 1 or block 2.
-- This is S8's hidden-fleet mechanism (sql/44_hidden_fleet.sql) reaching this
-- chapter — the same misfiling reaches sql/50's `heard` and `moving_msgs`.
--
-- BLOCK 1 — one row per (storm, mobile, ship_group, day), 12 columns:
--   day               UTC calendar day, start_day - 3 .. end_day + 3
--   offset_d          day - start_day
--   heard             uniqExact(mmsi) in `vessel_day` that day. EXACT.
--   moved             uniqExactIf(mmsi, dist_nm >= 1). EXACT.
--   share_moved       moved / heard
--   ref_day, ref_heard, ref_moved, ref_share_moved   the same a fortnight away
--
-- WHY dist_nm >= 1 AND NOT moving_msgs > 0. `dist_nm` is summed over moving
-- steps with four guards applied at load time (sql/03_aggregate.sql), so one
-- stray speed spike at anchor cannot manufacture a voyage; a single
-- `moving_msgs` can. One nautical mile is roughly ten minutes of a ferry and
-- well outside the drift of a ship at anchor in a gale — which is exactly the
-- confusion this chapter has to survive. sql/53_storm_oracle.sql recounts the
-- same collapse with the OTHER definition (`moving_msgs > 0`) so the two can
-- be compared instead of trusted.
--
-- THE WINDOW AND THE REFERENCE are sql/50_storm_window.sql's rules, at day
-- grain: the window is start_day - 3 .. end_day + 3 built from CALENDAR DATES
-- with no timezone conversion; Dagmar and Egon are one storm 'Dagmar·Egon';
-- the reference day is 14 days earlier (same weekday), else 14 days later,
-- else NULL and the row is still emitted. sql/50's header carries the
-- reasoning and the measurement of which rule fired for which storm.
--
-- BLOCK 2 — THE PEAK HOUR, and it is DERIVED FROM THE DATA, not given.
-- Every row of storms.csv says `date-only`: DMI publishes the DATE a storm
-- crossed Denmark and no hour at all. So the peak hour is defined here as the
-- hour of the storm's OWN CALENDAR DAYS at which the POOLED Class A
-- `ratio_moving` — sum of moving_msgs over ALL Class A groups divided by the
-- same sum at the reference hour — is lowest. Pooled, because a single thin
-- group's noisiest hour is not the storm.
--   MEASURED: 14 storms have a peak row (the 15 storms of sql/50's list minus
--   Alfrida, whose own days are all unloaded — see below). Restricting the
--   search to the storm's own days rather than to the whole -72/+72 h window
--   changes the answer for 6 of those 14 (Dave, Floriane, Freja, Helga, Nora,
--   Otto) and leaves the other 8 unchanged (Amy, Dagmar·Egon, Gorm, Johanne,
--   Knud, Malik, Pia, Sif). The storm's own days are used: a minimum three
--   days after the storm is a different weather
--   system, not this one's peak. Floriane is the case that makes the point —
--   its deepest hour inside its own date is a ratio of 1.05, i.e. NO DIP AT
--   ALL, while the whole-window minimum (0.76) sits on 2025-01-10, three days
--   later. A quiet storm must be allowed to read as quiet.
--   ALFRIDA HAS NO PEAK ROW: 2019 is unloaded, none of its own hours is in
--   the store, and a peak cannot be derived from nothing. It is absent from
--   block 2 on purpose, and present in block 1 for its three run-up days.
-- Columns, one row per (storm, mobile, ship_group), 11 of them:
--   peak_hour, peak_offset_h, peak_ratio  the derived peak and its pooled ratio
--   is_dip         peak_ratio < 1. The peak hour is an argMin, so it always
--                  exists — it is the LEAST BAD hour, and for a storm like
--                  Floriane (peak_ratio 1.05) there is no dip at all inside
--                  its own date. The definition is deliberately unchanged;
--                  this column just lets a consumer draw "no dip" as no dip
--                  instead of as a peak.
--   heard          uniqExactMerge(vessels) in that hour  (exact head count)
--   moving_share   moving_msgs / msgs in that hour       (a MESSAGE share)
--   ref_heard, ref_moving_share           the same at the reference hour
-- `moving_share` is a share of messages, not of vessels: comparable to the
-- same fleet's own reference hour and to nothing else (sql/30's rule).
--
-- PRIVACY: `vessel_day` holds MMSI and is INTERNAL (sql/01_schema.sql). This
-- file emits COUNTS of distinct MMSI and never an MMSI, a name or a position.
-- `uniqExact`/`uniqExactIf` are aggregated to a number here, not to a state.

-- ====================================================================
-- BLOCK 1 — vessels heard and vessels that moved, per day.
-- ====================================================================
WITH
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
win AS (
    SELECT storm, start_day,
           (start_day - 3)
             + arrayJoin(range(toUInt32(dateDiff('day', start_day - 3, end_day + 3)) + 1)) AS day
    FROM st
),
winr AS (
    SELECT storm, start_day, day, toInt32(day - start_day) AS offset_d,
           multiIf((day - 14) IN (SELECT day FROM loaded), toNullable(day - 14),
                   (day + 14) IN (SELECT day FROM loaded), toNullable(day + 14),
                   NULL) AS ref_day
    FROM win
),
days AS (
    SELECT DISTINCT day FROM (
        SELECT day FROM winr
        UNION ALL
        SELECT assumeNotNull(ref_day) AS day FROM winr WHERE ref_day IS NOT NULL
    )
),
vd AS (
    SELECT day, mobile, ship_group,
           uniqExact(mmsi)                 AS heard,
           uniqExactIf(mmsi, dist_nm >= 1) AS moved
    FROM vessel_day
    WHERE day IN (SELECT day FROM days)
    GROUP BY day, mobile, ship_group
)
SELECT w.storm       AS storm,
       v.mobile      AS mobile,
       v.ship_group  AS ship_group,
       w.day         AS day,
       w.offset_d    AS offset_d,
       v.heard       AS heard,
       v.moved       AS moved,
       if(v.heard = 0, NULL, toNullable(round(v.moved / v.heard, 4))) AS share_moved,
       w.ref_day     AS ref_day,
       if(w.ref_day IS NULL, NULL, toNullable(r.heard)) AS ref_heard,
       if(w.ref_day IS NULL, NULL, toNullable(r.moved)) AS ref_moved,
       if(w.ref_day IS NULL OR r.heard = 0, NULL,
          toNullable(round(r.moved / r.heard, 4)))      AS ref_share_moved
FROM winr AS w
INNER JOIN vd AS v ON v.day = w.day
LEFT  JOIN vd AS r ON r.day = assumeNotNull(w.ref_day)
                  AND r.mobile = v.mobile AND r.ship_group = v.ship_group
ORDER BY storm, mobile, ship_group, day
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 2 — the derived peak hour, and every fleet on it.
-- ====================================================================
WITH
-- --- sql/50_storm_window.sql's four CTEs, verbatim except that `st`,
-- --- `win` and `winr` also carry `end_day`, which block 2 needs to bound
-- --- the peak search to the storm's own days. sql/51's copy IS byte-
-- --- identical to sql/50's; diff all three before believing any change.
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
win AS (
    SELECT storm, start_day, end_day,
           toDateTime(start_day, 'UTC') - INTERVAL 72 HOUR
             + INTERVAL arrayJoin(range(toUInt32(dateDiff('hour',
                   toDateTime(start_day, 'UTC')   - INTERVAL 72 HOUR,
                   toDateTime(end_day + 1, 'UTC') + INTERVAL 72 HOUR)))) HOUR AS hour
    FROM st
),
winr AS (
    SELECT storm, start_day, end_day, hour,
           toInt32(dateDiff('hour', toDateTime(start_day, 'UTC'), hour)) AS offset_h,
           multiIf(toDate(hour - INTERVAL 14 DAY) IN (SELECT day FROM loaded),
                       toNullable(hour - INTERVAL 14 DAY),
                   toDate(hour + INTERVAL 14 DAY) IN (SELECT day FROM loaded),
                       toNullable(hour + INTERVAL 14 DAY),
                   NULL) AS ref_hour
    FROM win
),
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
-- --- end of the verbatim copy ---------------------------------------
pooled AS (
    SELECT hour, sum(moving_msgs) AS mm
    FROM agg WHERE mobile = 'Class A'
    GROUP BY hour
),
-- the pooled Class A ratio, restricted to the storm's OWN calendar days
storm_hours AS (
    SELECT w.storm AS storm, w.hour AS hour, w.offset_h AS offset_h,
           w.ref_hour AS ref_hour, p.mm / r.mm AS ratio
    FROM winr AS w
    INNER JOIN pooled AS p ON p.hour = w.hour
    INNER JOIN pooled AS r ON r.hour = assumeNotNull(w.ref_hour)
    WHERE w.ref_hour IS NOT NULL
      AND r.mm > 0
      AND w.offset_h >= 0
      AND w.hour < toDateTime(w.end_day + 1, 'UTC')
),
peak AS (
    SELECT storm,
           argMin(hour, ratio)     AS peak_hour,
           argMin(offset_h, ratio) AS peak_offset_h,
           argMin(ref_hour, ratio) AS peak_ref_hour,
           min(ratio)              AS peak_ratio
    FROM storm_hours
    GROUP BY storm
)
SELECT k.storm                     AS storm,
       k.peak_hour                 AS peak_hour,
       k.peak_offset_h             AS peak_offset_h,
       round(k.peak_ratio, 4)      AS peak_ratio,
       a.mobile                    AS mobile,
       a.ship_group                AS ship_group,
       a.heard                     AS heard,
       if(a.msgs = 0, NULL, toNullable(round(a.moving_msgs / a.msgs, 4))) AS moving_share,
       r.heard                     AS ref_heard,
       if(r.msgs = 0, NULL, toNullable(round(r.moving_msgs / r.msgs, 4))) AS ref_moving_share,
       k.peak_ratio < 1            AS is_dip
FROM peak AS k
INNER JOIN agg AS a ON a.hour = k.peak_hour
LEFT  JOIN agg AS r ON r.hour = assumeNotNull(k.peak_ref_hour)
                   AND r.mobile = a.mobile AND r.ship_group = a.ship_group
ORDER BY storm, mobile, ship_group
SETTINGS join_use_nulls = 0;


-- ====================================================================
-- BLOCK 3 — THE FERRY FLEET, BY THE SHIP TYPE IT WAS FILED UNDER THAT DAY.
-- 6 columns, one row per (storm, day, day_kind, ship_group):
--   storm       as everywhere else, Dagmar and Egon merged
--   day         a UTC calendar day: one of the storm's OWN dates, or one of
--               their reference days
--   day_kind    'storm' | 'reference'
--   ship_group  the group `vessel_day` resolved for that vessel THAT DAY
--   vessels     uniqExact(mmsi), Class A only. EXACT.
--   share       vessels / the day's total, so the rows of one (storm, day)
--               sum to 1
--
-- THE POPULATION IS FIXED AND THE LABEL IS NOT: every Class A MMSI that
-- appears anywhere in `ferry_crossing`, over the whole archive — the fleet
-- that demonstrably runs ferry crossings. It is deliberately NOT restricted
-- to the Danish lines sql/50's `ferry_crossings` column keeps: a Swedish or
-- German ferry is in the bbox and is counted in sql/50's `heard` and
-- `moving_msgs` like any other ship, so it belongs in this measurement of the
-- passenger group's composition.
--
-- WHY IT IS HERE AND NOT IN sql/53_storm_oracle.sql: it is not a check of
-- another file's arithmetic, it is a caveat that a reader needs while looking
-- at blocks 1 and 2 of THIS file — the passenger `share_moved` and the `other`
-- group both move with it. sql/53 recounts; this measures.
--
-- ONLY A LOADED STORM DATE PRODUCES ROWS, and its reference row is emitted
-- only next to it: Alfrida and Rolf have no loaded own day and contribute
-- nothing at all (a reference day with nothing to compare against is not a
-- measurement), and a loaded storm date whose reference is unloaded
-- contributes its 'storm' rows alone. 14 storms are left.
--
-- PRIVACY: ferries are public and no vessel is named here anyway — MMSI is a
-- join key inside the query and only counts are emitted.
-- ====================================================================
WITH
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
-- the storm's OWN dates only — the window's run-up and recovery days are not
-- what this compares
own AS (
    SELECT storm,
           start_day + arrayJoin(range(toUInt32(dateDiff('day', start_day, end_day)) + 1)) AS day
    FROM st
),
ownr AS (
    SELECT storm, day,
           -- computed here, not in `pairs`: the reference branch below
           -- projects ref_day AS day, and that alias would shadow this test.
           day IN (SELECT day FROM loaded) AS day_loaded,
           multiIf((day - 14) IN (SELECT day FROM loaded), toNullable(day - 14),
                   (day + 14) IN (SELECT day FROM loaded), toNullable(day + 14),
                   NULL) AS ref_day
    FROM own
),
-- one row per day to count, tagged with which side of the comparison it is.
-- A reference day is emitted only next to a loaded storm day.
pairs AS (
    SELECT storm, 'storm' AS day_kind, day AS day
    FROM ownr WHERE day_loaded
    UNION ALL
    SELECT storm, 'reference' AS day_kind, assumeNotNull(ref_day) AS day
    FROM ownr WHERE day_loaded AND ref_day IS NOT NULL
),
-- every Class A vessel that has ever run a crossing, whatever line
ferry_fleet AS (
    SELECT DISTINCT mmsi FROM ferry_crossing
),
vd AS (
    SELECT day, ship_group, uniqExact(mmsi) AS vessels
    FROM vessel_day
    WHERE day IN (SELECT day FROM pairs)
      AND mobile = 'Class A'
      AND mmsi IN (SELECT mmsi FROM ferry_fleet)
    GROUP BY day, ship_group
)
SELECT p.storm      AS storm,
       p.day        AS day,
       p.day_kind   AS day_kind,
       v.ship_group AS ship_group,
       v.vessels    AS vessels,
       round(v.vessels / sum(v.vessels) OVER (PARTITION BY p.storm, p.day_kind, p.day), 4) AS share
FROM pairs AS p
INNER JOIN vd AS v ON v.day = p.day
ORDER BY storm, day_kind, day, ship_group
SETTINGS join_use_nulls = 0;
