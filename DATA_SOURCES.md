# Data sources

Exact download URLs, sizes, SHA-256 hashes and fetch times for each build are in
`data/build/build_report.json` → `downloads`. Eurostat "last update" stamps are in the same file
→ `eurostat_last_update`. This page lists the sources, citations and licences.
Status: ✔ = used by the current full build (EU-27, UK, CH, NO; step 4).

## Population

| ✔ | Source | Version / table | URL | Licence and citation |
|---|---|---|---|---|
| ✔ | Eurostat Census 2021 population grid, 1 km | V3 (final), 30 May 2026; per-country files `CENSUS_GRID_N_{CC}_2021.csv`, STAT=T | https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip | © European Union 2026, Eurostat. Reuse allowed with source indicated; **this product modifies the data** (rescaled to yearly NUTS 3 totals). CC BY 4.0 |
| ✔ | Eurostat GISCO 1 km grid (NUTS 2016/2021/2024 codes and land share per cell) | v1.4, 03/07/2025, `grid_1km.parquet` | https://gisco-services.ec.europa.eu/grid/grid_1km.parquet | © European Union, Eurostat/GISCO. Population attributes (TOT_P_*) carry their own download rules; only the NUTS codes and LAND_PC are used here. Administrative boundaries © EuroGeographics |
| ✔ | Eurostat, population on 1 January by broad age group, sex and NUTS 3 region | `demo_r_pjanaggr3` (sex=T, age=TOTAL) | https://ec.europa.eu/eurostat/databrowser/view/demo_r_pjanaggr3/default/table | © European Union, Eurostat |
| ✔ | ONS mid-year population estimates by local authority (LAD 2023), UK | MYEB tables mid-2011 … mid-2025 (`myebtablesuk20112025.xlsx`, sheets MYEB3 and MYEB5) | https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/populationestimatesforukenglandandwalesscotlandandnorthernireland | Office for National Statistics, Open Government Licence v3.0 |
| ✔ | WorldPop Global2, constrained population counts, UK 2021, 3 arc-seconds (~100 m) | R2025A v1 (alpha), `gbr_pop_2021_CN_100m_R2025A_v1.tif` | https://hub.worldpop.org/geodata/listing?id=136 | CC BY 4.0. Bondarenko M. et al. 2025, WorldPop, University of Southampton, doi:10.5258/SOTON/WP00839. **Modified** (aggregated to 1 km, rescaled to ONS totals) |
| ✔ | ONS Local Authority Districts (May 2023) boundaries UK BGC | V2, ArcGIS feature service | https://geoportal.statistics.gov.uk | Office for National Statistics, OGL v3.0. Contains OS data © Crown copyright and database right; contains NRS and LPS Intellectual Property data |

## GDP

| ✔ | Source | Version / table | URL | Licence and citation |
|---|---|---|---|---|
| ✔ | Eurostat, GDP at current market prices by NUTS 3 region | `nama_10r_3gdp` (MIO_EUR, MIO_PPS_EU27_2020, MIO_NAC) | https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3gdp/default/table | © European Union, Eurostat |
| ✔ | Eurostat, GDP in volume by NUTS 2 region | `nama_10r_2gvagr` (B1GQ, I20) | https://ec.europa.eu/eurostat/databrowser/view/nama_10r_2gvagr/default/table | © European Union, Eurostat |
| (✔) | ARDECO, GDP at constant prices, NUTS 3 | variable `SOVGD`, NUTS 2024 | https://territorial.ec.europa.eu/ardeco-api-v2/rest/export/SOVGD | European Commission (JRC, DG REGIO). **API returned HTTP 500 on 2026-11-14/15; fallback used (see below)** |
| ✔ | Eurostat, national GDP (benchmark for real growth; validation) | `nama_10_gdp` (CP_MEUR, CP_MPPS_EU27_2020, CLV20_MEUR, CP_MNAC) | https://ec.europa.eu/eurostat/databrowser/view/nama_10_gdp/default/table | © European Union, Eurostat |
| ✔ | ONS, Regional GDP: local authorities (Table 5 current market prices; Table 9 chained volume index) | 1998–2024, released 23 Sep 2026 (corrected edition) | https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductlocalauthorities | Office for National Statistics, Open Government Licence v3.0 |
| ✔ | BFS, GDP by major region and canton (current prices; real change at previous-year prices) | je-d-04.02.06.01, 2011–2024 (provisional, revised method 2026), published 26 Oct 2026 | https://dam-api.bfs.admin.ch/hub/api/dam/assets/36251918/master | Swiss Federal Statistical Office (BFS). Open use, source must be cited ("OPEN-BY") |
| ✔ | SSB, regional accounts by county: value added at basic prices (current NOK) and volume change | StatBank 09391, 2011–2023 | https://www.ssb.no/en/statbank/table/09391 | Statistics Norway, CC BY 4.0 |
| ✔ | Eurostat purchasing power parities, GDP (PPS for UK, CH, NO; national sources only) | `prc_ppp_ind` (PPP_EU27_2020, GDP) | https://ec.europa.eu/eurostat/databrowser/view/prc_ppp_ind/default/table | © European Union, Eurostat |

