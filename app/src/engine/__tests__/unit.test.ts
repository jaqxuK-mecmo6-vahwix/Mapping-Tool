import { describe, expect, it } from "vitest";
import { MAX_CELLS, chooseLevel, geodesicCircle, geodesicDistanceKm, project, unproject } from "../geometry";
import { coverageWeights, rowInterval, subsamplingFor, weightedSumByCountry } from "../mask";
import { absPerYear, cagr, convertEur, currencyOptions, eurRate, gdpSummary, populationSummary } from "../stats";
import type { FxTable, Manifest, QueryResult } from "../types";

// ---------------------------------------------------------------------------------------------- CAGR
describe("growth", () => {
  it("CAGR is compound, not linear", () => {
    expect(cagr(121, 100, 2)).toBeCloseTo(0.1, 12);
    expect(cagr(100, 100, 10)).toBe(0);
    expect(cagr(50, 100, 1)).toBeCloseTo(-0.5, 12);
  });
  it("CAGR is NaN when undefined", () => {
    expect(cagr(10, 0, 3)).toBeNaN();
    expect(cagr(10, 5, 0)).toBeNaN();
  });
  it("absolute change per year", () => {
    expect(absPerYear(1_030_000, 1_000_000, 3)).toBe(10_000);
  });
});

// ------------------------------------------------------------------------------------------ geometry
describe("geometry", () => {
  it("EPSG:3035 false origin maps to 10E 52N", () => {
    const [x, y] = project(10, 52);
    expect(x).toBeCloseTo(4321000, 3);
    expect(y).toBeCloseTo(3210000, 3);
    const [lon, lat] = unproject(x, y);
    expect(lon).toBeCloseTo(10, 9);
    expect(lat).toBeCloseTo(52, 9);
  });
  it("geodesic circle vertices are at the radius", () => {
    for (const r of [1, 50, 500]) {
      for (const [lon, lat] of geodesicCircle(60, 10, r, 36)) {
        expect(geodesicDistanceKm(60, 10, lat, lon)).toBeCloseTo(r, 6);
      }
    }
  });
  it("level choice keeps the circle within the cell budget", () => {
    const levels = [1, 2, 4, 8, 16, 32];
    expect(chooseLevel(1, levels)).toBe(1);
    expect(chooseLevel(50, levels)).toBe(1);
    expect(chooseLevel(178, levels)).toBe(1);   // π·178² ≈ 99.5k
    expect(chooseLevel(179, levels)).toBe(2);
    expect(chooseLevel(500, levels)).toBe(4);   // ≈ 49k cells at 4 km
    expect(chooseLevel(282, levels, 250_000)).toBe(1);
    expect(chooseLevel(283, levels, 250_000)).toBe(2);
    for (const r of [1, 10, 100, 250, 400, 500]) {
      const lv = chooseLevel(r, levels);
      expect((Math.PI * r * r) / (lv * lv)).toBeLessThanOrEqual(MAX_CELLS);
      if (lv > 1) expect((Math.PI * r * r) / ((lv / 2) ** 2)).toBeGreaterThan(MAX_CELLS); // finest possible
    }
  });
});

// ------------------------------------------------------------------------------------------- masking
function circlePoly(cx: number, cy: number, r: number, n = 720): [number, number][] {
  return Array.from({ length: n }, (_, i) => [cx + r * Math.cos((2 * Math.PI * i) / n), cy + r * Math.sin((2 * Math.PI * i) / n)]);
}

