# Data sources — verified facts

Last verified: 2026-08-29. Anything marked *(unverified)* still needs a check.

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
- README in the bucket (`!_README_information_CSV_files.txt`) — 26 columns:

  | # | Column | Note |
  |---|--------|------|
  | 1 | Timestamp | `31/12/2015 23:59:59` (`DD/MM/YYYY HH:MM:SS`), from the base station. **UTC** — verified in S1 by the DST test, see `notes/s1-first-look.md` §6. 0 parse failures in 87.6 M rows. |
  | 2 | Type of mobile | Verified values: `Class A`, `Class B`, `AtoN`, `Base Station`, `SAR Airborne`, `Search and Rescue Transponder`, `Emergency PIRB`, `Man Overboard Device`. Only the first two are vessels. |
  | 3 | MMSI | |
  | 4–5 | Latitude, Longitude | **Decimal point** in the real files (the README example is wrong). Single sentinel `Latitude = 91, Longitude = 0`, 0.1–0.5 % of rows; filter on the Danish bbox lat 53–59 / lon 3–17, which keeps 99.2–99.4 %. |
  | 6 | Navigational status | text |
  | 7–10 | ROT, SOG, COG, Heading | |
  | 11 | IMO | |
  | 12–13 | Callsign, Name | |
  | 14 | Ship type | Verified: `Undefined`, `Sailing`, `Pleasure`, `Cargo`, `Fishing`, `Passenger`, `Tanker`, `Other`, `Tug`, `SAR`, `HSC`, `Dredging`, `Pilot`, `Military`, `Law enforcement`, `Towing`, `Port tender`, `Reserved`, `Diving`, `Anti-pollution`, `Medical`, `WIG`, `Spare 1/2`, `Towing long/wide`, `Not party to conflict`. Independent of column 2 — Class B `Cargo`/`Fishing`/`Passenger` all exist. |
  | 15 | Cargo type | |
  | 16–17 | Width, Length | |
  | 18 | Type of position fixing device | |
  | 19 | Draught | |
  | 20–21 | Destination, ETA | |
  | 22 | Data source type | |
  | 23–26 | Size A/B/C/D | GPS antenna offsets |

- Coverage: Danish coastal receivers; reaches into the Sound, Kattegat, the
  western Baltic and parts of Kiel Bay. Whether Kiel Week is visible is
  *(unverified — session S3)*.
- **Class B presence: verified on disk in S1.** 27.6 % of vessels on 2025-01-15,
  57.4–66.1 % on June/July days. `Sailing` (2091 vessels) and `Pleasure` (1765) on
  2025-07-12 are almost entirely Class B. Numbers and queries in
  `notes/s1-first-look.md`.
- **Caveat, verified in S1:** `Ship type = 'Undefined'` is the *largest* Class B
  group (4026 vessels on 2025-07-12) but carries ~9 positional messages per vessel
  against ~672 for `Sailing`. A raw distinct-MMSI count is a transponder count, not
  a boat count.

## Other open sources (context)

- **Kystverket (Norway)** — historical AIS from 2006, Parquet, NLOD licence.
  Excludes fishing vessels < 15 m and leisure craft < 45 m. Registration required.
  Useful for ferries/storm chapters only.
- **Digitraffic (Finland)** — realtime only, CC BY 4.0, Class B removed.
- **EMODnet Human Activities** — monthly vessel density 1 km grid by ship type,
  2017 →, commercial use allowed. Cross-check for coverage drift.
- **HELCOM** — annual density maps 2006–2024. Cross-check.
- **DMI** — Danish weather; named storms since 2013 (Allan 2013-10-28, Bodil
  2013-12-06, Carl 2014-03-15, Dagmar/Egon 2015-01, Freja/Gorm/Helga 2015-11/12,
  Urd 2016-12-27, Ingolf 2017-10-29, Johanne 2018-08-10, Knud 2018-09-21,
  Alfrida 2019-01-02, Laura 2020-03-12, Malik 2022-01-29/30, Nora 2022-02-18,
  Otto 2023-02-17, Pia 2023-12-21/22, Rolf …). Full list: da.wikipedia
  "Navngivne storme i Danmark".
- **Regattas** (2025 dates): Palby Fyn Cup May 22–25 (Bogense), Fyn Rundt
  May 30 – Jun 1 (Kerteminde), Sjælland Rundt Jun 7–15 (Helsingør), Kiel Week
  Jun 21–29. Historical dates per year: to collect in S5.
- **OpenStreetMap** — marinas (`leisure=marina`), ferry routes
  (`route=ferry`), coastline. Natural Earth — land polygons.

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
