#!/usr/bin/env bash
# The one runnable check for S5's context layers. Runs sql/04_context.sql
# itself — the real statement, not a copy — against a THROWAWAY store in
# data/ch_test, so it never touches, locks or writes data/ch. Loading the
# production store stays a separate step:  scripts/ch.sh sql/04_context.sql
#
# Everything it asserts comes from data/context/, which is the same on both
# stores, so the throwaway costs nothing in coverage: no assert here reads
# h3_hourly or any table the archive loader builds.
#
# Prints PASS/FAIL per assert and exits non-zero on any FAIL.
#
# The point of this file is assert group 3. `land` is a point-in-polygon
# dictionary whose key is (LON, LAT) while every H3 call in this project is
# (LAT, LON); swapping them does not error, it mirrors Denmark into the Arabian
# Sea and answers "not land" for every harbour. That is the bug that cost the
# project a 1.2 TB re-download (docs/DECISIONS.md, 2026-09-03), so the order is
# pinned here from both ends, with hard-coded expected values — and group 6
# range-checks every coordinate the file stores, because the same swap inside a
# JSONExtract tuple type would otherwise be silent.
set -euo pipefail
cd "$(dirname "$0")/.."

export CH_PATH=data/ch_test
cleanup() { rm -rf data/ch_test; }
trap cleanup EXIT
cleanup

fail=0
assert() {  # assert <name> <expected> <actual>
  if [ "$2" = "$3" ]; then printf 'PASS  %s\n' "$1"
  else printf 'FAIL  %s — expected %s, got %s\n' "$1" "$2" "$3"; fail=1; fi
}
q() { scripts/ch.sh -q "$1"; }

scripts/ch.sh sql/04_context.sql

# 1. The tables are populated at all. Thresholds, not exact counts: OSM and the
#    hand-collected CSVs both grow. A number far below these means the fetch
#    returned an error page or a partial Overpass reply, or a CSV lost rows.
read -r n_marina n_ferry n_storm n_regatta <<< "$(q "
  SELECT (SELECT count() FROM marina), (SELECT count() FROM ferry_route),
         (SELECT count() FROM storm),  (SELECT count() FROM regatta)
  FORMAT TSV" | tr '\t' ' ')"
echo "counts: marina $n_marina  ferry_route $n_ferry  storm $n_storm  regatta $n_regatta"
echo
assert "marina >= 2000"      1 "$(( n_marina  >= 2000 ))"
assert "ferry_route >= 200"  1 "$(( n_ferry   >= 200 ))"
assert "storm >= 10"         1 "$(( n_storm   >= 10 ))"
assert "regatta >= 5"        1 "$(( n_regatta >= 5 ))"

# 2. marina.h3 against an EXTERNAL oracle — the h3 reference library, never a
#    round trip through ClickHouse (a round trip is symmetric under the swap and
#    passes on mirrored data; that is exactly how S2 certified the S4 bug).
#    OSM node 431083103 is Lystbådehavn Troense, 55.0345377 N 10.6453392 E.
#    Expected value computed once with:
#      uv run --with h3 python -c \
#        "import h3; print(int(h3.latlng_to_cell(55.0345377, 10.6453392, 7), 16))"
#    -> 608531604955987967  (871f04543ffffff)
assert "marina.h3 is the h3 reference library's cell for Troense" \
  608531604955987967 "$(q "SELECT h3 FROM marina WHERE osm_id = 431083103")"

# 3. The land dictionary, both directions, in one query.
#    The land point is Viborg, deep in Jutland, NOT Copenhagen: Natural Earth
#    10 m generalises the Copenhagen shoreline about a kilometre inland, so
#    Rådhuspladsen (12.5683, 55.6761) is *outside* the land polygons in this
#    dataset (verified independently with shapely against the same GeoJSON —
#    it agrees with ClickHouse on all ten points tried). Asserting the swapped
#    Rådhuspladsen call proves nothing for the same reason: it is 0 whether the
#    dictionary is right or mirrored. Viborg is the point that bites, ~50 km
#    from any coast in both the true and the mirrored reading.
read -r d_viborg d_kattegat d_swap_viborg d_cell <<< "$(q "
  SELECT dictHas('land', ( 9.4020, 56.4531)) AS viborg,      -- (lon, lat), Jutland
         dictHas('land', (11.5000, 56.5000)) AS kattegat,    -- open water
         dictHas('land', (56.4531,  9.4020)) AS swap_viborg, -- mirrored: Arabian Sea
         dictHas('land', (h3ToGeo(608531686258376703).2,
                          h3ToGeo(608531686258376703).1)) AS cph_cell
  FORMAT TSV" | tr '\t' ' ')"
assert "land: Viborg (lon, lat) is land"                1 "$d_viborg"
assert "land: the open Kattegat is not land"            0 "$d_kattegat"
assert "land: Viborg read (lat, lon) is the Arabian Sea — not land" 0 "$d_swap_viborg"
# Flip the .1/.2 accessors below and this reads (55.68, 12.57) — Arabian Sea, 0.
assert "land: the documented h3ToGeo idiom finds Copenhagen's res-7 cell" 1 "$d_cell"

