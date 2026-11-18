/** One circle query: choose level, mask, read windows, sum per layer and country. */
import { chooseLevel, geodesicCircle, polygonToPixels, project, windowFor } from "./geometry";
import { coverageWeights, subsamplingFor, weightStats, weightedSumByCountry } from "./mask";
import type { RasterSource } from "./source";
import type { LayerSum, Manifest, QueryParams, QueryResult, Window } from "./types";

function levelRef(m: Manifest, layer: string, level: number): { url: string; band: number } {
  const meta = m.layers[layer];
  if (!meta) throw new Error(`unknown layer ${layer}`);
  const f = meta.levels[String(level)];
  if (!f) throw new Error(`layer ${layer} has no level ${level}`);
  return { url: f.url, band: f.band ?? 0 };
}

function read(src: RasterSource, m: Manifest, layer: string, level: number, win: Window, signal?: AbortSignal) {
  const { url, band } = levelRef(m, layer, level);
  return src.read(url, win, signal, band);
}

/** Country code at a point (1 km level), or undefined for sea / outside coverage / outside grid. */
export async function countryAt(m: Manifest, src: RasterSource, lat: number, lon: number,
                                signal?: AbortSignal): Promise<string | undefined> {
  const [x, y] = project(lon, lat);
  const col = Math.floor((x - m.grid.xmin) / m.grid.cell_m);
  const row = Math.floor((m.grid.ymax - y) / m.grid.cell_m);
  if (col < 0 || row < 0 || col >= m.grid.width || row >= m.grid.height) return undefined;
  const d = await read(src, m, "country", 1, { level: 1, row0: row, col0: col, width: 1, height: 1 }, signal);
  return m.countries.find((c) => c.id === d[0] && c.built)?.code;
}

export async function runQuery(m: Manifest, src: RasterSource, params: QueryParams,
                               signal?: AbortSignal): Promise<QueryResult> {
  const t0 = performance.now();
  const level = chooseLevel(params.radiusKm, m.levels_km);
  const poly = polygonToPixels(geodesicCircle(params.lat, params.lon, params.radiusKm), m, level);
  const win = windowFor(poly, m, level);
  const pointCountryP = countryAt(m, src, params.lat, params.lon, signal);

  const empty: QueryResult = {
    params, level, cellsInCircle: 0, landKm2: 0, coveredLandKm2: 0, coveredShare: 0,
    layers: Object.fromEntries(params.layers.map((l) => [l, { total: 0, byCountry: {} }])), ms: 0,
  };
  if (!win) return { ...empty, pointCountry: await pointCountryP, ms: performance.now() - t0 };

  const radiusCells = (params.radiusKm * 1000) / (m.grid.cell_m * level);
  const weights = coverageWeights(poly, win, subsamplingFor(radiusCells));
  const [country, land, landCovered, ...layerData] = await Promise.all([
    read(src, m, "country", level, win, signal),
    read(src, m, "land", level, win, signal),
    read(src, m, "land_covered", level, win, signal),
    ...params.layers.map((l) => read(src, m, l, level, win, signal)),
  ]);
  signal?.throwIfAborted();

  // land inside the circle, and the part of it in covered countries (sea does not count)
  const cellKm2 = (m.grid.cell_m * level / 1000) ** 2;
  let landKm2 = 0, coveredLandKm2 = 0;
  for (let i = 0; i < weights.length; i++) {
    const w = weights[i];
    if (w === 0) continue;
    landKm2 += land[i] * w * cellKm2;
    coveredLandKm2 += landCovered[i] * w * cellKm2;
  }

  const idToCode = new Map(m.countries.map((c) => [c.id, c.code]));
  const layers: Record<string, LayerSum> = {};
  params.layers.forEach((l, k) => {
    const { total, byId } = weightedSumByCountry(layerData[k], weights, country, m.nodata);
    const byCountry: Record<string, number> = {};
    for (const [id, v] of byId) {
      const code = idToCode.get(id) ?? (id === m.country_codes.sea ? "sea" : "other");
      byCountry[code] = (byCountry[code] ?? 0) + v;
    }
    layers[l] = { total, byCountry };
  });

  return {
    params, level,
    cellsInCircle: weightStats(weights).touched,
    landKm2, coveredLandKm2,
    coveredShare: landKm2 > 0 ? coveredLandKm2 / landKm2 : 1,
    pointCountry: await pointCountryP,
    layers,
    ms: performance.now() - t0,
  };
}

/** Layer ids a full result needs, visible group first (they are read in this order of priority). */
export function layersFor(m: Manifest, first: "population" | "gdp"): string[] {
  const y = m.years;
  const pop = [y.population.latest, ...y.population.compare].map((v) => `pop_${v}`);
  const gdp = [`gdp_nom_eur_${y.gdp.latest}`,
    ...[y.gdp.latest, ...y.gdp.compare].map((v) => `gdp_real_${v}`)];
  return first === "population" ? [...pop, ...gdp] : [...gdp, ...pop];
}
