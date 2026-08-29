# S1 — first look: does the story exist in the files?

Date: 2026-08-29. Four daily archive files, queried **inside their zips** (nothing
unpacked to disk):

| file | weekday | why this day |
|---|---|---|
| `aisdk-2025-07-12` | Saturday | peak summer weekend |
| `aisdk-2025-07-16` | Wednesday | peak summer weekday |
| `aisdk-2025-01-15` | Wednesday | winter baseline |
| `aisdk-2025-06-14` | Saturday | Sjælland Rundt |

Reproduce everything below with:

```bash
scripts/ch.sh sql/00_peek.sql       # ~40 s wall for all four files
```

ClickHouse reads the CSV straight out of the zip with
`file('data/raw/aisdk-2025-*.zip :: *.csv', CSVWithNames, '<columns>')`, matching
the 26 header columns by name and skipping the ones a query does not ask for
(`input_format_skip_unknown_fields=1`). One full pass over a 3.8 GB CSV takes
~5 s. **No `unzip` to disk, so the "never keep raw CSV" rule holds for free.**

---

## 1. Is Class B present? Yes, and it is the majority in summer

```
file                       msgs      vessels  class_a  class_b  class_b_pct
aisdk-2025-01-15.csv   19914968         3939     2841     1084         27.6
aisdk-2025-06-14.csv   26006001         9393     3720     5658         60.3
aisdk-2025-07-12.csv   21336303         8629     3729     5023         57.4
aisdk-2025-07-16.csv   20398510         8220     2844     5547         66.1
```

**Class B is 27.6 % of vessels on a January Wednesday and 57–66 % in June/July.**
Class A is nearly flat across seasons (2841 → 3729, +31 %); the swing is entirely
Class B (1084 → 5658, **+422 %**).

## 2. `Ship type` values, July Saturday (distinct vessels)

```
ship_type          class_a  class_b       msgs
Undefined             3449     4026    1908710
Sailing                 99     2091    1547528
Pleasure                81     1765    1185178
Cargo                  716      194    4525875
Fishing                444      181    3617439
Passenger              298       86    2438641
Tanker                 267       62    1722001
Other                  239       79    1038089
Tug                    158       35     681046
SAR                    108       33     516228
HSC                     95       32     554975
Dredging                89       22     426385
Pilot                   74       16     608937
Military                60        9     128852
Law enforcement         41       16      78373
Towing                  14        8     140083
Port tender             11       11      51887
Reserved                15        0      79787
Diving                   8        7       9164
Anti-pollution           7        1       4721
```

`Sailing` and `Pleasure` are populated and are overwhelmingly Class B — the
leisure fleet the whole project depends on. **Gate A passes.**

## 3. The leisure fleet, summer vs winter

Class B with `Ship type IN ('Sailing','Pleasure')`:

```
file                    sailing  pleasure  leisure_total  moving_msgs
aisdk-2025-01-15.csv        152       298            450        17530
aisdk-2025-06-14.csv       2502      2032           4533      1156858
aisdk-2025-07-12.csv       2091      1765           3855       904979
aisdk-2025-07-16.csv       2479      2053           4532      1635341
```

**~8.6× more leisure vessels on a June Saturday than on a January Wednesday**, and
**66× more moving messages** (17.5 k → 1.16 M). That is chapter 01 in two lines.

⚠️ **The July Saturday is *below* the July Wednesday** — 3855 vs 4532 vessels and
905 k vs 1635 k moving messages. Whatever else is true, "weekend > weekday" is not
a law, and a single Saturday is not evidence. 2025-07-12 was probably a bad-weather
day. S3 must build the weekday effect from whole months, never from picked days.

## 4. Coordinates: decimal point, and a single sentinel value

```
file                       msgs  sentinel_91_181  impossible  in_danish_bbox   lat_min  lat_max    lon_min   lon_max
aisdk-2025-01-15.csv   19914968            98124       98124        19758298  -84.7623  83.9261  -168.0017  103.6153
aisdk-2025-06-14.csv   26006001            53684       53684        25112044  -85.2313  83.9183  -155.6575  159.2776
aisdk-2025-07-12.csv   21336303            46455       46455        21198840  -87.0804  67.4293  -167.6663  149.1309
aisdk-2025-07-16.csv   20398510            23261       23261        20299568  -83.8002  82.1398  -151.3721  135.3566
```

- **Decimal point, not comma** — the columns parse as `Float64` straight from the
  CSV with no substitution.
- `sentinel_91_181 == impossible` in every file: **every out-of-range coordinate is
  exactly `Latitude = 91` (with `Longitude = 0`)**. There is no second sentinel and
  no partially-broken value. `abs(Latitude) <= 90` is a sufficient filter.
