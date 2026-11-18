# RadiusStats Europe — PLAN

Status, 2026-11-15: **step 1 (pipeline for one country, Belgium) done.** `pipeline/run.sh build`
builds 12 layers × 6 levels in ~5 s from cache; `run.sh validate` passes 39/39 checks; `run.sh test`
passes 10 unit tests. What step 1 found and changed:
- The census grid has no NUTS columns. The GISCO grid has NUTS **2016, 2021 and 2024** codes per cell,
  so each regional table/year is allocated in the NUTS version it is published in (Eurostat publishes
  BE population 2013/2015 under both old and new codes; the newest complete version is used and
  duplicates are ignored). No correspondence-table approximation is needed where this works.
- Per-country census files are used, so cells shared by two countries are split as each NSI reported.
- ARDECO still returns HTTP 500, so the NUTS 2 deflator fallback (Q5) is active and flagged in the report.
- Measured size: BE layer ≈ 3.7 bytes per populated cell at 1 km → Europe ≈ 17 MB per layer, in line with §2.
- The project folder name contains ':', which breaks PROJ and uv's PATH handling; `run.sh` keeps the
  virtualenv in `~/.local/share/radiusstats-europe/venv`.

Step 2 (query engine) done, 2026-11-15: `app/src/engine/` — geodesic circle (WGS84, geographiclib),
EPSG:3035 via proj4, scanline masking with 4×4 sub-cell sampling (16×16 below 20 cells radius),
per-country sums, geotiff.js window reads with block cache + window LRU + AbortSignal, a worker that
cancels stale queries and posts the visible layer group first. `npm test` (in app/): 30 tests, incl.
national totals reproduced at levels 1–8 km, and 7 circles (Brussels/Antwerp/Liège, 10–50 km) within
0.1 % of an independent pyproj computation. Changes made on the way:
- Cell budget lowered to **100k** cells (spec range 50k–250k) for 4G: r ≤ 178 km → 1 km, ≤ 356 km → 2 km,
  500 km → 4 km. To be re-tuned with measured bytes from the full build.
- Pipeline: coarse-level country = most *population* in the 2×2 block (was land), and a new
  `land_covered` layer gives the partial-coverage share exactly at every level.
- Local CPU time per cold query: 40–190 ms.

Step 3 (map UI) done, 2026-11-16: Vite + React + Tailwind app in `app/` (MapLibre with OpenFreeMap
positron, panning limited to Europe, uncovered countries greyed from GISCO 1:3M outlines, geodesic circle,
draggable marker, Nominatim search on submit, radius slider (square-root scale) + number input,
Population/GDP layers with PMTiles heat maps and legend, nominal/PPS and currency toggles, partial-coverage
and low-confidence notices, per-country table, reference years, Sources screen, URL hash state, PWA for
the app shell only). Checked in the browser on desktop and at 360 × 740 (no horizontal scroll; bottom
sheet collapses to a one-line headline). Bundle: 131 kB + 285 kB (MapLibre) gzipped.
Not yet checkable with the Belgium-only build: the currency toggle (needs a non-euro country), PWA install.
Dev notes: `npm run dev` in app/ serves `../data/build` at /data/ with Range support; Vite's fs.strict is
off in dev only because of the ':' in the folder name.

Step 4 (all countries) done, 2026-11-18: full build of EU-27 + UK + CH + NO in ~5 min (`run.sh build`),
`run.sh validate` 291/291 checks, `run.sh xcheck` 21 independent circles (Paris, London, Zurich, Oslo,
Warsaw, Basel, Brussels × 25/50/100 km) all reproduced by the engine within 0.1 %. App: 46 tests.
What step 4 found and changed:
- **UK:** no census grid → WorldPop 2021 100 m counts assigned to ONS local authorities (LAD 2023) and
  summed per 1 km cell × authority; ONS mid-year population (1 Jan = mean of the two mid-years, Q1) and
  ONS GDP by local authority (current prices + chained volume index). The ONS GDP and population files
  share the same 361 LAD 2023 codes, so no boundary conversion is needed.
- **CH:** BFS cantonal GDP 2011–2024 (revised 2026) for every year; Eurostat ends 2022 and is pre-revision.
- **NO:** Eurostat NUTS 3 GDP misses three regions and ends 2021 → SSB 09391 county value added scaled to
  Eurostat's mainland GDP (2011–2021), carried forward for 2022–2023; SSB county volumes for real growth.
