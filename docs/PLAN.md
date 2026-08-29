# Seafolk — session plan

> **For Claude Code sessions:** one session = one section below. Read `CLAUDE.md`
> and `docs/STATUS.md` first. Each section has a **Goal**, the **Files** it owns,
> **Validate** commands whose real output goes into `docs/STATUS.md`, a **You
> verify** list for the human, and a **Gate** that must hold before the next
> session starts. Check boxes as you go (`- [x]`).

**Goal:** Turn the open Danish AIS archive into four reproducible stories about the
human side of the sea, an open aggregated dataset, and a static explorer — within
70 GB of local disk and zero running cost.

**Architecture:** Stream each archive zip through `clickhouse local` into hourly
H3 aggregates, delete the raw file, keep only aggregates and a small public-vessel
track table. Everything downstream (analysis, dataset export, essay charts,
explorer tiles) reads the aggregates. Privacy invariant (k ≥ 5) is enforced in the
export, with a test.

**Tech stack:** ClickHouse (`clickhouse local --path data/ch`), Bash, Python via
`uv` (validation plots only), D3 + Scrollama (essay), MapLibre + deck.gl + PMTiles
(explorer), GitHub Pages, Hugging Face Datasets.

**Spec:** `README.md` (what), `docs/DATA.md` (sources), `docs/DECISIONS.md` (why).

## Global constraints

- Private vessels: aggregates only, k ≥ 5 per published cell (see CLAUDE.md).
- Disk: 70 GB working budget, 100 GB hard cap. Raw files deleted after load.
- H3 resolution 7, 1-hour bins, timestamps normalised to UTC once S1 settles the
  archive's timezone.
- Repo language English. Essay in RU and EN.
- No new dependency without a `docs/DECISIONS.md` line.
- Every chart in a published artefact is reproducible by a file in `sql/` or
  `notes/`.

## Phases at a glance

| Phase | Sessions | Ends with |
|-------|----------|-----------|
| 0 · Prove the story | S1–S3 | Three real charts from a few days and two full months; Class B confirmed |
| 1 · Fill the lake | S4–S5 | 2024 → today daily + reference years aggregated; context layers loaded |
| 2 · Analyse | S6–S10 | One notebook of findings per chapter + the honesty layer |
| 3 · Publish data | S11 | Parquet on GitHub Releases + Hugging Face, data card, privacy test |
| 4 · Tell it | S12–S14 | Essay (RU/EN), explorer, posters |
| 5 · Launch | S15 | HN / Reddit / Habr / outreach mails / ClickHouse example-dataset PR |

---

## S0 — Bootstrap *(done in the planning session)*

Repo skeleton, `CLAUDE.md`, `docs/*`, `scripts/fetch.sh`, `.gitignore`. Minimal
working set requested: `2025-07-12` (Sat), `2025-07-16` (Wed), `2025-01-15`
(winter Wed), `2025-06-14` (Sjælland Rundt Saturday).

- [x] Files above exist.
- [ ] `scripts/fetch.sh 2025-07-12 2025-07-16 2025-01-15 2025-06-14` completed
      (`ls data/raw/*.ok` shows four files).

---

## S1 — First look: does the story exist in the files?

**Goal:** Open one daily file without loading anything permanently and answer five
questions with numbers: Is Class B present? What share of active vessels is Class B
on a July Saturday vs a January Wednesday? What are the `Ship type` values and
their counts? Is the timestamp UTC or local? Are coordinates decimal-point?

**Files:**
- Create: `sql/00_peek.sql` — `SELECT` queries over `file('data/raw/…')` via
  `clickhouse local` with the zip streamed in (`unzip -p … | clickhouse local
  --query "… FROM table …" --input-format CSVWithNames`).
- Create: `scripts/ch.sh` — wrapper: `clickhouse local --path data/ch
  --multiquery < "$1"` (and `-q` passthrough). Make it executable.
- Create: `notes/s1-first-look.md` — the numbers, verbatim query output.

**Do:**
- [ ] Inspect the zip: `unzip -l data/raw/aisdk-2025-07-12.zip` (how many CSV
      entries, sizes).
- [ ] Stream the CSV into `clickhouse local` and run: row count; distinct MMSI by
      `Type of mobile`; distinct MMSI by `Ship type` for Class B only; count of
      rows with `Latitude`/`Longitude` outside Danish waters or at 91/181
      (sentinel); parse check of `Timestamp` with `parseDateTimeBestEffort`.
