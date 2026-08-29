# human-sea — project memory

Read this first, then `docs/STATUS.md` (where we are), then the session you were
asked to run in `docs/PLAN.md`. Do not start coding before those three are read.

## What this is

A data-storytelling project on the open Danish AIS archive (2006 → today) about the
*human* side of the sea: leisure boats (Class B), island ferries, and behaviour
around named storms. Output: a data essay (RU + EN), a static explorer, an open
aggregated dataset, posters. See `README.md` for the four chapters.

The audience is developers/data people and the general public. Reputation, not
revenue. Every chart must be reproducible from the repo.

## Hard rules

- **Aggregates only for private vessels.** No MMSI, name, callsign, or track of a
  Class B / leisure vessel is ever written to an exported file, a chart, a
  notebook that is committed, or a commit message. Internal tables may hold MMSI
  for de-duplication; they live in `data/ch` and never leave the machine.
  Exports enforce k ≥ 5 distinct vessels per published cell and the export must
  fail loudly if a cell violates it.
- **Ferries and commercial vessels are public** and may be named.
- **Disk budget: 70 GB total, hard cap 100 GB.** Raw archive files are deleted
  right after they are aggregated. Never keep raw CSV on disk. Check `df -h` and
  `du -sh data` before and after a bulk run.
- **Repository language is English** — code, comments, docs, commits. The essay
  has a Russian and an English version; both live under `site/` when it exists.
- **No new dependencies without a line in `docs/DECISIONS.md`** saying why.
- **Don't invent data.** If a number is not computed from the archive, label it as
  a mock. Charts in docs that are mocks say so in their caption.

## Stack (decided — see docs/DECISIONS.md)

- ClickHouse via `clickhouse local --path data/ch` (persistent, no server).
  DDL and queries live in `sql/`, run through `scripts/ch.sh`.
- Bash for fetch/orchestration, Python (uv, ≥3.12) only where SQL is awkward
  (plots for validation, notebook-style checks under `notes/`).
- Final charts and essay: plain HTML + D3 (+ Scrollama), static. Explorer:
  MapLibre GL + deck.gl over static PMTiles/Parquet. Hosted on GitHub Pages.
- Spatial grain: H3 resolution 7 (~5 km²). Time grain: 1 hour (UTC; verify the
  archive's timezone in session S1 before trusting any hour-of-day chart).

## How a session runs

1. Read `CLAUDE.md`, `docs/STATUS.md`, the session's section in `docs/PLAN.md`.
2. State in one paragraph what you will do and which files you will touch.
   Use plan mode for anything touching the loader or the export.
3. Do the work. Small commits, conventional prefixes (`feat:`, `fix:`, `docs:`,
   `data:` for findings). Never `git add -A`.
4. Run the session's **Validate** commands from `docs/PLAN.md` and paste their
   real output into `docs/STATUS.md` under the session heading.
5. **Design review before handoff.** If the session's diff touches code
   (`sql/`, `scripts/`, `site/`, `notes/*.py`), run the `punchcard:punchcard`
   skill on that diff (`git diff main...HEAD`, or the session's commits) before
   asking the user to review. Evaluate each finding on its merits — use
   `superpowers:receiving-code-review` for that — then fix the ones you agree
   with, and for the ones you don't, write the finding and your reason under
   "Design review" in `docs/STATUS.md`. Only then hand off. Skip this step for
   docs-only sessions and say so. Punchcard is design-only; it does not replace
   the session's tests or Validate commands.
6. Finish `docs/STATUS.md`: what was done, findings (numbers!), design-review
   outcome, open questions, and the exact next session id. This is the handoff
   — write it for someone with zero context.
7. Tell the user what to check by hand (the session's **You verify** list).

If something in the plan turns out to be wrong (a column is missing, a source is
gone), stop, write what you found in `docs/STATUS.md`, propose the change to
`docs/PLAN.md`, and ask before continuing.

## Data facts you can rely on (verified 2026-08-29, details in docs/DATA.md)

- Archive: `http://aisdata.ais.dk/` (S3-backed). Monthly zips `YYYY/aisdk-YYYY-MM.zip`
  for 2006-03 → 2024-02, daily zips `aisdk-YYYY-MM-DD.zip` from 2024-03-01, some
  under `YYYY/`, some at the root — `scripts/fetch.sh` tries both.
- Sizes: a 2016 month ≈ 18 GB zip; a 2025 day ≈ 0.75 GB zip. Whole archive ≈ 3.5 TB
  zip; 2014→2026 ≈ 2.3 TB.
- CSV, 26 columns, header row, timestamp format `DD/MM/YYYY HH:MM:SS`, decimal
  point in coordinates. Column 2 `Type of mobile` distinguishes Class A / Class B.
  Column 14 `Ship type` has values like `Sailing`, `Pleasure`, `Passenger`, `Cargo`,
  `Tanker`, `Fishing`.
- Finland's open feed strips Class B (privacy); Norway's excludes leisure craft
  under 45 m. Denmark is the only open source with the leisure fleet.