- **Real growth** (EU countries): benchmarked to the latest national chain-linked volumes per country
  and year, because the regional volume table lags national revisions (CY, MT were up to 1 pp p.a. off).
  Irish IE062/IE063 2018 nominal is suppressed → NUTS 2 volume used.
- Germany has no NUTS 3 population on 1 Jan 2013 → the 2013 GDP weights use 2014 (also NL, PL).
- **PPS** needs no raster: Eurostat applies one national PPP factor per country (verified: ratio constant
  within every country to 0.003 %), so PPS = Σ country EUR × factor (`manifest.pps_per_eur`).
- **Bytes per query (measured, real HTTP):** 256 px tiles and one file per layer made a 10 km circle in
  London cost 5 MB. Now: one **12-band pixel-interleaved COG per level**, **64 px tiles**, float32 rounded to
  **12 mantissa bits** (≤ 0.012 % per cell), 16 KiB range blocks → cold query 160–430 KB for r ≤ 50 km,
  ~1–1.3 MB at 100–200 km, ≤ 1.7 MB at 500 km, in 4–8 requests; moving the point a few km costs 0 bytes
  (cached). COGs total 80 MB (was 151 MB). Cell budget stays **100k**: 250k would cost up to 4.7 MB.
  Tools: `app/scripts/measure-bytes.mjs` (tile index) and `app/scripts/measure-http.mjs` (real requests).
- YAML reads a bare `NO` as false: the config now rejects non-string country codes.

Step 5 (validation) done, 2026-11-18: [VALIDATION.md](VALIDATION.md). Engine vs independent pyproj
computation: 21 circles (Paris, London, Zurich, Oslo, Warsaw, Basel, Brussels × 25/50/100 km) within
0.012 %; all 42 circle totals within bounds from official regional figures; 291/291 build checks.
Found and fixed on the way: population series breaks (census re-basing in DE/CZ/PL/PT/LU) now flagged in
the manifest and marked in the app; radius slider did not respond to arrow keys; map attribution and
zoom buttons hidden behind the mobile sheet; axe-core findings (landmarks, link styling, translucent
backgrounds) → 0 violations. Not tested: real screen reader, real phone on 4G, PWA install.

Original draft for review, 2026-11-14: Every fact marked ✅ was
checked on 2026-11-14 against the live Eurostat API or by reading the file. Facts marked ⚠️ come
from release notes or search results and are re-checked when the pipeline downloads the data.

---

## 1. Architecture

