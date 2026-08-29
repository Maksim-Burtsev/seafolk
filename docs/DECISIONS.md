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
