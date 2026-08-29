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
3. **Open dataset** — hourly aggregates on an H3 grid, 2014 → today, as Parquet on
   GitHub Releases and Hugging Face, plus the loader and notebooks that reproduce
   every chart.
4. **Posters and a short animation** — season rings, daily fingerprints, "the sea
   empties before a storm".

Four chapters share one engine: *01 A year under sail* · *02 Pulse* (the sea by
hour and weekday) · *03 Lifelines* (island ferries) · *04 When the storm comes*
(named Danish storms since 2013).

## Privacy rule

Class B transponders belong to private boats and the people on them. The project
publishes **aggregates only**: no MMSI, name, or track of a private vessel appears
anywhere — not in the essay, not in the explorer, not in the dataset. The minimum
published cell is H3 resolution 7 (~5 km²) × hour with at least five distinct
vessels. Ferries and commercial ships are public and are named.

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
