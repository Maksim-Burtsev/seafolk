# Status — living handoff log

Newest session on top. Each entry: what was done, findings with numbers, open
questions, and the exact next session. Write it for someone with zero context.

**Next session: S3** (phase-0 charts: two full months, three shapes).

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

8. **New data facts.** `SOG` carries the AIS sentinel 102.3 ("not available"),
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
- `ais_raw_stage` holds 9 typed columns, not the plan's 15: `cog`,
  `nav_status`, `imo`, `callsign`, `destination`, `draught` are not read by any
  planned session and are **gone forever for every loaded file**. `length` was
  added to `vessel_day` instead, as the one irrecoverable attribute worth
  keeping.
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