# 4. The route S8 validates chapter 03 against, and the promise that every row
#    holds a line to draw. Svendborg–Ærøskøbing is an OSM *way* (33847154), not
#    a route relation — see the comment in scripts/fetch_context.sh.
assert "ferry_route has the Svendborg–Ærøskøbing route" 1 \
  "$(q "SELECT count() > 0 FROM ferry_route
        WHERE positionUTF8(concat(name, ' ', from, ' ', to), 'Ærøskøbing') > 0")"
assert "every ferry_route row has geometry" 0 \
  "$(q "SELECT countIf(empty(geom)) FROM ferry_route")"

# 5. The two hand-collected, COMMITTED csv files. They have no machine source,
#    so nothing else will ever catch a typo in them.
#    The header asserts are not decoration: sql/04_context.sql reads both files
#    by column NAME, and a column simply missing from the header is not an
#    "unknown field" — it is absent, no format setting rejects it, and the
#    column silently loads as 1970-01-01 or 0. Verbatim headers are the only
#    thing that catches that.
assert "storms.csv header is unchanged" \
  "name,start_utc,end_utc,source_url,note" \
  "$(q "SELECT line FROM file('data/context/storms.csv', LineAsString) LIMIT 1")"
assert "regattas.csv header is unchanged" \
  "name,year,start_date,end_date,place,lat,lon,source_url" \
  "$(q "SELECT line FROM file('data/context/regattas.csv', LineAsString) LIMIT 1")"
# Same reason for the two S8 files. ferry_lines.csv is read by
# sql/40_ferry_trips.sql and decides which OSM object belongs to which ferry
# line; ferry_timetable.csv is the chapter's only external anchor. A column
# dropped from either header is not "unknown" to any input setting — `file()`
# simply returns '' for it — so a renamed `line` column would silently unmap
# every route and a renamed `osm_id` would silently map none.
assert "ferry_lines.csv header is unchanged" \
  "line,kind,island,osm_type,osm_id,note" \
  "$(q "SELECT line FROM file('data/context/ferry_lines.csv', LineAsString) LIMIT 1")"
assert "ferry_timetable.csv header is unchanged" \
  "route,operator,port_a,port_b,summer_weekday_departures_per_direction,crossing_minutes,source_url,read_on,note" \
  "$(q "SELECT line FROM file('data/context/ferry_timetable.csv', LineAsString) LIMIT 1")"
# And for the S9 file. anchorages.csv is read by sql/51_anchorage_fill.sql,
# which — unlike sql/04's two hand files — CANNOT use
# input_format_skip_unknown_fields = 0: it projects `source_url` away and the
# reader then refuses to open the file at all. So this assert is the ONLY
# thing standing between a renamed column and a silent ''. A renamed `note`
# would put every excluded cell (Lindoe yard, the oil fields, Aarhus harbour)
# back into the storm profile as an "anchorage"; a renamed `h3` would unlabel
# every cell, which sql/51's own throwIf would then catch.
assert "anchorages.csv header is unchanged" \
  "h3,name,source_url,note" \
  "$(q "SELECT line FROM file('data/context/anchorages.csv', LineAsString) LIMIT 1")"
# ...and the rest of that file's integrity. anchorages.csv is a hand file with
# no machine source; sql/51 joins it by `h3` and EXCLUDES by an exact `note`
# string, so each of these is a silently wrong chart, never an error:
#   * a duplicate h3 counts the same vessels under two anchorage names
#     (measured: block 3 goes 38 534 -> 41 150 rows);
#   * 'Not an anchorage' or a trailing space is not 'not an anchorage', and
#     every excluded cell — the oil fields, the Lindoe yard, Aarhus harbour —
#     silently comes back (measured: 38 534 -> 106 308 rows);
#   * an h3 that is not a valid res-7 cell labels nothing at all;
#   * the whole bar for a row is "a source, not an opinion", which is a URL.
# sql/51's block 2 throws on the first two as well (and on an h3 the rule never
# surfaced, which needs the archive store and so cannot be checked here).
read -r a_dup a_note a_url a_name a_h3 <<< "$(q "
  WITH anch AS (
      SELECT * FROM file('data/context/anchorages.csv', CSVWithNames,
          'h3 UInt64, name String, source_url String, note String')
      SETTINGS input_format_skip_unknown_fields = 1,
               input_format_defaults_for_omitted_fields = 0)
  SELECT count() - uniqExact(h3),
         countIf(note NOT IN ('', 'not an anchorage')),
         countIf(NOT startsWith(source_url, 'http')),
         countIf(name = ''),
         countIf(NOT h3IsValid(h3) OR h3GetResolution(h3) != 7)
  FROM anch
  FORMAT TSV" | tr '\t' ' ')"
assert "anchorages.csv: no duplicate h3"                    0 "$a_dup"
assert "anchorages.csv: every note is '' or 'not an anchorage'" 0 "$a_note"
assert "anchorages.csv: every source_url is a URL"          0 "$a_url"
assert "anchorages.csv: every row has a name"               0 "$a_name"
assert "anchorages.csv: every h3 is a valid res-7 cell"     0 "$a_h3"

