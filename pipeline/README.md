# RadiusStats Europe — data pipeline

```bash
./run.sh build      # downloads (cached in cache/downloads) + builds data/build   (~5–6 min, ~6 GB peak memory)
./run.sh validate   # checks regions (0.1 %), raster vs cell table, pyramids, country totals (1 %), real growth
./run.sh xcheck     # independent circle totals (pyproj geodesics) -> data/build/xcheck.json, for VALIDATION.md
./run.sh test       # unit tests
```

Requires `uv`. The virtualenv lives in `~/.local/share/radiusstats-europe/venv` (override with
`RADIUSSTATS_VENV`) because this folder's name contains `:`, which PROJ cannot handle.
The first build downloads about 0.9 GB (census grid 566 MB, GISCO grid 176 MB, WorldPop UK 86 MB, ONS, BFS,
SSB and Eurostat tables); everything is cached.

Years, coverage, currencies, national sources and the countries to build are in
`../config/radiusstats.yaml`. `build_countries: all` builds everything; a list (e.g. `[BE]`) builds a subset.
Quote `"NO"` in the YAML (a bare NO is read as false; the config loader refuses it).

## Outputs (`data/build/`)

| file | content |
|---|---|
| `manifest.json` | grid (EPSG:3035 origin/size), levels, years, countries, `bands`, layers with per-level `{url, band}`, `pps_per_eur` factors, heat-map metadata |
| `fx.json` | annual average rates (currency per EUR) by year, reference and real-base years |
| `cog/L{km}.tif` | **one multi-band COG per pyramid level** (1, 2, 4, 8, 16, 32 km): float32, pixel-interleaved, DEFLATE + floating-point predictor, nodata −1, 64 px tiles. Bands in `manifest.bands` order. Data bands of L2…L32 are exact 2×2 **sums** of the level below (not GDAL overviews), stored with 12 mantissa bits |
| band `country` | country id (manifest `countries[].id`), 0 = sea, 255 = land outside coverage; coarse levels: most-populated child |
| bands `land`, `land_covered` | land share of the cell, and the share lying in a covered country (partial-coverage notice); means |
| `heat/{population,gdp}.pmtiles` | Web Mercator PNG density tiles, z3–8, for the map |
| `coverage_mask.geojson` | land outside coverage (grey overlay) |
| `build_report.json` | gaps, fallbacks, NUTS mappings, benchmark factors, downloads with sha256, Eurostat update stamps |
| `validation_report.json` | output of `run.sh validate` |
| `xcheck.json` | output of `run.sh xcheck` |

Layers: `pop_{Y}` (persons, 1 Jan), `gdp_nom_eur_{Y}` (million EUR), `gdp_real_{Y}` (million EUR at
base-year prices and base-year exchange rates). PPS has no layer: it is EUR × one national factor per
country (`pps_per_eur`), which is how Eurostat derives regional PPS.

## Modules

`sources/` (Eurostat SDMX, GISCO/census readers, `national.py` for BFS/SSB/ONS, `uk_grid.py` for the
WorldPop-based UK base grid) → `population.py` (cell table, NUTS-version-aware allocation) → `gdp.py`
(nominal, PPS factors, real with ARDECO or NUTS 2 deflator fallback, national benchmark) → `pyramid.py`
→ `cog.py` (multi-band level stack) → `cli.py` (orchestration, manifest) · `validate.py` · `xcheck.py` ·
`fx.py` · `heat.py` · `coverage.py` · `report.py` · `fetch.py`.
