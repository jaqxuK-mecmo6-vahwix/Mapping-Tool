# RadiusStats Europe

Population and GDP within a chosen radius (1–500 km) of any point in the EU-27, the United Kingdom,
Switzerland and Norway. Population on 1 January 2025 with growth over 3, 5 and 10 years; GDP 2023 in EUR
(nominal or PPS) or the national currency, with real growth. A static web app (installable PWA) on open
data, non-commercial.

| Document | Content |
|---|---|
| [PLAN.md](PLAN.md) | architecture, decisions, status of each build step |
| [DATA_SOURCES.md](DATA_SOURCES.md) | every source, version, licence, and how the data are modified |
| [VALIDATION.md](VALIDATION.md) | checks, spot checks, status of each GDP figure, limitations |
| [pipeline/README.md](pipeline/README.md) | data pipeline commands and output format |

## Location tiers

For a 25 km or 50 km circle the results panel shows a screening grade, A–D, for comparing locations
(e.g. for real estate). It is not investment advice: rents, yields, supply and local rules are not in it.

- **25 km, city tier:** the city and its inner suburbs.
- **50 km, market tier:** the whole commuting region.

A circle gets the highest tier whose GDP **and** population thresholds it both meets (GDP 2023, nominal
EUR; population 1 January 2025):

| Tier | 25 km city tier | 50 km market tier |
|---|---|---|
| A | Global city: ≥ €200 bn and ≥ 4 M people | Gateway metro: ≥ €300 bn and ≥ 5 M people |
| B | Major city: ≥ €75 bn and ≥ 1.5 M | Major metro: ≥ €100 bn and ≥ 2 M |
| C | Regional city: ≥ €20 bn and ≥ 0.5 M | Regional centre: ≥ €30 bn and ≥ 1 M |
| D | Local market: below C | Local market: below C |

- **"+"**: population growth ≥ 0.8 % a year **and** real GDP growth ≥ 2.5 % a year, both over 10 years.
- **"−"**: population falling by more than 0.1 % a year. Smaller changes count as flat.
- **Borderline**: GDP and population both within 5 % of the next tier's thresholds.
- **Irish GDP warning**: shown when Ireland has ≥ 25 % of the circle's GDP. Multinational profits booked
  in Ireland inflate GDP there (Dublin about €150k per person at 25 km), so judge those areas by population.

**How the thresholds were chosen:** from the 25 km and 50 km totals of 51 European cities, read from
this data build at each city centre. The lines fall in natural gaps between groups of cities.

Examples:

| City | 25 km | 50 km |
|---|---|---|
| Madrid | A+ | A+ |
| Berlin | A | B |
| Amsterdam | B+ | A+ |
| Dublin | B+ | B+ |
| Athens | B− | B− |
| Bucharest | B | C (borderline B) |
| Oslo | C+ | C+ |
| Aarhus | C | D |

The rules and thresholds are in `app/src/engine/tier.ts`, with tests in
`app/src/engine/__tests__/tier.test.ts`. After a data update, re-check the thresholds against the new
totals.

## Layout

```
config/radiusstats.yaml   years, coverage, currencies, national sources (single source of truth)
pipeline/                 Python: downloads, 1 km rasters, pyramids, COGs, heat tiles, validation
app/                      Vite + React + TypeScript app; query engine in a Web Worker (app/src/engine)
data/build/               pipeline output, served to the app under data/ (not in git)
scripts/                  deploy to GitHub Pages, local preview, post-deploy check
```

## Run it locally

Requires `uv` (Python), Node 22+ and npm.

```bash
cd pipeline && ./run.sh build       # ~6 min; first run downloads ~0.9 GB (cached in pipeline/cache)
./run.sh validate                    # must pass before deploying
cd ../app && npm install && npm run dev   # http://localhost:5173 (serves ../data/build at /data/)
```

Tests: `pipeline/run.sh test` and `npm test` in `app/` (the app's integration tests use `data/build`).

## Deploy to GitHub Pages

The site is static: the app build plus `data/build` (~153 MB; largest file 53 MB, under GitHub's 100 MB
limit). GitHub Pages serves byte ranges (HTTP 206) and CORS headers, which the map data need. No server,
no database, no API keys.

The account steps are yours; nothing in this repository creates accounts or pushes on its own.

**Once:**

1. Create a GitHub account if you do not have one (free).
2. Create a new repository, e.g. `radiusstats-europe`. With a free account, GitHub Pages requires the
   repository to be **public**: the code, configuration and documents become visible. Downloads, the
   data build and the assembled site are in `.gitignore` and are not pushed with `main`; the data
   build is published only on the `gh-pages` branch, by the deploy script.
3. Connect this folder and push the code:
   ```bash
   git remote add origin https://github.com/<user>/radiusstats-europe.git
   git push -u origin main
   ```

**Each deploy** (after `pipeline/run.sh build` and `validate`):

4. Optional preview of exactly what will be published, served from a subfolder like GitHub Pages:
   ```bash
   scripts/deploy-gh-pages.sh --dry-run
   node scripts/serve-site.mjs        # http://localhost:4173/radiusstats-europe/
   ```
5. Publish (asks before pushing):
   ```bash
   scripts/deploy-gh-pages.sh
   ```
   It refuses to run if the validation report has failures, builds the app, assembles `site/` (app +
   `data/`) and force-pushes it as a single commit to the `gh-pages` branch, so old data builds do not
   accumulate in the history. `main` is not changed. GitHub warns that `cog/L1.tif` is over 50 MB;
   that is only a warning.
6. First deploy only: on GitHub, **Settings → Pages → Build and deployment → Source: Deploy from a
   branch**, branch `gh-pages`, folder `/ (root)`, Save.
7. Wait for "pages build and deployment" in the **Actions** tab (1–3 minutes), then check the live site:
   ```bash
   node scripts/check-deploy.mjs https://<user>.github.io/radiusstats-europe/
   node app/scripts/measure-http.mjs https://<user>.github.io/radiusstats-europe/data/
   ```
   The first checks the pages, the data manifest and range requests on the map data; the second
   measures what typical queries download on that host.

The app uses relative paths, so it works under any repository name or a custom domain (Settings →
Pages → Custom domain). Shared links keep their point, radius and layer in the URL after `#`.

**After deploying, check by hand:** the app installs as a PWA (browser menu → Install / Add to Home
Screen; the service worker cannot be tested on the local preview) and the map loads on a phone over
mobile data.

### Updating the data

Edit `config/radiusstats.yaml` (e.g. `population.latest`, `gdp.latest`), then
`pipeline/run.sh build && pipeline/run.sh validate`, review `data/build/build_report.json` and
`VALIDATION.md`, and run `scripts/deploy-gh-pages.sh` again. The data are not cached by the service
worker, so visitors get the new data on their next visit.

### Usage limits of third-party services

The base map (OpenFreeMap) and place search (Nominatim, OpenStreetMap Foundation) are free public
services. Nominatim allows at most one request per second and no heavy use; the app only searches when
the user submits the search box. For high traffic, switch place search to a hosted geocoder or your own
instance (`app/src/lib/nominatim.ts`).

## Licence and attribution

Non-commercial project. Data: © European Union (Eurostat, GISCO), © EuroGeographics for administrative
boundaries, ONS (Open Government Licence v3.0, contains OS data © Crown copyright), WorldPop (CC BY 4.0),
BFS, SSB (CC BY 4.0); map © OpenMapTiles © OpenStreetMap contributors (ODbL). Full list and the
modifications made: [DATA_SOURCES.md](DATA_SOURCES.md) and the app's "Sources & licences" screen.
