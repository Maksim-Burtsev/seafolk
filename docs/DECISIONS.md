# Decisions

One entry per decision. Newest at the bottom. Format: date — decision — why —
what it rules out.

- 2026-08-29 — **Denmark only for the leisure chapter.** Finland strips Class B,
  Norway excludes leisure craft < 45 m. Rules out a "Baltic-wide" leisure claim;
  the essay says "Danish waters".
- 2026-08-29 — **Aggregates only for private vessels, k ≥ 5 per published cell.**
  Finland's data-protection ombudsman treats Class B as personal data; we adopt
  the stricter reading voluntarily. Rules out any per-boat visual, including
  "anonymised" tracks.
- 2026-08-29 — **`clickhouse local --path data/ch` instead of a server.** One
  binary, persistent storage, no daemon, nothing to clean up but a folder. Rules
  out concurrent writers (fine: one loader at a time).
- 2026-08-29 — **Stream-and-delete ingestion.** Raw zips are unzipped straight
  into ClickHouse and removed; only aggregates persist. Keeps the project inside
  the 70 GB budget. Rules out re-running a new aggregate over old raw data without
  re-downloading — so aggregate tables must be designed once, in S2, with room to
  spare (keep `vessel_day` internal table, it is cheap).
- 2026-08-29 — **H3 resolution 7, 1-hour bins.** ~5 km² cells are coarse enough
  for privacy and fine enough to see the Sound vs the archipelago. Finer grids
  can be derived only for public vessel classes.
- 2026-08-29 — **Static everything.** Essay = HTML + D3 + Scrollama; explorer =
  MapLibre + deck.gl over static tiles; hosting = GitHub Pages. No backend, no
  running cost, nothing to keep alive after launch.
- 2026-08-29 — **Cloud only as an accelerator, at the end, if at all.** A Hetzner
  box for one week (~€25) if the laptop download proves too slow. Never as a
  permanent host.
- 2026-08-29 — **Zenodo alongside GitHub Releases and Hugging Face.** Hugging Face
  gives a viewer and traffic, a Release gives the download next to the code,
  neither gives a citable immutable address — and the researchers in the S15
  outreach list cannot cite a Release. The Zenodo concept-DOI is the canonical
  address; the other two mirror it and link back. Rules out shipping a version
  that only exists where it cannot be cited.
- 2026-08-29 (S1) — **Archive timestamps are UTC; store `DateTime('UTC')` and
  convert to `Europe/Copenhagen` only when rendering an hour-of-day.** Proved by
  daylight saving rather than by a timetable: the first sailing hour of
  `AEROESKOEBING`, `ELLEN` and `PRINSESSE ISABELLA` is exactly one hour higher in
  the January file than in the July file, in the file's own clock — a clock that
  does not observe DST. Absolute values agree with the published timetables
  (Ærøskøbing first departure 06:00 local = 04 file-clock in July, 05 in January).
  Rules out treating the file clock as local time, which would put every
  hour-of-day chart two hours early in summer and one in winter.
- 2026-08-29 (S1) — **Read the CSV inside the zip, never unzip to disk.**
  `file('data/raw/aisdk-*.zip :: *.csv', CSVWithNames, '<columns>')` matches the
  26 header columns by name and skips the rest via
  `input_format_skip_unknown_fields=1`; a full scan of a 3.8 GB daily CSV takes
  ~5 s. Measured only on **daily** zips (0.6–0.8 GB, one CSV member), which is all
  S2 and S3 need. The `unzip -p | clickhouse local` pipe planned for S2 stays the
  documented fallback and is *not* ruled out: the monthly files S4 loads are
  14–19 GB, past the zip64 boundary, and `docs/DATA.md` notes 2017 also ships
  `all_sources_2017-MM.zip` variants of unknown member layout. **S4 must confirm
  ClickHouse opens a monthly zip64 archive before the bulk run**, and fall back to
  the pipe if it cannot.
- 2026-08-29 (S1) — **Quality filter: `abs(Latitude) <= 90`.** Every impossible
  coordinate in the four sampled days is exactly `Latitude = 91, Longitude = 0`
  (0.1–0.5 % of rows). There is no second sentinel and no partially-broken value,
  so this one test is sufficient. Rules out inventing a cleaning heuristic.