## Other

| ✔ | Source | Version / table | URL | Licence and citation |
|---|---|---|---|---|
| ✔ | Eurostat/ECB euro exchange rates, annual averages | `ert_bil_eur_a` (statinfo=AVG) | https://ec.europa.eu/eurostat/databrowser/view/ert_bil_eur_a/default/table | © European Union, Eurostat; ECB |
| ✔ | Eurostat GISCO countries 2024, 1:3 million (grey-out mask of non-covered countries) | `CNTR_RG_03M_2024_4326.geojson` | https://gisco-services.ec.europa.eu/distribution/v2/countries/geojson/CNTR_RG_03M_2024_4326.geojson | © EuroGeographics for the administrative boundaries; non-commercial use with attribution |
| ✔ | OpenFreeMap vector tiles | — | https://openfreemap.org | © OpenMapTiles © OpenStreetMap contributors (ODbL) |
| ✔ | Nominatim geocoder | — | https://nominatim.openstreetmap.org | © OpenStreetMap contributors; OSMF usage policy |

## Methods that change source values (stated as required by the Eurostat reuse policy)

- Census 2021 cell populations are **rescaled** within each NUTS 3 region to that year's Eurostat
  total. Cells shared by two NUTS 3 regions are split equally between them.
- GDP is **allocated** to cells in proportion to the same year's cell population.
- **Real GDP fallback (in use):** ARDECO was unavailable, so real GDP per NUTS 3 region = nominal
  GDP (national currency) ÷ the implicit GDP deflator of its NUTS 2 region (Eurostat
  nama_10r_3gdp + nama_10r_2gvagr), at 2020 prices, converted to EUR at the 2020 average rate.
  Check for Belgium: country growth from the grid is within 0.03 pp p.a. of national chain-linked volumes.
- **Real GDP benchmark:** for countries using Eurostat regional data, regional real GDP is scaled per
  year so that the country's growth since 2020 equals the latest national chain-linked volumes
  (`nama_10_gdp` CLV20_MEUR). Regional volume tables lag national revisions (up to ~3 % on the level,
  e.g. Cyprus 2023, Romania 2013). Factors per country and year are in `build_report.json`.
- Where a NUTS 3 region's nominal GDP is suppressed in a year (Ireland IE062/IE063 in 2018), its real GDP
  moves with its NUTS 2 volume index from the nearest year.
- **PPS:** Eurostat converts regional GDP to PPS with one national factor per country, so the app
  computes a circle's PPS as the sum of each country's EUR part × that country's factor
  (`manifest.json` → `pps_per_eur`); for the UK, CH and NO the factor is national currency ÷ Eurostat PPP.
- **United Kingdom** (no Census 2021 grid and no Eurostat regional data after 2019): WorldPop 2021
  ~100 m counts are assigned to local authorities (LAD 2023) by pixel centre and summed per 1 km
  cell and authority; each year's ONS total per authority is spread in proportion. Population on
  1 January = mean of the ONS mid-year estimates of the previous and the same year. GDP: ONS current
  prices per authority, real growth from the ONS chained volume index, converted with Eurostat/ECB
  rates (GBP) and PPPs.
- **Switzerland:** GDP by canton from BFS for all years (newer and revised compared with Eurostat,
  which ends in 2022); real GDP chained from BFS real change at previous-year prices.
- **Norway:** Eurostat's NUTS 3 GDP has gaps (three regions missing) and ends in 2021. County value
  added from SSB is scaled to Eurostat's mainland GDP (NO0 minus Svalbard) for 2011–2021 and carried
  forward with the 2021 ratio for 2022–2023; real growth from SSB county volume changes, aggregated
  over the 2020 county reform; Trøndelag's 2018 change (merger year) uses the all-county average.
- Germany has no NUTS 3 population on 1 January 2013: the 2013 GDP weights use 2014 (within-region
  distribution only). French outermost regions (FRY) are not mapped and are excluded from national
  comparisons.
- **Series breaks:** years in which Eurostat flags a break (`b`) in a country's population series
  (census re-basing: CZ/PL 2021, PT 2022, DE 2023, LU 2017) are listed in `manifest.json` →
  `series_breaks`; the app marks growth periods that cross one. The data themselves are not adjusted.
- Data layers keep 12 of 23 float32 mantissa bits (rounded to nearest; ≤ 0.012 % per cell) for smaller
  downloads.
- Extra-regio GDP (NUTS code `..ZZZ`, e.g. embassies, offshore installations) cannot be located
  and is excluded (e.g. Belgium 2023: EUR 187 m, 0.03 %; Norway: the continental shelf).
