# Data sources — verified facts

Last verified: 2026-09-02. Anything marked *(unverified)* still needs a check.

## Danish Maritime Authority — historical AIS

- Index: <http://aisdata.ais.dk/> (static page listing an S3 bucket
  `aisdata.ais.dk.s3.eu-central-1.amazonaws.com`). Free under the Danish PSI act.
- **Terms of use: not yet read verbatim.** The PSI act is the general basis, but
  the archive's own terms have not been opened. S11 reads them before the export
  and records here the exact attribution string DMA requires, any disclaimer
  (AIS providers often require "not for navigation"), and whether redistribution
  of derivatives under CC BY 4.0 is actually allowed.
- Listing (checked by enumerating the bucket, 1 128 keys):
  - `YYYY/aisdk-YYYY-MM.zip` — monthly, 2006-03 → 2024-02 (a few months missing
    in 2016–2017; 2017 also has `all_sources_2017-MM.zip` variants).
  - `aisdk-YYYY-MM-DD.zip` — daily from 2024-03-01. Some days sit under `YYYY/`,
    others at the bucket root (e.g. `2025/aisdk-2025-01-15.zip` but
    `aisdk-2025-07-12.zip`). Try root first, then `YYYY/`.
- Sizes (HTTP Content-Length): `2010/aisdk-2010-06.zip` 14.5 GB,
  `2016/aisdk-2016-06.zip` 18.3 GB, `2020/aisdk-2020-06.zip` 19.1 GB,
  `aisdk-2025-06-15.zip` 0.75 GB.
- **Monthly zip structure (verified in S4 by loading 36 of them):** one
  monthly zip holds **31 daily CSV members**, not one big file — sometimes at
  the archive root, sometimes under `FtpRoot/ais_data/`, varying month to
  month with no rule (2015-01 root, 2015-07 subdir, 2017-01 subdir, 2017-07
  root). Read with the `**/*.csv` glob. zip64 offsets past 4 GB read fine;
  no member exceeds 4 GB anywhere in the probed archive.
- **Two CSV dialects, boundary at 2016-09/2016-10** (probed by HTTP range
  reads of first and last members; no month mixes them):
  - `2006-03 … 2016-09` — **no header row, `;` delimiter, decimal COMMA**,
    22 columns (the modern 26 minus the four antenna offsets; same order
    otherwise, same timestamp format). Parsed by `sql/02_stage_legacy.sql`.
  - `2016-10 → today` — header, `,`, decimal point, 22 columns until ~2020
    and 26 after. The modern parser handles both widths.
  `scripts/load.sh` picks the parser by reading the archive's first line, not
  by date.
- **`aisdk-2017-{02..06}.zip` is 404 at both URL layouts** — five months of
  2017 are not fetchable under the standard name (the `all_sources_2017-MM`
  variants were not probed).
- **⚠️ The archive duplicates its own feed 2015-08-28 → 2015-09-30:** message
  counts in that window run ~2.3x the neighbouring months (avg 7 512
  msgs/vessel-day vs 2 600–3 700; max 352 163 ≈ 4 msg/s sustained, above the
  physical AIS rate). Crosses three zip files, so it is upstream, not the
  loader. Distinct-vessel counts and `dist_nm` are structurally immune;
  message-count charts over that window are not — S10 masks or normalises it.
