# Status — living handoff log

Newest session on top. Each entry: what was done, findings with numbers, open
questions, and the exact next session. Write it for someone with zero context.

**Next session: S4-redo** — the reload on a rented VM, `docs/PLAN.md` § S4-redo.
The first store was mirrored (below) and has been deleted; S5 runs after it.

---

## S4-redo (prep) — The grid was mirrored; store deleted, reload prepared — 2026-09-03

**What happened.** S5 opened by checking the grid it was about to join
context layers to, and the grid was wrong. ClickHouse 25.5 changed `geoToH3`
to take `(lat, lon)` (PR [#78852](https://github.com/ClickHouse/ClickHouse/pull/78852),
*Backward Incompatible Change*; 25.1 did the same to `h3ToGeo`'s result,
[#74719](https://github.com/ClickHouse/ClickHouse/pull/74719)). The installed
binary is 26.7.5.10 (2026-08-21, before any load). S0 had written the pre-25.5
`geoToH3(lon, lat, 7)` into the plan and S2 implemented it, so **every cell of
all 945 archives was mirrored across the lat = lon diagonal into the Arabian
Sea.** The proof, in the order it was gathered:

```
system.settings: geotoh3_argument_order = lat_lon (default)   ← the engine's own statement
Python h3 (reference library), Copenhagen 55.676N 12.568E res 7:  608531686258376703
clickhouse geoToH3(55.676, 12.568, 7)                            608531686258376703   (lat first: same)
clickhouse geoToH3(12.568, 55.676, 7)  — as in 03_aggregate.sql  609739203143532543
rows in h3_hourly at the true Copenhagen cell:   0
rows at the mirrored one:                      528
distinct cells: 217 949 · centre in Danish bbox: 0 · centre in mirrored bbox (lat 3–17, lon 53–59): 217 441
six busiest cells, decoded by the h3 library: 10.6N 57.7E … — Skagen, Hirtshals, Hanstholm,
                                              Esbjerg, Thyborøn, Frederikshavn once the pair is swapped
```

**Why the test did not catch it.** `test_load.sh` assert 4 read `h3ToGeo(h3).2`
as latitude — the same swapped convention as the code — so it was symmetric
under the swap. Worse, the S2 entry below records a mutation check ("swapping
to `(lat, lon)` moves 13 873 cells out of the bbox") that fed the *correct*
call, saw the assert fail, and logged that as proof the oracle worked. S1 had
asked for "one known harbour cell" — the external oracle — and S2 substituted
the round trip. Chain: S0 `b5ee044` (plan text, Fable 5), S2 `b8cf176` (code
and test, Opus 5). Reasoning effort is not recorded anywhere.

**What was and was not damaged.** Only `h3_hourly.h3` and
`vessel_day.home_h3`. Every count, `dist_nm` (uses `geoDistance`, unaffected),
`public_track` (real lat/lon) and every S1–S4 finding stand.

**Remap was measured and rejected.** Un-swapping each mirrored cell's centre
and asking for the true cell (300–400 k random bbox points): 66.4 % exact at
res 7, 100 % within one ring, 85.9 / 93.4 / 97.4 % at res 6 / 5 / 4; median
position error 941 m against the 817 m floor of res 7 itself; 48 % of mirrored
footprints lie inside one true cell, 50 % straddle two. Usable for a chart, not
for a dataset whose claim is an exact H3 grid, and the sub-cell position is
gone with the raw files — so the store was deleted and is rebuilt from the
archive. `docs/DECISIONS.md` 2026-09-03 (three entries).

**Two scope facts surfaced on the way.** (1) Chapter 04's validation storms
Pia (2023-12) and Malik (2022-01) were never in scope (a) — `queues/storms.txt`
adds 2022-01, 2022-02, 2023-02, 2023-12. (2) The laptop is download-bound at
~11 MB/s; the reload moves to a rented VM (§ S4-redo in the plan), full scope,
as many nights as it takes — user's decision 2026-09-03.

**Done today:**
- `data/ch` deleted (13 GB → 314 GB free); `data/sample/aisdk-2025-08-01.zip`
  kept as the test fixture.
- `scripts/ch.sh` pins `--geotoh3_argument_order=lat_lon
  --h3togeo_lon_lat_result_order=0`; `sql/03_aggregate.sql` and the schema
  comment use `geoToH3(lat, lon, 7)`; `scripts/test_load.sh` asserts the
  hard-coded Copenhagen id and reads the bbox with the correct accessor.
  Verified to **fail on the old SQL** (`expected 0, got 23137`) and pass on
  the new.
- `scripts/vm/bootstrap.sh`, `night.sh`, `pull.sh`; `queues/storms.txt`;
  SSH key `~/.ssh/seafolk_vm`. See "Validate" below for what was run.
- Design review (below): four findings, four fixes, `3803bdc`.
- `docs/PLAN.md` § S4-redo, `docs/DECISIONS.md` ×3, this entry.

Commits: `2c1215f` loader fix + oracle test · `c54b4d9` VM scripts, storm
queue, runner portability · `3803bdc` review fixes · docs follow.

### Validate — real output

Laptop, after the fix (`scripts/test_load.sh` — 44 PASS, 1 SKIP at `2c1215f`; 46 PASS after the review's `home_h3` asserts, `3803bdc`):

```
PASS  geoToH3 takes (lat, lon): Copenhagen cell matches the h3 reference library
PASS  every h3 cell maps back into the Danish bbox
…
ALL PASS
exit=0
```

The same suite with the two calls reverted to `geoToH3(lon, lat, 7)`:

```
FAIL  every h3 cell maps back into the Danish bbox — expected 0, got 23137
FAILURES ABOVE
exit=1
```

The pin, straight from `clickhouse local`:

```
--geotoh3_argument_order=lon_lat  → 609739203143532543   (the mirrored id)
--geotoh3_argument_order=lat_lon  → 608531686258376703   (Copenhagen, = Python h3)
h3ToGeo(871f05831ffffff) under the pin: (55.6819, 12.5710)   (lat, lon)
```

`ubuntu:24.04` in Docker (aarch64), `scripts/vm/bootstrap.sh` then one real day:

```
ClickHouse local version 26.7.5.10 (official build).
get   http://aisdata.ais.dk/aisdk-2025-08-02.zip
ok    aisdk-2025-08-02.zip (663M)                                   1m12s
loaded  aisdk-2025-08-02.zip: 20292239 rows read, 18961928 kept in 8s (2536529 rows/s), zip removed
SELECT count(), uniqExactMerge(vessels) FROM h3_hourly          → 176429  7156
sum(msgs) = sum(rows_kept)                                       → 1
$ scripts/run_queue.sh --dry-run queues/storms.txt
queue    4 dates to load, 0 already in load_log … free disk 297 GB, floor 30 GB
$ scripts/vm/night.sh   (queues stubbed to a loaded date)
chain exited 0 · no lock left behind
$ scripts/vm/pull.sh    (docker exec standing in for ssh)
invariant_ok: 1   h3_msgs: 18961928   log_rows_kept: 18961928   files: 1
```

(The container cloned HEAD before the fix commit, so those 176 429 cells are
still mirrored — the run proves the Linux pipeline, not the grid.)

```
$ df -h . && du -sh data
314Gi free · 661M data (the test fixture) · data/ch absent by design
```

### Design review

`punchcard:punchcard` on `1949b85..c54b4d9`, three finder passes as subagents.
Verdict **🟠 Ship after #1** — four findings, **all four accepted**, fixed in
the follow-up commit, each fix exercised for real:

1. 🔴 *`pull.sh` printed "destroy the instance" on a partial, broken or
   mirrored store.* Its verify block printed the checks and exited 0 whatever
   they said; a finder drove a real `run_queue.sh` into the disk-floor STOP
   and showed the chain's exit, the lock's removal and the tmux session's end
   all passing the liveness gate, with `invariant_ok: 1, files: 0` — the
   invariant holds on any prefix and held on the mirrored store too. Fixed:
   refuse unless `night.log` ends in `chain exited 0`; extract into
   `data/ch.incoming`; require invariant 1, `load_log` = 949, rows in the
   ring around the h3 library's Copenhagen cell, zero mirrored centres; only
   then `mv` to `data/ch`, else exit 1 and say DO NOT DESTROY. Every branch
   run through ssh/scp shims against a scratch store (exit codes 1,1,1,1,1,1,0).
2. 🟡 *A re-run of `bootstrap.sh` did `git pull` under the running runner and
   opened the store under the loader's lock*, while its header said
   "idempotent". Fixed: refuses while tmux session `=queue` exists (verified
   on `queue`, and that `queue-old` does not trip it).
3. 🟡 *`[ -e data/ch ]` could not tell a store from the empty scaffold any
   `scripts/ch.sh` call leaves behind, or from a truncated tar.* Fixed: only a
   `data/ch/metadata` refuses; the scaffold is cleared; rubble lands in
   `data/ch.incoming` and is named as rubble on the next run.
4. 🟡 *`vessel_day.home_h3` was the one h3 column no assert read* — reverting
   its `geoToH3` alone left the suite green. Fixed: a bbox assert over
   `home_h3` and the exact cell `608531670018031615` for the legacy fixture's
   55.123456/12.654321 from the Python `h3` library. 46 PASS.

Notes taken without cards: `BatchMode=yes` on the pull's ssh (done), `=queue`
exact matching (done), `apt-get </dev/null` under `bash -s` (done),
`/root/seafolk` as two literals in `bootstrap.sh` and `pull.sh` (left — one
value, two files, both in the same directory), and the H3 pins equalling the
26.7 default so their removal is not caught by a test on this engine (by
design: they exist for the next engine).

### Open questions for S4-redo (the night)

- Which provider the user picks decides the destroy call; confirm it against
  the provider's API docs that night before relying on it.
- Whether the VM's 8 vCPU match the M4 for the serial load (27 s median per
  daily file at home). If not, the run spills into a second night — accepted.
- `sql/13_coverage_daily.sql` keys on `toDate(ts_min)` and the part-directory
  question — both carried from S4-tails, unchanged.

**Next session: S4-redo.** Read `docs/PLAN.md` § S4-redo. S5 follows it.

---

## S4-tails — Reference years and the monthly loader — 2026-09-01 → 09-02 *(S4 closed)*

**Done:** all three tails. (1) `load.sh` runs its four DELETEs only when the
range actually holds something — a fresh range costs **zero mutations** (the
35 fresh monthly loads produced 0 instead of 140). (2) One 2015 month was
loaded by hand and the question it was meant to settle **dissolved**: there is
no >4 GB member — a monthly zip is **31 daily CSVs**, sometimes at the root,
sometimes under `FtpRoot/ais_data/` (varies month to month with no rule).
(3) `queues/ref-years.txt` written and completed: **36 monthly archives,
2015/2018/2021, ~592 GB of traffic, ~26 h wall including incidents.**

```
load_log: 945 files (909 daily + 36 monthly), 30.49 B rows read, 28.37 B kept
sum(msgs) over h3_hourly == sum(rows_kept) == 28 368 283 499, exact
2015: 365 days, 33 328 vessels · 2018: 365, 40 887 · 2021: 365, 35 557
2004 distinct days total; data/ch 13 GB against the 40 GB gate; data/raw empty
```

**Gate C re-confirmed at the new size: 13 GB ≤ 40 GB.** A reference month
costs ~190 MB of store.

### The discovery that rewrote the plan: eras, not archives

The monthly files are not "the same CSV, bigger". Probed by HTTP range reads
(central directory + inflated first member — no full downloads), then verified
by loading:

- **Dialect boundary at 2016-09/2016-10.** Before it: no header row, `;`
  delimiter, decimal **comma**, 22 columns. After: header, `,`, decimal point,
  22 then 26 columns. No month mixes the two. `sql/02_stage_legacy.sql` parses
  the old era positionally; `load.sh` picks the parser by reading the
  archive's own first line (0.05 s on a 17 GB zip), not by trusting a date
  rule. The 12 columns we do not keep are the same 12 in both eras — nothing
  was lost to the dialect.
- **Member layout flips month to month** (2015-01 root, 2015-07 subdir,
  2017-01 subdir, 2017-07 root) — the glob is now `**/*.csv`.
- **zip64 offsets past 4 GB work** (last member of 2015-07 starts at ~17 GB
  and reads fine). The >4 GB *member* case does not exist in this archive.
- **`aisdk-2017-{02..06}.zip` is 404 at both URL layouts.** Five months of
  2017 are not fetchable; `queues/full.txt` (scope b) must handle that if it
  is ever written.

### ⚠️ Data finding for S10: the archive itself duplicates late-Aug/Sep 2015

`msgs` per leisure vessel-day in 2015-09 averages **7 512** against 2 600–3 700
in every neighbouring month, with a max of **352 163 msgs/vessel-day ≈ 4/s
sustained for 24 h** — physically above what an AIS transponder emits. The
elevation runs **2015-08-28 → 2015-09-30** and crosses three different zip
files, so it is upstream feed duplication in the archive, not our loader (the
sum(msgs) == rows_kept invariant is exact, and the elevation is in the source
rows). `vessels` (uniqExact) and `dist_nm` (the ≥1 s step guard drops
same-second duplicates) are structurally immune; **message counts for that
window are ~2.3x inflated and S10 must mask or normalise it** before any
2015-vs-2018-vs-2021 message chart.

### The adoption curve, first sight (present vessels, July, peak day)

```
2015: 2 055   2018: 3 598   2021: 5 068   2024: 6 903   2025: 7 400   2026: 7 676
```

3.7x in eleven years. How much is boats vs transponders vs receivers is
exactly S10's question — but the reference years now exist to answer it.

### Four defects fixed mid-run, all monthly-scale diseases

The daily queue could never have hit any of these:

1. **OOM at 806 M rows** (`a285c0e`). 2015-09 has 2.2x July's rows and blew
   the 21.6 GiB memory cap inside aggregation. `ch.sh` now sets
   `max_bytes_before_external_group_by/sort=6 GB` — the same file then loaded
   in 308 s, invariant exact.
2. **The 20-minute fetch fallback raced the prefetcher** (`965ce50`). A
   monthly download takes 30–90 min, so the runner started a second
   `curl -C -` into a file the prefetcher was still writing. Two writers
   corrupted `aisdk-2015-08.zip` twice and `2015-11` once — the "corrupt"
   files were our own interleaved bytes, verified by re-downloading 2015-08
   single-writer (byte-exact vs Content-Length, full CRC pass).
3. **"Stopped growing" is not "abandoned"** (`5f9bb6c`). The first fix's
   3-minute no-growth trigger fired during `fetch.sh`'s own `unzip -tq`
   (4–8 min on a monthly zip, file static) and deleted a *complete* archive.
   A date is busy while a live process names its zip (`pgrep`), idle 30 s is
   the fallback trigger.
4. **Legacy dialect + glob** (`d434154`, the discovery above), including a
   `kept > 0` guard so a wrong positional column order can never delete a
   17 GB archive while logging a "complete" load of zero vessels.

### Validate — real output

```
$ scripts/run_queue.sh --dry-run queues/ref-years.txt
queue    0 dates to load, 36 already in load_log

$ tail -3 data/progress.tsv
2026-09-02 12:56:07	2021-10	245	25	2	1.7
2026-09-02 12:58:27	2021-11	140	26	1	0.8
2026-09-02 13:31:22	2021-12	1975	27	0	0.0

$ scripts/ch.sh -q "SELECT toYear(day), count(DISTINCT day), uniqExact(mmsi) FROM vessel_day GROUP BY 1 ORDER BY 1"
2015	365	33328
2018	365	40887
2021	365	35557
2024	306	40138
2025	365	43772
2026	238	41625

$ scripts/test_load.sh
… ALL PASS

$ df -h . && du -sh data/ch
305Gi free · 13G data/ch · data/raw empty
```

### Design review

`punchcard:punchcard` on `cedbbed..HEAD`, three finder passes as subagents.
Verdict **🟡 Ship with care** — three findings, **all three accepted** and
fixed in `6ae991a` (each fix verified live, incl. reproducing the orphan
curl with the pre-fix fetch.sh): the worker-detection wait had no
upper bound and an orphaned curl — observed live during the run — could pin
it forever; the runner could read the prefetcher's pid file before it existed
and start a second writer on the queue's first date; and no test covered the
crash-between-INSERTs recovery that the DELETE guard was redesigned around
(its three table terms could be deleted with the suite staying green), nor
the `kept > 0` and dialect-sniff error arms. Out-of-scope notes recorded:
the Sep-2015 archive duplication (above, → S10); a latent pre-existing risk
that one wrong-date row stretches the DELETE range across years (a
staged-span sanity check is a cheap S5+ addition); `**/*.csv` would match
`__MACOSX/._*.csv` junk if a pre-2014 archive carries it; the 6 GB spill
writes into the same disk `FREE_FLOOR_GB` guards, checked only between files;
`kept > 0` would block a genuinely vessel-free 2006–2008 month (documented
tradeoff, needs a flag only if scope (b) happens).

### Deviations from the plan of record

- The plan's "conditional DELETE keyed on load_log overlap" was implemented
  as a count of what the DELETEs would actually remove — the load_log-only
  version silently breaks crash recovery (demonstrated before coding).
- `queues/full.txt` is **not** written: scope (a) was chosen at Gate B2, and
  five 2017 months are missing from the archive anyway.
- Role note: the incident-response fixes (2–4 above) were implemented
  directly by the supervising session mid-run rather than dispatched, to keep
  the queue's downtime short; everything else ran through subagents with
  review checkpoints.

### Open questions for S5

- **`sql/13_coverage_daily.sql` keys on `toDate(ts_min)`** — with monthly
  files in load_log, one day per month now carries the whole month's
  `rows_read` and the other 30 report nothing. S10's coverage query must
  aggregate differently (h3_hourly knows the truth; load_log no longer maps
  1:1 to days).
- The part-directory question (carried from S4 main) stands; 13 GB store,
  cold `SELECT 1` startup should be re-measured before S6's heavy queries.
- Sep-2015 duplication needs a mask/normalisation decision in S10 (above).

**Next session: S5 — context layers.** Read `docs/PLAN.md` § S5.

---

## S4 — Bulk runner — 2026-08-31 → 09-01 *(Gate C passed)*

**Done:** `scripts/prefetch.sh` (new), `scripts/run_queue.sh` (lock, `--dry-run`,
`data/progress.tsv`, free-disk floor), `scripts/fetch.sh` (retry gap),
`sql/13_coverage_daily.sql`, `queues/daily-2024-2026.txt` (909 dates).
`scripts/test_load.sh` is now **23 asserts, ALL PASS**.

**Gate C: PASSED — the queue finished, 2026-09-01.**

```
909 files, 909 distinct days, 2024-03-01 → 2026-08-26, zero gaps
17.67 billion rows read, 16.28 billion kept
sum(msgs) over h3_hourly == rows_kept exactly
4.42 M vessel-days, 188.29 M rows in public_track
0 rows where rows_read != non_vessel + sentinel + out_of_bbox + kept
data/ch 6.2 GB against a 40 GB gate, data/raw empty, 305 GB free
```

**The store is far smaller than projected: 6.8 MB per day, not 16.3.** The S3
figure was measured before ClickHouse's background merges had run; over 909
days they compact the parts by more than half. The part directories peaked at
**116 161 mid-run and settled at 14 723** once the merges caught up, and a cold
`scripts/ch.sh -q "SELECT 1"` is **0.43 s** — no lasting startup cost. Scope
(a)'s reference years (~1 095 days) therefore project to ~7.5 GB and all of
scope (a) to ~14 GB, against the ~36 GB this entry estimated yesterday.

**But the slowdown during the run was real:** 62 s/file over the first 50 files,
168 s over the last 25, and the per-load median rose from 40 s to 67 s as the
part count climbed. It recovered only after the run ended and the merges ran.
For the reference years — 1 095 files, ten times the tail that hurt here — the
DELETE-per-load that creates those mutations should be made conditional first;
in a bulk pass the range is always empty, because the runner already skips
dates that are in `load_log`.

The reference years (2015/2018/2021) are not started; see the open questions.

### The measurement that shaped the session

The archive throttles a single connection. Measured by running extra streams
alongside a live queue:

```
1 stream    3.78 MB/s
3 streams   7.81 MB/s aggregate   (3.77 + 2.32 + 1.71)
link total  ~11 MB/s              (matches the 11.7 MB/s measured in S3)
```

So serial downloading was wasting two thirds of the bandwidth — ~183 s of the
~214 s each file took. `scripts/prefetch.sh` downloads up to `AHEAD` (3) files
at a time while loading stays strictly serial (the store lock). Measured on the
live run afterwards:

```
before   214 s/file   →  37 h for the remaining 628 files
after     60 s/file   →  10.4 h
```

**3.6x, and it is the whole reason the queue finishes today rather than
Tuesday.** Disk is bounded by counting ready archives plus live downloads, so
never more than ~3 GB of raw at once.

### Two overnight failures, both now fixed

1. **A truncated download ended the run.** After 173 files:
   `curl: (18) transfer closed with 403832654 bytes remaining to read`.
   `--retry` covers timeouts and 5xx but not error 18, so `fetch.sh` exited
   non-zero and the queue stopped for the rest of the morning. Fixed with
   `--retry-all-errors` and 10 retries; `-C -` resumes from the bytes on disk.
2. **Editing a running script killed it.** S3's run died with
   `line 35: t:: command not found` after finishing all 92 files, because the
   file was edited under the running process. **It happened again this session**
   — I rewrote `run_queue.sh` while the queue was executing it, and had to stop
   and restart. The data was never at risk (`load_log` is authoritative and
   `load.sh` rewrites a date's whole range), but the rule stands: stop the
   runner, edit, restart.

### Validate — real output

```
$ scripts/run_queue.sh --dry-run queues/daily-2024-2026.txt
queue    620 dates to load, 289 already in load_log
--dry-run: would fetch and load these, in order:
         2024-09-14
         …
         free disk 307 GB, floor 30 GB, prefetching 3 ahead

$ tail -2 data/progress.tsv
2026-08-31 07:12:07	2024-09-25	40	9	608	15.6
2026-08-31 07:15:12	2024-09-27	21	1	606	3.5

$ scripts/test_load.sh
… 23 asserts …
ALL PASS

$ df -h . && du -sh data/ch
/dev/disk3s5   460Gi   118Gi   306Gi    28%
5.3G	data/ch
```

### Findings

0. **Two and a half years of season, and the amplitude is growing.** Mean
   leisure vessels that moved per day, by month:

   ```
   2024:  Mar 162   May 1417   Jul 2690   Sep 1382   Dec  95
   2025:  Mar 143   May 1149   Jul 3109   Sep 1129   Dec  91
   2026:  Mar 179   May 1609   Jul 3356   Aug 2639   (range ends 08-26)
   ```

   July against the following December, by year: **28.3x, 34.0x, 44.7x.** The
   summer peak rises (2 690 → 3 109 → 3 356) while the winter floor falls
   (95 → 91 → 75). Whether that is more boats, more transponders or better
   reception is exactly what S10 has to separate — it is not a finding yet, it
   is the question S10 exists for.

   The all-time peak day is **2026-07-21, a Tuesday, 5 890 vessels**, with
   Sunday 2025-07-20 second. S3's finding that Saturday is not the peak day
   survives at 909 days.

1. **Class A is a 1.48x instrument, not a constant.** `sql/13_coverage_daily.sql`
   assumes commercial traffic does not move with the season. Measured over the
   909 days, the monthly mean of Class A vessels per day runs 2 010 to 2 967 —
   a 1.48x swing. Against leisure's 44.7x the signal still dominates by a
   factor of thirty, but S10 must subtract the instrument rather than assume it
   flat.

2. **zip64 is half-confirmed.** The 2015 monthly archive really is zip64 — its
   last 64 KB carry both `PK\x06\x06` and `PK\x06\x07` — and ClickHouse reads
   a forced-zip64 archive correctly (`zip -fz`, returned the right 2 rows).
   **What is still untested is the size dimension: a member larger than 4 GB.**
   That needs one real monthly file, ~19 GB, and should wait until the daily
   queue frees the link.
2. **`cp -c` clones and costs nothing; plain `cp` does not.** Measured on a
   1.17 GB file: `cp -c` took 0.00 GB, `cp` took 1.17 GB. This is the answer to
   S3's open question about copying the store — use `cp -Rc`, same APFS volume.
3. **Every date in the queue exists.** All 909 checked with HEAD requests
   against both archive layouts: zero missing. The runner stops on the first
   failure, so one absent date would have cost a night.

### Design review

`punchcard:punchcard` on `1ddc4c8..HEAD`. Three findings, **all three accepted**,
and a fourth uncovered while fixing them. Subagents were not used; the three
passes were run in sequence by hand.

1. 🔴 *`--dry-run` truncated the running queue's work list.* `data/queue.work`
   was a fixed path written before the dry-run branch, and `--dry-run`
   deliberately takes no lock — so the file had no owner. Measured live: 620
   lines to 1, after which the prefetcher hit EOF and silently stopped reading
   ahead, with no error printed anywhere. **I had told the user `--dry-run` was
   safe to run at any time.** The list now lives inside the lock directory.
2. 🟡 *The test isolated `AIS_RAW` and `QUEUE_LOG` but not `QUEUE_LOCK`* — so
   its runner assert failed with "another runner is already going" during any
   bulk run. It also drew its sample from `data/raw`, racing the live queue for
   files and sometimes picking a half-downloaded one. Samples now come from
   `data/sample`. A follow-up found `PROGRESS` unisolated too, after a test run
   appended a bogus row to the real progress file.
3. 🔵 *`prefetch.sh` had no test.* Three asserts now cover it.
4. **The fourth, found while fixing 3:** `run_queue` took the prefetcher's
   handle from `$!`, and that pid was **not** the prefetcher — the script's own
   stdout is a process substitution. `cleanup`'s `kill` therefore hit the
   caller, and the test suite died with SIGTERM after assert 13 while the
   prefetcher's own TERM trap never fired. The prefetcher now publishes its pid
   to a file and the runner kills exactly that.

### Deviations from `docs/PLAN.md` § S4

- `sql/03_coverage_daily.sql` is **`sql/13_coverage_daily.sql`**:
  `sql/03_aggregate.sql` took that number in S2.
- `flock` is a `mkdir` lock — macOS ships no `flock(1)`. A lock whose pid is
  dead is taken over rather than blocking forever.
- `queues/ref-years.txt` and `queues/full.txt` are **not** written yet; the
  reference years wait on finding 1.
- Parallel downloading was not in the plan at all. It came out of the
  throughput measurement and is the session's largest change.

### Open questions for S5

- **Finish the daily queue and check Gate C** (`data/ch` <= 40 GB — it is on
  track for ~16 GB).
- **Load one 2015 month for real** before writing `queues/ref-years.txt`, to
  settle the >4 GB member question and to measure what a month costs. Until
  then the ~36 GB projection for scope (a) is an extrapolation.
- **The part directories still accumulate.** 31 per loaded day, and nothing
  collects them because `clickhouse local` exits before the cleaner runs. At
  909 days that is ~28 500 directories. Space is fine (hardlinks); the cost to
  watch is `scripts/ch.sh` startup, 1.1 s at 92 days.
- `data/sample/aisdk-2025-08-01.zip` (661 MB) is kept on purpose so
  `test_load.sh` has a fixture; it is the one raw file the project keeps.

**Next session: S5 — context layers.** Read `docs/PLAN.md` § S5.

---

## S3 — Phase-0 charts — 2026-08-30

**Done:** `scripts/run_queue.sh`, `queues/phase0.txt` (92 dates),
`sql/10_season_daily.sql`, `sql/11_week_profile.sql`, `sql/12_day_profile.sql`,
`notes/plot.py` + `notes/pyproject.toml`, `notes/img/*.png`,
`notes/s3-phase0.md`. All of January, June and July 2025 are loaded —
**92 days, 1 878 644 705 rows read, 1 735 448 756 kept, `data/ch` 1.5 GB,
`data/raw` empty.**

**Gate B2: three shapes readable, one absent.** The season (32x), the day
(leisure 12.1 % of its movement in one hour against three fleets that are flat)
and the week are all readable. The regattas are not present at a national
daily grain. **The human's look at the three PNGs is what actually decides the
gate and the scope of phase 1** — see "You verify" below.

### Validate — real output

```
$ scripts/ch.sh -q "SELECT count() FROM load_log"
92

$ scripts/ch.sh -q "SELECT day, uniqExact(mmsi) FROM vessel_day WHERE ship_group='leisure' GROUP BY day ORDER BY day LIMIT 5"
2025-01-01	386
2025-01-02	416
2025-01-03	418
2025-01-04	427
2025-01-05	419

$ scripts/ch.sh -q "SELECT min(day), max(day), count(DISTINCT day) FROM vessel_day"
2025-01-01	2025-07-31	92

$ uv run --project notes notes/plot.py
wrote notes/img/s3-season.png, s3-week.png, s3-day.png     (+ the numbers table)

$ du -sh data data/ch ; df -h . ; ls data/raw
1.5G	data
1.5G	data/ch
/dev/disk3s5   460Gi   143Gi   281Gi    34%
(data/raw is empty)
```

The honesty layer, over all 92 files:

```
rows_read:        1878644705
rows_kept:        1735448756
non_vessel:            6.82 %   (AtoN, base stations, SAR, PIRB, MOB)
sentinel:              0.29 %   (Latitude = 91)
out_of_bbox:           0.51 %   (55 rows on 2025-01-08 … 4.70 % on 2025-06-30)
rows_read != non_vessel + sentinel + out_of_bbox + kept:  0 rows
```

`scripts/test_load.sh` — 20 asserts, run against a freshly fetched
`aisdk-2025-08-01.zip` (deleted afterwards; `data/raw` is empty by design after
S3, so the test SKIPs until someone fetches a file):

```
PASS  h3_hourly sum(msgs) == load_log rows_kept
PASS  uniqExactMerge(vessels) == count(vessel_day)
PASS  no Class B vessel in public_track
PASS  …and Class B 'Passenger' vessels do exist here (assert 3 is not vacuous)
PASS  public_track is populated
PASS  every h3 cell maps back into the Danish bbox
PASS  rows_read == non_vessel + sentinel + out_of_bbox + kept
PASS  dist_nm: something moved
PASS  dist_nm: nothing did 1500 nm in a day
PASS  --force reload does not double sum(msgs)
PASS  --force reload leaves one load_log row
PASS  second load without --force says skip
PASS  …and sum(msgs) is unchanged
PASS  vessels summed over h3_hourly groups == vessel_day rows
PASS  imo is populated for passenger vessels
PASS  no stage parts survive a load
SKIP  cross-file merge — only one archive file on disk
PASS  a load with a multi-line file on stdin writes one load_log row
PASS  run_queue skips a date already in load_log
PASS  …and downloads nothing while doing it

ALL PASS
```

### Findings

Full write-up with the charts: `notes/s3-phase0.md`. The eight headlines:

1. **The season has two sizes and a chart must say which.** July against
   January is **11.2x** on vessels *present* and **32.4x** on vessels that
   *moved*, from the same query — because in January only **23.5 %** of
   leisure vessels present ever exceed 0.5 kn, against **67.7 %** in July.
   S1's 8.6x is confirmed, not corrected: June/January on the present count is
   7.8x over whole months.

2. **A winter floor of ~96 moving leisure vessels a day**, never below 79.
   Chapter 01 cannot draw a season that starts at zero.

3. **The weekend effect is strongest when the fleet is smallest.** Leisure
   weekend/weekday: **June 1.62x, January 1.55x, July 1.11x.** July, the peak
   month, is nearly flat — the Danish holiday, sailing on a Tuesday. No
   working fleet does this (ferries 1.01x in July, cargo 1.10x).

4. **Saturday is not the peak day and is the least predictable day.** July
   mean distinct leisure vessels that moved: Sun 3 690, Fri 3 559, Thu 3 157,
   Mon 3 084, **Sat 2 986**, Wed 2 841, Tue 2 626. Saturday's range is
   1 132–5 439 (**4.8x**), the widest of the week. This is S1's warning, now
   quantified: weather decides a Saturday.

5. **Leisure has a daily shape; the working fleets do not.** July weekday,
   busiest hour and night share (22:00–05:00, Europe/Copenhagen):

   ```
   fleet                 peak    that hour   night 22-05
   leisure   (Class B)   11:00       12.1 %         3.8 %
   ferries   (Class A)   17:00        5.1 %        22.5 %
   cargo     (Class A)   02:00        4.8 %        32.7 %
   fishing   (Class A)   00:00        5.6 %        36.0 %
   ```

   Flat would be 4.17 % an hour. Cargo and fishing peak *at night*. This is
   the most striking of the three charts and chapter 02's fingerprint.

6. **⚠️ Neither regatta is visible in a national daily count — a negative
   result.** Sjælland Rundt's Sunday (2025-06-15) is +9 % against the same
   weekday ±2 weeks and its Saturday is *below* it. Kiel Week's opening
   weekend is June's maximum and its closing weekend is June's minimum, so
   the pattern is weather. Against finding 4's 4.8x Saturday range, +9 % is
   not a signal. **S6's `sql/22_regatta_spikes.sql` must do this
   spatially** — it is the right instrument, and it should not repeat the
   national query.

7. **The out-of-bbox share swings four orders of magnitude between days** —
   55 rows of 15.1 M on 2025-01-08, 4.70 % on 2025-06-30. S1 saw a sevenfold
   swing over four days; over 92 it is far wider. S10's obligation stands and
   now has a real range.

8. **16.3 MB of store per day** (1.5 GB / 92 days; 21.6 M rows in `h3_hourly`,
   535 k in `vessel_day`, 19.1 M in `public_track`). **S4's option (a) —
   2024-03 → today, ~900 days — projects to ~15 GB**, well inside budget.
   Option (b), the full 2014 → 2026 archive at ~4 400 days, straight-lines to
   ~72 GB and would break the 70 GB budget — but that is an overestimate,
   since 2015 has far fewer transponders per day than 2025. **Before choosing
   (b), measure one 2015 reference month.**

### ⚠️ A defect in the S2 loader, found by running it 92 times

`load_log` held **8 919 rows for 92 archives** — ~98 exact duplicates each,
one per line of `queues/phase0.txt`.

`clickhouse local -q "INSERT INTO t SELECT <constants>"` binds whatever is on
stdin as its implicit input table and writes **one row per line of it**.
`scripts/run_queue.sh` runs its loop as `done < "$q"`, and `scripts/ch.sh`
passed the caller's stdin straight through. Reproduced in isolation: the same
INSERT emits 1 row with stdin on `/dev/null`, 98 with stdin on a 98-line file.

**The aggregates were never affected, and this was verified rather than
assumed.** They are written through `ch.sh`'s *file* branch, whose stdin is the
SQL file. `sum(msgs)` over `h3_hourly` equals `sum(rows_kept)` over `load_log`
to the row (1 735 448 756); `vessel_day` has 534 827 rows for 534 827 distinct
`(day, mmsi)`; `public_track` has 19 148 484 rows for as many distinct
`(mmsi, ts)`. Only `load_log` was damaged and only by exact copies, so
`OPTIMIZE TABLE load_log FINAL DEDUPLICATE` restored it to 92 rows, after which
the four counters still partition `rows_read` on every row.

Fixed with one redirect in `scripts/ch.sh` — the wrapper every caller routes
through — and pinned by `test_load.sh` assert 13, verified to fail without the
fix ("expected 1, got 3"). **If this had reached S10 unnoticed, every dropped-
row share in the essay's honesty section would have been computed from sums
inflated by the length of a queue file.**

### ⚠️ The queue run exited 127 — my mistake, not the data's

`run_queue.sh` finished all 92 dates and then died with
`line 35: t:: command not found`. Cause: I edited `scripts/run_queue.sh`
(applying the design-review fixes) **while bash was executing it**. Bash reads
a script by byte offset as it goes, so the edit shifted the offsets under the
running process and it resumed mid-token after the loop. The only thing lost
was the final `echo "queue done"`. **Rule for S4's overnight runs: never edit a
script that is running.** Everything the queue was supposed to do, it did — 92
dates in `load_log`, 92 distinct days in `vessel_day`, `data/raw` empty.

### Design review

`punchcard:punchcard` on the S3 diff (`ff8c15c^..HEAD`, touching
`scripts/run_queue.sh`, `scripts/fetch.sh`, `sql/1*.sql`, `notes/plot.py`).
Three findings, **all three accepted, none rejected.** Subagents were not
dispatched (the session forbids them), so the three passes were run in
sequence by hand.

1. 🟡 *`run_queue.sh` hardcoded `data/raw` while `fetch.sh` resolves
   `${AIS_RAW:-data/raw}`.* One copy of the archive-location rule was behind
   the other: setting `AIS_RAW` sent the download to one directory and the
   load to another, and the "did the zip survive?" guard would have fired on
   every file. Fixed — the runner reads the same variable, and `QUEUE_LOG`
   follows `CH_PATH`'s precedent so the test can redirect it.
2. 🟡 *`notes/plot.py` ran the queries with `check=True`, which reports an
   exit status and throws away the reason.* The likeliest reason is the store
   lock this session documented, so the failure now prints ClickHouse's own
   message and names that cause.
3. 🔵 *Nothing pinned `run_queue.sh`'s skip branch* — the one that decides
   whether a resumed queue re-downloads 72 GB it already has. `load.sh`'s own
   skip cannot cover it: that one fires after the file is on disk and leaves
   it there. Fixed — two asserts in `test_load.sh` with `AIS_RAW` and
   `QUEUE_LOG` pointed at throwaway paths, verified not vacuous (a date absent
   from `load_log` is not skipped; the runner goes to fetch and exits
   non-zero).

Assert 13 (the stdin defect above) came later, from running the loader 92
times rather than from the review.

### Deviations from `docs/PLAN.md` § S3

- **No `clickhouse-connect`.** § S3 named it, but it is a client for a
  ClickHouse *server* and this project deliberately runs none. `notes/plot.py`
  shells out to `scripts/ch.sh` and parses TSV. One new dependency
  (`matplotlib`) instead of two.
- June 2025 is in the queue rather than "if time allows" — confirmed with the
  user before the run. 92 dates, not 62.
- `sql/03_coverage_daily.sql` stays in S4, where the plan puts it.
- The three query files emit **all** months, groups and classes; the charts
  pick what they draw. January and June come free that way.

### Open questions for S4

- **Never edit a running script.** See the exit-127 note above. S4 leaves a
  queue running for whole nights.
- **`clickhouse local` locks `--path` exclusively** (`docs/DECISIONS.md`).
  A stray query during a bulk run can make *the loader* fail, not just itself.
  S4's progress reporting must read `data/progress.tsv`, never the store.
- **Before choosing scope (b), measure a 2015 reference month.** Finding 8's
  ~72 GB straight-line is an overestimate of unknown size.
- **`data/ch` is 2 881 part directories and 54 183 files for 92 days**, of which
  52 699 are hardlinks: 28.99 GB of nominal content over 1.43 GB of unique
  inodes. `system.parts` reports only 134 parts, so the rest are mutation
  versions the background cleaner never collected — `clickhouse local` exits
  before it runs. Harmless at this size (a query is 0.6 s), but it is 31
  directories per loaded day and S4 loads 909 of them. Two practical
  consequences: watch the startup cost as the run grows, and **never copy
  `data/ch` with `cp -a`** — it does not preserve hardlinks, so the copy is a
  real 29.8 GB, measured by `df` before and after deleting one. (An earlier
  draft of this entry claimed APFS cloning made such a copy free. It does not:
  macOS `cp` clones only when asked with `-c`.) A working copy for `CH_PATH`
  is still the right way to read the store while a load holds the lock — just
  budget the space for it, or reach for `cp -Rc`, and delete it afterwards.
- `scripts/test_load.sh` SKIPs its cross-file assert whenever `data/raw` holds
  fewer than two archives — which is always, now. S4 should decide whether the
  test fetches its own fixture or stays opportunistic.
- Why is Sunday so far above Saturday for leisure in every month (July 3 690
  against 2 986)? Return legs of weekend trips is the obvious guess; S6 can
  test it against `first_ts`/`last_ts` and `home_h3`.

### Disk

`data` 1.5 GB, all of it `data/ch`; `data/raw` empty; 281 GB free — unchanged
from the start of the session, since ~72 GB of archive passed through and was
deleted file by file. 16.3 MB of store per loaded day.

**Next session: S4 — bulk runner.** Read `docs/PLAN.md` § S4.

---

## S2 — The loader — 2026-08-30

**Done:** `sql/01_schema.sql` (five permanent tables, two stage tables, two
views), `sql/02_stage.sql` (one archive file into the stage), `sql/03_aggregate.sql`
(identity resolution + three aggregate INSERTs), `scripts/load.sh`,
`scripts/test_load.sh`, and `CH_PATH` support in `scripts/ch.sh`.
`aisdk-2025-07-16.zip` is loaded and deleted. `data/ch` is 7.7 MB.

**Gate B1: PASSED.** Loader idempotent and tested; **2.55–2.91 M rows/s**
against a target of 300 k — 8.5x headroom, no profiling needed.

`scripts/load.sh <zip>` stages the file, reads its own date range from the
staged rows, deletes that range from all three tables, writes the aggregates,
logs what it dropped, and removes the zip. `--force` reloads a logged file;
`--limit N` loads a sample and then refuses to delete the archive.

### Validate — real output

```
$ scripts/test_load.sh
sample: aisdk-2025-01-15.zip (first 2000000 rows)

PASS  h3_hourly sum(msgs) == load_log rows_kept
PASS  uniqExactMerge(vessels) == count(vessel_day)
PASS  no Class B vessel in public_track
PASS  …and Class B 'Passenger' vessels do exist here (assert 3 is not vacuous)
PASS  public_track is populated
PASS  every h3 cell maps back into the Danish bbox
PASS  rows_read == non_vessel + sentinel + out_of_bbox + kept
PASS  dist_nm: something moved
PASS  dist_nm: nothing did 1500 nm in a day
PASS  --force reload does not double sum(msgs)
PASS  --force reload leaves one load_log row
PASS  second load without --force says skip
PASS  …and sum(msgs) is unchanged
PASS  vessels summed over h3_hourly groups == vessel_day rows
PASS  no stage parts survive a load
PASS  two files merge: sum(msgs) == sum(rows_kept)
PASS  …and load_log has two rows

ALL PASS

$ scripts/load.sh data/raw/aisdk-2025-07-16.zip
loaded  aisdk-2025-07-16.zip: 20398510 rows read, 19010774 kept in 8s (2549813 rows/s), zip removed

$ scripts/ch.sh -q "SELECT count(), uniqExactMerge(vessels) FROM h3_hourly"
268161	7709

$ du -sh data/ch
7.7M	data/ch

$ df -h .          # before -> after the load
460Gi 144Gi used 280Gi avail 34%   ->   460Gi 143Gi used 281Gi avail 34%
$ du -sh data
2.7G   ->   2.0G
```

`load_log` for that file — the honesty layer S10 will read:

```
file:              aisdk-2025-07-16.zip
seconds:           8
ts_min:            2025-07-16 00:00:00
ts_max:            2025-07-16 23:59:58
rows_read:         20398510
rows_non_vessel:    1341773     (AtoN, base stations, SAR, PIRB, MOB — 6.58 %)
rows_sentinel:        22864     (Latitude = 91)
rows_out_of_bbox:     23099     (real positions outside Danish waters — 0.12 %)
rows_kept:         19010774
rows_h3:             268161
rows_vessel_day:       7709
rows_public_track:   226340
```

### Findings

1. **Throughput is a non-issue.** 20.4 M rows staged, aggregated into three
   tables and logged in 8 s. Disk: **7.7 MB for a whole day** — extrapolating,
   the 900 daily files of 2024-03 → today are ~7 GB, a tenth of the budget.
   Gate B2's scope choice in S3 is not going to be constrained by disk.

2. **A vessel does not report one identity per day, and this breaks anything
   that groups on a single message.** Two separate cases, both measured inside
   the Danish bbox, both fixed by resolving identity once per vessel-day:
   - `Ship type` — on 2025-07-12, **3 026 of 4 884 Class B vessels reported
     `Undefined` AND something else**. Grouping per message put **2 950
     vessels into two `ship_group`s at once**, so "how many leisure boats"
     was not even additive, and filed 96 156 leisure messages under `other`.
   - `Type of mobile` — **354 of 3 402 vessels on 2025-01-15 (10.4 %), and
     526 of 8 364 on 2025-06-14, reported BOTH `Class A` and `Class B`**.
     This is the privacy key, so one mislabelled message could have put a
     private vessel's positions into `public_track`.

3. **This corrects S1 finding 7.** S1 read "4 026 Class B `Undefined` vessels
   on 2025-07-12, inflating a distinct-vessel count by ~87 %" and concluded a
   raw `uniqExact(mmsi)` is a transponder count, not a boat count. The
   conclusion was right for the wrong reason: those 4 026 are not 4 026
   unclassifiable transponders. Of 4 884 Class B vessels with a position that
   day, **301 report `Undefined` and nothing else; 3 026 report it alongside
   their real type; 1 557 never report it.** The inflation was double-counting
   inside one query, not a fleet of empty transponders. `vessel_day` now
   carries one resolved type per vessel-day and the problem is gone at source.

4. **The Class A / Class B mix is bimodal, and the threshold sits in the gap.**
   Mixed vessels are either a Class A ship with a handful of stray messages or
   a genuinely ambiguous transponder, with almost nothing between:

   ```
   day          < 0.1 % B   0.1-1 % B   > 1 % B
   2025-01-15         229         110        15
   2025-06-14                     439        87     (< 1 % pooled)
   2025-07-12                     533        98     (< 1 % pooled)
   ```

   So "Class B even once" was tried and rejected: it filed ~340 obvious Class A
   ships a day as private and cut `public_track` by 21 %, costing chapter 03 a
   sixth of its ferries. **At a 1 % threshold, 285 Class A passenger vessels
   stay public and 46 Class B ones stay private**, and `public_track` holds
   226 340 rows against 222 747 under the old per-message filter — the
   difference is ferry minutes the old filter was silently dropping.

5. **The leisure fleet is a day-tripper fleet.** On 2025-07-16, per vessel-day
   distance covered while moving:

   ```
   ship_group  mobile   vessels     msgs  total_nm  median_nm  p90_nm
   leisure     Class B     4433  3229565     59436          8    36.0
   other       Class A     1093  4167722     18802        0.2    57.1
   cargo       Class A      765  4651760     70225       69.9   232.0
   fishing     Class A      408  3802314     11720       17.7    71.9
   passenger   Class A      285  2406796     20323       40.3   229.4
   ```

   **Median leisure vessel-day: 8 nm. p90: 36 nm.** Against 70 nm median for
   cargo. And leisure is **32 % of all distance sailed in Danish waters that
   day** (59 436 of 185 591 nm) on 58 % of the vessels. Chapter 01 has a second
   headline next to S1's seasonal one.

6. **⚠️ The k >= 5 rule does not survive at the working grain — S11 must
   publish coarser.** Class B cell-hours on 2025-07-16:

   ```
   grain          cells   cells surviving k>=5   messages surviving
   res7 / hour    81269                  7.3 %              47.7 %
   res7 / day     25995                 19.8 %              78.0 %
   res5 / hour    16259                 26.1 %              76.8 %
   res5 / day      1876                 38.1 %              91.8 %
   ```

   At the storage grain a k >= 5 export throws away 93 % of cells and half the
   movement. At res 5 / day it keeps 92 % of the movement. This is exactly the
   `leisure_daily.parquet` (per day, per res-5 cell) that S11 already plans —
   now with a number behind it. **The res-7 hourly layer is publishable for
   Class A, not for Class B.**

7. **Each `dist_nm` guard earns its place, and the first step is guarded
   twice on purpose.** Fleet total for 2025-07-16, in nm:

   ```
   all guards          185591
   no anchor guard     189634   (+2.2 %)
   no time guard       194392   (+4.7 %)
   no teleport guard   195042   (+5.1 %)
   no guards at all  26395719   (142x — the phantom first step, every vessel)
   ```

8. **⚠️ "Under sail or under engine?" cannot be answered from this archive.**
   `Navigational status` carries `Under way sailing` as a distinct value, which
   would be the obvious way to ask it — but the field is a Class A message
   field. On 2025-07-12 inside the bbox it is `Unknown value` on **2 704 358 of
   2 710 000 Class B messages**, and `Under way sailing` appears for **6 Class B
   vessels, 14 messages, in a whole day**. For Class A it is populated (1 988
   under way using engine, 1 008 moored, 191 at anchor, 84 under way sailing).
   The column is therefore not stored: it is dead for the fleet this project is
   about, and for Class A it only duplicates what S8 and S9 already take from
   SOG. If the essay wants to say something about sail versus motor it has to
   do it from speed and track shape, or not at all.

9. **What was kept and what was dropped, with the numbers behind each.** Raw
   files are deleted, so this was decided once. Fill rates measured on
   2025-07-12 inside the bbox:

   | column | kept? | why |
   |---|---|---|
   | `length` | **kept** in `vessel_day` | 18.4 M of 20.4 M rows, max 557 m. Boat size is the leisure fleet's one interesting attribute. |
   | `imo` | **kept** in `vessel_day` | 182 of 298 Class A passenger vessels (61 %; 58 % on 07-16, 97 % for cargo). The only stable key to ship registries — names change, MMSI is reassigned. Chapter 03's electric-ferry question needs it. |
   | `nav_status` | dropped | finding 8. |
   | `destination` | dropped | 266 of 298 ferries report it, but it is crew-typed free text; S8 assigns routes by endpoints, which is more reliable. |
   | `callsign` | dropped | redundant beside IMO and name for public vessels, and for Class B it is identifying data we are required not to keep. |
   | `cog`, `draught`, `ROT`, `Heading`, `ETA`, `Cargo type`, A/B/C/D | dropped | no planned session reads them, and a mean course over a cell-hour is meaningless. |

10. **New data facts.** `SOG` carries the AIS sentinel 102.3 ("not available"),
   27–66 k rows a day, read back as 102.2 in Float32 — hence the `sog < 100`
   filter. `Data source type` is `AIS` on every one of 20.4 M rows, so the
   column is not read. `Length` is populated on 18.4 M of 20.4 M rows (max
   557 m), which is why `vessel_day.length` is `max(length)`.

### Design review

`punchcard:punchcard` on `HEAD~1..HEAD`. Verdict **🔴 "Wrong shape. Talk before
more code."** — four findings, **all four accepted, none rejected.** Two of them
were structural enough to need the day re-downloaded and reloaded.

1. 🔴 *`ship_group` resolved per message, not per vessel.* Correct, and worse
   than the review knew: fixing it exposed the same fault in `Type of mobile`
   (finding 2 above), which the review had not looked at. Fixed by splitting
   the old `ais_clean` view into `ais_rows` (which rows count) and
   `ais_vessel_stage` (one identity per vessel-day), with `ais_clean` the join
   of the two — so all three aggregates read one grain and the `ship_group`
   mapping lives in exactly one place.
2. 🟡 *`LOAD_LIMIT` read from the ambient environment could truncate a load
   that then deleted its own source.* Correct: `rows_read` would look complete,
   the DELETE range would narrow to match, the zip would be gone and S3's
   `run_queue.sh` would skip the file forever. Fixed: the cap is now an
   explicit `--limit N` flag, and a capped load keeps the archive and says so.
3. 🟡 *The comment on `h3_hourly` claimed "No MMSI".* Correct and the reason it
   matters was verified in the store: `uniqExact` keeps the values, so merging
   a guess into a published state returns 1 for a hit and 2 for a miss, and
   **70.1 % of Class B cell-hours held exactly one vessel**. Over ~2 M Danish
   MMSIs (MID 219/220) that is a recoverable identity. Nothing leaked —
   `data/ch` never leaves the machine — but the comment invited S11 to export
   the column. Rewritten to say what the state is and that only
   `uniqExactMerge(...)` may cross an export boundary.
4. 🔵 *The assert meant to pin group resolution could not be made to fail.*
   Correct — reverting the resolution two different ways left it green.
   Replaced with a cross-grain assert (distinct vessels summed over
   `h3_hourly`'s groups must equal `vessel_day`'s row count), which was then
   the thing that caught the `Type of mobile` half of finding 2.

The out-of-scope note (the schema called `h3_hourly` "the one table every
published artefact reads" while S3 charts from `vessel_day`) was also fixed.

Two asserts were additionally proven to fail on a deliberate break rather than
being taken on trust: swapping `geoToH3` to `(lat, lon)` moves 13 873 cells out
of the Danish bbox, and dropping the `Class A` filter puts 1 426 Class B rows
into `public_track`.

### Deviations from `docs/PLAN.md` § S2 (§ S2 has been updated to match)

- `sql/02_aggregate.sql` became `sql/02_stage.sql` + `sql/03_aggregate.sql`, so
  `test_load.sh` runs the shipped SQL rather than a copy of it.
- Two stage tables (`ais_raw_stage`, `ais_vessel_stage`) and two views
  (`ais_rows`, `ais_clean`) exist beyond the plan's five tables. The stage
  tables are dropped after every load.
- `load_log` gained the drop counters S1's open questions asked for.
- `ais_raw_stage` holds 10 typed columns, not the plan's 15. `length` and
  `imo` were added to `vessel_day` beyond the plan; `cog`, `nav_status`,
  `callsign`, `destination`, `draught`, `ROT`, `Heading`, `ETA`, `Cargo type`
  and the antenna offsets are **gone forever for every loaded file**. Each was
  measured before being dropped — see finding 9.
- Timestamps are parsed with an explicit `%d/%m/%Y %H:%i:%S` mask rather than
  `--date_time_input_format best_effort`.
- New quality filter `sog < 100`.
- Only `aisdk-2025-07-16.zip` was loaded for real (the plan's Validate line);
  07-12, 01-15 and 06-14 stay on disk so `sql/00_peek.sql` can be re-run.

### Open questions for S3

- **`vessel_day` needs a minimum message count before a vessel is counted.**
  394 Class B vessels are `other` with a median `dist_nm` of 0 — transponders
  that reported a position and little else. The column to filter on is
  `msgs`/`moving_msgs`; S3 must pick a threshold and state it.
- **`scripts/run_queue.sh` must call `load.sh` without `--limit`.** A capped
  load logs the file and keeps the zip; the runner should treat a kept zip as
  a failure, not as success.
- `dist_nm` counts only movement, so a vessel that never exceeds 0.5 kn has
  `dist_nm = 0` rather than NULL. S6's radius chart must exclude, not average.
- Nothing yet guards against a monthly file (S4) spanning two months; the
  DELETE range is taken from the data, so it is correct, but it has not been
  exercised.

### Disk

`data` 2.0 GB (three S1 zips kept), `data/ch` 7.7 MB, 281 GB free.
One day of aggregates is 7.7 MB, so 2024-03 → today projects to ~7 GB.

**Next session: S3 — phase-0 charts.** Read `docs/PLAN.md` § S3.

## S1 — First look — 2026-08-29

**Done:** `scripts/ch.sh` (clickhouse-local wrapper over the persistent store in
`data/ch`), `sql/00_peek.sql` (six read-only checks over the four downloaded daily
zips), `notes/s1-first-look.md` (all numbers with the queries), `docs/DATA.md` and
`docs/DECISIONS.md` updated with what is now verified. Nothing was loaded into
ClickHouse; `data/ch` is 24 KB.

**Gate A: PASSED.** Class B exists and `Sailing`/`Pleasure` are populated.

### Validate — `scripts/ch.sh sql/00_peek.sql` (40.9 s wall for all four files)

```
=== 1. size and Class B presence, per day ===
aisdk-2025-01-15.csv	19914968	3939	2841	1084	27.6
aisdk-2025-06-14.csv	26006001	9393	3720	5658	60.3
aisdk-2025-07-12.csv	21336303	8629	3729	5023	57.4
aisdk-2025-07-16.csv	20398510	8220	2844	5547	66.1
=== 2. Ship type by mobile class, July Saturday (distinct vessels) ===
Undefined	3449	4026	1908710
Sailing	99	2091	1547528
Pleasure	81	1765	1185178
Cargo	716	194	4525875
Fishing	444	181	3617439
Passenger	298	86	2438641
Tanker	267	62	1722001
Other	239	79	1038089
Tug	158	35	681046
SAR	108	33	516228
HSC	95	32	554975
Dredging	89	22	426385
Pilot	74	16	608937
Military	60	9	128852
Law enforcement	41	16	78373
Towing	14	8	140083
Port tender	11	11	51887
Reserved	15	0	79787
Diving	8	7	9164
Anti-pollution	7	1	4721
=== 3. the leisure fleet (Sailing + Pleasure), summer vs winter ===
aisdk-2025-01-15.csv	152	298	450	17530
aisdk-2025-06-14.csv	2502	2032	4533	1156858
aisdk-2025-07-12.csv	2091	1765	3855	904979
aisdk-2025-07-16.csv	2479	2053	4532	1635341
=== 4. coordinates: sentinels, bounds, decimal separator ===
aisdk-2025-01-15.csv	19914968	98124	98124	19758298	-84.7623	83.9261	-168.0017	103.6153
aisdk-2025-06-14.csv	26006001	53684	53684	25112044	-85.2313	83.9183	-155.6575	159.2776
aisdk-2025-07-12.csv	21336303	46455	46455	21198840	-87.0804	67.4293	-167.6663	149.1309
aisdk-2025-07-16.csv	20398510	23261	23261	20299568	-83.8002	82.1398	-151.3721	135.3566
=== 5. timestamp: explicit DD/MM/YYYY parse vs best-effort ===
aisdk-2025-01-15.csv	19914968	0	0	0	2025-01-15 00:00:00	2025-01-15 23:59:58
aisdk-2025-06-14.csv	26006001	0	0	0	2025-06-14 00:00:00	2025-06-14 23:59:58
aisdk-2025-07-12.csv	21336303	0	0	0	2025-07-12 00:00:00	2025-07-12 23:59:58
aisdk-2025-07-16.csv	20398510	0	0	0	2025-07-16 00:00:00	2025-07-16 23:59:58
=== 6. timezone probe: island ferries, first/last moving hour in the file clock ===
AEROESKOEBING	17	5	4	19	1
ELLEN	17	5	4	16	1
PRINSESSE ISABELLA	21	4	3	21	1
```

Column headers, in order — 1: `file, msgs, vessels, class_a, class_b, class_b_pct` ·
2: `ship_type, class_a, class_b, msgs` · 3: `file, sailing, pleasure, leisure_total,
moving_msgs` · 4: `file, msgs, sentinel_91_181, impossible, in_danish_bbox, lat_min,
lat_max, lon_min, lon_max` · 5: `file, msgs, strict_parse_failed,
best_effort_failed, the_two_disagree, ts_min, ts_max` · 6: `ferry, jan_last,
jan_first, jul_first, jul_last, winter_shift_hours`.

```
$ df -h .
/dev/disk3s5   460Gi   140Gi   284Gi    34%   /System/Volumes/Data
$ du -sh data data/ch
2.7G	data
 24K	data/ch
```

### Findings

1. **Class B is present and is the majority of vessels in summer.** 27.6 % of
   vessels on the January Wednesday, 57.4 % / 60.3 % / 66.1 % on the three
   June–July days. Class A barely moves across seasons (2841 → 3729, +31 %); the
   entire swing is Class B (1084 → 5658, **+422 %**).
2. **The leisure fleet is ~8.6× bigger in June than in January** (450 → 4533
   distinct `Sailing`+`Pleasure` vessels) and moves **66× more** (17.5 k →
   1.16 M messages with SOG > 0.5). Chapter 01 has its headline.
3. **Timestamps are UTC.** Proved by daylight saving, not by trusting a
   timetable: `AEROESKOEBING`, `ELLEN` and `PRINSESSE ISABELLA` each start
   sailing exactly one hour later in the January file than in the July file, in
   the file's own clock — so the clock does not observe DST. Absolute values
   agree with the timetables (Ærøskøbing 06:00 local = 04 file-clock in July,
   05 in January). In `docs/DECISIONS.md`.
4. **Coordinates use a decimal point** (the bucket README's comma example is
   wrong) and there is exactly **one** sentinel, `Latitude = 91, Longitude = 0`,
   0.1–0.5 % of rows. `sentinel_91_181` and `impossible` are equal in all four
   files, so `abs(Latitude) <= 90` is a complete quality filter.
5. **Timestamps parse with zero failures across 87.6 M rows**, and the strict
   `%d/%m/%Y %H:%i:%S` parse and `parseDateTimeBestEffort` agree on every single
   row — `--date_time_input_format best_effort` is safe for the S2 loader.
6. **The Danish bbox is a scope decision, not a cleaning step.** lat 53–59 /
   lon 3–17 keeps 96.6 %–99.5 % of rows — 99.51 % on 07-16 but only **96.56 %**
   on 06-14. The ~894 k out-of-bbox rows of 06-14 are one coherent southern-Baltic
   cluster (lat 50–55 / lon 15–20), i.e. real traffic, not noise. **S10 must
   report the dropped share per day**, or a sevenfold swing in receiver reach will
   read as a change in traffic.
7. **`Ship type = 'Undefined'` is the largest Class B group and is nearly empty.**
   4026 Class B vessels on 07-12, of which 3353 report a position — but only
   30 733 positional messages between them, ~9 per vessel, against ~672 per
   vessel for `Sailing`. They inflate a distinct-vessel count by ~87 % while
   contributing ~1 % of the movement. **A raw `uniqExact(mmsi)` is a transponder
   count, not a boat count.**
8. **`Type of mobile` has eight values**, not two: `Class A`, `Class B`, `AtoN`
   (425), `Base Station` (87), `SAR Airborne`, `Search and Rescue Transponder`,
   `Emergency PIRB`, `Man Overboard Device`. S2's `mobile IN ('Class A','Class B')`
   filter is necessary. And `Ship type` is independent of `Type of mobile` —
   Class B `Cargo` (194), `Fishing` (181) and `Passenger` (86) all exist, so the
   privacy rule keys on `Type of mobile = 'Class B'`, never on ship group.
9. **Reading the CSV inside the zip is fast and needs no temp file.**
   `file('data/raw/aisdk-*.zip :: *.csv', CSVWithNames, '<cols>')` matches the 26
   header columns by name; a full scan of a 3.8 GB daily CSV takes ~5 s
   (~4.3 M rows/s). S2's Gate B1 target of 300 k rows/s has a lot of headroom, and
   the "never keep raw CSV on disk" rule holds for free.

### ⚠️ Warning for S3

**The July Saturday is below the July Wednesday.** 2025-07-12 (Sat) has 3855
leisure vessels and 905 k moving messages; 2025-07-16 (Wed) has 4532 and 1635 k.
Almost certainly weather. Whatever else is true, "weekend > weekday" is not a law
and a single picked Saturday is not evidence — S3 must build the weekday effect
from whole months.

### Design review

`punchcard:punchcard` on the S1 diff (`HEAD~1..HEAD`, touching `scripts/ch.sh` and
`sql/00_peek.sql`). Verdict "🟠 Ship after #1", three findings, **all three
accepted and fixed**:

1. 🔴 *The bbox filter drops real Baltic traffic, and the stated retention is
   wrong.* Correct — the first draft of the `docs/DECISIONS.md` entry said the
   bbox "keeps 99.2–99.4 % of rows" and called what it removes "GPS junk". The
   real range is 96.6–99.5 %, and the dropped rows on 06-14 are a coherent
   southern-Baltic cluster. Fixed: the entry is split into a *quality* filter
   (`abs(lat) <= 90`) and a *scope* filter (the bbox) with the measured numbers,
   plus the S10 obligation to report the dropped share per day. This is finding 6
   above.
2. 🟡 *`minIf` over an absent ferry returns 0, not "no data".* Correct and
   verified (`minIf(h, false)` → `0`; `0 - 6` → `-6` as `Int16`). A summer-only
   ferry added to the probe's list would report a confident `winter_shift_hours`
   of −6 and quietly poison the project's only timezone evidence. Fixed: a
   `HAVING countIf(day = …) > 0` guard on both days, and `ANHOLT` (July-only) is
   now deliberately *in* the ferry list as the live check that the guard fires —
   if it ever appears in query 6's output, the guard is broken.
3. 🔵 *Archive reading is ruled in on daily zips, and rules out the pipe for
   monthly ones.* Correct — the evidence is four sub-1 GB daily zips, but the
   entry ruled out `unzip -p` for S4's 14–19 GB monthly zip64 archives. Fixed:
   the decision is narrowed to daily files, the pipe is kept as the documented
   fallback, and "confirm ClickHouse opens a monthly zip64 archive" is now a
   prerequisite on S4.

No findings were rejected.

### Open questions for S2

- Does `geoToH3` need `(lon, lat)` in that order? Get it wrong and every cell is
  in the wrong hemisphere — assert one known harbour cell in `test_load.sh`.
- `ship_group` mapping: `Undefined` → `other`, never folded into `leisure`
  (finding 7). Decide whether `vessel_day` also stores a per-day message count so
  S3/S6 can require a minimum before counting a vessel — it should.
- The S2 loader must **count and log** the rows it drops (sentinel, out-of-bbox,
  non-vessel `mobile`), not discard them silently; S10 needs those numbers.
- The plan's `unzip -p | clickhouse local` pipe is superseded by the archive
  syntax for daily files — write `scripts/load.sh` against `file(… :: *.csv)`,
  keeping the pipe as a fallback for S4's monthly zips.

### Disk

`data` 2.7 GB (the four zips, kept for S2's loader test), `data/ch` 24 KB,
284 GB free. Well inside budget.

**Next session: S2 — the loader.** Read `docs/PLAN.md` § S2. Use plan mode: it
touches the loader.

## S0 — Bootstrap — 2026-08-29

**Done:** repo skeleton (`README.md`, `CLAUDE.md`, `docs/PLAN.md`, `docs/DATA.md`,
`docs/DECISIONS.md`, `.gitignore`, `scripts/fetch.sh`). Archive layout verified by
enumerating the S3 bucket (1 128 keys, 2006-03 → 2026-08-26).

**Findings:**
- Daily files live either at the bucket root or under `YYYY/` — `fetch.sh`
  handles both.
- Sizes: 2016 month 18.3 GB zip, 2025 day 0.75 GB zip.
- `clickhouse`, `uv`, `node`, `ffmpeg` are installed on the machine.

**Open questions (for S1):** timestamp timezone; decimal separator in
coordinates; Class B presence on disk.

**Started:** download of the minimal set (`2025-07-12`, `2025-07-16`,
`2025-01-15`, `2025-06-14`) — check `ls data/raw/*.ok`.