- Sentinels are 0.1–0.5 % of rows.
- Beyond the sentinels there is ordinary GPS junk *inside* the valid range
  (lat −87, lon −168). It is small: the Danish bbox (lat 53–59, lon 3–17) holds
  **99.2–99.4 %** of all rows. The loader must filter on the bbox, not only on
  `abs(lat) <= 90`.

## 5. Timestamps parse cleanly, and there is only one reading

```
file                       msgs  strict_failed  best_effort_failed  disagree  ts_min                ts_max
aisdk-2025-01-15.csv   19914968              0                   0         0  2025-01-15 00:00:00   2025-01-15 23:59:58
aisdk-2025-06-14.csv   26006001              0                   0         0  2025-06-14 00:00:00   2025-06-14 23:59:58
aisdk-2025-07-12.csv   21336303              0                   0         0  2025-07-12 00:00:00   2025-07-12 23:59:58
aisdk-2025-07-16.csv   20398510              0                   0         0  2025-07-16 00:00:00   2025-07-16 23:59:58
```

Format is `DD/MM/YYYY HH:MM:SS` as documented. Zero parse failures over 87.6 M rows,
and `parseDateTime(…, '%d/%m/%Y %H:%i:%S')` and `parseDateTimeBestEffort` agree on
every single row — so `--date_time_input_format best_effort` is safe for the S2
loader. Each file covers exactly its own day, 00:00:00 → 23:59:5x.

## 6. The clock is UTC — proved by daylight saving, not by a timetable

Ferry timetables are written in **local** time and keep the same local first
departure all year. So: if the file clock followed Danish local time, a ferry's
first sailing hour would be the same number in January and in July. If the file
clock is UTC, the January number must be exactly **one hour higher** (CET = UTC+1,
CEST = UTC+2).

First/last hour with sustained movement (`SOG > 3`, >20 messages in the hour), in
the file's own clock:

```
ferry                jan_last  jan_first  jul_first  jul_last  winter_shift_hours
AEROESKOEBING              17          5          4        19                   1
ELLEN                      17          5          4        16                   1
PRINSESSE ISABELLA         21          4          3        21                   1
```

All three shift by exactly +1 h in winter. **The archive timestamps are UTC.**

Sanity check on the absolute values: Ærøfærgerne's `AEROESKOEBING` first sails at
04 file-clock in July = **06:00 CEST**, and 05 file-clock in January = **06:00 CET**
— the same local first departure, which is what the published timetable says.
`PRINSESSE ISABELLA` (Kalundborg–Ballen, Samsø) runs 03–21 UTC = 05:00–23:00 local.

`TYCHO BRAHE` (Helsingør–Helsingborg) was rejected as a probe: it moves in all 24
hours, so it has no first departure.

**Consequence:** store `DateTime('UTC')`, and convert to `Europe/Copenhagen` only
at the point where a chart says "hour of day". Every hour-of-day chart in this
project is a *local* hour and must be converted, or the summer peak lands two hours
early. Written into `docs/DECISIONS.md`.

---

## Findings that change later sessions

1. **`Ship type = 'Undefined'` is the largest Class B group and is almost noise.**
   On 2025-07-12: 4026 Class B vessels are `Undefined`; 3353 of them report at
   least one real position, but between them only **30 733 positional messages —
   ~9 per vessel**, against ~672 per vessel for `Sailing`. They inflate a distinct-
   vessel count by ~87 % while contributing ~1 % of the movement.
   → S2: keep them as `ship_group = 'other'`, never fold them into `leisure`.
   → S3/S6: headline leisure counts must require a minimum message count per
   vessel-day, or be message-weighted. A raw `uniqExact(mmsi)` is a transponder
   count, not a boat count.
2. **Class B `Cargo` (194), `Fishing` (181), `Passenger` (86) exist.** The
   `ship_group` mapping in S2 must key on `Ship type`, not on `Type of mobile`,
   and the privacy rule must key on `Type of mobile = 'Class B'` regardless of
   ship group — a Class B "Cargo" is still a private transponder.
3. **`Type of mobile` has more than two values**: `Class A`, `Class B`, `AtoN`
   (425 vessels), `Base Station` (87), `SAR Airborne`, `Search and Rescue
   Transponder`, `Emergency PIRB`, `Man Overboard Device`. The S2 filter
   `mobile IN ('Class A','Class B')` is correct and necessary.
4. **`Name` is empty for most Class A cargo rows** but populated for ferries —
   chapter 03 can rely on it.
5. **Throughput is not going to be the bottleneck**: ~5 s per daily file for a
   full scan straight out of the zip, ~4.3 M rows/s. The S2 Gate B1 target of
   300 k rows/s has a lot of headroom.

## Privacy note

No Class B MMSI, name, or callsign appears in this file or in `sql/00_peek.sql`.
The only vessels named anywhere are passenger ferries, which are public.
