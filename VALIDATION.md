# RadiusStats Europe — Validation

Build of 18 Nov 2026: EU-27, United Kingdom, Switzerland, Norway. Population on 1 January 2025
(compared with 2022, 2020, 2015); GDP 2023 (real growth compared with 2020, 2018, 2013).
All numbers below are reproducible from the cached downloads:

```bash
cd pipeline && ./run.sh build && ./run.sh validate && ./run.sh xcheck
cd ../app && node node_modules/vite-node/vite-node.mjs scripts/spotchecks.ts && npm test
```

| What is checked | Result |
|---|---|
| Every region's allocation reproduces its official total (9 layers × ~1,550 regions) | max difference 2 × 10⁻¹⁶ (spec: 0.1 %) |
| Country totals in the 1 km rasters vs official national figures (30 countries × 6 measures) | all within 1 %, worst 0.57 % (Luxembourg, see §4) |
| Every 1 km raster cell equals the sum of its cell-table allocations | all 9 layers |
| Every pyramid level (2–32 km) has the same total as the 1 km level | all 9 layers, ≤ 5 × 10⁻⁶ (rounding, §5) |
| Real growth of each country vs national chain-linked volumes (EU + CH, 3 periods) | all within 0.3 pp p.a., worst 0.07 pp (CH) |
| Browser engine vs an independent Python computation (21 circles) | all within 0.012 % (spec for spot checks: 0.1 %) |
| Circle totals within bounds from official regional figures (21 circles × population, GDP) | 42 / 42 |
| App unit + integration tests | 51 pass |
| Pipeline unit tests | 14 pass |
| Accessibility (axe-core 4.14.0, WCAG 2.2 A/AA + best practice; desktop, 360 px, dialog open) | 0 violations |

`pipeline/run.sh validate` exits non-zero if any check fails; results with every number are in
`data/build/validation_report.json`, gaps and fallbacks in `data/build/build_report.json`.

---

## Status of each GDP figure

