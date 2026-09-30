# Seafolk

*Sea folk* — the people on the water, not the cargo.

Twenty years of Danish waters seen through the people on them — sailors, island
ferries, fishermen, and everyone who waits out a storm — built from the open AIS
archive of the Danish Maritime Authority (2006 → today).

Commercial shipping has been analysed to death. The leisure fleet (Class B
transponders) and the small-island ferry lines are thrown away as noise by almost
every AIS pipeline. This project keeps exactly that part and tells its story.

## What comes out

1. **The essay site** (`site/`, English, static, opens from `file://` by
   double-click): [`site/index.html`](site/index.html) — the story in three acts
   (the fleet of small boats that tripled, who stops when a storm comes, and
   where the archive lies) — and four chapters: *A year under sail*
   (`season.html`), *The sea by the hour* (`pulse.html`), *Lifelines*
   (`ferries.html`), *When the storm comes* (`storms.html`), plus *How it was
   made* (`how.html`): the pipeline, the privacy rule, the bugs.
2. **The map** (`site/explore/`) — deck.gl hexagons by month and fleet, built only
   from the open dataset below.
3. **Open dataset** — H3 aggregates for 2015, 2018, 2021, two storm months each
   of 2022 and 2023, and 2024-03 → today, as Parquet, plus the loader and the
   queries that reproduce every chart.
4. **Animation and posters** (`site/media/`, `site/posters/`) — three storms hour
   by hour ("the sea empties"), the four day clocks, two A3 posters.

Every number in the site's prose is written into the page by
`scripts/build_site_data.sh` from the store (`<span data-n>`), never typed; the
brief the site was built to is [`docs/SITE.md`](docs/SITE.md).

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
**Download: <https://huggingface.co/datasets/mburtsev/seafolk-danish-ais>.**

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
site/              the essay, the map, media and posters (static; docs/SITE.md is its brief)
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

# Rebuild the site's numbers from the store and check the pages
scripts/build_site_data.sh && uv run scripts/test_site.py
```

Everything else is in `docs/PLAN.md`.

## Data

Danish Maritime Authority, historical AIS: <http://aisdata.ais.dk/> — published
under the Danish PSI act, free to use. Weather context: DMI. Coastline and
marinas: OpenStreetMap / Natural Earth.

## License

Code: MIT. Published aggregates: CC BY 4.0 (source data © Danish Maritime
Authority, cite as such).
