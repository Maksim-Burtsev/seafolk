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
| 1 · Fill the lake | S4–S5 | 2024 → today daily + reference years + storm months aggregated **with a correct H3 grid** (S4-redo, on a VM); context layers loaded |
| 2 · Analyse | S6–S10 | One notebook of findings per chapter + the honesty layer |
| 3 · Publish data | S11 | Parquet on GitHub Releases + Hugging Face + Zenodo (DOI), data card, privacy test |
| 4 · Tell it | S12–S14 | Essay (RU/EN), explorer, posters |
| 5 · Launch | S15 | HN / Reddit / Habr / outreach mails / ClickHouse example-dataset PR |

---

## S0 — Bootstrap *(done in the planning session)*

Repo skeleton, `CLAUDE.md`, `docs/*`, `scripts/fetch.sh`, `.gitignore`. Minimal
working set requested: `2025-07-12` (Sat), `2025-07-16` (Wed), `2025-01-15`
(winter Wed), `2025-06-14` (Sjælland Rundt Saturday).

- [x] Files above exist.
- [x] `scripts/fetch.sh 2025-07-12 2025-07-16 2025-01-15 2025-06-14` completed
      (`ls data/raw/*.ok` shows four files).

---

## S1 — First look: does the story exist in the files? *(done — Gate A passed)*

**Goal:** Open one daily file without loading anything permanently and answer five
questions with numbers: Is Class B present? What share of active vessels is Class B
on a July Saturday vs a January Wednesday? What are the `Ship type` values and
their counts? Is the timestamp UTC or local? Are coordinates decimal-point?

**Files:**
- Create: `sql/00_peek.sql` — `SELECT` queries over `file('data/raw/…')` via
  `clickhouse local`. *(Done differently: ClickHouse opens the zip itself with
  `file('data/raw/aisdk-*.zip :: *.csv', CSVWithNames, '<cols>')`, so the
  `unzip -p | clickhouse local` pipe was not needed. See `docs/DECISIONS.md`.)*
- Create: `scripts/ch.sh` — wrapper: `clickhouse local --path data/ch
  --multiquery < "$1"` (and `-q` passthrough). Make it executable.
- Create: `notes/s1-first-look.md` — the numbers, verbatim query output.

**Do:**
- [x] Inspect the zip: one CSV member, `aisdk-2025-07-12.csv`, 3.84 GB.
      Superseded in practice: ClickHouse opens the archive itself, no `unzip`.
- [x] Read the CSV inside the zip with `file(… :: *.csv)` and run: row count;
      distinct MMSI by `Type of mobile`; distinct MMSI by `Ship type` for Class B
      only; count of rows with `Latitude`/`Longitude` outside Danish waters or at
      the 91/181 sentinel; parse check of `Timestamp`. All six checks are in
      `sql/00_peek.sql`, output in `notes/s1-first-look.md`.
- [x] Timezone test → **UTC**, recorded in `docs/DECISIONS.md`. Done by the
      daylight-saving shift rather than by trusting a timetable: the island
      ferries `AEROESKOEBING`, `ELLEN` and `PRINSESSE ISABELLA` each start
      sailing exactly one hour later in the January file than in the July file,
      in the file's own clock. `TYCHO BRAHE` (Helsingør–Helsingborg) was
      rejected as a probe — it moves in all 24 hours and has no first departure.
- [x] Repeat the Class B share query on `aisdk-2025-01-15.zip`. 27.6 % vs 57–66 %.