- [ ] Timezone test: take the Rødby–Puttgarden or Helsingør–Helsingborg ferries
      (`Ship type = 'Passenger'`, names containing e.g. `TYCHO BRAHE`, `AURORA`,
      `HAMLET`), list the first departure hour of the day in the file's clock,
      compare with the published timetable (first Helsingør departure ≈ 05:xx
      local). Decide UTC vs Europe/Copenhagen and record it in
      `docs/DECISIONS.md`.
- [ ] Repeat the Class B share query on `aisdk-2025-01-15.zip`.

**Validate:**
```bash
scripts/ch.sh sql/00_peek.sql        # prints the five answers as small tables
```
Expected: Class B distinct MMSI on 2025-07-12 is in the thousands; `Ship type`
contains `Sailing` and `Pleasure`; winter Class B share is clearly lower than
summer.

**You verify:** open `notes/s1-first-look.md`; the Class B share numbers are
there with the exact queries; the timezone decision is written down with the
ferry evidence.

**Gate A:** Class B exists in the files and `Sailing`/`Pleasure` are populated. If
not, stop: chapter 01 is dead, re-plan around chapters 02–04.

**Commit:** `feat(s1): first look — class B share, ship types, timezone evidence`

---

## S2 — The loader: one zip in, aggregates out, raw file gone

**Goal:** A single command that takes an archive file, streams it through
ClickHouse, appends to persistent aggregate tables, and deletes the zip. Designed
once, because raw data is not kept.

**Files:**
- Create: `sql/01_schema.sql` — DDL, idempotent (`CREATE TABLE IF NOT EXISTS`):
  - `ais_raw_stage` (Memory or MergeTree, truncated per file): typed columns for
    the 26 fields; `ts DateTime('UTC')`, `mmsi UInt32`, `mobile LowCardinality
    (String)`, `lat Float64`, `lon Float64`, `sog Float32`, `cog Float32`,
    `nav_status LowCardinality(String)`, `ship_type LowCardinality(String)`,
    `name String`, `length UInt16`, `width UInt16`, `draught Float32`,
    `imo UInt32`, `destination String`.
  - `h3_hourly` (AggregatingMergeTree, ORDER BY (h3, hour, mobile, ship_group)):
    `h3 UInt64` (res 7), `hour DateTime('UTC')`, `mobile`, `ship_group
    LowCardinality(String)` (mapping: Sailing/Pleasure → `leisure`, Passenger →
    `passenger`, Cargo/Tanker → `cargo`, Fishing → `fishing`, else `other`),
    `msgs SimpleAggregateFunction(sum, UInt64)`, `vessels
    AggregateFunction(uniqExact, UInt32)`, `moving_msgs SimpleAggregateFunction
    (sum, UInt64)` (SOG > 0.5 kn), `sog_sum SimpleAggregateFunction(sum, Float64)`.
  - `vessel_day` (ReplacingMergeTree, ORDER BY (day, mmsi)): `day Date`, `mmsi`,
    `mobile`, `ship_group`, `ship_type`, `first_ts`, `last_ts`, `msgs UInt32`,
    `moving_msgs UInt32`, `dist_nm Float32` (sum of `geoDistance` between
    consecutive positions / 1852), `home_h3 UInt64` (H3 of the first position
    of the day). **Internal only — contains MMSI.**
  - `public_track` (MergeTree, ORDER BY (mmsi, ts)): 1-minute downsampled
    positions for `ship_group IN ('passenger')` only. Used by chapter 03.
  - `load_log` (MergeTree): `file String`, `rows UInt64`, `loaded_at DateTime`,
    `seconds Float32`.
- Create: `sql/02_aggregate.sql` — `INSERT … SELECT` from `ais_raw_stage` into
  the three tables, using `geoToH3(lon, lat, 7)`, `toStartOfHour(ts)`,
  `uniqExactState(mmsi)`, and a `multiIf` for `ship_group`. Filters: drop
  sentinel coordinates (lat > 90, lon > 180), drop `mobile` not in
  (`Class A`, `Class B`).
- Create: `scripts/load.sh <zip>` — for each CSV entry in the zip: `unzip -p
  "$zip" "$entry" | clickhouse local --path data/ch --query "INSERT INTO
  ais_raw_stage FORMAT CSVWithNames" --date_time_input_format best_effort`;
  then run `sql/02_aggregate.sql`; write `load_log`; `TRUNCATE ais_raw_stage`;
  `rm "$zip" "$zip.ok"`. Exit non-zero and keep the zip if any step fails.
