---
license: cc-by-4.0
language:
  - en
tags:
  - ais
  - maritime
  - denmark
  - h3
  - leisure-boating
  - ferries
size_categories:
  - 100M<n<1B
pretty_name: Seafolk — Danish AIS aggregates
configs:
  - config_name: class_a_hourly
    data_files: class_a_hourly_*.parquet
  - config_name: leisure_daily
    data_files: leisure_daily.parquet
  - config_name: ferry_daily
    data_files: ferry_daily.parquet
---

# Seafolk — Danish AIS aggregates

Danish waters counted, not tracked. The Danish Maritime Authority's open AIS
archive is the only open European source that still contains the leisure fleet —
Finland strips Class B for privacy, Norway excludes leisure craft under 45 m —
and almost every pipeline throws that part away as noise. This dataset keeps it,
as aggregates: how many distinct vessels of each kind were in a cell of sea in an
hour (or a day), how many messages they sent, how fast the moving ones went, plus
a per-day crossing count for every named Danish ferry line. Private boats —
every Class B transponder and every pleasure craft whatever its transponder —
appear only in cells shared by at least five of them. It is built by the
[Seafolk](https://github.com/Maksim-Burtsev/seafolk) project and every number in
it is reproducible from that repository.

## Source and terms

Source: the Danish Maritime Authority (DMA) historical AIS archive,
<http://aisdata.ais.dk/>, granted as open data on the basis of act no. 596 of
24 June 2005 on the further use of public sector information (the Danish PSI
act).

The DMA's AIS data management policy (read verbatim 2026-09-12, see
`docs/DATA.md`) states the conditions and the disclaimer:

> The data recipient is responsible for handing the data received appropriately
> and in accordance with the law.

> Data must not be combined with other data in a manner that will create data
> from which persons are identifiable, without a permit to do so from the Danish
> Data Protection Agency. In this connection, the data recipient should be
> considered the data responsible person in the sense of the act on personal
> data.

> The Danish Maritime Authority does not guarantee the correctness of the AIS
> data transmitted and is not liable for any damages that may arise as a
> consequence of the use of AIS data, irrespective of how they have been caused.
> The Danish Maritime Authority is not liable in case of delay, interruption or
> loss of data due to failure of the transmission and communication facilities
> used or for other reasons beyond the control of the Danish Maritime Authority.

> The Danish Maritime Authority can, at any time and without notice, change the
> nature of the data flow received, for example by changing the updating
> frequency, the area of coverage, safety updates, force majeure situations, etc.