describe("circle masking", () => {
  it("weights sum to the circle area (edge supersampling)", () => {
    for (const r of [0.6, 1.5, 3, 10, 57.3, 250]) {
      const pad = Math.ceil(r) + 2;
      const win = { level: 1, row0: 0, col0: 0, width: 2 * pad, height: 2 * pad };
      const w = coverageWeights(circlePoly(pad + 0.37, pad + 0.81, r), win);
      const sum = w.reduce((a, b) => a + b, 0);
      const area = Math.PI * r * r;
      // 4x4 sampling error is unbiased noise that shrinks with radius (measured: 0.2 % at 10 cells,
      // < 0.05 % from 20 cells); the engine switches to 16x16 below 20 cells
      expect(Math.abs(sum - area) / area).toBeLessThan(r < 2 ? 0.2 : r < 10 ? 0.015 : r < 20 ? 0.004 : 0.001);
      const fine = coverageWeights(circlePoly(pad + 0.37, pad + 0.81, r), win, subsamplingFor(r)).reduce((x, y) => x + y, 0);
      expect(Math.abs(fine - area) / area).toBeLessThan(r < 1 ? 0.03 : r < 20 ? 0.01 : 0.001);
      expect(w.reduce((x, y) => Math.max(x, y), 0)).toBeLessThanOrEqual(1 + 1e-6);
      expect(w.reduce((x, y) => Math.min(x, y), 1)).toBeGreaterThanOrEqual(0);
    }
  });
  it("interior cells weigh 1, far cells 0, edge cells are fractional", () => {
    const win = { level: 1, row0: 0, col0: 0, width: 40, height: 40 };
    const w = coverageWeights(circlePoly(20, 20, 10), win);
    expect(w[20 * 40 + 20]).toBe(1);
    expect(w[0]).toBe(0);
    let fractional = 0;
    for (let r = 0; r < 40; r++) for (let c = 0; c < 40; c++) {
      const d = Math.hypot(c + 0.5 - 20, r + 0.5 - 20);
      const v = w[r * 40 + c];
      if (d < 10 - 0.75) expect(v).toBe(1);        // whole cell inside
      if (d > 10 + 0.75) expect(v).toBe(0);        // whole cell outside
      if (v > 0 && v < 1) fractional++;
    }
    expect(fractional).toBeGreaterThan(40);       // ≈ circumference 2π·10 ≈ 63 edge cells
  });
  it("an axis-aligned half cell gets weight 0.5", () => {
    const poly: [number, number][] = [[0, 0], [2.5, 0], [2.5, 1], [0, 1]];
    const w = coverageWeights(poly, { level: 1, row0: 0, col0: 0, width: 4, height: 1 });
    expect(Array.from(w)).toEqual([1, 1, 0.5, 0]);
  });
  it("windows offset into the grid use absolute pixel coordinates", () => {
    const poly = circlePoly(105.5, 205.5, 3);
    const a = coverageWeights(poly, { level: 1, row0: 200, col0: 100, width: 12, height: 12 });
    const b = coverageWeights(circlePoly(5.5, 5.5, 3), { level: 1, row0: 0, col0: 0, width: 12, height: 12 });
    expect(Array.from(a)).toEqual(Array.from(b));
  });
  it("rowInterval of a square", () => {
    expect(rowInterval([[1, 1], [3, 1], [3, 3], [1, 3]], 2)).toEqual([1, 3]);
    expect(rowInterval([[1, 1], [3, 1], [3, 3], [1, 3]], 5)).toBeNull();
  });
  it("weighted sums split by country and skip nodata", () => {
    const { total, byId } = weightedSumByCountry([10, -1, 5, 3], new Float32Array([1, 1, 0.5, 0]), [1, 1, 2, 2], -1);
    expect(total).toBe(12.5);
    expect(byId.get(1)).toBe(10);
    expect(byId.get(2)).toBe(2.5);
  });
});

// ------------------------------------------------------------------------- sum-conserving pyramids
/** 2×2 sum, same rule as the pipeline (nodata children count 0). */
function sum2x2(a: Float32Array, w: number, h: number, nd: number): Float32Array {
  const o = new Float32Array((w / 2) * (h / 2));
  for (let r = 0; r < h / 2; r++) for (let c = 0; c < w / 2; c++) {
    let s = 0, all = true;
    for (const [dr, dc] of [[0, 0], [0, 1], [1, 0], [1, 1]]) {
      const v = a[(2 * r + dr) * w + 2 * c + dc];
      if (v !== nd) { s += v; all = false; }
    }
    o[r * (w / 2) + c] = all ? nd : s;
  }
  return o;
}

