# Seafolk

*Sea folk* — the people on the water, not the cargo.

Twenty years of Danish waters seen through the people on them — sailors, island
ferries, fishermen, and everyone who waits out a storm — built from the open AIS
archive of the Danish Maritime Authority (2006 → today).

Commercial shipping has been analysed to death. The leisure fleet (Class B
transponders) and the small-island ferry lines are thrown away as noise by almost
every AIS pipeline. This project keeps exactly that part and tells its story.

## What comes out

1. **Data essay "A year under sail"** — the shape of a Danish summer: when the
   season opens and closes, the Friday effect, regattas as spikes, ten years of
   season drift. Russian and English.
2. **Explorer** — a static map (MapLibre + deck.gl over pre-computed tiles) with a
   year/month slider, vessel-class toggle, and a page per island.
3. **Open dataset** — H3 aggregates for 2015, 2018, 2021, two storm months each
   of 2022 and 2023, and 2024-03 → today, as Parquet on GitHub Releases and
   Hugging Face, plus the loader and notebooks that reproduce every chart.
4. **Posters and a short animation** — season rings, daily fingerprints, "the sea
   empties before a storm".

Four chapters share one engine: *01 A year under sail* · *02 Pulse* (the sea by
hour and weekday) · *03 Lifelines* (island ferries) · *04 When the storm comes*
(named Danish storms since 2013).

## Privacy rule

Private boats belong to the people on them. The **private fleet is every Class B
transponder and every vessel grouped as leisure whatever its transponder class**
— a pleasure craft with a Class A radio is a private boat with a better radio,
not a ship. The project publishes **aggregates only**: no MMSI, name, or track of
a private vessel appears anywhere — not in the essay, not in the explorer, not in
the dataset. Every published private-fleet cell holds at least five distinct
vessels; resolution 7 × hour does not survive that floor (7.1 % of cell-hours,
20.8 % of the moving messages), so the published private grain is H3 resolution 5
(~250 km²) × day and the hourly resolution-7 layer is commercial Class A only.
Ferries and commercial ships are public and are named.

## Dataset

The published aggregates are described by [`docs/dataset-card.md`](docs/dataset-card.md),
which is also the README of the release and the Hugging Face card. Three files:
`class_a_hourly_<year>.parquet` (commercial traffic only — cargo, passenger,
fishing, other — H3 resolution 7 × hour), `leisure_daily.parquet` (the private
fleet, Class B or leisure, H3 resolution 5 × day, **only cells with at least
five distinct vessels** — the privacy rule above, enforced by
`scripts/test_export.py`, which the export refuses to skip), and
`ferry_daily.parquet` (crossings per named ferry line per day, with the coverage
columns that say whether a zero means "cancelled" or "not heard"). Build them
with `scripts/export.sh`, publish with `scripts/publish.sh`. Licence CC BY 4.0.
**DOI: pending.**

## Layout

```
CLAUDE.md          project memory for Claude Code sessions
docs/PLAN.md       the session-by-session plan — source of truth for "what next"
docs/STATUS.md     living log: what is done, what was found, what is next
docs/DATA.md       verified facts about the data sources
docs/DECISIONS.md  decisions and why
scripts/           shell entry points (fetch, load, run)
sql/               ClickHouse DDL and aggregation queries
notes/             analysis notebooks and scratch findings (curated)
data/raw           downloaded archive files — deleted after processing (gitignored)
data/ch            clickhouse-local storage (gitignored)
```

## Quick start

```bash
# ClickHouse binary (already installed via Homebrew on the dev machine)
clickhouse --version

# Fetch a minimal working set: a summer Saturday, a summer Wednesday, a winter
# Wednesday and the Sjælland Rundt weekend of 2025 (≈0.75 GB each)
scripts/fetch.sh 2025-07-12 2025-07-16 2025-01-15 2025-06-14
```

Everything else is in `docs/PLAN.md`.

## Data

Danish Maritime Authority, historical AIS: <http://aisdata.ais.dk/> — published
under the Danish PSI act, free to use. Weather context: DMI. Coastline and
marinas: OpenStreetMap / Natural Earth.

## License

Code: MIT. Published aggregates: CC BY 4.0 (source data © Danish Maritime
Authority, cite as such).