The "persons are identifiable" condition is the one sentence that binds a
derivative like this one, and the k ≥ 5 floor described under
[Privacy rule](#privacy-rule) is how this dataset complies with it: no private
vessel is distinguishable in any published cell, and nothing here is combined
with a register that could name one.

## Licence

The aggregates in this dataset are released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Required attribution:

```
Data: Danish Maritime Authority (aisdata.ais.dk), aggregated by the Seafolk project
```

The DMA publishes no licence name and no attribution string of its own (see
`docs/DATA.md`); CC BY 4.0 is the Seafolk project's choice for its own
aggregates, permitted because the PSI act allows re-use and nothing in the DMA
policy restricts derivatives.

**Not for navigation.** These are historical, aggregated counts with a known
message-count bias and known coverage gaps. Nothing here is a position report,
and nothing here may be used for navigation, collision avoidance, or any
safety-of-life purpose.

## Coverage

Bounding box: latitude 53–59 N, longitude 3–17 E, in hourly or daily UTC slices.

**This box is not Denmark.** It reaches into the German Baltic, the Sound, Kiel
Bay and the Skagerrak. German-flagged Class B transponders outnumber Danish ones
in every loaded year (0.32–0.36 of the fleet against 0.18–0.26). Read every
number as "the fleet in this box", never as "the Danish fleet".

Loaded days — 2 122 in total, and the gaps are real gaps, not zeros:

| Period | Days | Grain of the source file |
|---|---|---|
| 2015-01-01 → 2015-12-31 | 365 | monthly archives |
| 2018-01-01 → 2018-12-31 | 365 | monthly archives |
| 2021-01-01 → 2021-12-31 | 365 | monthly archives |
| 2022-01, 2022-02 | 59 | monthly archives (storms Malik, Nora) |
| 2023-02, 2023-12 | 59 | monthly archives (storms Otto, Pia) |
| 2024-03-01 → 2026-08-26 | 909 | daily archives, no gaps (2024: 306, 2025: 365, 2026: 238) |

2016, 2017, 2019 and 2020 are not loaded at all. Any year-over-year series in
this dataset therefore compares 2015 / 2018 / 2021 / 2024 / 2025 / 2026, and
2022 and 2023 contribute two months each.

## Privacy rule

Private boats and the people on them are the whole reason this file exists.
**The private fleet is every Class B transponder AND every vessel whose
`ship_group` is `leisure`, whatever transponder class it carries** — a pleasure
craft with a Class A radio is still a private boat, and 337–467 of them appear
in the archive each year.

- **Aggregates only** for the private fleet. No MMSI, name, callsign, or track
  of a private vessel exists in any file here — no identifier column exists at
  all.
- **k ≥ 5**: every published leisure cell-day has at least five distinct
  vessels in it. Cells below the floor are dropped, not rounded or suppressed
  in place.
- **The private hourly resolution-7 layer is never published, at any k.** It
  does not survive the floor (whole-store measurement, 2026-09-12: at
  resolution 7 × hour the Class B layer would keep 7.1 % of the cell-hours and
  20.8 % of the moving messages), and a single-vessel exact-distinct state is a
  membership oracle over MMSI. `leisure_daily.parquet` at resolution 5 × day is
  the private-fleet product, and it is the only place a `leisure` row is
  published.
- Ferries and commercial vessels are public and are named.
- The floor is enforced by a test that the export refuses to skip:
  `scripts/test_export.py` asserts that no private-fleet row has fewer than
  five vessels, that no `leisure` row appears in a Class A file, and that every
  file's columns and types are exactly the schema published below — an extra
  column is a failure, not a bonus. The export fails loudly.

Cost of the floor, measured 2026-09-12: 341 092 of 1 445 495 private-fleet
cell-days survive — 23.6 % of the cells, but 82.0 % of the moving messages.

## Files and schema

### `class_a_hourly_<year>.parquet` — Class A, hourly, H3 resolution 7

One file per loaded year (2015, 2018, 2021, 2022, 2023, 2024, 2025, 2026).
These files carry `cargo`, `passenger`, `fishing` and `other` only — a
commercial vessel is public and required to broadcast, so no privacy floor is
applied to it. **Class A leisure is not here**: it is part of the private fleet
and lives in `leisure_daily.parquet`, under the floor.

| Column | Type | Meaning |
|---|---|---|
| `h3` | uint64 | H3 cell id, resolution 7 (~5 km²), `geoToH3(lat, lon, 7)` |
| `hour` | timestamp (UTC) | start of the hour |
| `ship_group` | string | `cargo` (Cargo + Tanker), `passenger`, `fishing`, `other`; resolved once per vessel-day, not per message. Never `leisure` |
| `msgs` | uint64 | position/static messages counted in the cell-hour |
| `moving_msgs` | uint64 | of those, messages with 0.5 kn < SOG < 100 kn |
| `vessels` | uint64 | exact distinct vessel count |
| `mean_sog` | double | knots, mean over **moving** messages only; NULL when `moving_msgs = 0` |

### `leisure_daily.parquet` — the private fleet, daily, H3 resolution 5

Every Class B transponder **or** any vessel with `ship_group = leisure`
whatever its class. The rule is applied per cell-hour, not per vessel: a boat
that reports Class B one day and Class A another is under the floor on its
Class B days in any case, and on its Class A days too when it is grouped as
leisure.

| Column | Type | Meaning |
|---|---|---|
| `h3` | uint64 | H3 cell id, resolution 5 (~250 km²) |
| `day` | date (UTC) | calendar day |
| `ship_group` | string | same vocabulary, plus `leisure` = Sailing + Pleasure; a non-leisure group here is a Class B vessel of that group |
| `msgs` | uint64 | messages in the cell-day |
| `moving_msgs` | uint64 | of those, moving |
| `vessels` | uint64 | exact distinct vessel count, **always ≥ 5** |
| `mean_sog` | double | knots, moving messages only; NULL when `moving_msgs = 0` |

### `ferry_daily.parquet` — named ferry lines, per local day

One row per (line, local day in Europe/Copenhagen). Ferries are public vessels.

| Column | Type | Meaning |
|---|---|---|
| `line` | string | the ferry service, resolved at build time from OSM route endpoints |
| `kind` | string | `island` / `domestic` / `international` / `foreign` / `harbour` (see `sql/40_ferry_trips.sql`) |
| `island` | string | the island served, for `kind = island`; else empty |
| `day` | date | **local** date (Europe/Copenhagen) of the crossing's departure |
| `year`, `season`, `dow` | uint16, string, uint8 | the baseline's grouping keys: calendar year, `may-sep` / `oct-apr`, ISO day of week |
| `daytype` | string | `weekday` / `sat` / `sun`, kept for coarse splits; not the baseline key |
| `routes` | uint64 | how many OSM route objects were folded into the line that day |
| `crossings` | uint64 | crossings that departed that local day, both directions |
| `vessels` | uint64 | distinct vessels that made them |
| `baseline` | uint32 | median crossings over the same line, year, season (May–Sep / Oct–Apr) and **day of week**, counting signal days only. Observed, not a timetable — Danish operator timetables are not archived per year |
| `missed` | int64 | `greatest(baseline - crossings, 0)` |
| `is_storm_day` | uint8 | 1 if the local day is a named-storm date from DMI's list |
| `fleet_positions` | uint64 | position messages heard from this line's fleet that day |
| `fleet_sog_known` | uint64 | of those, with a usable speed field |
| `fleet_moving` | uint64 | of those, moving |
| `fleet_vessels_reporting` | uint64 | distinct vessels of the line heard at all |

**How to read a zero** — the coverage columns exist for exactly this, and a
consumer that prints "cancelled" without checking them is printing the
receiver's bad day. **Read the four cases in order** and stop at the first that
matches:

| What you see | What it means |
|---|---|
| `crossings = 0` and `fleet_positions = 0` | **Silent.** Nothing was heard from this line's fleet. Not a cancellation; not evidence. |
| `fleet_positions > 0`, `fleet_sog_known = 0` | **Cannot tell.** The vessel was heard, its speed field was empty all day, and neither a stay nor a crossing can be built from that. |
| `fleet_moving = 0` | **The fleet lay still.** A real cancellation, or a docking — *unless* `crossings > 0`, see the note on the fleet below. |
| `fleet_moving > 0`, `crossings = 0` | **Moved, nothing matched.** The matcher or OSM, not the weather. |

The `fleet_*` columns count **this line's own fleet**, and a vessel-year belongs
to exactly one line: the one on which it made the most crossings that year
(own-majority, `sql/41_ferry_daily.sql`'s rule; ties broken on the line name).
So a relief vessel borrowed from another line has its crossings counted for the
line it sailed, while its positions are counted for its home line — which is
why 18 547 line-days in this file have `fleet_moving = 0` **and**
`crossings > 0`. Those are not still fleets; they are days worked by somebody
else's boat.

## Known biases

Read these before plotting anything.

1. **`msgs` and `moving_msgs` are not comparable across September 2015.** The
   archive duplicated its own feed 2015-08-28 → 2015-09-30: message counts in
   that window run ×2.199 on the Class A vessel-day median and ×2.552 on the
   daily mean. Flagged, never rewritten.
2. **`msgs` and `moving_msgs` are not comparable across 2023 either.** The Class
   A message *tail* doubles permanently between 2022-03 and 2023-11 while the
   median stands still: p90 8 749–9 428 → 16 261–19 607, p99 14 156–16 980 →
   31 633–44 041. Vessel-days above the 43 200 position reports a Class A
   transponder can physically send in a day go from 0–0.06 % to 0.18–1.09 %;
   the worst day is 359 899 messages, 8.3× the ceiling. **Any message count
   compared across 2023 compares two instruments.**
3. **`vessels`, and every head count, are comparable.** Exact distinct counts are
   structurally immune to duplication — that is why head counts, not message
   counts, carry the cross-year story.
4. **The loader drops rows, and says how many.** Per loaded day: 4.0–11.3 % of
   rows as non-vessel (AtoN, base stations, SAR, PIRB, MOB), 0–6.3 % as outside
   the bounding box, 0.04–0.98 % as the `Latitude = 91` sentinel.
5. **Receiver reach barely moved — once.** Of 139 sea regions, exactly one busy
   region steps on its head count: the Skagerrak approach at 57.9965 N
   10.7602 E, 75 → 113 vessels (×1.507), between 2018-12 and 2021-01. The other
   eleven charted regions drift within ×0.82 .. ×1.16 over eleven years.
6. **An independent source agrees on where the fleet is.** Against EMODnet Human
   Activities' July-2021 leisure vessel density, Spearman ρ = 0.85 where both
   sources see the cell. Levels are not comparable (EMODnet measures track time,
   we measure presence: a moored boat is many vessel-hours to us and ~0 to
   EMODnet), so only rank was compared. 10.3 % of EMODnet's leisure hours fall
   where we have nothing, almost all of it outside the Danish core.

## How to reproduce

```bash
git clone https://github.com/Maksim-Burtsev/seafolk
cd seafolk
# fetch and load the archive (see docs/PLAN.md; ~1.2 TB downloaded, deleted as
# it is aggregated, ~11 GB of ClickHouse storage left behind)
scripts/export.sh          # sql/70_export.sql -> dist/dataset/, then test_export.py
```

The export runs on `clickhouse local --path data/ch` (no server). The privacy
test is part of `scripts/export.sh`, not an optional step.

## Cite as

```
Burtsev, M. (2026). Seafolk — Danish AIS aggregates (version 0.1.0) [Data set].
Zenodo. DOI: pending
Source data: Danish Maritime Authority (aisdata.ais.dk).
```

```bibtex
@dataset{seafolk_danish_ais_2026,
  author    = {Burtsev, Maksim},
  title     = {Seafolk --- Danish AIS aggregates},
  year      = {2026},
  version   = {0.1.0},
  publisher = {Zenodo},
  doi       = {pending},
  url       = {https://github.com/Maksim-Burtsev/seafolk},
  note      = {Aggregated from the Danish Maritime Authority AIS archive,
               aisdata.ais.dk}
}
```

## Versioning

The **Zenodo concept DOI is the canonical address** — it always resolves to the
newest version, and it is the only address a paper can cite. The GitHub Release
and the Hugging Face dataset are mirrors: they are where people download, and
both point back at the DOI. Version here is 0.1.0.
