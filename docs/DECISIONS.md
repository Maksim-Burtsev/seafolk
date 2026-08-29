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
  ~5 s. Rules out the `unzip -p | clickhouse local` pipe planned for S2 — there is
  no reason to stream through a pipe when ClickHouse opens the archive itself, and
  no temporary CSV ever touches the disk.
- 2026-08-29 (S1) — **Position filter is the Danish bbox, not just `abs(lat)<=90`.**
  Every impossible coordinate in the archive is exactly `Latitude = 91`
  (0.1–0.5 % of rows), but ordinary GPS junk inside the valid range (lat −87,
  lon −168) survives that test. The Danish bbox lat 53–59 / lon 3–17 keeps
  99.2–99.4 % of rows. Rules out H3 cells scattered over the Pacific in the
  explorer.
