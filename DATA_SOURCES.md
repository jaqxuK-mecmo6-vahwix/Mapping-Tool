# Data sources

Exact download URLs, sizes, SHA-256 hashes and fetch times for each build are in
`data/build/build_report.json` → `downloads`. Eurostat "last update" stamps are in the same file
→ `eurostat_last_update`. This page lists the sources, citations and licences.
Status: sources used by the **Belgium** build (step 1) are marked ✔; the rest are added in step 4.

## Population

| ✔ | Source | Version / table | URL | Licence and citation |
|---|---|---|---|---|
| ✔ | Eurostat Census 2021 population grid, 1 km | V3 (final), 30 May 2026; per-country files `CENSUS_GRID_N_{CC}_2021.csv`, STAT=T | https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip | © European Union 2026, Eurostat. Reuse allowed with source indicated; **this product modifies the data** (rescaled to yearly NUTS 3 totals). CC BY 4.0 |
| ✔ | Eurostat GISCO 1 km grid (NUTS 2016/2021/2024 codes and land share per cell) | v1.4, 03/07/2025, `grid_1km.parquet` | https://gisco-services.ec.europa.eu/grid/grid_1km.parquet | © European Union, Eurostat/GISCO. Population attributes (TOT_P_*) carry their own download rules; only the NUTS codes and LAND_PC are used here. Administrative boundaries © EuroGeographics |
| ✔ | Eurostat, population on 1 January by broad age group, sex and NUTS 3 region | `demo_r_pjanaggr3` (sex=T, age=TOTAL) | https://ec.europa.eu/eurostat/databrowser/view/demo_r_pjanaggr3/default/table | © European Union, Eurostat |
| | ONS mid-year population estimates, local authorities | mid-2015 … mid-2025 | ons.gov.uk | Open Government Licence v3.0 |
| | WorldPop Global2, constrained 1 km population counts | R2025A v1 (alpha) | https://hub.worldpop.org/geodata/listing?id=136 | CC BY 4.0, WorldPop (University of Southampton) |

## GDP

| ✔ | Source | Version / table | URL | Licence and citation |
|---|---|---|---|---|
| ✔ | Eurostat, GDP at current market prices by NUTS 3 region | `nama_10r_3gdp` (MIO_EUR, MIO_PPS_EU27_2020, MIO_NAC) | https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3gdp/default/table | © European Union, Eurostat |
| ✔ | Eurostat, GDP in volume by NUTS 2 region | `nama_10r_2gvagr` (B1GQ, I20) | https://ec.europa.eu/eurostat/databrowser/view/nama_10r_2gvagr/default/table | © European Union, Eurostat |
| (✔) | ARDECO, GDP at constant prices, NUTS 3 | variable `SOVGD`, NUTS 2024 | https://territorial.ec.europa.eu/ardeco-api-v2/rest/export/SOVGD | European Commission (JRC, DG REGIO). **API returned HTTP 500 on 2026-11-14/15; fallback used (see below)** |
| ✔ | Eurostat, national GDP (validation) | `nama_10_gdp` (CP_MEUR, CP_MPPS_EU27_2020, CLV20_MEUR) | https://ec.europa.eu/eurostat/databrowser/view/nama_10_gdp/default/table | © European Union, Eurostat |
| | ONS, Regional GDP: local authorities | 1998–2024, released 23 Sep 2026 | ons.gov.uk | Open Government Licence v3.0 |
| | BFS, cantonal GDP | revised provisional 2011–2024 | bfs.admin.ch | BFS terms of use (source must be cited) |
| | SSB, county national accounts | StatBank 09391 | ssb.no | CC BY 4.0 |
| | Eurostat purchasing power parities (PPS for UK, CH) | `prc_ppp_ind` | Eurostat | © European Union, Eurostat |

## Other

| ✔ | Source | Version / table | URL | Licence and citation |
|---|---|---|---|---|
| ✔ | Eurostat/ECB euro exchange rates, annual averages | `ert_bil_eur_a` (statinfo=AVG) | https://ec.europa.eu/eurostat/databrowser/view/ert_bil_eur_a/default/table | © European Union, Eurostat; ECB |
| | OpenFreeMap vector tiles | — | https://openfreemap.org | © OpenMapTiles © OpenStreetMap contributors (ODbL) |
| | Nominatim geocoder | — | https://nominatim.openstreetmap.org | © OpenStreetMap contributors; OSMF usage policy |

## Methods that change source values (stated as required by the Eurostat reuse policy)

- Census 2021 cell populations are **rescaled** within each NUTS 3 region to that year's Eurostat
  total. Cells shared by two NUTS 3 regions are split equally between them.
- GDP is **allocated** to cells in proportion to the same year's cell population.
- **Real GDP fallback (in use):** ARDECO was unavailable, so real GDP per NUTS 3 region = nominal
  GDP (national currency) ÷ the implicit GDP deflator of its NUTS 2 region (Eurostat
  nama_10r_3gdp + nama_10r_2gvagr), at 2020 prices, converted to EUR at the 2020 average rate.
  Check for Belgium: country growth from the grid is within 0.03 pp p.a. of national chain-linked volumes.
- Extra-regio GDP (NUTS code `..ZZZ`, e.g. embassies, offshore installations) cannot be located
  and is excluded (Belgium 2023: EUR 187 m, 0.03 %).
