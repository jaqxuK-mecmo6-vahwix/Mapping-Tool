# RadiusStats Europe — data pipeline

```bash
./run.sh build      # downloads (cached in cache/downloads) + builds data/build
./run.sh validate   # checks regions (0.1 %), raster vs cell table, pyramids, country totals (1 %)
./run.sh test       # unit tests
```

Requires `uv`. The virtualenv lives in `~/.local/share/radiusstats-europe/venv` (override with
`RADIUSSTATS_VENV`) because this folder's name contains `:`, which PROJ cannot handle.

Years, coverage, currencies and the countries to build are in `../config/radiusstats.yaml`.
`build_countries: [BE]` builds one country; `all` builds everything.

## Outputs (`data/build/`)

| file | content |
|---|---|
| `manifest.json` | grid (EPSG:3035 origin/size), levels, years, countries, layers with per-level COG URLs |
| `fx.json` | annual average rates (currency per EUR) by year, reference and real-base years |
| `cog/{layer}/L{km}.tif` | float32 COG, DEFLATE + floating-point predictor, nodata −1, 256 px tiles. L2…L32 are exact 2×2 **sums** of the level below (not GDAL overviews) |
| `cog/country/L{km}.tif` | uint8 country id (manifest `countries[].id`), 0 = sea, 255 = land outside coverage |
| `cog/land/L{km}.tif` | land share of the cell, 0–1 |
| `build_report.json` | gaps, fallbacks, NUTS mappings, downloads with sha256, Eurostat update stamps |
| `validation_report.json` | output of `run.sh validate` |

Layers: `pop_{Y}` (persons, 1 Jan), `gdp_nom_eur_{Y}` (million EUR), `gdp_pps_{Y}` (million PPS),
`gdp_real_{Y}` (million EUR at base-year prices and base-year exchange rates).

## Modules

`sources/` (Eurostat SDMX, GISCO/census readers) → `population.py` (cell table, NUTS-version-aware
allocation) → `gdp.py` (nominal, PPS, real with ARDECO or NUTS 2 deflator fallback) → `pyramid.py`
→ `cog.py` → `cli.py` (orchestration, manifest) · `validate.py` · `fx.py` · `report.py` · `fetch.py`.