**Validate:**
```bash
scripts/ch.sh sql/00_peek.sql        # prints the answers as small tables, ~41 s
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

## S2 — The loader: one zip in, aggregates out, raw file gone *(done — Gate B1 passed)*

**Goal:** A single command that takes an archive file, streams it through
ClickHouse, appends to persistent aggregate tables, and deletes the zip. Designed
once, because raw data is not kept.

**Files (as built — see `docs/STATUS.md` § S2 for why each differs from the
original plan):**
- `sql/01_schema.sql` — DDL, idempotent. Five permanent tables:
  - `h3_hourly` (AggregatingMergeTree, PARTITION BY toYYYYMM(hour), ORDER BY
    (h3, hour, mobile, ship_group)): `h3 UInt64` (res 7, `geoToH3(lat, lon, 7)` —
    **`(lat, lon)` since ClickHouse 25.5**; this line said `(lon, lat)` until
    2026-09-03 and the whole first store was mirrored, see § S4-redo),
    `hour DateTime('UTC')`, `mobile`, `ship_group`,
    `msgs SimpleAggregateFunction(sum, UInt64)`,
    `vessels AggregateFunction(uniqExact, UInt32)`,
    `moving_msgs SimpleAggregateFunction(sum, UInt64)`,
    `sog_sum SimpleAggregateFunction(sum, Float64)` — summed over moving
    messages only. **`vessels` is an exact state and must never be exported.**
  - `vessel_day` (ReplacingMergeTree, PARTITION BY toYYYYMM(day), ORDER BY
    (day, mmsi)): `day`, `mmsi`, `mobile`, `ship_type`, `ship_group`,
    `first_ts`, `last_ts`, `msgs`, `moving_msgs`, `dist_nm` (distance covered
    *while moving*), `home_h3`, `length`, `imo` (0 if never reported; the join
    key for S8's ferry registry lookups). **Internal only — contains MMSI.**
  - `public_track` (MergeTree, PARTITION BY toYYYYMM(ts), ORDER BY (mmsi, ts)):
    1-minute downsampled positions, `mobile = 'Class A' AND ship_group =
    'passenger'`, plus `name`. Chapter 03 reads this.
  - `load_log` (MergeTree): `file`, `loaded_at`, `seconds`, `ts_min`, `ts_max`,
    `rows_read`, `rows_non_vessel`, `rows_sentinel`, `rows_out_of_bbox`,
    `rows_kept`, `rows_h3`, `rows_vessel_day`, `rows_public_track`.
    The four row counters partition `rows_read` exactly; S10 reads them.
  - plus two per-file stage tables (`ais_raw_stage`, `ais_vessel_stage`) and two
    views (`ais_rows` = which rows count, `ais_clean` = those rows joined to one
    resolved identity per vessel-day). Stage tables are dropped after each load.
- `sql/02_stage.sql` — `INSERT INTO ais_raw_stage SELECT … FROM
  file({src:String}, CSVWithNames, …) LIMIT {lim:UInt64}`. Timestamps parsed
  with an explicit `%d/%m/%Y %H:%i:%S` mask.
- `sql/03_aggregate.sql` — step 0 resolves one identity per vessel-day into
  `ais_vessel_stage`, then three `INSERT … SELECT` from `ais_clean`.
- `scripts/load.sh [--force] [--limit N] <zip>` — stage, read the file's own
  date range from the staged rows, delete that range from all three tables,
  aggregate, log, drop the stage, `rm` the zip. Exit non-zero and keep the zip
  on any failure. A `--limit`ed load never deletes the archive.
- `scripts/test_load.sh` — runs `load.sh` itself against hard links to the real
  zips. 17 asserts; prints PASS/FAIL and exits non-zero on any FAIL. SKIPs
  cleanly when `data/raw` is empty.
- `scripts/ch.sh` — gained `CH_PATH` so the test gets a throwaway store.

**Interfaces:** later sessions rely on the table names and columns above.
**Never group on a raw `Ship type` or `Type of mobile` column** — neither is
constant within a vessel-day; read the resolved values from `vessel_day` or
`ais_clean`.

**Do:**
- [x] Write `sql/01_schema.sql`; run it; the tables exist.
- [x] Write `sql/03_aggregate.sql` and `scripts/load.sh`.
- [x] Write `scripts/test_load.sh`; ALL PASS. *(Written after the SQL, not
      before it as planned. Compensated by breaking the logic deliberately and
      confirming each assert fires — see `docs/STATUS.md` § S2 design review.)*
- [x] Load `aisdk-2025-07-16.zip` for real: 20 398 510 rows in 8 s
      (2.55 M rows/s), `data/ch` 7.7 MB.

**Validate:**
```bash
scripts/test_load.sh                                  # ALL PASS
scripts/load.sh data/raw/aisdk-2025-07-16.zip         # ends with "loaded … rows in … s", zip removed
scripts/ch.sh -q "SELECT count(), uniqExactMerge(vessels) FROM h3_hourly"
du -sh data/ch                                        # tens of MB for one day
```

**You verify:** the zip is gone, `data/ch` is small, `load_log` has one row, the
test prints ALL PASS.

**Gate B1: PASSED.** Loader idempotent and tested; 2.55–2.91 M rows/s against a
300 k target.

**Commit:** `feat(s2): streaming loader into hourly H3 aggregates`

---

## S3 — Phase-0 charts: three months, three shapes *(done — Gate B2 open for the human)*

**Goal:** Download and load January, June and July 2025 in full (92 daily files,
~72 GB traffic, nothing kept). Produce three quick charts and decide whether the
story holds. *(June was promoted from "if time allows" to the queue before the
run — it is the only month that can answer the regatta question.)*

**Files (as built — `docs/STATUS.md` § S3 has why each differs):**
- `scripts/run_queue.sh <dates-file>` — reads dates one per line, runs
  `fetch.sh` then `load.sh` for each, appends to `${QUEUE_LOG:-data/queue.log}`,
  skips dates already in `load_log` *before downloading them*, stops on the
  first failure. Resolves the archive directory from `${AIS_RAW:-data/raw}`,
  the same variable `fetch.sh` reads. Safe to re-run.
- `queues/phase0.txt` — 92 dates: 2025-07, then 2025-01, then 2025-06.
- `sql/10_season_daily.sql` — per (day, mobile) for leisure: `present`,
  `active` (= `moving_msgs > 0`), 7-day mean of `active` partitioned by month.
- `sql/11_week_profile.sql` — mean `moving_msgs` per *occurrence* of each
  weekday, per month, per (ship_group, mobile), plus each weekday's share.
- `sql/12_day_profile.sql` — `moving_msgs` by local hour, per month, per
  daytype (weekday / sat / sun), normalised within each fleet.
- Both time-of-day queries drop local days that are not fully covered (UTC+2
  leaves the first local day of a block missing two hours).
- `notes/s3-phase0.md`, three PNGs under `notes/img/`, `notes/plot.py`,
  `notes/pyproject.toml`. **`matplotlib` only — no `clickhouse-connect`:** it
  is a client for a *server*, and this project runs none. `plot.py` shells out
  to `scripts/ch.sh` and reads TSV.

**Do:**
- [x] Write and start `scripts/run_queue.sh queues/phase0.txt` under
      `caffeinate -i`. 92 files in ~2 h 45 m.
- [x] While it runs, write the three SQL files — against a **copy** of the
      store via `CH_PATH`, never `data/ch`: `clickhouse local` locks `--path`
      exclusively and a stray reader can kill the running loader.
- [x] Plot; findings with numbers in `notes/s3-phase0.md`. Sjælland Rundt and
      Kiel Week do **not** show as spikes in a national daily count — see
      finding 6 there, and do the spatial version in S6 instead.

**Validate:**
```bash
scripts/ch.sh -q "SELECT count() FROM load_log"                 # 92
scripts/ch.sh -q "SELECT day, uniqExact(mmsi) FROM vessel_day WHERE ship_group='leisure' GROUP BY day ORDER BY day LIMIT 5"
scripts/ch.sh -q "SELECT min(day), max(day), count(DISTINCT day) FROM vessel_day"
uv run --project notes notes/plot.py                            # writes notes/img/*.png
du -sh data && df -h . && ls data/raw                           # 1.5 GB, data/raw empty
```

**You verify:** look at the three PNGs. Does the Saturday spike read at a glance?
Do ferries and leisure have visibly different hour profiles? Is the regatta
weekend a spike or nothing?

**Gate B2 (end of phase 0):** the shapes are readable and not noise. Decide the
scope of phase 1: (a) all 2024 → today dailies + reference years 2015/2018/2021,
or (b) the full 2014 → 2026 archive. **Measured input:** 16.3 MB of store per
day → (a) is ~15 GB, (b) straight-lines to ~72 GB against a 70 GB budget, so
(b) needs a 2015 reference month measured first.

**Commit:** `feat(s3): phase-0 queue runner and first three charts`

---

## S4 — Bulk runner: nights, resume, disk guard *(done — but every cell was mirrored; the store was deleted 2026-09-03 and is rebuilt in § S4-redo. The runner itself stands.)*

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
- [x] **Never edit a script while a queue is running it.** Bash reads a script
      by byte offset as it goes; S3's run died with `line 35: t:: command not
      found` after finishing all 92 files, because the file was edited under
      the running process. Stop the runner, edit, restart — it resumes from
      `load_log`.
- [ ] **Deal with the part directories `clickhouse local` never collects.**
      *(still open — carried to S5)*
      92 days left **2 881 part directories / 54 183 files** under `data/ch/store`
      — 31 directories a day, against 134 parts that `system.parts` admits to.
      Each load runs three `DELETE` mutations, every mutation writes a new part
      version hardlinking the unchanged columns, and the background cleaner
      never runs because `clickhouse local` exits first (the same mechanism as
      S2's stage-table finding). Space is fine — the hardlinks mean 28.99 GB of
      nominal content costs 1.43 GB — but 909 days projects to ~28 500
      directories and ~535 000 files, and every `scripts/ch.sh` invocation
      scans them at startup (1.1 s today). Measure the startup cost as the run
      grows; the likely fix is a periodic `OPTIMIZE TABLE … FINAL` or a lower
      `old_parts_lifetime`, not more RAM.
- [x] **Replace "copy the store" as the way to read it during a load.** Answered:
      `cp -Rc` clones on APFS and costs nothing — measured, 0.00 GB against
      1.17 GB for a plain `cp` of the same file. S3's
      working copy of a 1.8 GB store was a real 29.8 GB, because `cp -a` does
      not preserve the hardlinks that 97 % of the store's files are. The store
      is heading for ~36 GB, where the same copy would be several hundred GB —
      the workflow does not survive its own success. Pick one before S4 needs
      it: `cp -Rc` (clonefile, same APFS volume, near-free), or stop copying
      and instead pause the queue for the seconds a query takes.
- [x] **Progress reporting reads `data/progress.tsv`, never the store.**
      `clickhouse local` locks `--path` exclusively and a stray query can make
      the *loader* fail, not just itself (`docs/DECISIONS.md`).
- [x] *(format only)* **Confirm `clickhouse local` opens a monthly zip64 archive** (14–19 GB, and
      the 2017 `all_sources_*` variants) with `file('… :: *.csv')`. If it cannot,
      fall back to the `unzip -p | clickhouse local` pipe. See the S1 entry in
      `docs/DECISIONS.md`.
- [x] Implement the guards; `--dry-run`, the mkdir lock, the free-disk floor
      and `data/progress.tsv` are in, and parallel prefetching was added after
      measuring that one connection gets a third of the link (3.6x).
- [x] Started as `queues/daily-2024-2026.txt` (909 dates). 60 s/file after the
      prefetcher, against 214 s/file before it.
- [x] Then `queues/ref-years.txt` — written and completed 2026-09-02: 36
      monthly archives (2015/2018/2021), 12.8 B rows read, store 13 GB total.
      The >4 GB member question dissolved: a monthly zip is 31 daily CSVs
      (member layout varies; glob is `**/*.csv`), and everything before
      2016-10 is a different CSV dialect — `sql/02_stage_legacy.sql`.
      `queues/full.txt` is NOT written: scope (a) was chosen at Gate B2, and
      `aisdk-2017-{02..06}.zip` does not exist in the archive.

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

## S4-redo — The reload: one rented VM, one command each way *(next)*

**Why:** S4 loaded 945 archives through `geoToH3(lon, lat, 7)` on ClickHouse
26.7, which has taken `(lat, lon)` since 25.5 (PR #78852, *Backward
Incompatible Change*). Every `h3_hourly.h3` and `vessel_day.home_h3` was
mirrored across the lat = lon diagonal into the Arabian Sea, and the S2 test
could not see it because it read `h3ToGeo` in the same swapped order. The raw
files were gone (stream-and-delete), so `data/ch` was deleted on 2026-09-03.
Evidence and the decision not to remap: `docs/STATUS.md` § S4-redo,
`docs/DECISIONS.md` 2026-09-03. Counts, `dist_nm` and `public_track` were
never wrong; only the grid was.

**Where:** a rented Linux VM, because the laptop link (~11 MB/s) makes this a
two-day job and a 1 Gbit machine next to the Danish S3 makes it a night. The
loader, the runner and the store format are unchanged; only the machine is.

| | |
|---|---|
| Machine | Ubuntu 24.04 · 8 vCPU · 32 GB · ≥ 300 GB NVMe · Amsterdam / Frankfurt / Helsinki |
| Candidates | Vultr `vc2-8c-32gb` $0.219/h (email + SMS + card, no ID) · UpCloud 8xCPU-32GB $0.356/h (card + €10 deposit) · Hetzner CX53 $0.056/h (may ask for ID) |
| Budget | $10; expected $2–5 |
| Queue | `queues/daily-2024-2026.txt` (909) → `queues/ref-years.txt` (36) → `queues/storms.txt` (4) — 949 archives, ≈ 1.4 TB in, ≈ 15 GB out |
| Time | ≈ 9–10 h serial loading if the VM's CPU matches the M4; a second night if it does not — acceptable, decided 2026-09-03 |
| ClickHouse | pinned to the laptop's **26.7.5.10** by `scripts/vm/bootstrap.sh` |
| SSH key | `~/.ssh/seafolk_vm` (ed25519, made 2026-09-03; public half goes into the provider console) |

**Files:**
- Modify: `scripts/ch.sh` (H3 order settings pinned), `sql/03_aggregate.sql`
  and `sql/01_schema.sql` (`geoToH3(lat, lon, 7)`), `scripts/test_load.sh`
  (external-oracle assert on Copenhagen's cell id).
- Create: `scripts/vm/bootstrap.sh` (on the VM: packages, pinned ClickHouse,
  clone, schema), `scripts/vm/night.sh` (on the VM: the three queues in one
  `tmux` session, `AHEAD=8`), `scripts/vm/pull.sh IP` (on the laptop: refuses
  while the queue runs, streams `data/ch` home as a hardlink-preserving
  tarball, verifies the invariants).
- Create: `queues/storms.txt` — 2022-01, 2022-02, 2023-02, 2023-12 (Malik,
  Nora, Otto, Pia: chapter 04's validation storms, never in scope (a)).

**Do — the night:**
- [ ] Operator (ten minutes, then sleep): create the instance with the public
      key from `~/.ssh/seafolk_vm.pub`; create a provider API token; hand the
      session the IP and the token in an environment variable.
- [ ] `ssh -i ~/.ssh/seafolk_vm root@IP 'bash -s' < scripts/vm/bootstrap.sh`
- [ ] `ssh -i ~/.ssh/seafolk_vm root@IP 'cd seafolk && scripts/vm/night.sh'`
- [ ] Every couple of hours: `ssh … tail -3 seafolk/data/progress.tsv`, report
      ETA, rate and free disk to the user in the chat. Never query the store
      on the VM while the queue runs (exclusive lock — `docs/DECISIONS.md`).
- [ ] Morning: `scripts/vm/pull.sh IP` (no `data/ch` may exist locally — the
      operator deleted it on purpose). Read its verification block.
- [ ] Destroy the instance through the API, then tell the operator to log out.
      Check the exact call against the provider's docs that night; the shapes:
      Vultr `DELETE https://api.vultr.com/v2/instances/{id}` with
      `Authorization: Bearer $VULTR_API_KEY`; Hetzner
      `DELETE https://api.hetzner.cloud/v1/servers/{id}`; UpCloud
      `DELETE https://api.upcloud.com/1.3/server/{uuid}?storages=1` (stop it
      first). Confirm with a GET that it is gone.

**Validate:**
```bash
scripts/test_load.sh                                                   # ALL PASS, incl. the Copenhagen oracle
scripts/ch.sh -q "SELECT count() FROM load_log"                        # 949
scripts/ch.sh -q "SELECT sum(msgs) = (SELECT sum(rows_kept) FROM load_log) FROM h3_hourly"   # 1
scripts/ch.sh -q "SELECT count() FROM h3_hourly WHERE h3 = 608531686258376703"               # > 0: Copenhagen exists
scripts/ch.sh -q "SELECT count() FROM (SELECT DISTINCT h3 FROM h3_hourly) WHERE h3ToGeo(h3).1 NOT BETWEEN 52.9 AND 59.1"  # 0
scripts/ch.sh -q "SELECT toYear(day), count(DISTINCT day) FROM vessel_day GROUP BY 1 ORDER BY 1"
df -h . && du -sh data/ch
```

**You verify:** the provider console shows no instance and the account has no
running charges; `data/ch` is on the laptop and nowhere else.

**Gate C′:** 949 files in `load_log`, invariant exact, Copenhagen's cell
non-empty, zero mirrored cells, VM destroyed, `data/ch` ≤ 40 GB.

**Commit:** `data(s4-redo): store rebuilt on a VM with the correct H3 grid`

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
  **Measured in S2 (2025-07-16): the res-7 hourly Class B layer does not
  survive k >= 5 — it keeps 7.3 % of cells and 47.7 % of the movement. Res 5 /
  daily keeps 38.1 % and 91.8 %. So the hourly Class B layer is not published
  at any k; `leisure_daily.parquet` is the leisure product, and the hourly
  res-7 export is Class A only.**
  **`vessels` is exported as `uniqExactMerge(vessels)`, a number. The
  `AggregateFunction` column itself is a membership oracle over MMSI and must
  never be written to a file** — see `docs/DECISIONS.md`.
- Create: `scripts/export.sh` — runs the export into `dist/dataset/`, then
  `scripts/test_export.py` (uv): asserts no row with Class B and vessels < 5,
  asserts no MMSI-like column, asserts row counts vs ClickHouse. Fails loudly.
- Create: `dist/dataset/README.md` — data card: source, licence (CC BY 4.0 +
  DMA attribution), grain, privacy rule, known biases (from S10), schema,
  citation.
- Create: `scripts/publish_hf.sh` — `huggingface-cli upload` to
  `datasets/<user>/seafolk-danish-ais` (dependency line in DECISIONS).
- Create: `CITATION.cff` (repo root) — GitHub renders a "Cite this repository"
  button from it natively, no dependency. Filled in with the Zenodo concept-DOI
  once it is minted.

**Do:**
- [ ] **Read the DMA terms of use verbatim before exporting anything.** The
      published licence line in `README.md` (CC BY 4.0 on the aggregates) is
      currently an assumption, not a checked fact. Copy the exact required
      attribution string and any disclaimer — AIS providers commonly require a
      "not for navigation" notice — into `docs/DATA.md`, and use that exact
      wording in the data card. If the terms forbid redistribution of
      derivatives or impose share-alike, stop: the licence claim in `README.md`
      is wrong and has to change before anything is published.
- [ ] Export, then publish to three places: GitHub Release, Hugging Face, and a
      Zenodo record under CC BY 4.0. Take the Zenodo **concept** DOI — it always
      resolves to the newest version — and write it into `dist/dataset/README.md`,
      `CITATION.cff`, the root `README.md` and the Hugging Face card. One
      canonical address, two mirrors pointing back at it. Releases and Hugging
      Face are where people download; only the DOI is something a paper can cite,
      and the researchers in the S15 outreach list need exactly that.

**Validate:**
```bash
scripts/export.sh          # PASS from test_export, sizes printed
```

**You verify:** open one Parquet in DuckDB/Polars, try to find any Class B cell
with < 5 vessels. There must be none. The DOI resolves to the dataset, and the
data card carries a ready-to-paste "cite as" block and the DMA attribution string
copied word for word.

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
- **The visual system is already prototyped in `site/day-clocks.html`** (built
  in S3 as a phase-0 taste): Bodoni Moda / Karla / IBM Plex Mono, a cool marine
  neutral, and one accent reserved for the leisure fleet while every working
  fleet shares a muted ink. The "daily fingerprint radial" in the list above is
  that page. Reuse its tokens rather than inventing a second system, and keep
  the pattern of embedding each page's numbers in an inline JSON block that
  `scripts/build_site_data.sh` rewrites — one file that works from `file://`,
  from Pages, and as a published artifact.
- Create: `scripts/build_site_data.sh` — SQL → `site/data/*.json`.
- Create: `.github/workflows/pages.yml` — deploy `site/` to GitHub Pages.
- Create: `site/method.html` (EN) and `site/ru/method.html` — the privacy method
  note: what a Class B transponder is, why every other pipeline throws it away,
  k ≥ 5, H3 res 7, what is never published and why that is enough. Compiled from
  `docs/DECISIONS.md` and the data card — not new work. Linked from the essay,
  the data card and the root `README.md`. "Are you tracking private boats?" is
  the first question the project will be asked in public; the answer has to
  already exist at a URL, not be improvised in a comment thread.
- Create: a Danish summary of the essay, ~300 words — `site/da/index.html` or a
  `lang="da"` section. Not a full translation. Waves 2 and 3 in S15 are addressed
  to Danish clubs, island municipalities and local papers; they will read an
  English page but they forward a Danish one.
- Add: a `<script type="application/ld+json">` block, `@type: Dataset` — `name`,
  `description`, `license`, `identifier` (the S11 DOI), `creator`,
  `temporalCoverage`, `spatialCoverage`, `distribution` — on whichever page ends
  up being the dataset's landing page. This is what Google Dataset Search
  indexes; without it the dataset does not exist for it. Independent of where the
  site is hosted.

**Validate:** Lighthouse ≥ 90 perf/accessibility locally; every chart has a
table fallback; page renders without JS errors in Safari and Chrome; dark mode
checked; `validator.schema.org` reports no errors on the dataset landing page.

**You verify:** read it end to end in both languages as a stranger. Three
sailors read the draft, and one Danish reader checks the Danish summary and the
island and storm names in it.

**Commit:** `feat(s12): essay site`

---

## S13 — The explorer

**Files:**
- Create: `scripts/build_tiles.sh` — `h3_hourly` → monthly res-7 aggregates →
  GeoJSON → PMTiles (tippecanoe; dependency line), one layer per `ship_group`.
- Create: `site/explore/` — MapLibre + deck.gl H3HexagonLayer, year/month slider,
  group toggles, island pages (`site/explore/islands/<slug>.html`) fed by
  `ferry_daily.parquet`. Each island page opens with a Danish paragraph — these
  pages are what wave 3 in S15 mails to Ærø, Samsø, Læsø, Anholt and Bornholm.

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
- **An animated version of the day clocks** — the four wind roses of
  `site/day-clocks.html` with a hand sweeping the 24 hours, or the same dial
  morphing January → July. Short loop, GIF/MP4, made to be posted on its own
  without the essay around it. Requested after seeing the static page; it is
  the one chart in the project whose finding is a *cycle*, so it is the one
  that actually earns motion.

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
