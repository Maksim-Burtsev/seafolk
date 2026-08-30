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
