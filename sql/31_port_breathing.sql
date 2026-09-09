-- S7 chart 2 — what does a harbour do over a day: when do boats arrive, when do
-- they leave, and when does a transponder simply switch on at the berth?
-- Run: scripts/ch.sh sql/31_port_breathing.sql
-- Columns: h3, place, n_marinas, lat, lon, fleet, season, lhour, season_days,
--          days_seen, vessels_seen, mean_present, mean_appeared,
--          mean_arrived_from_ring, mean_vanished, mean_left_to_ring
--   fleet:  'leisure Class B' | 'ferry Class A' (the control, as in sql/24)
--   season: 'May-Sep' | 'Oct-Apr', from the LOCAL month
--   lhour:  hour of day in Europe/Copenhagen, 0-23
--   lat/lon: the CELL CENTRE, h3ToGeo(h3).1 = lat, .2 = lon (pinned in
--           scripts/ch.sh), not the position of any marina or vessel
--
-- ===================================================================
-- ARRIVALS AND DEPARTURES ARE EXACTLY RECOVERABLE FROM h3_hourly.
-- `vessels` is AggregateFunction(uniqExact, UInt32): merging two hours' states
-- gives |A ∪ B|, so |A ∩ B| = |A| + |B| − |A ∪ B| and
--     appeared(h) = |A_h|     − |A_h ∩ A_{h−1}|
--     vanished(h) = |A_{h−1}| − |A_h ∩ A_{h−1}|
-- are exact counts, not estimates. No MMSI is read, emitted or compared: the
-- states are only ever merged, and `uniqExactMerge` returns a number. The state
-- column itself is a membership oracle over MMSI and never leaves this machine
-- (sql/01_schema.sql, docs/DECISIONS.md) — nothing below writes one out.
--
-- The unions are built in one pass: each hour's state is emitted twice, once at
-- its own slot and once at slot + 1 hour, and one `uniqExactMerge` per slot then
-- holds |A_slot ∪ A_{slot−1}|. Three unions are needed, tagged u1/u2/u3 below.
--
-- THE CONFOUND, AND THE RING-1 FIX. A Class B transponder is powered with the
-- boat (docs/DECISIONS.md 2026-09-09), so a boat switching on at its berth is an
-- "arrival out of nowhere" and a naive appeared/vanished pair would show a
-- harbour arriving and departing at the same morning hour. Split the appearance
-- by asking where the vessel was an hour earlier — inside the cell's ring-1
-- NEIGHBOURHOOD, or nowhere near it:
--     appeared(h)          = |A_h| − |A_h ∩ A_{h−1}|              new to the cell
--     arrived_from_ring(h) = |A_h ∩ Ring_{h−1}| − |A_h ∩ A_{h−1}| sailed in from next door
--     switched_on(h)       = appeared(h) − arrived_from_ring(h)   turned on, or came from far
-- and symmetrically vanished / left_to_ring / switched_off. `Ring_h` is the
-- merged state over h3kRing(cell, 1) — the SEVEN cells INCLUDING the centre — so
-- A ⊆ Ring and 0 <= arrived_from_ring <= appeared holds by construction (checked:
-- max(arrived_from_ring − appeared) = 0 over the whole store).
-- `switched_on` and `switched_off` are not emitted as columns; they are the
-- subtraction above, and keeping them out of the file keeps the two measured
-- quantities and the derived one visibly apart.
--
-- READ `arrived_from_ring` AS A SPEED TEST, NOT ONLY AS A TRANSPONDER TEST.
-- Ring 1 at res 7 is ~15 km across, so it is one hour of travel for a vessel
-- doing ~8 kn and much less than one hour for a ferry at 20 kn. Measured on the
-- Svendborg cell in July 2025, with this file's own machinery: 485 of 2 748
-- leisure appearances (17.6 %) came from the ring against 19 of 502 for the
-- ferries (3.8 %). The ferry number is NOT
-- evidence that ferries switch their transponders on and off — it is a fast
-- vessel outrunning the ring in an hour. For the leisure fleet, which mostly
-- moves at ring-1 speed, the split does mean what it says.
--
-- MISSING HOURS ARE ZERO, NOT ABSENT. An empty cell-hour writes no h3_hourly
-- row, so the hour-to-hour step is a LEFT JOIN from a slot domain that contains
-- every hour present PLUS the hour after it — an INNER JOIN would silently
-- delete exactly the hours where a harbour empties out, and Σvanished would come
-- out below Σappeared by construction. With the LEFT JOIN, Σappeared = Σvanished
-- per cell and fleet up to the archive's own edges. The residual is small and
-- runs both ways: the worst of the 20 (cell, fleet) pairs is the Sønderborg
-- leisure pair at 17 against 53 738 appearances there (0.0003), and Troense
-- leisure runs one the other way, at −1. The per-pair residuals cannot be
-- recomputed from this file's ROUNDED output, so they are not stated here as a
-- count — notes/ch02-findings.md § "Σappeared = Σvanished" carries the ad-hoc
-- query that produces them, with its raw output. What is left is the
-- coverage filter and the archive's ends: boats present in the last covered hour
-- of a block have no following hour to leave in, and boats present when a day is
-- dropped reappear as arrivals after it. A harbour that gained boats forever
-- would show a residual of the order of its arrivals, not of one part in 3 000.
--
-- CHECKED AGAINST AN INDEPENDENT SOURCE: sql/33_port_oracle.sql recomputes the
-- Class A passenger half of ONE cell-month (608531604905656319, 2025-07) from
-- raw `public_track` positions with plain set differences over MMSI — no
-- aggregate states, no union trick — and emits that answer NEXT TO the same
-- month computed with the algebra below, so notes/plot_ch02.py can subtract the
-- two and assert on the gap. 20 of 24 local hours agree exactly; raw month sums
-- present 1 646 vs 1 648, appeared 503 vs 502, arrived_from_ring 20 vs 19,
-- vanished 501 vs 501, left_to_ring 8 vs 8 — ~3 vessel-hours in 1 648. That
-- file is the reason this one is trusted; see its header for the four
-- disagreeing hours. It certifies THAT cell, THAT month and the ferry fleet,
-- and nothing else.
-- ===================================================================
--
-- THE CELLS: the ten res-7 cells that CONTAIN a marina (`marina.h3` is on the
-- same grid as `h3_hourly.h3`, so the join is a plain equality), ranked by
-- uniqExactMerge(vessels) over Class B leisure across the whole store. Ranked on
-- DISTINCT VESSELS, not messages, so the Sep-2015 duplication window — which
-- inflates `msgs` ~2.3x and cannot touch a uniqExact state — could not choose
-- the cells. Ring 0, not ring 1: sql/23_radius.sql established that ring 1 is
-- saturated at 92 % of vessel-days and separates nothing.
--
-- FOUR OF THE TEN CELLS ARE ONE HARBOUR. Vindebyøre Bro (608531604905656319),
-- Lystbådehavn Troense, Vindeby Havn and Rantzausminde Lystbådehavn are four
-- ADJACENT res-7 cells in Svendborg Sund. They are kept — a quarter of the
-- busiest leisure cells in Denmark being one sound is itself the finding — but
-- their ring-1 neighbourhoods overlap, so a boat hopping from Troense to Vindeby
-- is `arrived_from_ring` for one and `left_to_ring` for the other and is present
-- in both cells' rings at once. THE FOUR CURVES MUST NOT BE ADDED TOGETHER; read
-- them as four views of one harbour, or pick one.
--
-- A res-7 cell is ~5 km across and may hold several marinas AND a commercial
-- harbour AND a ferry berth — the Svendborg cell (608531604905656319) holds five
-- marinas and the Ærø ferry terminal. `place` names ONE of them, the named
-- marina nearest the cell centre, so it is a landmark, not an inventory;
-- `n_marinas` is the count and is the column that says how coarse the label is.
-- 475 of the 2 833 marina rows have no name (sql/04_context.sql keeps them, a
-- place a boat sits is a place whether OSM named it or not); a cell whose
-- marinas are all unnamed is labelled 'unnamed marina cell'. Marinas are public
-- places and may be named — the privacy rule is about vessels.
--
-- `vessels_seen` is the number of DISTINCT vessels behind the bucket over the
-- whole season, all years pooled: uniqExactMerge over the OWN-CELL states of
-- the slot's own hour, i.e. |A_h| unioned over the season. It exists so the
-- k >= 5 export rule is CHECKABLE downstream — a bucket with vessels_seen < 5
-- must not be published, and without this column a reader of the means could
-- not tell. READ THE BOUND EXACTLY: it is the vessel set behind `present` and
-- `appeared`, both of which are drawn from A_h. `vanished` and `left_to_ring`
-- are drawn from A_{h−1}, the PREVIOUS hour's set, which this column does not
-- cover; it bounds them only through the neighbouring hour's row. In practice
-- nothing comes close — the minimum leisure vessels_seen over the whole file is
-- 12 — but a bucket that passed k >= 5 on this column has not thereby been
-- cleared for its departure half.
--
-- TWO DAY COLUMNS, AND ONLY ONE OF THEM IS THE DENOMINATOR.
--   season_days  every covered local day in that season, over the six loaded
--                years, pooled — 846 for 'May-Sep' and 1 116 for 'Oct-Apr'.
--                A CONSTANT per season, and the divisor of every mean_* below.
--   days_seen    the covered local days on which this fleet was actually inside
--                this cell's ring at this hour. Informative, never a divisor.
-- The archive is national: a covered day covers every cell, so a day on which no
-- vessel of the fleet came near the cell is a TRUE ZERO, not a missing sample,
-- and it belongs in the denominator. It cannot get there by itself — an empty
-- cell-hour writes no h3_hourly row, so such a day never reaches `ev` at all.
-- Dividing by days_seen instead would not merely raise a level, IT WOULD DESTROY
-- THE SHAPE, which is the only thing this chart is for: within one
-- (cell, fleet, season) curve days_seen runs 7 to 846 for Rantzausminde ferries
-- and 273 to 411 for Rantzausminde leisure in winter, so two neighbouring hours
-- would be divided by denominators up to 120x apart. An hour where one ferry
-- called on 7 days out of 846 would read as mean_appeared 0.14 instead of 0.001.
-- The busy curves hide it — Svendborg leisure May-Sep is 846 of 846 — which is
-- exactly why the two columns are both emitted: their ratio is the audit.
--
-- season_days also makes the coverage visible rather than hiding it: 2015
-- contributes 118 May-Sep days and 2025 contributes 153, and the pooled 846 is
-- the sum over the years the archive holds.
--
-- COVERAGE, REPAIRED FOR DST — the same repaired chain as sql/30 and sql/32,
-- and it differs on purpose from sql/11, sql/12 and sql/24. Those keep a local
-- day when uniqExact(toHour(local)) = 24, which the 23-hour spring-forward
-- Sunday fails by construction, dropping it in every year (2015-03-29,
-- 2018-03-25, 2021-03-28, 2024-03-31, 2025-03-30, 2026-03-29 — six local days,
-- measured). Here the test is that the day's number of DISTINCT UTC HOURS equals
-- dateDiff('hour', toStartOfDay(lt), toStartOfDay(lt) + INTERVAL 1 DAY), which
-- this machine's ClickHouse returns as 23 / 25 / 24 for spring-forward /
-- fall-back / ordinary days. It must count UTC hours: uniqExact(toHour(lt)) is
-- 24 on a fall-back day against an expected 25 and would drop the five autumn
-- Sundays. sql/11, sql/12 and sql/24 are NOT retrofitted — their numbers are
-- quoted verbatim in notes/ch01-findings.md — and the measured cost of running
-- two conventions is at most 0.0010 on sql/24's night shares, all in 'Oct-Apr'.
--
-- The Sep-2015 duplication window is excluded in `base`, before the coverage
-- test (sql/24's ordering rule), so its two edge days cannot survive as
-- part-days. This file counts distinct vessels, which duplication cannot move,
-- but the exclusion is kept so all three S7 files describe the same calendar.
--
-- 2022 AND 2023 ARE EXCLUDED IN SQL, NOT IN THE CALLER — the one place this
-- file departs from sql/30 and sql/32. Those two are 59 storm-window winter
-- days each (Jan/Feb 2022, Feb + Dec 2023), a sample and not a year, and every
-- chart and headline in notes/ch02-findings.md drops them. sql/30 and sql/32
-- emit a `year` column and notes/plot_ch02.py filters on it; THIS FILE POOLS
-- THE YEARS BY DESIGN and emits no `year`, so a caller cannot drop them
-- afterwards. Left in, all 116 of those days would sit in every Oct-Apr
-- numerator AND in season_days: 1 232 = 1 116 + 116, and every Oct-Apr number
-- in the file would be a six-year figure with a two-window sample stirred in.
-- May-Sep is untouched (the windows hold no May-Sep day), which is why the
-- Oct-Apr constant moves and 846 does not.
--
-- `SETTINGS join_use_nulls = 0` IS PINNED AT THE END OF THE QUERY, for the same
-- reason scripts/ch.sh pins the H3 argument order: the contract below — "a
-- missing hour is the empty set, n = 0" — is a DEFAULT, and a default that
-- changes under a caller does not fail, it returns a plausible wrong number.
-- Under `join_use_nulls = 1` an unmatched LEFT JOIN side is NULL, the
-- arithmetic in `ev` propagates the NULL, and sum() then skips the row instead
-- of adding a zero: measured, the ferry appearance total for the Svendborg cell
-- in July 2025 reads 501 instead of 502. A query-level SETTINGS wins over the
-- command line, so the file states what it means.
--
-- COST: `h3` is the first column of h3_hourly's ORDER BY, so restricting to the
-- ten cells plus their ring-1 neighbours (70 pairs, 59 distinct cells here — four
-- of the ten Svendborg Sund cells are neighbours of each other) does the
-- pruning, the sql/22 pattern. The one full-store pass is `covered`, which reads
-- `hour` alone.
WITH
base AS (
    SELECT hour,                                   -- UTC, kept for the coverage count
           toTimeZone(hour, 'Europe/Copenhagen') AS lt,
           h3, mobile, ship_group, vessels
    FROM h3_hourly
    WHERE NOT (hour >= toDateTime('2015-08-28 00:00:00', 'UTC')
           AND hour <  toDateTime('2015-10-01 00:00:00', 'UTC'))
      -- the storm-sample windows, dropped here because this file emits no
      -- `year` for a caller to drop them by. See the header.
      AND toYear(toTimeZone(hour, 'Europe/Copenhagen')) NOT IN (2022, 2023)
),
covered AS (
    SELECT toDate(lt) AS lday
    FROM base
    GROUP BY lday
    HAVING uniqExact(hour) = dateDiff('hour', toStartOfDay(min(lt)),
                                              toStartOfDay(min(lt)) + INTERVAL 1 DAY)
),
-- the denominator: how many covered local days each season has, at all, anywhere.
season_days AS (
    SELECT if(toMonth(lday) BETWEEN 5 AND 9, 'May-Sep', 'Oct-Apr') AS season,
           count() AS n_days
    FROM covered
    GROUP BY season
),
cells AS (
    SELECT h3
    FROM base
    WHERE mobile = 'Class B' AND ship_group = 'leisure'
      AND h3 IN (SELECT DISTINCT h3 FROM marina)
    GROUP BY h3
    ORDER BY uniqExactMerge(vessels) DESC
    LIMIT 10
),
-- (centre cell, one of its seven ring-1 members). The ten centres are close
-- enough that a member belongs to more than one centre, which is why this is a
-- join key and not a flat cell list.
ring AS (
    SELECT h3 AS cell, arrayJoin(h3kRing(h3, 1)) AS member FROM cells
),
label AS (
    SELECT h3,
           count() AS n_marinas,
           if(countIf(name != '') = 0, 'unnamed marina cell',
              argMinIf(name,
                       geoDistance(toFloat32(lon), toFloat32(lat),
                                   toFloat32(h3ToGeo(h3).2), toFloat32(h3ToGeo(h3).1)),
                       name != '')) AS place
    FROM marina
    WHERE h3 IN (SELECT h3 FROM cells)
    GROUP BY h3
),
-- one row per (centre cell, fleet, UTC hour): the cell's own membership state,
-- the ring's, and both sizes. own_* is the centre only; ring_* is all seven.
per AS (
    SELECT r.cell AS cell,
           if(b.mobile = 'Class B', 'leisure Class B', 'ferry Class A') AS fleet,
           b.hour AS hour,
           uniqExactMergeStateIf(b.vessels, b.h3 = r.cell) AS own_st,
           uniqExactMergeState(b.vessels)                  AS ring_st,
           uniqExactMergeIf(b.vessels, b.h3 = r.cell)      AS own_n,
           uniqExactMerge(b.vessels)                       AS ring_n
    FROM base AS b
    INNER JOIN ring AS r ON b.h3 = r.member
    WHERE b.h3 IN (SELECT member FROM ring)
      AND (   (b.mobile = 'Class B' AND b.ship_group = 'leisure')
           OR (b.mobile = 'Class A' AND b.ship_group = 'passenger'))
    GROUP BY cell, fleet, hour
),
-- the three unions, in one pass. Each tuple is (hour offset, which union, which
-- state: 0 = own, 1 = ring). Offset 1 puts an hour's state at the NEXT slot, so
-- a slot's merge sees itself and its predecessor.
--   u1 = |A_slot     ∪ A_{slot−1}|
--   u2 = |A_slot     ∪ Ring_{slot−1}|
--   u3 = |Ring_slot  ∪ A_{slot−1}|
-- The offset-1 rows also create the slot AFTER the last hour a cell is occupied,
-- which is the slot where an emptying harbour records its departures.
ustage AS (
    SELECT cell, fleet,
           hour + k.1 * 3600 AS slot,           -- DateTime + Int adds seconds
           k.2               AS kind,
           uniqExactMerge(if(k.3 = 1, ring_st, own_st)) AS n
    FROM per
    ARRAY JOIN [(0, 'u1', 0), (1, 'u1', 0),
                (0, 'u2', 0), (1, 'u2', 1),
                (0, 'u3', 1), (1, 'u3', 0)] AS k
    GROUP BY cell, fleet, slot, kind
),
grid AS (
    SELECT cell, fleet, slot,
           maxIf(n, kind = 'u1') AS un_aa,
           maxIf(n, kind = 'u2') AS un_ar,
           maxIf(n, kind = 'u3') AS un_ra
    FROM ustage
    GROUP BY cell, fleet, slot
),
-- LEFT JOIN, twice: a slot whose own hour or previous hour has no row keeps
-- n = 0 there, and every intersection collapses to 0, which is the correct
-- empty-set answer. An INNER JOIN here is the single most likely way to get a
-- wrong answer out of this file. The "n = 0" half of that sentence holds only
-- under join_use_nulls = 0, which the query pins for itself at the bottom.
ev AS (
    SELECT g.cell AS cell, g.fleet AS fleet, g.slot AS slot,
           toTimeZone(g.slot, 'Europe/Copenhagen') AS lt,
           if(toMonth(toTimeZone(g.slot, 'Europe/Copenhagen')) BETWEEN 5 AND 9,
              'May-Sep', 'Oct-Apr') AS season,
           n.own_n  AS n_now,   p.own_n  AS n_prev,
           n.ring_n AS ring_now, p.ring_n AS ring_prev,
           n_now  + n_prev    - g.un_aa AS i_own,        -- |A_h ∩ A_{h−1}|
           n_now  + ring_prev - g.un_ar AS i_ring_prev,  -- |A_h ∩ Ring_{h−1}|
           n_prev + ring_now  - g.un_ra AS i_ring_now,   -- |A_{h−1} ∩ Ring_h|
           n_now  - i_own               AS appeared,
           i_ring_prev - i_own          AS arrived_from_ring,
           n_prev - i_own               AS vanished,
           i_ring_now  - i_own          AS left_to_ring,
           n.own_st AS own_st
    FROM grid AS g
    LEFT JOIN per AS n ON n.cell = g.cell AND n.fleet = g.fleet AND n.hour = g.slot
    LEFT JOIN per AS p ON p.cell = g.cell AND p.fleet = g.fleet AND p.hour = g.slot - 3600
    WHERE toDate(toTimeZone(g.slot, 'Europe/Copenhagen')) IN (SELECT lday FROM covered)
)
SELECT
    e.cell                                                    AS h3,
    l.place                                                   AS place,
    l.n_marinas                                               AS n_marinas,
    round(h3ToGeo(e.cell).1, 4)                               AS lat,
    round(h3ToGeo(e.cell).2, 4)                               AS lon,
    e.fleet                                                   AS fleet,
    e.season                                                  AS season,
    toHour(e.lt)                                              AS lhour,
    max(sd.n_days)                                            AS season_days,
    uniqExact(toDate(e.lt))                                   AS days_seen,
    uniqExactMerge(e.own_st)                                  AS vessels_seen,
    round(sum(e.n_now)             / season_days, 2)          AS mean_present,
    round(sum(e.appeared)          / season_days, 2)          AS mean_appeared,
    round(sum(e.arrived_from_ring) / season_days, 2)          AS mean_arrived_from_ring,
    round(sum(e.vanished)          / season_days, 2)          AS mean_vanished,
    round(sum(e.left_to_ring)      / season_days, 2)          AS mean_left_to_ring
FROM ev AS e
INNER JOIN label AS l ON l.h3 = e.cell
INNER JOIN season_days AS sd ON sd.season = e.season
GROUP BY h3, place, n_marinas, lat, lon, fleet, season, lhour
ORDER BY h3, fleet, season DESC, lhour
SETTINGS join_use_nulls = 0;