- 2026-08-29 (S1) — **Scope filter: the Danish bbox lat 53–59 / lon 3–17 — a
  choice about what the project is about, not a cleaning step.** It keeps
  96.6–99.5 % of rows across the four sampled days (96.6 % on 2025-06-14,
  99.5 % on 2025-07-16). What it drops is mostly *not* junk: on 2025-06-14 the
  ~894 k out-of-bbox rows form one coherent southern-Baltic cluster (5° cells
  lat 50–55 / lon 15–20, 364 k messages alone), i.e. real traffic the Danish
  receivers picked up beyond Danish waters. A little genuine junk (lat −87,
  lon −168) is inside the valid range and is removed by the same filter.
  Consequences: the essay says "Danish waters" and means it; **S10's coverage
  layer must report the dropped share per day**, because it varies by a factor
  of seven between days and would otherwise look like a change in traffic; and
  S2's loader must count what it drops rather than discard it silently.
- 2026-08-30 (S2) — **Vessel identity is resolved once per vessel-day, never
  per message.** A vessel reports several `Ship type` values in a day (position
  messages say `Undefined`, static messages carry the real type: 3 026 of 4 884
  Class B vessels on 2025-07-12 said both) and sometimes both values of `Type of
  mobile` (354 of 3 402 vessels on 2025-01-15). Grouping on the per-message
  value made vessel counts non-additive — one boat in two `ship_group`s at once
  — and dropped 1.93 % of ferry minutes from `public_track`. `ais_vessel_stage`
  holds one identity per (day, mmsi) and `ais_clean` joins it. Rules out any
  downstream query grouping on a raw `Ship type` or `Type of mobile` column.
- 2026-08-30 (S2) — **`Type of mobile` is resolved toward Class B at a 1 %
  threshold.** A vessel whose messages are at least 1 % Class B is private for
  that day. Not "Class B even once": that was tried and filed ~340 obvious
  Class A ships a day as private, cutting `public_track` by 21 %. Not a
  majority either: the asymmetry is deliberate, because mislabelling a ferry as
  private costs a row while mislabelling a boat as public publishes its track.
  The threshold sits in a measured gap — mixed vessels are bimodal, 339 under
  1 % against 15 above on 2025-01-15. Rules out treating `Type of mobile` as a
  per-message fact anywhere in the project.
- 2026-08-30 (S2) — **`h3_hourly.vessels` is an exact uniqExact state and must
  never cross an export boundary.** `uniqExact` keeps the values, so merging a
  guess into a published state answers "is this you?" — verified: 1 for a hit,
  2 for a miss. 70.1 % of Class B cell-hours on 2025-07-16 hold exactly one
  vessel, and Danish MMSIs live under MID 219/220, so a published state is a
  recoverable identity over ~2 M candidates. Safe only because `data/ch` never
  leaves the machine. S11 exports `uniqExactMerge(vessels)` as a number under
  k >= 5 and never the column itself.
- 2026-08-30 (S2) — **k >= 5 is not publishable at res 7 / 1 hour for Class B.**
  Measured on 2025-07-16: the storage grain keeps 7.3 % of Class B cells and
  47.7 % of their messages; res 5 / day keeps 38.1 % and 91.8 %. The stored
  grain stays res 7 / hourly (it is what the analysis needs); the *published*
  leisure layer is res 5 / daily. Rules out publishing the hourly Class B
  layer at all, at any k.
- 2026-08-30 (S2) — **Quality filter `sog < 100`.** `SOG` carries the AIS
  sentinel 102.3 ("speed not available"), 27–66 k rows a day, stored as 102.2
  in Float32. It is excluded from `moving`, from `moving_msgs`, from `sog_sum`
  and from `dist_nm`. Rules out reading `mean_sog` as a plain average of the
  column.
- 2026-08-30 (S2) — **`dist_nm` is distance covered while moving, not distance
  between fixes.** Four guards on each step: gap/first-row (`ts - pts` in
  1–3600 s), 50 kn implied-speed cap, both endpoints moving, and `sog < 100`.
  Measured contribution on 2025-07-16: 2.2 %, 4.7 %, 5.1 % individually, and
  142x if all are removed (the first step of every window is otherwise measured
  from the Gulf of Guinea). Rules out reading `dist_nm` as a track length.
