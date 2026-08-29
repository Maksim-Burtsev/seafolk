# Status — living handoff log

Newest session on top. Each entry: what was done, findings with numbers, open
questions, and the exact next session. Write it for someone with zero context.

**Next session: S2** (the loader: one zip in, aggregates out, raw file gone).

---

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