describe("sum-conserving pyramids", () => {
  it("a circle that contains all data gives the same total at every level", () => {
    const W = 128, nd = -1;
    let a: Float32Array = new Float32Array(W * W);
    let seed = 7;
    for (let i = 0; i < a.length; i++) {
      seed = (seed * 16807) % 2147483647;
      const r = Math.floor(i / W), c = i % W;
      const inDisk = (r - 64) ** 2 + (c - 64) ** 2 < 30 ** 2;
      a[i] = inDisk ? (seed % 1000) / 10 : (seed % 5 === 0 ? nd : 0);
    }
    const ref = a.reduce((s, v) => s + (v === nd ? 0 : v), 0);
    let size = W;
    for (let level = 1; level <= 16; level *= 2) {
      const poly = circlePoly(64 / level, 64 / level, 60 / level); // contains every coarse cell with data
      const w = coverageWeights(poly, { level, row0: 0, col0: 0, width: size, height: size });
      const { total } = weightedSumByCountry(a, w, new Uint8Array(size * size).fill(1), nd);
      expect(Math.abs(total - ref) / ref).toBeLessThan(1e-6);
      a = sum2x2(a, size, size, nd);
      size /= 2;
    }
  });
});

// ---------------------------------------------------------------------------------------- currency
const fx: FxTable = {
  reference_year: 2023, real_base_year: 2020,
  euro_area: ["BE", "DE", "BG"],
  country_currency: { BE: "EUR", DE: "EUR", BG: "EUR", PL: "PLN", UK: "GBP" },
  rates: { PLN: { "2023": 4.542 }, GBP: { "2023": 0.86979 } },
};

describe("currency", () => {
  it("converts at the reference-year rate", () => {
    expect(convertEur(1000, fx, "PLN", 2023)).toBeCloseTo(4542, 9);
    expect(convertEur(1000, fx, "EUR", 2023)).toBe(1000);
    expect(() => eurRate(fx, "PLN", 2019)).toThrow();
  });
  it("offers the national currency only outside the euro area", () => {
    expect(currencyOptions(fx, "PL")).toEqual(["EUR", "PLN"]);
    expect(currencyOptions(fx, "BG")).toEqual(["EUR"]);
    expect(currencyOptions(fx, undefined)).toEqual(["EUR"]);
  });

  const manifest = {
    years: { population: { latest: 2025, compare: [2022] }, gdp: { latest: 2023, compare: [2020], real_base_year: 2020 } },
    low_confidence_gdp_radius_km: 25,
  } as unknown as Manifest;
  const result = {
    params: { lat: 0, lon: 0, radiusKm: 20, layers: [] },
    layers: {
      gdp_nom_eur_2023: { total: 100, byCountry: { PL: 60, DE: 40 } },
      gdp_pps_2023: { total: 150, byCountry: { PL: 110, DE: 40 } },
      gdp_real_2023: { total: 110, byCountry: {} },
      gdp_real_2020: { total: 100, byCountry: {} },
      pop_2025: { total: 1030, byCountry: {} },
      pop_2022: { total: 1000, byCountry: {} },
    },
  } as unknown as QueryResult;

  it("converts the whole circle incl. other countries; real growth ignores currency", () => {
    const eur = gdpSummary(manifest, fx, result, "nominal", "EUR");
    const pln = gdpSummary(manifest, fx, result, "nominal", "PLN");
    expect(pln.totalMillions).toBeCloseTo(454.2, 9);
    expect(pln.byCountryMillions.DE).toBeCloseTo(40 * 4.542, 9);
    expect(pln.realGrowth).toEqual(eur.realGrowth);
    expect(eur.realGrowth[0].pctPerYear).toBeCloseTo(Math.cbrt(1.1) - 1, 12);
    expect(eur.lowConfidence).toBe(true);
    expect(gdpSummary(manifest, fx, result, "pps", "EUR").currency).toBe("PPS");
  });
  it("population summary", () => {
    const p = populationSummary(manifest, result);
    expect(p.growth[0].absPerYear).toBe(10);
    expect(p.growth[0].pctPerYear).toBeCloseTo(Math.cbrt(1.03) - 1, 12);
  });
});