```
            ┌─────────────────────── /pipeline (Python 3.12 via uv) ───────────────────────┐
 sources →  │ fetch (cached) → harmonise to NUTS 2024 → 1 km base grid → yearly rasters     │
            │ → sum-pyramids (1,2,4,8,16,32 km) → COGs + heat tiles → manifest/fx/report    │
            └──────────────────────────────────────────────┬────────────────────────────────┘
                                                           │ static files (COG, PMTiles, JSON)
                                       static host with HTTP range requests + CORS
                                                           │
 ┌──────────────────────────── /app (Vite + React + TS + Tailwind, PWA) ──────────────────────┐
 │ MapLibre map ─ point/radius/layer state ─ URL hash                                        │
 │      │ query(lat, lon, r)                                                                 │
 │ Web Worker: proj4 → EPSG:3035 bbox → pick level → geotiff.js window reads (LRU cache,     │
 │             AbortController) → mask + 4×4 edge supersampling → sums per layer × country   │
 │      │ results                                                                            │
 │ Results panel (side panel ≥ md, bottom sheet < md), Sources screen                       │
 └────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Layers (step 4: all layers are bands of ONE COG per pyramid level, float32, pixel-interleaved, 64 px tiles, DEFLATE + predictor 3, nodata = -1)

| id | content | years (from `config/years.yaml`) |
|---|---|---|
| `pop_{Y}` | population on 1 Jan | 2025, 2022, 2020, 2015 |
| `gdp_nom_eur_{Y}` | GDP, current prices, mio EUR | 2023 |
| ~~`gdp_pps_{Y}`~~ | dropped in step 4: PPS = country EUR × national factor (`pps_per_eur`) | — |
| `gdp_real_{Y}` | GDP, constant prices, mio EUR at fixed base-year rates | 2023, 2020, 2018, 2013 |
| `country` | country ID (0 = sea, 255 = land outside coverage), stored as a float32 band | — |
| `land`, `land_covered` | land share of the cell, and the share in covered countries (partial-coverage %) | — |

The country breakdown and the currency toggle use `country`. Each layer is summed **per country**
inside the circle, so the breakdown and the currency conversion come out of the same pass.

### Pyramids (sum-conserving)
GDAL's internal overviews average values, so they are **not** used. The pipeline writes one
COG per level: 1, 2, 4, 8, 16 and 32 km. Each coarser cell is the exact sum of its 2×2 children
(numpy reshape-sum in float64, then cast to float32). A unit test checks that totals are equal at
every level. `land` and `country` are aggregated as a mean and a mode, respectively; at coarse
levels `country` can be replaced by per-country sum bands if mixed border cells turn out to matter
(decided after the step-2 tests).

### Level choice
Circle area = πr². The worker picks the finest level for which πr²/cell² ≤ 100k (see status above):
r = 1–178 km → 1 km; up to 356 km → 2 km; 500 km → 4 km. Tiny radii are kept at 1 km (a 1 km radius covers
only ~3 cells, which is why there is a low-confidence warning below 25 km).
Each window read covers a bbox of 2r × 2r. At 500 km on the 2 km level that is 500 × 500 cells ×
~2 bytes compressed per layer → about 0.5 MB per layer; 9 layers ≈ 4–5 MB for the largest
query. That is the 4G worst case, so layers are read in priority order: the visible layer first,
then the rest.

### Heat layer
MapLibre cannot draw EPSG:3035 COGs directly. The pipeline pre-renders a density colour ramp
(people/km², EUR/km²) to Web Mercator PNG tiles, z0–10, packed into one **PMTiles** file per
layer and served through the `pmtiles` protocol. Static, no server, and it uses the same range-request host.

---

## 2. Data sizes (estimates — measured after step 1)

| item | size |
|---|---|
| GISCO grid_1km.parquet (download) | 168 MB ✅ |
| Census grid 2021 V3 zip (download) | 540 MB ✅ (only the 76 MB parquet inside is needed) |
| WorldPop R2025A 1 km, GBR (2015–2025) | ~10 × 3 MB ⚠️ |
| Eurostat / ONS / BFS / SSB tables | < 50 MB in total |
| Coverage raster extent (EPSG:3035, mainland + islands in coverage, no outermost regions) | ≈ 6 500 × 4 700 cells ≈ 30 M cells at 1 km |
| One 1 km float32 COG (≈ 85 % zeros/nodata) | ~15–30 MB |
| One layer, all pyramid levels | ~ × 1.33 |
| 9 data layers + country + land | **≈ 300–450 MB** on the host |
| PMTiles heat tiles, 2 visible layers × 3 variants | ~100–200 MB |
| App shell | < 1 MB gzipped (MapLibre is most of it) |

Outermost regions (Canaries, Azores, Madeira, French overseas departments) are in the EU but
far from the map. **Proposal:** cover the Canaries, Azores and Madeira (one extra small window of
the same grid), and leave out the French overseas departments, Svalbard and Jan Mayen, listing them
on the Sources screen. See open question Q4.

---

## 3. Confirmed table codes and latest years

Checked through the Eurostat dissemination API (SDMX-CSV) on 2026-11-14.

| # | Dataset | Code / file | Coverage found | Use |
|---|---|---|---|---|
| 1 | GISCO 1 km grid v1.4 (2025-07-03) | `grid_1km.parquet` — columns `GRD_ID, X_LLC, Y_LLC, CNTR_ID, TOT_P_2021, LAND_PC, NUTS2024_0..3` ✅ | EU-27, CH, NO have population. UK cells exist but TOT_P_2021 = 0 ✅ | cell → NUTS 2024 code, land share |
| 1b | Census 2021 grid **V3** (final, 30 May 2026) | `Eurostat_Census-GRID_2021_V3.zip` → `ESTAT_Census_2021_V3.parquet`, column `T` ✅ | EU-27 + CH + NO (CH and NO cells present); **no UK** (UK was not in the EU 2021 census round) ✅ | 2021 cell population (newer than grid v1.4's TOT_P_2021; joined on GRD_ID) |
| 2 | Population 1 Jan by NUTS 3 | `demo_r_pjanaggr3` (sex=T, age=TOTAL) ✅ | **2025** for all EU-27 + CH + NO; UK stops at 2019 ✅ | yearly scaling |
| 3 | UK mid-year estimates by local authority | ONS MYE ⚠️ | E&W mid-2025 published (29 Jul 2026); full UK incl. Scotland/NI for mid-2025 planned for autumn 2026 — to check at download | UK |
| 3b | WorldPop Global2 R2025A v1, 1 km, constrained counts | hub.worldpop.org listing 136 ⚠️ | 2015–2030 per country; labelled **alpha** | UK cell weights |
| 5 | GDP current prices, NUTS 3 | `nama_10r_3gdp`, units `MIO_EUR`, `MIO_PPS_EU27_2020` ✅ | **2023 complete** for all EU-27 NUTS 3 regions; 2024 missing in AT, DE, EL, ES, IT, LV, PL; **CH ends 2022, NO ends 2021**, UK absent ✅ | nominal + PPS |
| 6 | ARDECO GDP at constant prices | variable `SOVGD` (SUVGD = current prices), NUTS 2024 version, REST `https://territorial.ec.europa.eu/ardeco-api-v2/rest/export/SOVGD?version=2024&level=3` (found in the R package source) | ⚠️ **site and API were down for maintenance on 2026-11-14** (HTTP 500). Base year not yet confirmed | real growth |
| 6b | GDP volume, NUTS 2 | `nama_10r_2gvagr` (B1GQ, PCH_PRE / I20) ✅ | 2024 for EU-27; no CH/NO/UK ✅ | cross-check; fallback for #6 |
| 7 | ONS regional GDP, local authorities | "Regional gross domestic product: local authorities" ⚠️ | 1998–**2024**, released 23 Sep 2026 (current prices + chained volume) | UK |
| 8a | BFS cantonal GDP | ⚠️ revised provisional series 2011–2024 (consolidated version due March 2027) | CH |
| 8b | SSB county accounts | StatBank table **09391** ⚠️ | 2011–**2023** (2024 due ~Dec 2026) | NO |
| 9 | National PPS for UK and CH | `prc_ppp_ind` (`na_item=PPP_EU27_2020`, `ppp_cat=GDP`) ✅ | CH and UK to 2024 ✅. Note `nama_10_gdp` has no CH PPS series | PPS for UK, CH |
| 10 | Exchange rates, annual average | `ert_bil_eur_a` (statinfo=AVG) ✅ | CHF, CZK, DKK, GBP, HUF, NOK, PLN, RON, SEK to 2025 ✅ | fx.json |
| 10b | National GDP (country checks) | `nama_10_gdp` (`CP_MEUR`, `CLV20_MEUR`, `CP_MPPS_EU27_2020`) ✅ | to 2025 ✅ | validation |
| 11 | Boundaries | GISCO NUTS 2024 (01M), GISCO countries; ONS LAD boundaries (BFC) | — | country raster, UK LAD raster |

