# The site — design spec for S12–S14

Decided with the owner on 2026-09-18. This file is the brief every S12–S14
implementer reads after `CLAUDE.md`. `docs/PLAN.md` § S12–S14 says *who builds
what, in which order*; this file says *what good looks like*.

## What the owner asked for

The analysis is done (findings 1–68, `notes/*.md`). What is missing is a
presentation a normal person can read. The owner's words, condensed:

- The validation PNGs under `notes/img/` are **analyst charts**: fifteen panels,
  log axes, three-line legends. They stay where they are as evidence. Nothing
  reader-facing reuses them.
- A chart must read like a chart in a newspaper: "bitcoin goes up — everybody
  gets it". If a reader needs the caption to find the point, the chart failed.
- The text is a human story in an engineer's plain language. No data-science
  vocabulary. The earlier essay draft was rejected as slop: a wall of numbers
  with nobody in it.
- English only. First person. (The RU version is dropped — DECISIONS 2026-09-18.)
- No GitHub Pages yet: everything is committed and must open from `file://` by
  double-click. The owner enables Pages himself later.
- Launch/outreach (S15) and dataset publishing (DOI) are postponed, not ours.

## Voice

The narrator is the owner: a software engineer who got curious, pushed 2.3 TB
of ship radio through a desktop Mac into 11 GB, and looked at what people do at
sea. He is not a sailor and not a data scientist, and says so.

- Say what happened, then show it, then give the number as proof. Never open a
  paragraph with a number. At most two numbers in a sentence.
- Words a reader never sees: *Class A/B, MMSI, H3, resolution, k-anonymity,
  quantile, p90, median, aggregate, cell-hour, vessel-day, uniqExact, ratio,
  baseline, proxy, cohort, retention*. Say instead: big ships / small boats,
  radio ID, hexagon about the size of a town, "at least five boats", typical,
  "one in ten", "a usual day", "boats we heard again the next year".
  `how.html` may name the real terms once, in parentheses, for the engineers.
- Concrete over general: "the Anholt ferry sails once a day, five days a week,
  never on a Wednesday" beats "service frequency varies across lines".
- Admit what the data cannot say, in one plain sentence, where it matters:
  the fleet "tripled" means *boats carrying a transmitter* tripled.
- No filler: no "in today's world", "let's dive in", "it turns out that",
  "interestingly", no rhetorical questions as headings, no three-adjective
  lists, no closing moral. If a sentence can be deleted without loss, delete it.
- Every number in prose is a `<span data-n="key">` filled by the build from
  computed data (see Build). No hand-typed numbers except years and dates.

## Chart rules (the newspaper test)

1. **One chart, one sentence.** The chart's headline *is* that sentence, as a
   claim: "Cargo ships never stopped. Fishing boats stopped first." Not a
   description of axes.
2. Linear axes. No log scales, no dual axes, no small-multiple grids above 4
   panels. If the data needs a log axis, the chart is asking the wrong question —
   change the measure (e.g. "share of a normal day", 0–150 %).
3. Direct labels on the lines/bars; no separate legend when ≤ 4 series.
4. One accent colour (`--accent`) for the thing the sentence is about;
   everything else in muted ink. Tokens come from `site/css/site.css`
   (lifted from `site/day-clocks.html`); light and dark both work.
5. Units in plain words on the axis ("boats out that day", "% of a normal day").
   At most 5 ticks per axis.
6. One annotation pointing at the point of the chart.
7. Interaction adds depth and never carries the message: hover for exact
   values, a selector for "another storm / another ferry line". The default
   state must tell the story with JS-less eyes in a screenshot.