**Official** = the published figure, used unchanged (only converted at the ECB annual average rate or
with Eurostat's national PPP). **Derived** = calculated by this project from official figures.
**Imputed** = a missing value filled by assumption. **Extrapolated** = carried forward beyond the
source's last year. Flags are Eurostat's: p = provisional, e = estimated.

| Country group | Source (regions) | Nominal 2023 (EUR, national currency) | PPS 2023 | Real GDP 2013 / 2018 / 2020 / 2023 |
|---|---|---|---|---|
| EU-27 | Eurostat `nama_10r_3gdp` (NUTS 3, ~1,500) | **Official.** Provisional (p) for DE, FR, ES, EL; final elsewhere. Not yet revised to the latest national accounts (e.g. CY −2.1 %, LT −1.6 %, DE −0.8 % vs `nama_10_gdp`). Extra-regio GDP excluded | **Official** (one national factor per country, reproduces Eurostat's regional PPS) | **Derived.** No regional constant-price series is published (ARDECO unavailable): NUTS 3 nominal ÷ NUTS 2 implicit deflator (`nama_10r_2gvagr`, 2023 index flagged e for most countries, p for ES/FR), then scaled per country to national chain-linked volumes (factors mostly within ±0.5 %; IE 2018 −10.5 %, RO 2013 −3.0 %, CY 2023 +2.9 %). 2020 = nominal at 2020 rates. **Imputed:** IE062/IE063 2018 (nominal suppressed; NUTS 2 volume growth) |
| United Kingdom | ONS, regional GDP by local authority (361 LAD 2023), 23 Sep 2026 | **Official** (final for 2023; £1 m rounding in the source) | **Derived:** GBP ÷ Eurostat PPP (Eurostat's method) | **Official:** ONS chained volume index per authority, unchanged |
| Switzerland | BFS, GDP by canton (26), revised method 2026 | **Official**, provisional (BFS marks all years p). 0.17 % above Eurostat's national figure | **Derived:** CHF ÷ Eurostat PPP | **Official-based:** chained from BFS real change at previous-year prices |
| Norway | SSB 09391 county value added + Eurostat mainland GDP (11 counties) | **Derived** for 2013 / 2018 / 2020 (2021: national level official, split between counties by value added, taxes on products pro rata). **Extrapolated for 2023:** SSB's official 2023 county value added × the 2021 GDP / value-added ratio (Eurostat has no Norwegian regional GDP after 2021) | **Derived:** NOK ÷ Eurostat PPP | **Official-based:** chained from SSB county volume change; aggregated across the 2020 county reform with nominal weights (derived). **Imputed:** Trøndelag 2018 (merger year, all-county average) |
| All | — | Below the source region, every 1 km cell is **modelled**: the region's GDP split by resident population of the same year (2013 weights: 2014 for DE, NL, PL). Circle totals are exact sums of the cells | same | same |

Norway 2023 nominal GDP is the only GDP level carried forward in time; every other country's 2023 level
is a published 2023 figure.

## 1. Spot checks: browser engine vs independent computation

The engine (TypeScript, in the browser worker) and `pipeline/run.sh xcheck` (Python) share no code.
The engine projects the geodesic circle to EPSG:3035 and weights edge cells by 4×4 (16×16 for small
circles) sub-samples; `xcheck` takes every 1 km cell near the circle, samples it at 10 × 10 points,
projects each point to WGS84 with pyproj and measures its geodesic distance to the centre on the WGS84
ellipsoid. Same data (1 km level), different geometry code. Points: city-centre coordinates
(Paris Notre-Dame area, London Charing Cross area, Zurich HB, Oslo Sentrum, Warsaw centre, Basel
Marktplatz area, Brussels Grand-Place area).

| Place | r (km) | Population, engine | Population, independent | Diff | GDP EUR m, engine | GDP EUR m, independent | Diff |
|---|---:|---:|---:|---:|---:|---:|---:|
| Paris | 25 | 9,686,283 | 9,687,009 | -0.007 % | 715,525 | 715,560 | -0.005 % |
| Paris | 50 | 12,259,670 | 12,259,091 | +0.005 % | 816,720 | 816,697 | +0.003 % |
| Paris | 100 | 14,518,510 | 14,518,663 | -0.001 % | 890,965 | 890,972 | -0.001 % |
| London | 25 | 9,716,924 | 9,717,035 | -0.001 % | 749,551 | 749,547 | +0.001 % |
| London | 50 | 14,360,598 | 14,361,362 | -0.005 % | 979,044 | 979,046 | -0.000 % |
| London | 100 | 22,180,608 | 22,181,264 | -0.003 % | 1,319,520 | 1,319,550 | -0.002 % |
| Zurich | 25 | 1,934,656 | 1,934,702 | -0.002 % | 206,843 | 206,839 | +0.002 % |
| Zurich | 50 | 3,819,562 | 3,819,580 | -0.000 % | 350,319 | 350,317 | +0.001 % |
| Zurich | 100 | 8,900,889 | 8,899,979 | +0.010 % | 697,623 | 697,586 | +0.005 % |
| Oslo | 25 | 1,225,922 | 1,225,854 | +0.006 % | 100,582 | 100,579 | +0.003 % |
| Oslo | 50 | 1,690,062 | 1,690,005 | +0.003 % | 123,520 | 123,517 | +0.002 % |
| Oslo | 100 | 2,425,231 | 2,425,288 | -0.002 % | 158,992 | 158,994 | -0.002 % |
| Warsaw | 25 | 2,783,060 | 2,783,038 | +0.001 % | 127,425 | 127,425 | +0.000 % |
| Warsaw | 50 | 3,473,921 | 3,473,815 | +0.003 % | 140,850 | 140,849 | +0.001 % |
| Warsaw | 100 | 5,387,807 | 5,387,993 | -0.003 % | 175,007 | 175,009 | -0.001 % |
| Basel | 25 | 941,830 | 941,731 | +0.010 % | 101,919 | 101,918 | +0.001 % |
| Basel | 50 | 2,455,468 | 2,455,599 | -0.005 % | 181,604 | 181,608 | -0.002 % |
| Basel | 100 | 8,743,111 | 8,744,024 | -0.010 % | 669,057 | 669,096 | -0.006 % |
| Brussels | 25 | 2,606,048 | 2,605,736 | +0.012 % | 178,369 | 178,351 | +0.010 % |
| Brussels | 50 | 5,999,821 | 5,999,554 | +0.004 % | 346,615 | 346,602 | +0.004 % |
| Brussels | 100 | 14,525,136 | 14,525,663 | -0.004 % | 727,246 | 727,260 | -0.002 % |

Worst difference 0.012 % (Brussels 25 km). The difference is the edge sampling (4×4 or 16×16 vs 10×10),
as expected. Engine CPU time per query on the 1 km level: median 135 ms, max 440 ms (100 km circle,
31,000 cells; Node on an M-series laptop, cold).

## 2. Plausibility against official figures

Matching each other does not prove the population is in the right place. So each circle total is also
compared with **official regional totals** (Eurostat NUTS 3 / ONS local authorities / BFS cantons /
SSB counties, read from the source tables): the regions lying entirely inside the circle give a lower
bound, all regions the circle touches give an upper bound. In brackets: regions inside / touched.

| Place | r (km) | Population | Official bounds (regions inside – touched) | GDP EUR m | Official bounds |
|---|---:|---:|---|---:|---|
| Paris | 25 | 9,687,009 | 3,733,835 – 12,549,288 (2/8) | 715,560 | 456,190 – 829,638 |
| Paris | 50 | 12,259,091 | 6,900,499 – 13,377,216 (4/9) | 816,697 | 602,236 – 855,197 |
| Paris | 100 | 14,518,663 | 12,549,288 – 18,649,092 (8/18) | 890,972 | 829,638 – 1,038,364 |
| London | 25 | 9,717,035 | 7,612,517 – 12,048,298 (28/53) | 749,547 | 655,393 – 867,214 |
| London | 50 | 14,361,362 | 12,028,048 – 16,477,342 (58/83) | 979,046 | 872,687 – 1,067,059 |
| London | 100 | 22,181,264 | 20,215,032 – 24,522,796 (107/131) | 1,319,550 | 1,236,312 – 1,409,729 |
| Zurich | 25 | 1,934,702 | 0 – 4,196,233 (0/9) | 206,839 | 0 – 376,693 |
| Zurich | 50 | 3,819,580 | 1,842,426 – 5,933,378 (3/20) | 350,317 | 219,790 – 473,767 |
| Zurich | 100 | 8,899,979 | 6,575,464 – 11,774,267 (24/41) | 697,586 | 562,797 – 860,392 |
| Oslo | 25 | 1,225,854 | 0 – 2,050,625 (0/4) | 100,579 | 0 – 141,581 |
| Oslo | 50 | 1,690,005 | 724,290 – 2,686,252 (1/6) | 123,517 | 77,017 – 179,870 |
| Oslo | 100 | 2,425,288 | 1,464,970 – 4,920,320 (2/9) | 158,994 | 77,017 – 284,244 |
| Warsaw | 25 | 2,783,038 | 1,875,287 – 3,298,955 (1/3) | 127,425 | 108,751 – 137,735 |
| Warsaw | 50 | 3,473,815 | 1,875,287 – 5,516,306 (1/9) | 140,849 | 108,751 – 173,954 |
| Warsaw | 100 | 5,387,993 | 3,552,922 – 8,464,477 (4/16) | 175,009 | 142,355 – 227,083 |
| Basel | 25 | 941,731 | 201,384 – 4,127,536 (1/10) | 101,918 | 60,017 – 289,864 |
| Basel | 50 | 2,455,599 | 740,970 – 5,489,778 (3/14) | 181,608 | 92,473 – 361,888 |
| Basel | 100 | 8,744,024 | 4,478,093 – 13,129,491 (16/36) | 669,096 | 327,556 – 921,349 |
| Brussels | 25 | 2,605,736 | 1,271,709 – 5,114,741 (1/10) | 178,351 | 103,569 – 311,308 |
| Brussels | 50 | 5,999,554 | 2,934,707 – 8,751,354 (6/24) | 346,602 | 186,690 – 474,781 |
| Brussels | 100 | 14,525,663 | 8,831,329 – 22,209,977 (24/53) | 727,260 | 485,718 – 1,080,919 |

All 42 values lie within their bounds. Bounds are wide where regions are large compared with the
circle (Swiss cantons, Norwegian counties, Paris' large outer départements) and tight where regions are
small (London's boroughs: 7.6–12.0 M at 25 km). For orientation: Paris + the three inner départements
(762 km², 6.9 M) lie entirely inside the 50 km circle (lower bound 6.9 M at 50 km, 4 regions).

## 3. Detail for the spot checks

Growth figures, PPS, national currency and the per-country split, as the app shows them
(population growth = CAGR, % p.a.; real GDP growth at 2020 prices and fixed 2020 exchange rates).

| Place | r (km) | Pop. growth p.a. 3 / 5 / 10 y | Real GDP growth p.a. 3 / 5 / 10 y | GDP PPS m | National currency | Countries (population) |
|---|---:|---|---|---:|---|---|
| Paris | 25 | +0.35 % / +0.35 % / +0.31 % | +4.83 % / +1.19 % / +1.35 % | 658,681 | — | FR 100 % |
| Paris | 50 | +0.42 % / +0.42 % / +0.36 % | +4.76 % / +1.19 % / +1.32 % | 751,837 | — | FR 100 % |
| Paris | 100 | +0.38 % / +0.39 % / +0.33 % | +4.65 % / +1.16 % / +1.27 % | 820,184 | — | FR 100 % |
| London | 25 | +1.00 % / +0.58 % / +0.60 % | +5.40 % / +0.75 % / +1.80 % | 618,791 | GBP 652 bn | UK 100 % |
| London | 50 | +1.06 % / +0.69 % / +0.66 % | +4.92 % / +0.70 % / +1.72 % | 808,249 | GBP 852 bn | UK 100 % |
| London | 100 | +1.13 % / +0.85 % / +0.76 % | +4.62 % / +0.83 % / +1.87 % | 1,089,328 | GBP 1,148 bn | UK 100 % |
| Zurich | 25 | +1.21 % / +1.08 % / +1.16 % | +2.05 % / +0.56 % / +1.31 % | 130,555 | CHF 201 bn | CH 100 % |
| Zurich | 50 | +1.22 % / +1.08 % / +1.09 % | +2.54 % / +1.05 % / +1.52 % | 223,617 | CHF 340 bn | CH 94 %, DE 6 % |
| Zurich | 100 | +0.95 % / +0.82 % / +0.83 % | +3.12 % / +1.42 % / +1.69 % | 475,964 | CHF 678 bn | CH 67 %, DE 26 %, AT 4 %, FR 3 % |
| Oslo | 25 | +1.42 % / +1.19 % / +1.32 % | +5.17 % / +3.54 % / +3.03 % | 81,007 | NOK 1,149 bn | NO 100 % |
| Oslo | 50 | +1.42 % / +1.21 % / +1.28 % | +4.87 % / +3.33 % / +2.91 % | 99,480 | NOK 1,411 bn | NO 100 % |
| Oslo | 100 | +1.26 % / +1.09 % / +1.12 % | +4.49 % / +2.98 % / +2.70 % | 128,076 | NOK 1,816 bn | NO 99 %, SE 1 % |
| Warsaw | 25 | +0.36 % / +1.27 % / +1.02 % | +4.92 % / +3.77 % / +4.72 % | 188,239 | PLN 579 bn | PL 100 % |
| Warsaw | 50 | +0.38 % / +1.24 % / +0.99 % | +4.75 % / +3.70 % / +4.68 % | 208,072 | PLN 640 bn | PL 100 % |
| Warsaw | 100 | +0.03 % / +0.33 % / +0.34 % | +4.62 % / +3.64 % / +4.46 % | 258,530 | PLN 795 bn | PL 100 % |
| Basel | 25 | +0.93 % / +0.69 % / +0.61 % | +8.78 % / +5.42 % / +3.89 % | 67,930 | CHF 99 bn | CH 63 %, DE 24 %, FR 13 % |
| Basel | 50 | +0.83 % / +0.67 % / +0.63 % | +6.03 % / +3.21 % / +2.50 % | 125,388 | CHF 176 bn | CH 57 %, FR 23 %, DE 20 % |
| Basel | 100 | +0.83 % / +0.71 % / +0.71 % | +3.24 % / +1.62 % / +1.80 % | 456,976 | CHF 650 bn | CH 63 %, DE 19 %, FR 17 % |
| Brussels | 25 | +1.00 % / +0.79 % / +0.75 % | +3.75 % / +1.71 % / +1.59 % | 158,377 | — | BE 100 % |
| Brussels | 50 | +0.90 % / +0.72 % / +0.66 % | +4.02 % / +1.88 % / +1.77 % | 307,764 | — | BE 100 % |
| Brussels | 100 | +0.67 % / +0.56 % / +0.49 % | +3.67 % / +1.63 % / +1.61 % | 644,621 | — | BE 75 %, FR 13 %, NL 12 % |

Notable values, checked against the source tables:

- **Warsaw:** population +1.27 % p.a. over 5 years but +0.36 % over 3. Poland re-based its population on
  the 2021 census; Eurostat flags a break in 2021 (Warsaw city PL911 +4.3 % from 2020 to 2021 while
  Poland −2.3 %). Since this check the app shows a notice when a growth period crosses a flagged break
  (§4).
- **Basel 25 km:** real GDP +8.8 % p.a. over 3 years. BFS reports real growth for Basel-Stadt of +16.4 %,
  +12.9 % and +13.3 % in 2021–2023 (pharmaceuticals); 63 % of the circle's population is Swiss.
- **London:** real growth +5.4 % p.a. 2020–2023 vs +4.8 % for the UK as a whole (sum of the ONS
  local-authority chained volumes; COVID rebound in 2021).
- **Oslo:** real growth +4.9 % p.a. 2020–2023; SSB county volumes (Oslo +17.7 % 2020–2023).

## 4. Known differences, breaks and limitations

**Regional vs national accounts (vintage).** Eurostat's regional GDP (nama_10r_3gdp) is not yet revised
to the latest national accounts. The build reproduces the regional table exactly; against the newest
national GDP (nama_10_gdp) the regional country totals for 2023 differ by: Cyprus −2.1 %,
Lithuania −1.6 %, Germany −0.8 %, Croatia −0.8 %, Bulgaria −0.6 %; Ireland +0.8 %, Estonia +0.5 %; others
smaller. Country checks therefore use the country row of the same regional table (and report the
national-accounts difference in `validation_report.json`).

**Real growth benchmark.** For EU countries the regional volume series is scaled per country and year to
the latest national chain-linked volumes (as ARDECO does). Factors different from 1 by more than 1 %:
Ireland 2018 (0.895), Romania 2013 (0.970), Bulgaria 2023 (0.976), Malta 2023 (0.982), Cyprus 2023 (1.029),
Estonia 2023 (1.017), Latvia 2013 (1.011), Denmark 2013 (1.013). With the benchmark, the check against
national growth (§ summary) mainly tests allocation and rasterisation, not the source data. ARDECO itself
was unavailable (HTTP 500) during all builds; the NUTS 2 deflator method is used.

**Population series breaks** (Eurostat flag `b`) inside the comparison window: Germany 2023 (census 2022
re-basing; affects 3-, 5- and 10-year growth), Czechia 2021 and Poland 2021 (census 2021; 5 and 10
years), Portugal 2022 (5 and 10 years), Luxembourg 2017 (10 years). The app marks affected periods with
an asterisk and a notice when the country has at least 1 % of the circle's population.

**Gaps and fallbacks** (all in `build_report.json`):
- Germany, the Netherlands and Poland have no complete NUTS 3 population on 1 January 2013 in a NUTS
  version the grid knows: the 2013 GDP weights use 2014. This affects only how 2013 real GDP is spread
  within each region.
- Ireland IE062 / IE063: 2018 nominal GDP suppressed; real GDP moves with the NUTS 2 volume index.
- Norway: Eurostat's NUTS 3 GDP lacks three regions and ends in 2021; SSB county value added is scaled to
  Eurostat's mainland GDP (2011–2021: matches within 0.06 %), 2022–2023 carried forward with SSB growth.
  Trøndelag's 2018 volume change (county merger year) uses the all-county average (+2.07 %).
- Switzerland: BFS cantonal GDP (revised 2026) for every year; Swiss GDP in EUR is 0.17 % above Eurostat's
  national figure.
- UK: WorldPop 2021 (alpha release R2025A) distributes each local authority's ONS population; 31,000
  people (0.05 %) sit in WorldPop pixels just outside the generalised authority boundaries and were given
  the nearest authority. Population on 1 January = mean of the two mid-year estimates.
- French outermost regions (FRY, 2.2 M people) are not mapped; national comparisons exclude them.
- Extra-regio GDP (embassies, Norway's continental shelf, etc.) cannot be located and is excluded.

**Per-country split at borders.** A 1 km cell is labelled with the country that has most of its people.
Circle totals are unaffected, but the per-country breakdown counts a mixed border cell entirely to one
country. Population totals read through the country raster differ from the official ones by up to
0.57 % (Luxembourg, which has many mixed cells with FR/BE/DE); all other countries ≤ 0.11 %.

**GDP is spread by where people live.** Regional GDP is allocated to cells by resident population, so
small circles put GDP in residential areas rather than at workplaces. Below 25 km the app shows a
low-confidence notice. For example, a small circle around La Défense gets Hauts-de-Seine's GDP in
proportion to the people who live there, not to the jobs there. The effect is smaller where the source
regions are small: the City of London is its own local authority, so its GDP stays in the City's cells.

**Coarse levels.** Circles beyond 178 km use 2 km cells, beyond 356 km 4 km cells. Edge cells are assumed
uniform inside, which is visible only at the edge: the Malta test (§ tests) gives the same total at
1–8 km within 0.012 %; Brussels 25 km at 1 vs 2 km differs by < 2 %.

## 5. Precision of the stored rasters

Data bands keep 12 of 23 float32 mantissa bits (rounded to nearest) for smaller downloads: at most
0.012 % per cell; on the European total ≤ 5 × 10⁻⁶ per level. The spot checks above include this.

## 6. Download per query (4G)

Measured with real HTTP range requests against the Vite dev server (`app/scripts/measure-http.mjs`),
cell budget 100,000, one 12-band COG per level with 64 px tiles:

| Circle | Level | Cold query (first) | Moving 5 km |
|---|---|---|---|
| 10–50 km (London, Paris, Warsaw) | 1 km | 160–430 KB, 4–6 requests | 0 B (cached) |
| 100 km | 1 km | 1.0–1.3 MB, 7–8 requests | 0 B |
| 200 km | 2 km | 1.1–1.2 MB, 5 requests | 0 B |
| 500 km | 4 km | 1.0–1.7 MB, 5–6 requests | 0–112 KB |

At about 10 Mbit/s that is under 0.5 s for typical circles and about 1.5 s in the worst case, plus CPU
time (§1). Not measured on a real phone over 4G.

## 7. Accessibility and devices

- **axe-core 4.14.0** (WCAG 2.0/2.1/2.2 A and AA, best practice), run in the browser on the dev build:
  0 violations on desktop (population and GDP views, Sources dialog open) and at 360 × 740 (sheet
  collapsed and expanded). Fixed during this step: content outside landmarks (root is now `<main>`),
  map attribution links distinguished by colour only (now underlined), translucent panel and legend
  backgrounds that made contrast undeterminable over dark heat-map areas (now opaque; the lightest text,
  slate-500 on white, is 4.76 : 1).
- **Keyboard:** tab order Sources → search → radius slider → radius box → layer → heat map → "Point at map
  centre" → map → zoom buttons. Enter on the focused map places the point at the map centre. The radius
  slider did not move with the arrow keys (its square-root scale made each step smaller than the
  rounding); fixed: arrows step 0.5 / 1 / 5 km by range, PageUp/PageDown ten steps, Home/End 1 / 500 km
  (unit-tested). Sources dialog: focus moves to Close, Escape closes it, focus returns to the button.
- **360 px:** no horizontal scrolling; the bottom sheet starts collapsed with a one-line headline; the
  map's zoom buttons and attribution now sit above the collapsed sheet (they were hidden behind it).
- **Not tested:** a real screen reader (VoiceOver/NVDA), a real phone, PWA installation, browsers other
  than the Chromium-based preview.