### Latest common years (into `config/years.yaml`)

| | latest | compared with | limiting source |
|---|---|---|---|
| Population | **2025** (1 Jan) | 2022, 2020, 2015 | all EU/CH/NO have 2025; UK built from mid-year estimates (see Q1) |
| GDP | **2023** | 2020, 2018, 2013 | EU-27 NUTS 3 complete only to 2023; SSB to 2023 |

Notes on the years:
- **2020 is the COVID trough.** Real growth "over the last 3 years" (2020→2023) will look strong
  everywhere. That is correct by the definition, but the panel should show a footnote.
- Rolling forward: GDP 2024 becomes possible when Eurostat fills 2024 for the 7 missing countries
  (usually in the spring release) and SSB publishes 2024 counties (~Dec 2026).

### Euro area (checked)
Bulgaria joined the euro area on **1 January 2026** (21 members). The non-euro countries in coverage are
exactly CZ, DK, HU, PL, RO, SE + UK, CH, NO, matching the spec. Bulgarian GDP for 2023 is already in EUR in
Eurostat, so no BGN toggle is needed. The euro-area list lives in `config/years.yaml` next to the years.

---

## 4. Licences

| Source | Licence / terms | Obligations |
|---|---|---|
| Census 2021 grid (Eurostat) | CC BY 4.0 / Commission reuse policy ✅ (read.me: "the source needs to be indicated"; modifications must be stated) | Attribution + a "modified by RadiusStats" statement on the Sources screen |
| GISCO grid, NUTS, countries | Eurostat reuse policy; administrative boundaries © EuroGeographics — free for **non-commercial** use with attribution ⚠️ | "© EuroGeographics for the administrative boundaries" |
| Eurostat tables | Eurostat copyright policy (free reuse, cite source) | cite |
| ARDECO | ⚠️ no licence text found yet (site in maintenance). Commission reuse decision 2011/833/EU expected to apply | confirm before release |
| WorldPop | CC BY 4.0 ⚠️ (alpha product) | cite DOI |
| ONS | Open Government Licence v3.0 | OGL attribution statement |
| BFS | opendata.swiss terms ("open use, must provide the source") ⚠️ | cite |
| SSB | CC BY 4.0 ⚠️ | cite |
| OpenStreetMap / OpenFreeMap tiles | ODbL (data); OpenFreeMap free, no key | "© OpenMapTiles © OpenStreetMap contributors" |
| Nominatim | OSMF usage policy: ≤ 1 request/s, identifying referer, **no autocomplete** | see Q2 |