- 2026-08-30 (S2) — **Timestamps are parsed with an explicit
  `%d/%m/%Y %H:%i:%S` mask, not `best_effort`.** S1 measured them identical
  over 87.6 M rows including the ambiguous `12/07/2025`, but the mask costs the
  same and removes the whole class of silent month/day swap. Rules out relying
  on a ClickHouse setting for correctness of the project's only time column.
- 2026-08-30 (S2) — **The row cap is a flag, and a capped load never deletes
  its archive.** `scripts/load.sh --limit N` exists for the test; it was an
  ambient environment variable first, which meant a truncated load could log
  itself as complete and delete the only copy of the day. Rules out any future
  loader option that changes how much is loaded without changing what is kept.
- 2026-08-30 (S2) — **Stage tables are dropped with `DROP TABLE ... SYNC`, not
  truncated.** `TRUNCATE` leaves the old parts inactive and `clickhouse local`
  exits before the background cleaner runs, so one daily file left ~58 MB of
  dead stage behind — ~52 GB over the 900 files of S4, against a 70 GB budget.
- 2026-08-30 (S3) — **A leisure vessel-day counts as `active` when
  `moving_msgs > 0`, and there is no minimum message count.** S2 asked S3 to
  pick a `msgs >= N` floor; measured on 2025-07-16 it is the wrong lever. At
  N = 100 it drops 19.2 % of leisure vessels but only 0.72 % of their moving
  messages, and the median `dist_nm` of what it drops is 0 at *every* N — it
  only ever removes boats that did not move, so say that instead. 32 % of
  leisure vessel-days (1 457 of 4 554) never exceed 0.5 kn, and only 16 of the
  3 097 that do move have fewer than 5 messages, so a floor on top of
  `moving_msgs > 0` would be redundant. Both counts are carried in
  `sql/10_season_daily.sql`: `present` (a transponder reported) and `active`
  (the boat moved). Rules out any chart that says "boats" without saying which
  of the two it counted.
- 2026-08-30 (S3) — **`matplotlib` is the only new dependency; there is no
  ClickHouse client library.** `docs/PLAN.md` § S3 named `clickhouse-connect`,
  but that is a client for a ClickHouse *server* and this project deliberately
  has none. `notes/plot.py` runs the query files through `scripts/ch.sh` and
  parses the TSV that comes back. Rules out a notebook or script that talks to
  the store any other way than through `scripts/ch.sh`.
- 2026-08-30 (S3) — **`clickhouse local` holds an exclusive lock on `--path`, so
  nothing may read `data/ch` while a load runs.** A second invocation fails with
  `Cannot lock file data/ch/status`, and the failure lands on whichever process
  loses the race — a stray query can therefore kill a bulk run, not merely fail
  itself. Development against a live queue uses `CH_PATH=<copy> scripts/ch.sh`
  on a copy of the store. Rules out a progress dashboard, a monitoring query, or
  any second reader during S4's overnight runs.