read -r u_storm u_regatta o_storm o_regatta dup early bad_year <<< "$(q "
  SELECT (SELECT countIf(NOT startsWith(source_url, 'http')) FROM storm),
         (SELECT countIf(NOT startsWith(source_url, 'http')) FROM regatta),
         (SELECT countIf(start_utc  > end_utc)  FROM storm),
         (SELECT countIf(start_date > end_date) FROM regatta),
         (SELECT count() - uniqExact((name, year)) FROM regatta),
         -- A date that failed to parse lands on the epoch, and the archive
         -- starts in 2006 — nothing in either file may predate 2013.
         (SELECT countIf(start_utc < '2013-01-01 00:00:00') FROM storm),
         -- year is redundant with start_date on purpose: it is the check digit.
         (SELECT countIf(year != toYear(start_date)) FROM regatta)
  FORMAT TSV" | tr '\t' ' ')"
assert "storms.csv: every source_url is a URL"          0 "$u_storm"
assert "regattas.csv: every source_url is a URL"        0 "$u_regatta"
assert "storms.csv: no storm ends before it starts"     0 "$o_storm"
assert "regattas.csv: no regatta ends before it starts" 0 "$o_regatta"
assert "regattas.csv: no duplicate (name, year)"        0 "$dup"
assert "storms.csv: no start_utc before 2013 (an unparsed date lands on 1970)" \
  0 "$early"
assert "regattas.csv: year matches toYear(start_date) on every row" 0 "$bad_year"

# 6. Every coordinate this file stores, against hard-coded bounds. Without
#    these, swapping the two names in `Tuple(lon Float64, lat Float64)` stores
#    the whole ferry network mirrored and nothing fails; and a mirrored
#    marina.h3 on all 2 833 rows would fail only the single Troense oracle.
#    The ferry box is loose on purpose — Smyril Line reaches Iceland
#    (lon -14.0) and Gotland is at lon 25.2 — but a swap puts latitudes in
#    -14…25, far outside 50…70, so it still bites.
#    The marina box is the Danish bbox with the same 0.1° slack
#    scripts/test_load.sh gives h3_hourly: an H3 res-7 cell is ~5 km across, so
#    the CENTRE of the cell holding a marina at 53.0001 N sits below 53.
read -r geom_out h3_out reg_out <<< "$(q "
  SELECT (SELECT countIf(NOT (arrayMin(arrayMap(p -> p.2, arrayFlatten(geom))) >= 50
                          AND arrayMax(arrayMap(p -> p.2, arrayFlatten(geom))) <= 70
                          AND arrayMin(arrayMap(p -> p.1, arrayFlatten(geom))) >= -20
                          AND arrayMax(arrayMap(p -> p.1, arrayFlatten(geom))) <=  30))
          FROM ferry_route),
         (SELECT countIf(NOT (h3ToGeo(h3).1 BETWEEN 52.9 AND 59.1
                          AND h3ToGeo(h3).2 BETWEEN  2.9 AND 17.1)) FROM marina),
         (SELECT countIf(NOT (lat BETWEEN 53 AND 59 AND lon BETWEEN 3 AND 17))
          FROM regatta)
  FORMAT TSV" | tr '\t' ' ')"
assert "ferry_route: every stored point is (lon, lat) in the North Atlantic box" \
  0 "$geom_out"
assert "marina: every h3 cell centre maps back into the Danish bbox" 0 "$h3_out"
assert "regattas.csv: every place is inside the Danish bbox" 0 "$reg_out"

# 7. Idempotence. sql/04_context.sql is re-run before every chapter that needs
#    a refreshed layer, so a second run must rebuild the tables, not append to
#    them, and must not leave the old ones behind. metadata_dropped is the
#    observable for the second half: CREATE OR REPLACE parks the old table there
#    and `clickhouse local` exits before the deferred drop ever runs.
# metadata_dropped only exists once something has been parked there, and this
# script runs under `set -o pipefail`, so a bare `ls` on the missing directory
# would take the whole script down.
dropped_tables() { { ls data/ch_test/metadata_dropped 2>/dev/null || true; } | wc -l | tr -d ' '; }
dropped_before=$(dropped_tables)
store_before=$(du -sk data/ch_test/store | cut -f1)
scripts/ch.sh sql/04_context.sql
read -r r_marina r_ferry r_storm r_regatta <<< "$(q "
  SELECT (SELECT count() FROM marina), (SELECT count() FROM ferry_route),
         (SELECT count() FROM storm),  (SELECT count() FROM regatta)
  FORMAT TSV" | tr '\t' ' ')"
assert "re-running sql/04_context.sql leaves the four counts unchanged" \
  "$n_marina $n_ferry $n_storm $n_regatta" "$r_marina $r_ferry $r_storm $r_regatta"
assert "…and orphans no dropped table" "$dropped_before" "$(dropped_tables)"
assert "…and does not grow the store" \
  "$store_before" "$(du -sk data/ch_test/store | cut -f1)"

echo
[ "$fail" = 0 ] && echo "ALL PASS" || echo "FAILURES ABOVE"
exit "$fail"