---

## 5. Method details and deviations from the spec

1. **NUTS codes per cell.** The census grid itself has no NUTS columns (only `CNTR_ID`). The NUTS 2024
   codes come from GISCO `grid_1km.parquet`, joined on `GRD_ID`. Border cells can carry several
   NUTS 3 codes. Those are split by the per-country census values (`ESTAT_Census_2021_country.csv.zip`)
   across countries, and equally between NUTS 3 regions within one country; logged in the report.
2. **Unallocated census population** (FR, IT, FI, BG, EL, SE, DK, NO, BE, LV, LU, SI) has no cell. It
   disappears automatically, because each year is rescaled to the regional total.
3. **Real GDP across countries.** `gdp_real_Y` = regional constant-price GDP (national currency where
   applicable) × the exchange rate of a single **fixed base year** (= the reference year of the volume
   series, configured). Chained volume series are not exactly additive; the error is small over 10
   years and is noted on the Sources screen.
4. **Real GDP for CH / NO / UK.** CH: BFS growth at previous-year prices chained onto the base year.
   NO: SSB constant-price county values. UK: ONS CVM by local authority.
5. **PPS for UK and CH** = nominal national currency × (PPS per national currency for that year) from
   `prc_ppp_ind`. NO has regional PPS in Eurostat up to 2021 only, so the same national-ratio method
   is used for NO in 2023 (flagged in the report).
6. **Partial coverage.** Covered-land share = Σ land over cells with a covered country ID ÷ Σ land over all
   cells in the circle. Sea doesn't count. Land outside coverage comes from the GISCO countries layer.
7. **GDP allocation** uses the population raster of the same year as the weight (spec). In CBDs, where far
   more people work than live, GDP is shifted towards residential areas. That is a known bias of this
   method and is documented in VALIDATION.md.

---

## 6. Build order and milestones

1. **Pipeline for one country (Belgium: small, 3 languages, cross-border with FR/NL/DE/LU)** → COGs,
   manifest, fx, report; pyramid and validation tests.
2. **Query engine** (TS worker) + unit tests (CAGR, masking, pyramids, currency) against the BE COGs.
3. **Map UI** (MapLibre, OpenFreeMap, panel, URL state, a11y, 360 px).
4. **All countries** incl. UK/CH/NO special paths.
5. **Validation** script + VALIDATION.md (Paris, London, Zurich, Oslo, Warsaw, Basel at 25/50/100 km).
6. **Deploy instructions** in README.md.

Local tools: Python 3.12 via `uv` (system Python is 3.9), Node 26. No GDAL CLI; rasterio wheels ship
their own. Disk: 28 GB free, enough (peak ~5 GB).

---

## 7. Open questions

- **Q1 UK population date.** ONS gives mid-year (30 June), everyone else 1 January.
  Proposal: estimate UK 1 Jan Y as the mean of mid-(Y-1) and mid-Y. For 2025 this needs mid-2025 for all
  four nations; if Scotland/NI aren't out yet, use mid-2024 rolled forward with the E&W growth rate, and
  flag it.
- **Q2 Place search.** Nominatim's usage policy forbids search-as-you-type. Options: (a) Nominatim, but
  searching only on Enter/submit (default, follows the spec's source); (b) Photon (komoot), which
  allows type-ahead and uses the same OSM data.
- **Q3 Hosting (needs an account).** (a) **Cloudflare R2 + Pages**: free tier (10 GB, no egress
  fees), but R2 requires adding a payment method to the Cloudflare account; (b) **GitHub Pages only**:
  free, range requests and CORS expected to work (⚠️ to test with one COG), but there is a 1 GB site limit and files must be < 100 MB — our ~0.5 GB
  fits. Recommendation: build for either; start with GitHub Pages if you have a GitHub account.
- **Q4 Outermost regions.** OK to include Canaries/Azores/Madeira and exclude the French overseas
  departments, Svalbard and Jan Mayen?
- **Q5 ARDECO outage.** If ARDECO is still down when step 4 starts, fall back to Eurostat
  `nama_10r_2gvagr` (NUTS 2 volume growth) applied to every NUTS 3 inside the NUTS 2 region, and flag it?