- README in the bucket (`!_README_information_CSV_files.txt`) — 26 columns:

  | # | Column | Note |
  |---|--------|------|
  | 1 | Timestamp | `31/12/2015 23:59:59` (`DD/MM/YYYY HH:MM:SS`), from the base station. **UTC** — verified in S1 by the DST test, see `notes/s1-first-look.md` §6. 0 parse failures in 87.6 M rows. |
  | 2 | Type of mobile | Verified values: `Class A`, `Class B`, `AtoN`, `Base Station`, `SAR Airborne`, `Search and Rescue Transponder`, `Emergency PIRB`, `Man Overboard Device`. Only the first two are vessels (6.6 % of a day's rows are the rest). **Not constant per vessel per day** — 354 of 3 402 vessels on 2025-01-15 (10.4 %) and 526 of 8 364 on 2025-06-14 report both `Class A` and `Class B`; see S2's resolution rule in `docs/DECISIONS.md`. |
  | 3 | MMSI | |
  | 4–5 | Latitude, Longitude | **Decimal point** in the real files (the README example is wrong). Single sentinel `Latitude = 91, Longitude = 0`, 0.1–0.5 % of rows; filter on the Danish bbox lat 53–59 / lon 3–17, which keeps **96.6–99.5 %** of all rows (99.51 % on 2025-07-16, 96.56 % on 2025-06-14) — a scope decision, not cleaning; what it drops on 06-14 is a coherent southern-Baltic cluster. |
  | 6 | Navigational status | **A Class A field — do not plan around it.** Inside the bbox on 2025-07-12 it is `Unknown value` on 2 704 358 of 2 710 000 Class B messages, and `Under way sailing` covers 6 Class B vessels / 14 messages in a whole day. Populated for Class A (1 988 under way using engine, 1 008 moored, 191 at anchor). Not stored by the S2 loader. |
  | 7–10 | ROT, SOG, COG, Heading | `SOG` is empty on ~6.7 % of rows and carries the AIS sentinel **102.3** ("not available") on 27–66 k rows a day, stored as 102.2 in Float32. Max observed 258 kn. S2 filters `sog < 100`. |
  | 11 | IMO | String: digits or `Unknown`. Fill rate inside the bbox on 2025-07-12: 61 % of Class A passenger vessels, 97 % of cargo, 4 of 3 799 Class B leisure. Stored in `vessel_day.imo` as `toUInt32OrZero`. |
  | 12–13 | Callsign, Name | `Name` is empty for most Class A cargo rows but populated for ferries. `Callsign` is not stored — redundant beside IMO/Name for public vessels, identifying data for Class B. |
  | 14 | Ship type | Verified: `Undefined`, `Sailing`, `Pleasure`, `Cargo`, `Fishing`, `Passenger`, `Tanker`, `Other`, `Tug`, `SAR`, `HSC`, `Dredging`, `Pilot`, `Military`, `Law enforcement`, `Towing`, `Port tender`, `Reserved`, `Diving`, `Anti-pollution`, `Medical`, `WIG`, `Spare 1/2`, `Towing long/wide`, `Not party to conflict`. Independent of column 2 — Class B `Cargo`/`Fishing`/`Passenger` all exist. |
  | 15 | Cargo type | |
  | 16–17 | Width, Length | `Length` is populated on 18.4 M of 20.4 M rows on 2025-07-16, max 557 m. Carried on static messages, so `vessel_day.length` takes `max()` over the day. |
  | 18 | Type of position fixing device | |
  | 19 | Draught | |
  | 20–21 | Destination, ETA | `Destination` is crew-typed free text; 266 of 298 Class A passenger vessels report something. Not stored — S8 assigns ferry routes by endpoints instead. |
  | 22 | Data source type | `AIS` on every one of 20.4 M rows of 2025-07-16. Not read by the loader. |
  | 23–26 | Size A/B/C/D | GPS antenna offsets |

- Coverage: Danish coastal receivers; reaches into the Sound, Kattegat, the
  western Baltic and parts of Kiel Bay. Whether Kiel Week is visible is
  *(unverified — session S3)*.
- **Class B presence: verified on disk in S1.** 27.6 % of vessels on 2025-01-15,
  57.4–66.1 % on June/July days. `Sailing` (2091 vessels) and `Pleasure` (1765) on
  2025-07-12 are almost entirely Class B. Numbers and queries in
  `notes/s1-first-look.md`.
- **`Ship type` is not constant per vessel per day — corrected in S2.** S1 read
  `Undefined` as the largest Class B group (4026 vessels on 2025-07-12) and
  concluded those were near-empty transponders. They are not: of 4 884 Class B
  vessels with a position in Danish waters that day, **301 report `Undefined`
  and nothing else, 3 026 report it alongside their real type, and 1 557 never
  report it.** Position messages carry `Undefined` while static messages carry
  the type, so a query grouping on the raw column counts one boat several
  times. S1's *conclusion* still stands for a different reason: a raw
  `uniqExact(mmsi)` over raw rows is not a boat count. Use `vessel_day`, which
  holds one resolved type per vessel-day.

## Other open sources (context)

- **Kystverket (Norway)** — historical AIS from 2006, Parquet, NLOD licence.
  Excludes fishing vessels < 15 m and leisure craft < 45 m. Registration required.
  Useful for ferries/storm chapters only.
- **Digitraffic (Finland)** — realtime only, CC BY 4.0, Class B removed.
- **EMODnet Human Activities** — monthly vessel density 1 km grid by ship type,
  2017 →, commercial use allowed. Cross-check for coverage drift.
- **HELCOM** — annual density maps 2006–2024. Cross-check.
- **DMI** — Danish weather; named storms since 2013. Collected in S5 into
  `data/context/storms.csv` (24 rows, committed, one source URL per row).
  22 of the 24 come from DMI's own list,
  `STORMS_IN_DENMARK_SINCE_1891.pdf` (last updated 2026-04-14); Alexander (2014)
  and Sif (2024) come from a DMI news-archive page and da.wikipedia
  "Navngivne storme i Danmark" because DMI never classified them. Where DMI and
  Wikipedia disagree on a date (Carl, Egon, Freja, Urd, Nora, Otto, Floriane),
  DMI wins. All rows are date-only — DMI publishes no start hour — so a storm is
  stored as whole UTC days. Latest named storm: Dave, 2026-04-05.
- **Regattas** — collected in S5 into `data/context/regattas.csv` (30 rows,
  committed, one source URL per row): five events × the six years the store
  holds (2015, 2018, 2021, 2024, 2025, 2026). Sjælland Rundt (Helsingør),
  Silverrudder (Svendborg), Fyn Cup (Bogense — renamed from Palby Fyn Cup, so
  the key is `Fyn Cup`), Classic Fyn Rundt (Kerteminde), Kieler Woche
  (Kiel-Schilksee — 2021 ran in September because of Covid). Dates are the
  racing period, not the shore week. Bornholm Rundt and Watski 2Star could not
  be sourced per year and were left out rather than guessed.
- **OpenStreetMap** — marinas (`leisure=marina`), ferry routes (`route=ferry`).
  **Natural Earth** — 10 m land polygons. Both fetched by
  `scripts/fetch_context.sh` and loaded by `sql/04_context.sql`; the files
  themselves are not committed. See docs/DECISIONS.md 2026-09-08 for the bbox,
  the `nwr` fetch and what the `land` dictionary can and cannot answer.

## Prior work (so we don't claim too much)

- Hütten, M. (2025). *Maritime Activities Observed Through Open-Access
  Positioning Data: Moving and Stationary Vessels in the Baltic Sea.* Geomatics
  5(4), 69. Three months of open Baltic AIS (Aug–Oct 2024); notes Class B is
  ≳40 % of vessels in summer vs ~20 % in winter. No leisure-fleet story.
- Johansson et al. (2020). *Model for leisure boat activities and emissions –
  implementation for the Baltic Sea* (BEAM). Ocean Science 16. Survey-based;
  explicitly lacks an AIS-derived leisure dataset. Outreach candidate.
- RISE (2016). *Spatial distribution of leisure boats in the Baltic Sea region.*
- Hermannsen et al. (2019). Recreational vessels without AIS dominate noise in a
  shallow Danish soundscape. PMC6820791. Outreach candidate.