- 2026-09-03 (S4-redo) — **`geoToH3(lat, lon, 7)`, and both H3 order settings
  are pinned in `scripts/ch.sh`.** ClickHouse 25.5 flipped `geoToH3` to
  `(lat, lon)` ([#78852](https://github.com/ClickHouse/ClickHouse/pull/78852),
  listed under *Backward Incompatible Change*; setting
  `geotoh3_argument_order`, legacy `lon_lat`) and 25.1 flipped `h3ToGeo` to
  return `(lat, lon)` ([#74719](https://github.com/ClickHouse/ClickHouse/pull/74719),
  setting `h3togeo_lon_lat_result_order`). S0 wrote the pre-25.5 `(lon, lat)`
  into the plan, S2 implemented it on 26.7.5.10, and every cell of 945 loaded
  archives was mirrored across the lat = lon diagonal into the Arabian Sea:
  Copenhagen's true res-7 cell (`608531686258376703`, from the h3 reference
  library) held 0 rows, its mirror 528; of 217 949 distinct cells, 0 had a
  centre in the Danish bbox and 217 441 in the mirrored one. The S2 test read
  `h3ToGeo` in the same swapped order, so it was a tautology — its mutation
  check fed the *correct* call, saw a failure, and certified the bug. `ch.sh`
  now passes `--geotoh3_argument_order=lat_lon --h3togeo_lon_lat_result_order=0`
  so no future default can change the meaning silently, and `test_load.sh`
  asserts the hard-coded Copenhagen id. **A coordinate-order test must use an
  external oracle, never a round trip through the same functions.** Rules out
  any H3 call not routed through `ch.sh`, and any spatial assert without a
  fixed expected value.
- 2026-09-03 (S4-redo) — **The store is rebuilt from the archive, not
  remapped.** A remap from the mirrored cells (un-swap each cell centre, ask
  for the true cell) was measured on 300–400 k random bbox points: 66 % land in
  the exact res-7 cell, 100 % within one ring, 93 % agree at res 5; median
  position error 941 m against the 817 m floor of res 7 itself; 48 % of mirrored
  footprints sit inside one true cell, 50 % straddle two. Good enough for a
  chart, not for a dataset whose claim is an exact H3 grid, and the sub-cell
  position is gone with the raw files (stream-and-delete), so it is a
  re-download: 909 daily + 36 reference months + 4 storm months (2022-01,
  2022-02, 2023-02, 2023-12 — Malik, Nora, Otto and Pia were never inside scope
  (a), so chapter 04 had no data at all) ≈ 1.4 TB. `data/ch` was deleted on
  2026-09-03. Rules out publishing anything spatial from a remapped store.
- 2026-09-03 (S4-redo) — **Bulk loading runs on a rented Linux VM; the store
  comes home as one tarball; the VM is destroyed.** The laptop link is ~11 MB/s
  (17 h for the dailies alone, two days for everything); on a 1 Gbit VM near
  the Danish S3 the run is CPU-bound instead (~9–10 h serial on 8 vCPU / 32 GB,
  a second night if it spills). Cost $2–10 a night (Vultr `vc2-8c-32gb`
  $0.219/h, UpCloud 8xCPU-32GB $0.356/h, Hetzner CX53 $0.056/h but may ask for
  ID). ClickHouse on the VM is pinned to the laptop's 26.7.5.10 so the store is
  byte-compatible. Privacy: `data/ch` holds MMSI of private vessels and the
  rule says it never leaves the machine; the reading adopted here is that a VM
  under the user's control, holding the store for hours and destroyed with its
  disk before the account is closed, is "the machine" for the duration —
  `scripts/vm/pull.sh` brings the tarball straight to the laptop and nothing is
  uploaded anywhere else. Rules out snapshots, object-storage copies, or a
  long-lived VM.
- 2026-09-08 (S4-redo) — **The reload ran on the Mac Mini after all, not on a
  VM.** Supersedes the 2026-09-03 VM entry for this run: one provider had
  banned the account, the others want ID or a deposit, and the user chose not
  to open any (decision 2026-09-06). Same loader, same runner, the three queues
  chained in one `tmux` session with `AHEAD=8` for dailies and `4` for
  monthlies; `caffeinate -i -s -w <chain pid>` held the machine awake for the
  run's lifetime. 949 archives, 1.23 TB, 34 h 54 min wall, ~4.4 h of that
  ClickHouse time — download-bound at 5–15 MB/s depending on the hour.
  `scripts/vm/*` stay in the repo, tested but unused; if a VM ever becomes
  available the 09-03 entry still describes how to use one.
- 2026-09-08 (S5) — **Overpass output is read straight into ClickHouse; no
  GeoJSON conversion step.** Marinas come as Overpass `out:csv` (TSV, because
  this Overpass build rejects the separator argument) and are read by
  `file(…, TSV, …)`; ferry routes come as `[out:json]; … out geom;` and are
  read by `file(…, JSONAsString)` + `JSONExtract`; Natural Earth comes as its
  own GeoJSON, pinned to release tag **v5.1.2** rather than master because the
  file is regenerated in place and a silent shape change would move the
  coastline under an already published chart. ClickHouse parses all three
  formats natively, so the fetch script is three `curl`s and the loader is one
  SQL file. Rules out `ogr2ogr`/GDAL, `osmtogeojson`, and any Python conversion
  step as project dependencies — and rules out `overpass turbo`'s GeoJSON
  export, which drops the member roles `ferry_route` needs.
- 2026-09-08 (S5) — **The context bbox is the project bbox (lat 53–59, lon
  3–17), not "Denmark".** `h3_hourly` covers everything the Danish AIS receivers
  hear, which includes Kiel, the Swedish west coast and the German shore of
  Flensburg Fjord; a context layer clipped to the Danish border would leave
  those cells with no marina and no coastline and make them read as open sea.
  So Kiel-Schilksee is in `marina` and in `regatta` exactly as it is in
  `h3_hourly`. Rules out a "Denmark only" clip of the context layers, and means
  any published count of marinas is a count in the project bbox, never a count
  of Danish marinas — the essay must say so.
- 2026-09-08 (S5) — **`ferry_route` is every OSM object tagged `route=ferry`,
  ways AND relations (`nwr`), one row per object.** In Danish waters most
  small-island lines are a single tagged way, not a route relation:
  `relation[route=ferry]` returns 326 objects in this bbox and not one of them
  is an Ærø route — Svendborg–Ærøskøbing, the line S8 validates chapter 03
  against, is **way 33847154**. 1 324 rows load: 1 001 ways + 323 relations.
  `geom` is `Array(Array(Tuple(lon, lat)))` — one entry per member way, in
  ClickHouse geo order, **not stitched into a single line**, because member
  order and direction in an OSM relation are not guaranteed and a wrong stitch
  draws a ferry through land. Member ways with role `platform` /
  `platform_entry_only` / `platform_exit_only` are excluded (101 of them here,
  38 relations lose at least one member): they are quay outlines, not the
  crossing. Rules out treating a row as one polyline, and rules out a
  relations-only fetch.
- 2026-09-08 (S5) — **`land` is Natural Earth 10 m as a `POLYGON_INDEX_EACH`
  dictionary keyed on `(lon, lat)`.** Called as
  `dictHas('land', (h3ToGeo(h3).2, h3ToGeo(h3).1))` — the swap is mandatory,
  because H3 is `(lat, lon)` under `scripts/ch.sh`'s pins and ClickHouse geo
  types are `(x, y) = (lon, lat)`. `POLYGON_INDEX_EACH` over the default
  `POLYGON` (= `POLYGON_INDEX_CELL`) because every `clickhouse local` process
  rebuilds the dictionary on first use, so its build cost is paid per query:
  measured 16.4 s / 150 MB against **3.5 s / 82 MB**, identical answers on all
  116 289 cell centres. **Oracle rule: a land assert uses an inland point
  (Viborg, 9.4020 E 56.4531 N) and its mirror, never a coastal one** — at 10 m
  scale the coast is generalised up to ~1 km inland and Rådhuspladsen in
  Copenhagen reads as sea, so a coastal assert is 0 whether the dictionary is
  right or mirrored (that is a tautology, the same class of bug that mirrored
  the whole store in S4). Consequence for the chapters: **`land` is an
  open-water / inland split, not a harbour / sea split** — 794 of 2 833 marina
  cell centres (28 %) read "not land". Rules out using `dictHas('land', …)` as
  "is this boat in a harbour"; **`marina` is the harbour signal** (1 891 res-7
  cells hold ≥ 1 marina, 50 hold ≥ 5).
- 2026-09-08 (S5) — **`data/context/storms.csv` and `regattas.csv` are
  hand-collected, are the source of record, and are committed by name.** They
  have no machine source, so the CSV *is* the data; every row carries the URL it
  was read off, because a named storm's start is an editorial choice and the
  essay has to be able to show whose. No row without a URL that shows the date —
  Bornholm Rundt and Watski 2Star could not be sourced and were left out
  entirely rather than guessed. Both are loaded strictly:
  `date_time_input_format='basic'` (never `best_effort`, which guesses which
  half of `05/12/2013` is the month), `input_format_skip_unknown_fields=0`,
  `input_format_defaults_for_omitted_fields=0`, plus a verbatim header assert in
  `scripts/test_context.sh` because a column simply *missing* from the header is
  not an "unknown field" and no setting rejects it. `.gitignore` un-ignores the
  two files **by name**, not by `*.csv` under `data/context/`, so a stray
  `INTO OUTFILE` off `vessel_day` can never be one `git add` away from
  publishing MMSIs. Scope: `regatta` covers the six years the store actually
  holds (2015, 2018, 2021, 2024, 2025, 2026) — dates for years with no AIS data
  would be decoration; `storm` is the whole DMI named-storm list since 2013
  (24 rows), because chapter 04 picks its storms from that list. Rules out
  scraping either source at build time, and rules out any `*.csv` negation in
  `.gitignore`.
- 2026-09-08 (S5) — **Context tables rebuild with `DROP … SYNC` + `CREATE`,
  never `CREATE OR REPLACE`.** On an Atomic database `CREATE OR REPLACE` renames
  the old table aside and defers the real drop by
  `database_atomic_delay_before_drop_table_sec` (480 s); `clickhouse local`
  exits long before that, no later process picks the work up, and the bytes stay
  in `data/ch/store` forever with a stub in `data/ch/metadata_dropped`. Measured
  during S5's own development: 20 orphaned `_tmp_replace_*` tables, 20.7 MB, in
  one evening of re-runs. This is the same pattern `scripts/load.sh` already
  uses, and `scripts/test_context.sh` now asserts that a second run of
  `sql/04_context.sql` orphans no table and does not grow the store. Rules out
  `CREATE OR REPLACE TABLE` anywhere in this project's SQL.
- 2026-09-09 (S6) — **A season is defined on the 7-day trailing mean of
  distinct Class B leisure vessels that moved (`moving_msgs > 0`), per calendar
  year: the outer season is where that mean is ≥ 25 % of the year's peak, the
  core is ≥ 50 %.** Distinct moved vessels, not messages, so the Sep-2015
  archive duplication and per-class reporting rates cannot move the edges; a
  trailing 7-day window, so a rainy weekend does not open or close a season;
  fractions of the year's own peak, so 2015 (peak 1 165) and 2026 (peak 5 178)
  are measured on the same scale. A year needs ≥ 200 loaded days to be scored
  (keeps 2024 and 2026, drops the 59-day storm samples of 2022/2023), and a
  year whose loaded range starts after Jan 7 or ends before Dec 24 is marked
  `censored` rather than reported as if its edge were observed. Rules out
  "first day above N boats" thresholds, which would not survive a fleet that
  grew 3.6× in eleven years.
- 2026-09-09 (S6) — **"Friday-evening departure" is measured by a proxy:
  the share of moved leisure vessel-days whose first position of the day is
  after 15:00 Europe/Copenhagen.** The aggregates keep `first_ts` (first
  position) and `moving_msgs` per vessel-day but not the first *moving* hour,
  and the raw files are gone. A Class B transponder is powered with the boat,
  so a late first message on a day the boat moved is a late departure to
  within a switch-on delay. Stated as a proxy wherever it is quoted; the
  weekday of a vessel-day is its UTC date (a 1–2 h smear that misfiles ~0.1 %
  of moved vessel-days — measured in S6's review, sql/21 header).
- 2026-09-09 (S7) — **A local day is covered when it holds every UTC hour it
  spans — `uniqExact(hour) = dateDiff('hour', toStartOfDay(lt),
  toStartOfDay(lt) + INTERVAL 1 DAY)` — so the daylight-saving Sundays count.**
  The rule sql/11, sql/12 and sql/24 use, `uniqExact(toHour(local)) = 24`,
  fails the 23-hour spring-forward Sunday by construction and dropped one
  Sunday a year from every hour-of-day result (2015-03-29, 2018-03-25,
  2021-03-28, 2024-03-31, 2025-03-30, 2026-03-29 — six days, measured). For a
  chapter whose subject is the clock and the week that is a hole in the
  deliverable, so sql/30–32 repair it. The count must be of UTC hours, not
  local ones: on a fall-back day the local clock strikes 02 twice and
  `uniqExact(toHour(lt))` reads 24 against an expected 25. The three older
  files are not retrofitted — their output is quoted verbatim in published
  notes — and the cost of running two conventions was measured at ≤ 0.0010 on
  sql/24's night shares, all of it in Oct–Apr. Rules out a per-day
  expected-hour table, which the S6 review had judged too much machinery: the
  repair is one expression.
- 2026-09-09 (S7) — **An arrival into a cell is a vessel present in the cell's
  `uniqExact` state this hour and absent from it the hour before; a departure
  is the mirror. Both are exact, computed by inclusion–exclusion over merged
  states, never over MMSI.** |A ∩ B| = |A| + |B| − |A ∪ B| holds for
  `uniqExact` states, so `appeared = |A_h| − |A_h ∩ A_{h−1}|` is a count with
  no sampling and no proxy, and the state itself never leaves the query. The
  appearance is split by whether the vessel was in the cell's ring-1
  neighbourhood the hour before (`arrived_from_ring`) or nowhere near it
  (switched on at the berth, or came from further than ~15 km in an hour) —
  because a Class B transponder is powered with the boat, and without the
  split a harbour would appear to arrive and depart in the same morning hour.
  The split is a speed test as much as a transponder test: a ferry at 20 kn
  outruns the ring in an hour. Certified against an independent MMSI-set
  computation over `public_track` for one cell-month (sql/33). Rules out
  `first_ts`/`last_ts` from `vessel_day` as a departure signal — they are
  first and last message, which for a moored boat is midnight.
- 2026-09-10 (S8) — **A ferry's expected trips are the data's own median, not a
  timetable.** `baseline` in `sql/41` is the median of observed crossings over
  the same (line, calendar year, May–Sep / Oct–Apr, day of the week), on days
  the line's own fleet was heard; `missed = baseline − crossings`, floored at
  zero. Day of the week, not weekday / Sat / Sun: Grenaa–Anholt never sails a
  Wednesday and Hirsholmene runs three days a week, and a Mon–Fri pool read
  every such day as a cancellation (237 on Anholt alone). Operator timetables are not
  archived per year and the store spans 2015 → 2026, so a hand-made
  expected-departures table for every line × year × season would be invented
  data. A committed anchor, `data/context/ferry_timetable.csv` (one number per
  line: summer-weekday departures per direction in the current published
  timetable, with its URL), exists only to check the machinery — Svendborg–
  Ærøskøbing 11 per direction against 22 crossings a day observed, Branden–Fur
  72 against 134–142. Rules out the plan's `timetables.csv` of expected trips;
  `missed` is read as "fewer than a comparable day", never "cancelled sailings",
  and always next to the coverage columns from `ferry_day` (positions, positions
  with a known speed, moving positions of the line's own-majority fleet that
  day), so a zero-crossing day reads as silent, cannot tell, lay still, or
  moved-but-unmatched — never as a cancellation by default.
- 2026-09-10 (S8) — **A berth call is any maximal run of positions at SOG < 0.5
  kn — one position is enough — and a crossing is the move between two
  consecutive calls of one vessel inside one gap-free session, when they are
  more than 100 m apart and match two different ends of one OSM ferry route.**
  Three thresholds were measured on July 2025 before this was fixed: a 5-minute
  stay rule deleted Fursund and Hals–Egense outright (a third of Fur's berth
  calls are under two minutes; 17 crossings in the store against 4 216 in the
  track for one month) and a 1 km distance rule deleted every crossing shorter
  than a kilometre (the 400–1 000 m bin holds ~100 000 real crossings a year
  and no clean gap separates it from harbour shuffles). Neither threshold moved
  Ærø, Læsø or any line longer than a few minutes by more than 4 %. The route
  match does the discrimination the thresholds could not: each berth's nearest
  endpoint of the route must differ. Cost, measured: 8.3 % of crossings match
  no route (185 116 of them under 1 km, harbour shuffles by construction) and a
  line whose intermediate call OSM does not draw as an endpoint loses the legs
  through it (Svendborg–Skarø–Drejø via Hjortø, −74 %). `ferry_stay.minutes`
  is kept so any threshold can be re-imposed after the fact. Rules out a
  distance or duration guard as the definition of a crossing.
- 2026-09-10 (S8) — **High-speed craft are not in `public_track` and cannot be
  added.** `sql/03_aggregate.sql` maps AIS `Ship type = 'HSC'` to `ship_group =
  'other'`, and `public_track` keeps `passenger` only, so the 475 HSC vessels
  (785 M messages) — Molslinjen's Express ferries Aarhus–Odden and Rønne–Ystad,
  Bornholm's fast tonnage — left no track before the raw files were deleted.
  Chapter 03 therefore reads Rønne–Ystad on conventional relief tonnage only
  (414 crossings) and uses Helsingør–Helsingborg, Rødby–Puttgarden, Rønne–Køge
  and Gedser–Rostock as its big-line contrast. Recorded, not fixed: a fix is a
  2.3 TB reload. S10's honesty layer names it.
- 2026-09-10 (S8) — **A ferry line is a hand-labelled set of OSM objects,
  `data/context/ferry_lines.csv`, committed.** OSM carries one physical service
  as several objects — Helsingør–Helsingborg is seven, Rødby–Puttgarden four,
  Læsø two ways — and 363 of the 1 324 `route=ferry` rows have no name, the
  busiest of them (Hönö–Lilla Varholmen, 372 371 crossings) among them. The
  file maps every route with ≥ 200 crossings that the chapter needs to a line
  label and a kind (island / domestic / international / foreign); `sql/40`
  loads it as `ferry_line`, and `sql/41`/`42` group by line. It is labelling,
  not measurement: no number in it. Rules out grouping by OSM object in any
  published table, and rules out a data-driven merge of routes by shared
  endpoints (union-find in SQL for a 280-row fact a human can read).
- 2026-09-10 (S9) — **"Moving vessels per hour" does not exist in the store;
  chapter 04 uses three instruments instead and says which one each number
  is.** `h3_hourly.vessels` is a uniqExact state over every vessel present in
  a cell-hour, moving or not, and no state of the moving subset was stored, so
  the plan's "hourly moving vessels by group" is unrecoverable (the constraint
  sql/11, 12, 24 and 30 already state). `sql/50` therefore emits, per hour,
  an exact head count (`heard`, the merged state over all cells) and a
  message-based movement signal (`moving_msgs` against the same hour a
  fortnight away — a ratio within one fleet, never a level across fleets);
  `sql/52` gives the exact count of vessels that moved ≥ 1 nm from
  `vessel_day`, at day grain; ferries are counted in departures from
  `ferry_crossing`. Rules out quoting any hourly number as "vessels moving".
- 2026-09-10 (S9) — **The reference for a storm hour is the same UTC hour
  14 days earlier, else 14 days later, else NULL — one fortnight, not a
  seasonal baseline.** A fortnight keeps the weekday, the hour and the season.
  Measured: −14 d for thirteen storms, +14 d for Dagmar·Egon (the archive
  starts 2015-01-01), both for Otto (2023 holds February and December only);
  no storm lost its reference. The windows are calendar dates with no
  timezone conversion (`sql/41`'s rule) and Dagmar and Egon are one event.
  Rules out a seasonal median as the baseline: the 2022/2023 storm windows are
  59 days each and have no season to take a median over.
- 2026-09-10 (S9) — **An anchorage is a rule plus a hand label, and the rule
  has no marina test.** A cell-year is a candidate when Class A cargo + other
  vessels leave four messages in five at under 0.5 kn there, at sea (the
  `land` dictionary), with ≥ 50 distinct vessels in the year; the ≥ 100 cells
  are hand-labelled in `data/context/anchorages.csv` with a source URL
  (an OSM `seamark:type=anchorage` object within 8 km, or a published
  roadstead), and the build throws on an unlabelled one. The plan's "not a
  marina cell" filter was measured and removed: a res-7 cell is ~5 km² and
  Skagen's marina shares its cell with the Skagen roadstead — the filter
  deleted the country's biggest anchorage (1 021 / 1 158 / 273 vessels in
  2015 / 2018 / 2025) and 44 of the 143 labelled cells. Rules out any
  data-driven "is an anchorage" decision: the label is the decision, the rule
  only proposes.
- 2026-09-10 (S9) — **A storm's peak hour is derived from the data, inside the
  storm's own dates.** DMI publishes dates, not hours, so the peak is the hour
  of the storm's calendar dates at which the pooled Class A moving-message
  ratio is lowest. Restricting to the storm's own dates changes the answer
  for 6 of 14 storms; Floriane's least-bad own-date hour is a ratio of 1.05 —
  no dip — and is reported as such rather than borrowing the dip three days
  later. Rules out a whole-window minimum as "the storm".