- Create: `scripts/test_load.sh` — the one runnable check: loads a 50 000-row
  sample extracted from a zip into a throwaway `--path data/ch_test`, asserts
  `sum(msgs)` in `h3_hourly` equals the staged row count after filters, asserts
  `vessels` merged over a day equals `uniqExact(mmsi)` from the stage, asserts
  no Class B row exists in `public_track`. Prints PASS/FAIL.

**Interfaces:** later sessions rely on table names and columns exactly as above.

**Do:**
- [ ] Write `sql/01_schema.sql`; run it; `SHOW TABLES` lists the five tables.
- [ ] Write `scripts/test_load.sh` first; run it; it fails (no aggregate yet).
- [ ] Write `sql/02_aggregate.sql` and `scripts/load.sh`; run the test; PASS.
- [ ] Load `aisdk-2025-07-16.zip` for real; note wall time and rows/s in
      `docs/STATUS.md`.

**Validate:**
```bash
scripts/test_load.sh                                  # PASS
scripts/load.sh data/raw/aisdk-2025-07-16.zip         # ends with "loaded … rows in … s", zip removed
scripts/ch.sh -q "SELECT count(), uniqExactMerge(vessels) FROM h3_hourly"
du -sh data/ch                                        # tens of MB for one day
```

**You verify:** the zip is gone, `data/ch` is small, `load_log` has one row, the
test prints PASS.

**Gate B1:** loader idempotent and tested; throughput ≥ 300 k rows/s (otherwise
profile before bulk).

**Commit:** `feat(s2): streaming loader into hourly H3 aggregates`

---

## S3 — Phase-0 charts: two months, three shapes

**Goal:** Download and load July 2025 and January 2025 in full (≈ 62 daily files,
≈ 45 GB traffic, nothing kept), plus June 2025 if time allows (Sjælland Rundt,
Kiel Week). Produce three quick charts and decide whether the story holds.

**Files:**
- Create: `scripts/run_queue.sh <dates-file>` — reads dates one per line, runs
  `fetch.sh` then `load.sh` for each, appends to `data/queue.log`, skips dates
  already in `load_log`, stops on the first failure. Safe to re-run.
- Create: `queues/phase0.txt` — all days of 2025-01 and 2025-07 (and 2025-06).
- Create: `sql/10_season_daily.sql` — daily distinct leisure vessels (from
  `vessel_day`), 7-day rolling mean.
- Create: `sql/11_week_profile.sql` — leisure `moving_msgs` share by weekday.
- Create: `sql/12_day_profile.sql` — hourly share of moving vessels by
  `ship_group` for a summer weekday and a summer Saturday.
- Create: `notes/s3-phase0.md` with three PNGs under `notes/img/` (matplotlib
  via `uv run`, `notes/plot.py`; add `uv` project in `notes/pyproject.toml` —
  matplotlib + clickhouse-connect are the only deps, record in DECISIONS).

**Do:**
- [ ] Write and start `scripts/run_queue.sh queues/phase0.txt` (it can run
      overnight with `caffeinate -i`).
- [ ] While it runs, write the three SQL files against the days already loaded.
- [ ] Plot; write findings with numbers: weekend/weekday ratio, peak hour for
      leisure vs ferries, Class B share summer vs winter, whether Sjælland Rundt
      (2025-06-14/15) and Kiel Week (2025-06-21–29) show as spikes.

**Validate:**
```bash
scripts/ch.sh -q "SELECT count() FROM load_log"                 # ≈ 62 (or 92)
scripts/ch.sh -q "SELECT day, uniqExact(mmsi) FROM vessel_day WHERE ship_group='leisure' GROUP BY day ORDER BY day LIMIT 5"
uv run --project notes notes/plot.py                            # writes notes/img/*.png
du -sh data                                                     # < 5 GB
```

**You verify:** look at the three PNGs. Does the Saturday spike read at a glance?
Do ferries and leisure have visibly different hour profiles? Is the regatta
weekend a spike or nothing?

**Gate B2 (end of phase 0):** the shapes are readable and not noise. Decide the
scope of phase 1: (a) all 2024 → today dailies + reference years 2015/2018/2021,
or (b) the full 2014 → 2026 archive.

