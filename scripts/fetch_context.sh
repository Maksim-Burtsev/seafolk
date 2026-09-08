#!/usr/bin/env bash
# S5 — download the context layers the chapters join against, into data/context/.
#   scripts/fetch_context.sh
# Three files, one request each, all skipped when already on disk:
#   marinas.tsv         OSM leisure=marina in the project bbox   (S6, S7)
#   ferry_routes.json   OSM route=ferry ways and relations, with geometry (S8)
#   ne_10m_land.geojson Natural Earth 10 m land polygons         → the `land`
#                       dictionary in sql/04_context.sql
# storms.csv and regattas.csv are hand-collected and committed; nothing here
# writes them.
#
# Every download lands on a temp name and is moved into place only after it has
# been checked, so a truncated file or an Overpass HTML error page served with
# HTTP 200 never counts as done. Re-running is free.
set -euo pipefail
cd "$(dirname "$0")/.."

DEST=data/context
BBOX="53,3,59,17"                      # lat_min,lon_min,lat_max,lon_max — Overpass order
OVERPASS=https://overpass-api.de/api/interpreter
# Natural Earth is pinned to a release tag, not master: the file is regenerated
# in place and a silent shape change would move the coastline under an already
# published chart. v5.1.2 is the newest tag that serves geojson/ne_10m_land.geojson
# (probed 2026-09-08; v5.1.1 and v5.0.0 also do).
NE_URL=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_land.geojson

# JSON is validated by parsing it, not by looking at it — with the same reader
# sql/04_context.sql uses, so "the fetch is good" means "the loader can read it".
# `clickhouse local` without --path touches no store and takes no lock.
json_len() {  # json_len <file> <key> -> number of elements under that key
  clickhouse local -q \
    "SELECT length(JSONExtractArrayRaw(json, '$2')) FROM file('$1', JSONAsString)"
}

# Overpass reports a hit timeout or a memory bail as HTTP 200 with a `remark`
# key and however many elements it managed — a partial answer that looks exactly
# like a complete one. Since a downloaded file is never re-fetched, accepting
# one freezes a silently short dataset into every chapter that reads it.
json_remark() {  # json_remark <file> -> the remark text, empty if there is none
  clickhouse local -q \
    "SELECT JSONExtractString(json, 'remark') FROM file('$1', JSONAsString)"
}

fetch() {  # fetch <name> <curl args…>; the caller checks $tmp and calls keep
  name="$1"; shift
  out="$DEST/$name"; tmp="$DEST/.$name.part"
  if [ -s "$out" ]; then echo "skip  $name"; return 1; fi
  echo "get   $name"
  rm -f "$tmp"
  # A failed download must stop the script, not fall through the `if` as if
  # the target had merely been skipped.
  curl -sf --retry 3 --retry-all-errors -o "$tmp" "$@" \
    || { echo "$name: download failed" >&2; rm -f "$tmp"; exit 1; }
}
keep() { mv "$tmp" "$out"; echo "ok    $name ($(du -h "$out" | cut -f1))"; }

mkdir -p "$DEST"

# 1. Marinas. TSV, not the ;-separated csv variant — Overpass rejects the
#    separator argument on this build. Header row: @type @id name @lat @lon.
if fetch marinas.tsv -G --data-urlencode \
     "data=[out:csv(::type,::id,name,::lat,::lon;true)][timeout:180];
            nwr[\"leisure\"=\"marina\"]($BBOX);out center;" \
     "$OVERPASS"; then
  head -n1 "$tmp" | grep -q '^@type' || { echo "marinas.tsv: no @type header — Overpass returned:" >&2
                                          head -c 300 "$tmp" >&2; echo >&2; exit 1; }
  # csv output has no `remark` field to check, so a truncated answer shows up
  # only as a short file. Zero data rows is the one length that is certainly
  # wrong; anything else is judged by scripts/test_context.sh's count floors.
  [ "$(wc -l < "$tmp")" -gt 1 ] || { echo "marinas.tsv: header only, no data rows" >&2; exit 1; }
  keep
fi

# 2. Ferry routes, with geometry (that is what `out geom` adds).
#    `nwr`, not `relation`: in Danish waters most island ferries are a single
#    tagged WAY, not a route relation. relation["route"="ferry"] returns 326 rows
#    in this bbox and not one of them is an Ærø route — Svendborg–Ærøskøbing is
#    way 33847154, Søby–Fynshav is way 171896489, both tagged route=ferry
#    directly (checked 2026-09-08). S8's validation route only exists on the way.
#    sql/04_context.sql normalises both shapes into one geom column.
if fetch ferry_routes.json -G --data-urlencode \
     "data=[out:json][timeout:180];
            nwr[\"route\"=\"ferry\"]($BBOX);out geom;" \
     "$OVERPASS"; then
  n=$(json_len "$tmp" elements) || { echo "ferry_routes.json: not JSON — Overpass returned:" >&2
                                     head -c 300 "$tmp" >&2; echo >&2; exit 1; }
  [ "$n" -gt 0 ] || { echo "ferry_routes.json: zero elements" >&2; exit 1; }
  r=$(json_remark "$tmp")
  [ -z "$r" ] || { echo "ferry_routes.json: Overpass returned a partial answer: $r" >&2; exit 1; }
  keep
fi

# 3. Natural Earth land polygons.
if fetch ne_10m_land.geojson -L "$NE_URL"; then
  n=$(json_len "$tmp" features) || { echo "ne_10m_land.geojson: not JSON" >&2; exit 1; }
  [ "$n" -gt 0 ] || { echo "ne_10m_land.geojson: zero features" >&2; exit 1; }
  keep
fi

echo
echo "marina rows      $(( $(wc -l < "$DEST/marinas.tsv") - 1 ))"
echo "ferry elements   $(json_len "$DEST/ferry_routes.json" elements)"
echo "land features    $(json_len "$DEST/ne_10m_land.geojson" features)"
