-- S7 check — an EXTERNAL ORACLE for sql/31_port_breathing.sql: recompute one
-- cell's ferry arrivals and departures from raw positions instead of from
-- merged uniqExact states, and emit BOTH answers side by side so the caller can
-- subtract them.
-- Run: scripts/ch.sh sql/33_port_oracle.sql
-- Columns: h3, lhour, window_days, days_seen, vessels_seen,
--          present, appeared, arrived_from_ring, vanished, left_to_ring,
--          st_present, st_appeared, st_arrived_from_ring, st_vanished,
--          st_left_to_ring
--   lhour:  hour of day in Europe/Copenhagen, 0-23
--   the five bare names are the ORACLE side, from raw positions; the five
--   st_* are the STATE side, sql/31's algebra on h3_hourly. RAW MONTH SUMS,
--   not means: a mean rounded to 2 dp and multiplied back by 31 days carries
--   up to ±3.7 per column, which is the same order as the difference this file
--   exists to measure. Divide by window_days for a mean if a chart needs one.
--
-- WHY THIS IS AN ORACLE AND NOT A ROUND TRIP. docs/STATUS.md § S4-redo: the S2
-- spatial test passed while the store was mirrored into the Arabian Sea because
-- it checked an expression against itself. The ORACLE side shares NOTHING with
-- sql/31's machinery except the cell id and the H3 resolution:
--   * source        `public_track` (raw 1-minute positions with an MMSI), not
--                   the h3_hourly aggregate;
--   * cell test     geoToH3(lat, lon, 7) computed here from the position, not
--                   the `h3` column written by sql/03_aggregate.sql;
--   * set algebra   plain uniqExact / has() over MMSI arrays, not
--                   |A ∩ B| = |A| + |B| − |A ∪ B| over aggregate states, and no
--                   union trick anywhere.
-- If sql/31's inclusion–exclusion, its slot domain or its LEFT JOINs were
-- wrong, the two sides would disagree; they are not two spellings of one
-- expression.
--
-- THE STATE SIDE IS SQL/31'S ALGEBRA RESTATED HERE, ON PURPOSE. `sev` below
-- rebuilds the three unions, the ring-1 neighbourhood and the inclusion–exclusion
-- for THIS one cell and month, in the plain UNION ALL form — 744 hours and one
-- cell do not need sql/31's ARRAY JOIN packing. It is a copy, and a copy is what
-- makes the comparison possible at all: nothing here imports or references
-- sql/31's CTEs, so a caller can run this one file and subtract two columns.
-- The oracle's value is that the OTHER column NEVER TOUCHES AN AGGREGATE STATE.
-- A duplicated block that is checked against an independent source every run is
-- worth more than a shared block that nothing checks.
--
-- ONE CELL, ONE MONTH, ONE FLEET. 608531604905656319 — the Svendborg Sund cell,
-- centre 55.0589 N 10.6251 E, five marinas plus the Ærø ferry berth. It is the
-- busiest of sql/31's ten cells for Class A passenger traffic (16.0 M messages
-- against 4.3 M for the runner-up), so it is the one where a ferry rhythm is
-- loud enough to check. 2025-07 is a fully loaded month with no DST changeover,
-- so all 31 local days pass sql/31's coverage test and the two sides cover the
-- same calendar. Bounded on purpose: this is a check, not a chart. NOTHING HERE
-- CERTIFIES ANY OTHER CELL, ANY OTHER MONTH OR THE LEISURE FLEET.
--
-- CLASS A PASSENGER ONLY, which is what `public_track` holds — the only fleet
-- for which per-vessel data legally exists in this project (public vessels may
-- be named; sql/01_schema.sql keeps Class B out even when it reports
-- Ship type = 'Passenger'). The leisure half of sql/31 has no oracle and cannot
-- have one; what this file certifies is the MACHINERY, on the fleet where the
-- machinery can be checked at all.
-- PRIVACY: MMSI is used inside the query as a set element and NOTHING BUT
-- COUNTS is emitted — no MMSI, no vessel name, not even a vessel count small
-- enough to be one boat by name.
--
-- TWO REASONS THE TWO SIDES MAY DIFFER BY A VESSEL OR TWO, both real:
--   1. `public_track` is downsampled to one position per minute
--      (sql/03_aggregate.sql), while h3_hourly is built from every message. A
--      res-7 cell is ~5 km across, which is ~8 minutes at 20 kn, so a transit
--      that leaves no sampled minute inside the cell is unlikely but possible.
--      For the PRESENCE SET this is one-directional: the sampled set is a
--      subset of the full one, so `present` here can only come out at or below
--      `st_present`. FOR appeared / vanished IT IS NOT. A gap in the middle of
--      a stay splits one stay into two and manufactures an extra appearance AND
--      an extra departure, so a sparser source can read HIGHER on those columns
--      — and it does here: appeared 503 against 502, arrived_from_ring 20
--      against 19, on a present total that is 2 lower.
--   2. Both tables take `mobile` from the same per-vessel-day resolution (the
--      1 % Class-B threshold in sql/03_aggregate.sql), so the fleet definition
--      does agree; but a vessel that h3_hourly places in the cell through a
--      message `public_track` did not keep is a genuine one-sided difference.
-- MEASURED, 2025-07, this cell, Class A passenger, raw month sums:
--   present 1 646 vs 1 648, appeared 503 vs 502, arrived_from_ring 20 vs 19,
--   vanished 501 vs 501, left_to_ring 8 vs 8
-- — so ~3 underlying vessel-hours out of 1 648 (0.2 %) separate the two sources,
-- and 20 of the 24 local hours agree EXACTLY on all five totals. The four
-- disagreeing hours are all explained:
--   * lhour 2, appeared 1 here against 0 on the state side — the window artefact
--     of the ORACLE side. 2025-07-01 00:00 UTC is 02:00 local, so the first slot
--     has no previous hour inside `pos` and the vessel already berthed reads as
--     an arrival. The state side reads June's hour out of h3_hourly (`sh` starts
--     one hour before t0) and correctly calls it continuing. Verified: it is the
--     only hour-2 appearance in the month, on 2025-07-01.
--   * lhour 19 (present 98 vs 100, appeared 36 vs 38) and lhour 20 (appeared 27
--     vs 25, arrived_from_ring 15 vs 13) are the two halves of one difference:
--     two vessel-hours that h3_hourly holds at 19:00 and the 1-minute sample
--     does not, so here the vessel arrives an hour later than there.
--   * lhour 22, arrived_from_ring 0 here against 1 — the same one-sided gap in a
--     ring cell.
-- The presence differences all run the predicted way — h3_hourly is built from
-- every message and public_track from one minute in sixty, so h3_hourly's
-- presence set contains this file's. The event columns do not have to, and the
-- +1 on appeared and on arrived_from_ring is the split-stay artefact above.
--
-- The ring columns use h3kRing(cell, 1) — the seven cells INCLUDING the centre,
-- the same definition as sql/31 — so 0 <= arrived_from_ring <= appeared holds
-- here too and the confound fix, not just the arrival count, is checked.
--
-- `vessels_seen` counts distinct vessels with the -Array combinator,
-- uniqExactArray(a_now), NOT uniqExact(arrayJoin(a_now)): arrayJoin in a
-- SELECT list expands the rows BEFORE the other aggregates see them, which
-- silently multiplied mean_present here by the size of the hour's vessel set
-- (16.35 present against 7 vessels ever seen — an impossible row, which is how
-- it was caught).
--
-- MISSING HOURS ARE ZERO, NOT ABSENT, here as well — and the SLOT DOMAIN IS THE
-- CALENDAR, not the occupancy: every one of the window's 744 hours gets a row
-- from `numbers()` and both sides' occupancy are LEFT JOINed onto it. An hour
-- with no ferry anywhere near the cell is therefore a real zero, in the
-- numerator and in the denominator both. Building the domain from the hours
-- that happen to hold a position instead would drop those hours entirely and
-- divide the rest by a denominator that depends on the answer.
-- The LEFT JOINs are why the query carries `SETTINGS join_use_nulls = 0`: under
-- `= 1` an unmatched side comes back NULL, the arithmetic below propagates it
-- and sum() then skips the row, which silently lowers a total instead of
-- failing. Same reasoning as in sql/31_port_breathing.sql.
--
-- TWO DAY COLUMNS, the same convention as sql/31_port_breathing.sql, so the two
-- files divide by the same kind of quantity:
--   window_days  local days on which this local hour exists inside the window —
--                31 for every hour here, since the window is exactly 744 hours.
--                The divisor if a mean is wanted.
--   days_seen    local days on which a ferry was actually in the cell at that
--                hour. Informative, never a divisor.
WITH
608531604905656319 AS cell,
toDateTime('2025-07-01 00:00:00', 'UTC') AS t0,
toDateTime('2025-08-01 00:00:00', 'UTC') AS t1,
-- ---------------------------------------------------------------------------
-- THE ORACLE SIDE: raw positions, MMSI sets, no aggregate state anywhere.
-- ---------------------------------------------------------------------------
-- one row per (hour, vessel) with two flags: in the centre cell, in the ring.
pos AS (
    SELECT toStartOfHour(ts) AS hour,
           mmsi,
           maxIf(1, geoToH3(lat, lon, 7) = cell)                        AS in_cell,
           maxIf(1, has(h3kRing(cell, 1), geoToH3(lat, lon, 7)))        AS in_ring
    FROM public_track
    WHERE ts >= t0 AND ts < t1
    GROUP BY hour, mmsi
    HAVING in_ring = 1
),
-- the two membership SETS per hour, as plain arrays of MMSI. Never emitted.
occ AS (
    SELECT hour,
           groupUniqArrayIf(mmsi, in_cell = 1) AS a,
           groupUniqArray(mmsi)                AS r
    FROM pos
    GROUP BY hour
),
-- every hour of the window, occupied or not
hours AS (
    SELECT t0 + number * 3600 AS hour
    FROM numbers(dateDiff('hour', t0, t1))
),
-- ---------------------------------------------------------------------------
-- THE STATE SIDE: sql/31's algebra, restated for this one cell (see the header).
-- `sh` starts ONE HOUR BEFORE t0 so the window's first slot has a real
-- predecessor, which is what sql/31 has and the oracle side does not.
-- ---------------------------------------------------------------------------
sh AS (
    SELECT hour, h3, vessels
    FROM h3_hourly
    WHERE hour >= t0 - 3600 AND hour < t1
      AND has(h3kRing(cell, 1), h3)
      AND mobile = 'Class A' AND ship_group = 'passenger'
),
sper AS (
    SELECT hour,
           uniqExactMergeStateIf(vessels, h3 = cell) AS own_st,
           uniqExactMergeState(vessels)              AS ring_st,
           uniqExactMergeIf(vessels, h3 = cell)      AS own_n,
           uniqExactMerge(vessels)                   AS ring_n
    FROM sh
    GROUP BY hour
),
-- each hour's state emitted twice, once at its own slot and once at slot + 1h:
--   u1 = |A_slot    ∪ A_{slot−1}|
--   u2 = |A_slot    ∪ Ring_{slot−1}|
--   u3 = |Ring_slot ∪ A_{slot−1}|
sustage AS (
              SELECT hour        AS slot, 'u1' AS kind, own_st  AS st FROM sper
    UNION ALL SELECT hour + 3600 AS slot, 'u1' AS kind, own_st  AS st FROM sper
    UNION ALL SELECT hour        AS slot, 'u2' AS kind, own_st  AS st FROM sper
    UNION ALL SELECT hour + 3600 AS slot, 'u2' AS kind, ring_st AS st FROM sper
    UNION ALL SELECT hour        AS slot, 'u3' AS kind, ring_st AS st FROM sper
    UNION ALL SELECT hour + 3600 AS slot, 'u3' AS kind, own_st  AS st FROM sper
),
sun AS (
    SELECT slot,
           uniqExactMergeIf(st, kind = 'u1') AS un_aa,
           uniqExactMergeIf(st, kind = 'u2') AS un_ar,
           uniqExactMergeIf(st, kind = 'u3') AS un_ra
    FROM sustage
    GROUP BY slot
),
sev AS (
    SELECT h.hour AS hour,
           n.own_n  AS n_now,    p.own_n  AS n_prev,
           n.ring_n AS ring_now, p.ring_n AS ring_prev,
           n_now  + n_prev    - g.un_aa AS i_own,        -- |A_h ∩ A_{h−1}|
           n_now  + ring_prev - g.un_ar AS i_ring_prev,  -- |A_h ∩ Ring_{h−1}|
           n_prev + ring_now  - g.un_ra AS i_ring_now,   -- |A_{h−1} ∩ Ring_h|
           n_now  - i_own              AS appeared,
           i_ring_prev - i_own         AS arrived_from_ring,
           n_prev - i_own              AS vanished,
           i_ring_now  - i_own         AS left_to_ring
    FROM hours AS h
    LEFT JOIN sun  AS g ON g.slot = h.hour
    LEFT JOIN sper AS n ON n.hour = h.hour
    LEFT JOIN sper AS p ON p.hour = h.hour - 3600
),
ev AS (
    SELECT s.hour AS hour,
           toTimeZone(s.hour, 'Europe/Copenhagen') AS lt,
           length(n.a) AS n_now,
           length(arrayFilter(x ->  NOT has(p.a, x), n.a))                    AS appeared,
           length(arrayFilter(x ->  NOT has(p.a, x) AND has(p.r, x), n.a))    AS arrived_from_ring,
           length(arrayFilter(x ->  NOT has(n.a, x), p.a))                    AS vanished,
           length(arrayFilter(x ->  NOT has(n.a, x) AND has(n.r, x), p.a))    AS left_to_ring,
           n.a AS a_now,
           v.n_now             AS st_present,
           v.appeared          AS st_appeared,
           v.arrived_from_ring AS st_arrived_from_ring,
           v.vanished          AS st_vanished,
           v.left_to_ring      AS st_left_to_ring
    FROM hours AS s
    LEFT JOIN occ AS n ON n.hour = s.hour
    LEFT JOIN occ AS p ON p.hour = s.hour - 3600
    LEFT JOIN sev AS v ON v.hour = s.hour
)
SELECT
    cell                                AS h3,
    toHour(lt)                          AS lhour,
    uniqExact(toDate(lt))               AS window_days,
    uniqExactIf(toDate(lt), n_now > 0)  AS days_seen,
    uniqExactArray(a_now)               AS vessels_seen,
    sum(n_now)                          AS present,
    sum(appeared)                       AS appeared,
    sum(arrived_from_ring)              AS arrived_from_ring,
    sum(vanished)                       AS vanished,
    sum(left_to_ring)                   AS left_to_ring,
    sum(st_present)                     AS st_present,
    sum(st_appeared)                    AS st_appeared,
    sum(st_arrived_from_ring)           AS st_arrived_from_ring,
    sum(st_vanished)                    AS st_vanished,
    sum(st_left_to_ring)                AS st_left_to_ring
FROM ev
GROUP BY h3, lhour
ORDER BY lhour
SETTINGS join_use_nulls = 0;