**Commit:** `feat(s3): phase-0 queue runner and first three charts`

---

## S4 — Bulk runner: nights, resume, disk guard

**Goal:** Make the queue runner safe to leave unattended for nights: disk guard,
resume, progress, one log line per file, and a summary at the end.

**Files:**
- Modify: `scripts/run_queue.sh` — add: stop if free disk < 30 GB; `flock` to
  prevent two runners; `--dry-run`; a `data/progress.tsv` (date, rows, seconds,
  MB/s); `caffeinate -i` wrapper in the docs; an ETA line every 10 files.
- Create: `queues/2024-2026.txt` (daily dates 2024-03-01 → today),
  `queues/ref-years.txt` (monthly 2015-01 … 2015-12, 2018-*, 2021-*), and
  `queues/full.txt` (every month 2014-01 → 2024-02, generated by a one-liner in
  the file's header comment).
- Create: `sql/03_coverage_daily.sql` — daily Class A distinct vessels and
  message counts; the coverage-drift reference used in S10.

**Do:**
- [ ] Implement the guards; test with `--dry-run` on `queues/ref-years.txt`.
- [ ] Start `queues/2024-2026.txt`; record MB/s and per-file seconds in
      `docs/STATUS.md` after the first night.
- [ ] Then `queues/ref-years.txt`. Monthly zips are 14–19 GB: confirm free disk
      before each.

**Validate:**
```bash
scripts/run_queue.sh --dry-run queues/ref-years.txt
tail -3 data/progress.tsv
scripts/ch.sh -q "SELECT min(day), max(day), count() FROM (SELECT DISTINCT day FROM vessel_day)"
df -h . && du -sh data/ch
```

**You verify:** after each night, `docs/STATUS.md` has the row count, disk
usage, and the next queue to run. Nothing in `data/raw` except the file in flight.

**Gate C:** ≥ 2024-03 → today loaded; `data/ch` ≤ 40 GB.

**Commit:** `feat(s4): unattended bulk runner with disk guard and resume`

---

## S5 — Context layers

**Goal:** Everything the chapters join against, loaded once into ClickHouse
dictionaries/tables.

**Files:**
- Create: `scripts/fetch_context.sh` — Overpass queries for `leisure=marina` and
  `route=ferry` within a Denmark bbox → GeoJSON in `data/context/` (gitignored;
  the *script* is committed). Natural Earth 10 m land polygons download.
- Create: `sql/04_context.sql` — tables `marina` (name, lat, lon, h3),
  `ferry_route` (name, from, to, geometry), `land` polygon dictionary,
  `storm` (name, start, end, source), `regatta` (name, start, end, place, year).
- Create: `data/context/storms.csv` **committed** (small; from DMI/Wikipedia list)
  and `data/context/regattas.csv` **committed** (2014–2026 dates collected by hand
  from event sites; note the source URL per row).

**Do:**
- [ ] Fetch, load, count: marinas (expect hundreds), ferry routes (dozens).
- [ ] Sanity: `SELECT count() FROM h3_hourly WHERE dictHas('land', …)` → what
      share of leisure hours is "on land" (harbours) vs at sea.

**Validate:**
```bash
scripts/ch.sh -q "SELECT count() FROM marina; SELECT count() FROM ferry_route; SELECT count() FROM storm; SELECT count() FROM regatta"
```

**You verify:** open `data/context/regattas.csv` — every row has a source URL.

**Commit:** `feat(s5): marinas, ferry routes, land, storms, regattas`

---

## S6 — Chapter 01 analysis: the shape of summer

**Goal:** One notebook of findings with numbers and reproducible SQL.

**Files:**
- Create: `sql/20_season_bounds.sql` — per year: first/last day when the 7-day
  mean of distinct leisure vessels crosses 25 % / 50 % of that year's peak;
  season length in days.
- Create: `sql/21_weekend_effect.sql` — per year, weekend/weekday ratio; Friday
  evening departures (first moving hour after 15:00 local).
- Create: `sql/22_regatta_spikes.sql` — leisure vessel count in the regatta H3
  region on race days vs the same weekday ±2 weeks.
- Create: `sql/23_radius.sql` — distribution of `dist_nm` per vessel-day; share
  of vessel-days with `home_h3` within 1 cell of a marina.
- Create: `sql/24_night.sql` — share of moving leisure messages 22:00–05:00.
- Create: `notes/ch01-findings.md` — numbers + PNGs, with the claim → query
  mapping.

**Validate:** each SQL runs under 60 s; `notes/ch01-findings.md` lists at least
five numeric findings with the query file next to each.

**You verify:** read the findings as a reader would. Which three are the story?

**Commit:** `data(s6): chapter 01 findings`

---

## S7 — Chapter 02 analysis: the pulse

**Files:**
- Create: `sql/30_hour_profiles.sql` — hourly moving share by `ship_group`, split
  summer/winter, weekday/weekend; normalised per group.
- Create: `sql/31_port_breathing.sql` — for the ten busiest H3 cells containing
  a harbour: arrivals/departures by hour.
- Create: `sql/32_week_shape.sql` — 168-hour week profile per group.
- Create: `notes/ch02-findings.md`.

**Validate & verify:** as S6. The radial "fingerprint" of each group must be
distinct by eye; if leisure and fishing look alike, split fishing further by
`Ship type`.

**Commit:** `data(s7): chapter 02 findings`

---

## S8 — Chapter 03 analysis: lifelines

**Goal:** Trips per ferry line, punctuality, cancellations, seasonality, for the
small-island lines (Ærø, Samsø, Læsø, Anholt, Tunø, Bornholm, Fanø, Fur…) and
the big ones as contrast.

**Files:**
- Create: `sql/40_ferry_trips.sql` — from `public_track`: sessionise a vessel's
  positions into port stays (SOG < 0.5 kn inside a harbour cell for ≥ 5 min) and
  crossings; assign crossings to `ferry_route` by endpoints.
- Create: `sql/41_ferry_daily.sql` — trips per route per day; expected trips
  from a timetable table (`data/context/timetables.csv`, committed, hand-made
  for the small islands); cancellations = expected − observed on storm days.
- Create: `sql/42_ferry_speed.sql` — median crossing speed per route per year
  (electric-ferry transitions).
- Create: `notes/ch03-findings.md`.

**Validate:** for one known route (Svendborg–Ærøskøbing) observed daily trips
≈ timetable on a calm summer weekday.

**Commit:** `data(s8): chapter 03 findings`

---

## S9 — Chapter 04 analysis: when the storm comes

**Files:**
- Create: `sql/50_storm_window.sql` — for each row in `storm`: hourly moving
  vessels by group from −72 h to +72 h, normalised to the same weekday a fortnight
  earlier.
- Create: `sql/51_anchorage_fill.sql` — vessels stationary (SOG < 0.5) in known
  anchorage cells (Ålbæk Bugt, Skagen Red, Aarhus Bugt …) by hour in the window.
- Create: `sql/52_who_stays.sql` — share of each group still moving at peak.
- Create: `notes/ch04-findings.md`.

**Validate:** Pia (2023-12-21/22) and Malik (2022-01-29/30) both show a visible
dip in ferries; if a storm shows nothing, note it — that is a finding too.

**Commit:** `data(s9): chapter 04 findings`

---

## S10 — The honesty layer: coverage and adoption

**Goal:** Separate "more boats" from "more transponders" and "more receivers".

**Files:**
- Create: `sql/60_coverage_index.sql` — Class A distinct vessels and messages
  per day per H3 macro-region (res 4) — receivers added → step changes here.
- Create: `sql/61_adoption.sql` — Class B distinct MMSI per year, first-seen
  year per MMSI, retention; leisure vessels per Class A vessel ratio.
- Create: `notes/honesty.md` — the paragraph the essay opens with: what we can
  and cannot claim, with numbers. Cross-check one summer month against EMODnet
  density (download the GeoTIFF for that month; compare rank order of the ten
  densest cells).

**Validate:** the coverage index is flat or has explainable steps; adoption
curve is written down.

**Commit:** `data(s10): coverage and adoption analysis`

---

## S11 — Open dataset

**Goal:** Publish aggregates that cannot leak a private vessel.

**Files:**
- Create: `sql/70_export.sql` — `h3_hourly` → Parquet per year, only rows where
  `uniqExactMerge(vessels) >= 5` for `mobile = 'Class B'` (any k for public
  groups); columns: `h3`, `hour`, `mobile`, `ship_group`, `msgs`, `vessels`,
  `moving_share`, `mean_sog`. Plus `leisure_daily.parquet` (per day, per res-5
  cell) and `ferry_daily.parquet`.
- Create: `scripts/export.sh` — runs the export into `dist/dataset/`, then
  `scripts/test_export.py` (uv): asserts no row with Class B and vessels < 5,
  asserts no MMSI-like column, asserts row counts vs ClickHouse. Fails loudly.
- Create: `dist/dataset/README.md` — data card: source, licence (CC BY 4.0 +
  DMA attribution), grain, privacy rule, known biases (from S10), schema,
  citation.
- Create: `scripts/publish_hf.sh` — `huggingface-cli upload` to
  `datasets/<user>/seafolk-danish-ais` (dependency line in DECISIONS).

**Validate:**
```bash
scripts/export.sh          # PASS from test_export, sizes printed
```

**You verify:** open one Parquet in DuckDB/Polars, try to find any Class B cell
with < 5 vessels. There must be none.

**Commit:** `feat(s11): privacy-checked dataset export and data card`

---

## S12 — The essay

**Goal:** "A year under sail", RU + EN, static, scrollytelling, six charts.

**Files:**
- Create: `site/` — `index.html` (EN), `ru/index.html`, `css/`, `js/charts/*.js`
  (one D3 module per chart, each reading a small JSON produced by
  `scripts/build_site_data.sh` from the SQL in S6–S10), `js/scroll.js`
  (Scrollama). Fonts from Google Fonts; D3 and Scrollama pinned from cdnjs.
- Charts: season rings (Canvas), season curves by year, weekend bars, regatta
  spikes, daily fingerprint radial, night share; each with a caption, a source
  line, and a "reproduce" link to the SQL file.
- Create: `scripts/build_site_data.sh` — SQL → `site/data/*.json`.
- Create: `.github/workflows/pages.yml` — deploy `site/` to GitHub Pages.

**Validate:** Lighthouse ≥ 90 perf/accessibility locally; every chart has a
table fallback; page renders without JS errors in Safari and Chrome; dark mode
checked.

**You verify:** read it end to end in both languages as a stranger. Three
sailors read the draft.

**Commit:** `feat(s12): essay site`

---

## S13 — The explorer

**Files:**
- Create: `scripts/build_tiles.sh` — `h3_hourly` → monthly res-7 aggregates →
  GeoJSON → PMTiles (tippecanoe; dependency line), one layer per `ship_group`.
- Create: `site/explore/` — MapLibre + deck.gl H3HexagonLayer, year/month slider,
  group toggles, island pages (`site/explore/islands/<slug>.html`) fed by
  `ferry_daily.parquet`.

**Validate:** tiles ≤ 300 MB total; first paint < 2 s on a laptop; no per-vessel
data reachable from the browser (grep the built assets for `mmsi`).

**Commit:** `feat(s13): explorer`

---

## S14 — Posters and animation

**Files:**
- Create: `site/posters/` — Canvas renders at print resolution (season rings,
  four fingerprints, "the sea empties" frame sequence); `scripts/render_posters.js`
  (node + canvas; dependency line).
- Animation: 20–30 s, frames → `ffmpeg` (already on the machine).

**You verify:** print one poster at A3 and look at it from two metres.

**Commit:** `feat(s14): posters and storm animation`

---

## S15 — Launch and outreach

**Files:**
- Create: `docs/LAUNCH.md` — the checklist below with dates and links filled in.
- Create: `docs/outreach/` — one short email per recipient group (EN), sent by
  the human, not by Claude.

**Checklist:**
- [ ] Wave 1: "Show HN: 12 years of Danish sailing seasons from open AIS";
      r/dataisbeautiful (rings + fingerprints); Information is Beautiful Awards
      entry; PR to ClickHouse `example-datasets` with the loader and three queries.
- [ ] Habr article (RU): the engineering story — 2.3 TB through a laptop into 40 GB,
      with the charts.
- [ ] Wave 2: Dansk Sejlunion, KDY, r/sailing, Sjælland Rundt organisers; Danish
      media via a data-journalist (DR, Politiken, TV2) with the RU/EN essay link;
      posters to Øresund clubs.
- [ ] Wave 3: island municipalities and local papers (Ærø, Samsø, Læsø, Anholt,
      Bornholm) with their island page; BEAM authors (Johansson et al.) and the
      Danish soundscape authors (Hermannsen et al.) with the dataset link and the
      data card.
- [ ] Storm portrait: publish within 24 h of the next named storm.

**Gate:** none — this is the end. Write a retrospective in `docs/STATUS.md`.
