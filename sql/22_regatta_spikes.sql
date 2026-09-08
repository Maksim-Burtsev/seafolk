-- S6 chart 3 — does a regatta show up in the fleet count?
-- Run: scripts/ch.sh sql/22_regatta_spikes.sql
-- Columns: name, year, place, race_day, dow, race_vessels,
--          base_days, base_mean, base_min, base_max, ratio, event_mean_ratio
--
-- For every row of `regatta` (sql/04_context.sql) the REGION is the res-7 cell
-- of the start harbour plus its two rings — h3kRing(geoToH3(lat, lon, 7), 2),
-- 19 cells, roughly 20 km across. That is the start area, not the course: a
-- round-Fyn or round-Sjælland race leaves it within hours, so what this
-- measures is the gathering, not the racing.
--
-- `race_vessels` is the number of DISTINCT Class B leisure vessels seen
-- anywhere in the region on that UTC day — uniqExactMerge over the h3_hourly
-- states of all 19 cells and all 24 hours, so a boat in three cells counts once.
--
-- The baseline is the SAME WEEKDAY at -14, -7, +7 and +14 days, which controls
-- for the weekend effect that sql/21_weekend_effect.sql measures (weekends run
-- 1.13-1.88x a weekday) while staying inside the same part of the season.
-- A baseline day that falls INSIDE the event's own [start_date, end_date] is
-- dropped. For an event longer than 7 days the ±7 offsets land on the event
-- itself and the race would be measured against its own opening weekend: Kieler
-- Woche runs 9 days, so its days 1–2 and days 8–9 baselined each other — the
-- 2025-06-28 row had base_max = 216, which is opening day. Those four rows per
-- Kieler year now carry base_days 3 instead of 4, stated in the column rather
-- than hidden. No other event moves: every Danish regatta here is 1–5 days
-- long, so none of its ±7 / ±14 offsets can reach its own range.
-- `base_days` says how many of the four actually exist in the archive and lie
-- outside the event; a baseline day that the archive covers but where the region
-- held no leisure vessel at all contributes a genuine 0, because an empty
-- cell-hour writes no h3_hourly row. Race days the archive does not cover are
-- dropped entirely — that removes Silverrudder 2026 (2026-09-18, after the archive's last day
-- 2026-08-26); every other regatta row lands inside a loaded year.
--
-- `ratio` = race_vessels / base_mean. `event_mean_ratio` is the mean of `ratio`
-- over that event-year's race days, repeated on each of its rows, so the file
-- stays one tidy result set instead of two.
--
-- COST: h3_hourly is scanned ONCE. The region cells of all 30 regatta rows are
-- 5 distinct start harbours x 19 cells, and `h3` is the first column of the
-- table's ORDER BY, so the cell set does the pruning; the day set prunes the
-- partitions on top of it.
--
--
-- SHORT UTC DAYS ARE COUNTED WHOLE. Two of the 2 122 loaded days hold fewer than
-- 24 hours of h3_hourly — 2015-06-24 (21) and 2018-05-17 (20), receiver gaps in
-- the source — and this file counts them as ordinary days. No coverage filter is
-- applied on purpose: what is counted here is DISTINCT VESSELS (or vessel-days),
-- which a missing hour barely moves — a boat out sailing reports in the other
-- 20-odd hours too — and dropping 2 days in 2 122 would cost more in a special
-- case than it buys. sql/11, sql/12 and sql/24 do drop such days, because they
-- count messages by hour of the day, where a missing hour is a hole in the shape.
-- The Sep-2015 duplication (docs/STATUS.md § S4-tails) does not reach this
-- query: it inflates `msgs`, and `vessels` is a uniqExact state, which is
-- structurally immune to a duplicated message. Silverrudder 2015 (2015-09-18)
-- and its baselines sit inside that window and are still trustworthy here.
--
-- Days are UTC, as the archive stores them; a race starting in the morning is
-- nowhere near the 01:00/02:00 local day boundary, so no local-time cut is
-- needed (contrast sql/21_weekend_effect.sql, which does care).
WITH
reg AS (
    SELECT name, year, place, start_date, end_date,
           h3kRing(geoToH3(lat, lon, 7), 2) AS cells
    FROM regatta
),
-- one row per (event-year, cell). Cells repeat across years — same harbour —
-- which is why the region is keyed by the regatta row and not by the cell.
cellmap AS (
    SELECT name, year, arrayJoin(cells) AS h3 FROM reg
),
-- one row per (event-year, race day, offset). offset 0 is the race day itself.
pairs AS (
    SELECT name, year, place, race_day,
           off,
           race_day + off AS d,
           -- offset 0 is in_event by definition; for an event longer than a week
           -- so are the -7 / +7 offsets of its first and last days, and those are
           -- the ones the baseline below drops.
           d BETWEEN start_date AND end_date AS in_event
    FROM (
        SELECT name, year, place, start_date, end_date,
               start_date + arrayJoin(range(toUInt32(end_date - start_date) + 1)) AS race_day
        FROM reg
    )
    ARRAY JOIN [-14, -7, 0, 7, 14] AS off
),
-- the days the archive actually holds, read off vessel_day's own key
archive_days AS (
    SELECT DISTINCT day FROM vessel_day
),
-- the single pass over h3_hourly
daily AS (
    SELECT c.name AS name, c.year AS year,
           toDate(h.hour) AS d,
           uniqExactMerge(h.vessels) AS vessels
    FROM h3_hourly AS h
    INNER JOIN cellmap AS c ON h.h3 = c.h3
    WHERE h.mobile = 'Class B' AND h.ship_group = 'leisure'
      AND h.h3 IN (SELECT h3 FROM cellmap)
      AND toDate(h.hour) IN (SELECT d FROM pairs)
    GROUP BY name, year, d
),
joined AS (
    SELECT p.name AS name, p.year AS year, p.place AS place,
           p.race_day AS race_day, p.off AS off,
           p.d IN (SELECT day FROM archive_days) AS in_archive,
           -- a day that counts towards the baseline: a real offset, covered by
           -- the archive, and outside the event's own range
           p.off != 0 AND in_archive AND NOT p.in_event AS base,
           x.vessels AS vessels
    FROM pairs AS p
    LEFT JOIN daily AS x ON p.name = x.name AND p.year = x.year AND p.d = x.d
)
SELECT
    name,
    year,
    place,
    race_day,
    toDayOfWeek(race_day)                             AS dow,
    anyIf(vessels, off = 0)                           AS race_vessels,
    countIf(base)                                     AS base_days,
    round(avgIf(vessels, base), 1)                    AS base_mean,
    minIf(vessels, base)                              AS base_min,
    maxIf(vessels, base)                              AS base_max,
    round(race_vessels / nullIf(base_mean, 0), 3)     AS ratio,
    round(avg(ratio) OVER (PARTITION BY name, year), 3) AS event_mean_ratio
FROM joined
GROUP BY name, year, place, race_day
HAVING anyIf(in_archive, off = 0)
ORDER BY name, year, race_day;