8. Under each chart: one line of source ("Danish Maritime Authority AIS
   archive; computed by `sql/52_who_stays.sql`", linked to GitHub) and a
   collapsed `<details>` data table (accessibility + reproducibility).
9. Works at 380 px width without horizontal scroll.

**Acceptance — the blind read.** For every chart the implementer takes a
screenshot (`scripts/shot.sh`) and the reviewing session gives *only the image*
to a fresh small-model subagent: "In one sentence, what does this chart say?"
If the answer does not match the chart's intended sentence, the chart is
redone. The intended sentences are in the storyboard below.

## Privacy on the site

The site is an export. The hard rule applies: nothing about a private boat
(small-boat transponder, or any leisure vessel) at finer grain than the open
dataset, and **every private-fleet number on the site counts ≥ 5 boats** — the
build throws otherwise (finding: S9 has whole-bbox leisure counts of 2).
The map and the storm animation read **only `dist/dataset/*.parquet`** (already
privacy-tested by `scripts/test_export.py`), never the store. No 9-digit
integer anywhere under `site/` (test).

## Pages and storyboard

`→` is the sentence the blind reader must give back. Findings in brackets.

### `site/index.html` — the story (≈ 1 500 words, 8 charts)

Opening: who I am, what ship radio is (every ship shouts its position every few
seconds; Denmark is the one country that publishes all of it, small boats
included), what I did with it. Three acts.

**Act 1 — More and more people go to sea.**
- I1 *Season hills*: boats out per day across the calendar year, one line per
  year, 2015 pale → 2026 accent. → "Every summer more small boats are out than
  the summer before; winter is empty." [1, 2, 53]
- I2 *Boats vs ships*: small boats heard per year (bars, 6 → 23 thousand) with
  big ships as a flat grey line. → "Small boats tripled while the number of
  big ships did not change." Prose states plainly: boats *with a transmitter*.
  [53, 54]
- I3 *Whose boats*: share by flag, German vs Danish vs others, per year. →
  "There are more German boats than Danish ones in these waters." [57]

**Act 2 — When the storm comes.**
- I4 *One storm, four fleets*: activity as % of a normal day (same hours a
  fortnight away), −3 … +3 days, storm shaded, Pia by default, selector over
  the storms with clean data. → "When the storm came fishing boats stopped
  almost completely and cargo ships carried on as normal." [38, 39, 41]
- I5 *Who stops first*: a single strip — fishing 0 h, sailors +6 h, work boats
  +9 h, ferries +17 h, cargo never. → "Fishing boats stop first, ferries last,
  cargo ships never." [40]
- I6 *The sea empties*: hour-by-hour map animation of one storm from the open
  dataset (public fleets only), play/scrub. → "The dots thin out as the storm
  arrives and come back after." [S14]

**Act 3 — The archive lies, a little.**
- I7 *Impossible ships*: share of ships per month that sent more messages in a
  day than a transmitter physically can (43 200), ~0 until 2023, then ~1 %.
  → "Since 2023 the archive contains ships that sent more messages than is
  physically possible — it stores messages twice." [59]
- I8 *Denmark in the Arabian Sea*: sketch map — where my first grid put
  Copenhagen (mirrored across lat = lon) — and what it cost: a 35-hour reload.
  Labelled as an illustration of a bug, not archive data. [S4-redo]
- Text only: a fifth of the ferry fleet is invisible because the ships are
  filed under the wrong type (Fanø's two ferries: "Undefined", every year) [23].

Close: what is in the repo (dataset, code, every chart reproducible), links to
the four chapters, the map and `how.html`. No moral.

### `site/season.html` — A year under sail [1–10]
- S1 → "The sailing season peaks about three weeks earlier than it did in 2015."
- S2 → "On a summer weekend a quarter more boats go out than on a weekday."
- S3 → "Almost half of the boats that switch on their radio never leave the berth that day."
- S4 → "On the day of the Silverrudder race five times more boats are at the start than usual."

### `site/pulse.html` — The sea by the hour [11–22]
- P1 day clocks (rebuild of `site/day-clocks.html`, animated hand) → "Sailors
  go out at noon; ferries, cargo and fishing run around the clock."
- P2 the 168-hour week, sailors vs cargo → "Sailors live for the weekend; cargo
  does not know what day it is."
- P3 a harbour breathing (≥ 5 boats per point) → "A marina empties late morning
  and fills again in the late afternoon."

### `site/ferries.html` — Lifelines [23–37]
- F1 one line's year as a calendar strip, line selector → "This island's ferry
  sails every day of the year, with fewer trips in winter."
- F2 summer vs winter crossings per island line (dumbbell) → "Some islands keep
  the same timetable all year; others lose most of it in winter."
- F3 storms, small lines vs big lines → "Storms cancel the small island ferries
  first; the big lines keep sailing."
- F4 ELLEN → "The new electric ferry made the crossing 13 % faster."

### `site/storms.html` — When the storm comes [38–52]
- T1 = I4 with all fifteen storms selectable and sailors shown where enough
  boats were out.
- T2 share of boats that moved, storm day vs usual day, per fleet, per storm
  (sorted dot plot) → "In every storm fishing loses the most and cargo loses
  nothing."
- T3 anchorages → "Ships do not pile into anchorages to wait out a storm."
- T4 the full animation (I6) with storm selector.

### `site/how.html` — How it was made
Pipeline as a diagram (2.3 TB of zips → streamed, never stored → 11 GB of
counts); "are you tracking private boats?" answered first and plainly, with a
picture of the ≥ 5 boats rule; the three bugs worth telling (mirrored grid,
double-stored messages, invisible ferries); what the data cannot say (the box
is not Denmark, transmitters ≠ boats); how to reproduce; dataset + licence.
JSON-LD `Dataset` block lives here (DOI `pending`).

### `site/explore/index.html` — The map
deck.gl `H3HexagonLayer` + Natural Earth land as a `GeoJsonLayer`; month
slider with play; fleet toggles (cargo, ferries, fishing, work boats at
hexagon res 6 from `class_a_hourly_*`; small boats at res 5 from
`leisure_daily`, already ≥ 5). Data as `site/explore/data/YYYY-MM.js`
(`window.SEAFOLK_MONTH[...] = …`, loaded by a `<script>` tag so `file://`
works). Budget: ≤ 40 MB committed for all months. No MapLibre, no PMTiles, no
tippecanoe (DECISIONS 2026-09-18).

### Animations and posters (S14)
- `scripts/render_storm.py` → `site/media/storm-<name>.mp4` (+ a short GIF):
  matplotlib frames → ffmpeg, same data as I6.
- `site/media/day-clocks.mp4`: the four clocks with a sweeping hand.
- `site/posters/*.pdf|svg`: season hills; four clocks; A3. Lowest priority.

## Build

- `scripts/build_site_data.py` (uv, stdlib only; shells out to `scripts/ch.sh`
  like `notes/plot_*.py`). One module per page under `scripts/site_data/<page>.py`
  exposing `build(ch) -> dict`; the driver discovers modules by file name,
  enforces the guards, and rewrites each page's
  `<script type="application/json" id="data">` block **and** every
  `<span data-n="key">` from the dict's `"n"` map. A missing key fails the build.
  `scripts/build_site_data.sh` stays as a thin wrapper (`CH_PATH` passthrough).
- Guards in the driver: no 9-digit integer in any output; any value under a key
  path containing `leisure`/`small_boats` that is a boat count must be ≥ 5 or
  the build throws; every number printed to stdout (the ledger reviewers check).
- `scripts/test_site.py`: every page parses; every `data-n` filled; prose
  (`<p>`, `<h*>`, `<figcaption>`) holds no bare digits outside `data-n` spans
  except years/dates; banned-vocabulary list from *Voice* (except `how.html`
  parentheses); no `mmsi`/9-digit under `site/`; explorer data ≤ 40 MB.
- `scripts/shot.sh <page> [selector]` — screenshots via the Playwright
  headless shell already cached on this machine
  (`~/Library/Caches/ms-playwright/chromium_headless_shell-*/…/chrome-headless-shell
  --screenshot`), light and dark, 1280 and 380 wide, into the scratch dir — not
  committed. No new dependency.
- Libraries from cdnjs/jsdelivr, pinned: D3 7, Scrollama 3 (only if a page
  scrolls a sticky chart), deck.gl 9 + h3-js 4 (map and animation only).
- Readers run concurrently only on APFS clones of the store
  (`cp -Rc data/ch data/ch_<name>`, `CH_PATH=`), removed afterwards.

## Definition of done

`scripts/build_site_data.sh && scripts/test_site.py` green; every chart passed
the blind read; every page opened from `file://` in light and dark at both
widths with no console error; punchcard review judged; `docs/STATUS.md`
written; pushed.

## Round 2 — the owner's review, 2026-09-19 (binding; overrides the storyboard above where they differ)

The owner rated round 1 "3 of 5": too little material, presentation so-so.

- **Headline face.** Bodoni Moda's hairlines read badly. Every headline (h1, h2,
  figure h3, posters' next render) moves to **Source Serif 4, weight 600**
  (Google Fonts), one change in `site/css/site.css`.
- **Interactivity is a minus on the story page.** Nobody clicks through fourteen
  buttons. A figure on `index.html` shows everything it has to say at once;
  selectors live only on chapter pages.
- **I4 → one static chart of all storms together**: days −3…+3, "of every 100
  boats heard, how many went out"; the mean of all storms for fishing (accent,
  thick) and cargo (ink, thick), each storm as a thin pale line behind its
  fleet's mean. No buttons.
- **I5 (the onset strip) is removed** — unreadable. In its place five horizontal
  bars: on a storm day, how many of every 100 boats of each fleet stay in
  compared with a usual day (fishing, sailing boats, work boats, ferries, cargo).
- **I6, the animation**: autoplays and loops like a GIF (muted, no Play needed;
  pause on click, `prefers-reduced-motion` shows the triptych instead); boats are
  small boat **icons**, not dots; the sea looks like sea (tinted water, soft
  land); a big phase label — "before the storm" / "the storm" / "after" — and a
  large fishing-boat counter. Beside it a static **triptych** of three small maps
  (the day before, the storm day, two days after) so the point is readable
  without watching anything.
- **I7** is redrawn as a picture: two bars — the most a ship's radio can send in
  a day vs what the archive holds for the worst ship-day — above a quiet
  timeline.
- **I8 (Copenhagen in the Arabian Sea) is removed from the story.** On
  `how.html` the episode shrinks to one neutral paragraph with no "my".
- **More material, more maps.** New static map figures from `dist/dataset` only
  (small boats at the published coarse grain, every cell ≥ 5, asserted on the
  written file): small boats in July vs January; small boats July 2015 vs July
  2025; where the fishing happens; the web of ferry lanes; used on `index.html`
  and in the chapters where they fit.
