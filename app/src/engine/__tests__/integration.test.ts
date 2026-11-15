/**
 * Engine against the real pipeline output in ../data/build (Belgium build of step 1).
 * Skipped when the build is absent. Reads COGs from disk with the same geotiff.js code path.
 */
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { fromFile } from "geotiff";
import { describe, expect, it } from "vitest";
import { layersFor, runQuery } from "../query";
import { CogSource } from "../source";
import { gdpSummary, populationSummary } from "../stats";
import type { FxTable, Manifest } from "../types";

const BUILD = fileURLToPath(new URL("../../../../data/build/", import.meta.url));
const has = existsSync(BUILD + "manifest.json");
const manifest: Manifest = has ? JSON.parse(readFileSync(BUILD + "manifest.json", "utf8")) : ({} as Manifest);
const fx: FxTable = has ? JSON.parse(readFileSync(BUILD + "fx.json", "utf8")) : ({} as FxTable);
const src = () => new CogSource(pathToFileURL(BUILD).toString(), (u) => fromFile(fileURLToPath(u)));

const BRUSSELS = { lat: 50.8467, lon: 4.3525 };
const BE_CENTRE = { lat: 50.64, lon: 4.67 };

describe.skipIf(!has)("query engine on the Belgium build", () => {
  it("a circle containing all of Belgium returns the national totals at every pyramid level", async () => {
    const layers = layersFor(manifest, "population");
    for (const lv of manifest.levels_km.filter((l) => l <= 8)) {
      const m = { ...manifest, levels_km: [lv] };   // force the level
      const r = await runQuery(m, src(), { ...BE_CENTRE, radiusKm: 220, layers });
      expect(r.level).toBe(lv);
      for (const l of layers) {
        const total = manifest.layers[l].total!;
        expect(Math.abs(r.layers[l].total - total) / total).toBeLessThan(1e-5);
        expect(r.layers[l].byCountry.BE).toBeCloseTo(r.layers[l].total, 3);
      }
    }
  });

  it("Brussels 25 km: plausible totals, consistent across levels 1 and 2", async () => {
    const layers = ["pop_2025", `gdp_nom_eur_${manifest.years.gdp.latest}`];
    const r1 = await runQuery({ ...manifest, levels_km: [1] }, src(), { ...BRUSSELS, radiusKm: 25, layers });
    const r2 = await runQuery({ ...manifest, levels_km: [2] }, src(), { ...BRUSSELS, radiusKm: 25, layers });
    const p1 = r1.layers.pop_2025.total, p2 = r2.layers.pop_2025.total;
    expect(p1).toBeGreaterThan(2.0e6);
    expect(p1).toBeLessThan(3.2e6);
    expect(Math.abs(p1 - p2) / p1).toBeLessThan(0.02); // coarser level: edge cells assumed uniform
    expect(r1.pointCountry).toBe("BE");
    expect(r1.coveredShare).toBe(1);
  });

  it("partial coverage near the French border (France not in this build)", async () => {
    const r = await runQuery(manifest, src(), { lat: 50.73, lon: 3.23, radiusKm: 30, layers: ["pop_2025"] });
    expect(r.coveredShare).toBeGreaterThan(0.2);
    expect(r.coveredShare).toBeLessThan(0.9);
    const lille = await runQuery(manifest, src(), { lat: 50.63, lon: 3.06, radiusKm: 5, layers: ["pop_2025"] });
    expect(lille.pointCountry).toBeUndefined();
  });

  it("summaries: growth, real growth and currency", async () => {
    const r = await runQuery(manifest, src(), { ...BRUSSELS, radiusKm: 50, layers: layersFor(manifest, "gdp") });
    const p = populationSummary(manifest, r);
    expect(p.growth.map((g) => g.years)).toEqual([3, 5, 10]);
    for (const g of p.growth) expect(Math.abs(g.pctPerYear)).toBeLessThan(0.03);
    const eur = gdpSummary(manifest, fx, r, "nominal", "EUR");
    const pln = gdpSummary(manifest, fx, r, "nominal", "PLN");
    expect(pln.totalMillions / eur.totalMillions).toBeCloseTo(fx.rates.PLN[String(fx.reference_year)], 9);
    expect(pln.realGrowth).toEqual(eur.realGrowth);
    for (const g of eur.realGrowth) expect(Math.abs(g.pctPerYear)).toBeLessThan(0.06);
  });

  // Independent reference: pyproj geodesic distance on a 10x10 sample of every 1 km cell
  // (scratch script xcheck.py, 2026-11-15, pop_2025 of the Belgium build).
  const REF: [string, number, number, number, number][] = [
    ["Brussels", 50.8467, 4.3525, 10, 1580365], ["Brussels", 50.8467, 4.3525, 25, 2605729],
    ["Brussels", 50.8467, 4.3525, 50, 5997768], ["Antwerp", 51.2194, 4.4025, 10, 774081],
    ["Antwerp", 51.2194, 4.4025, 25, 1632981], ["Liege", 50.6326, 5.5797, 25, 949123],
    ["Liege", 50.6326, 5.5797, 50, 1951985],
  ];
  it.each(REF)("%s %d km matches an independent geodesic computation within 0.1 %%", async (_n, lat, lon, r, ref) => {
    const q = await runQuery(manifest, src(), { lat, lon, radiusKm: r, layers: ["pop_2025"] });
    expect(Math.abs(q.layers.pop_2025.total - ref) / ref).toBeLessThan(0.001);
  });

  it("a circle fully outside the grid returns zeros, not an error", async () => {
    const r = await runQuery(manifest, src(), { lat: 40.4, lon: -3.7, radiusKm: 50, layers: ["pop_2025"] });
    expect(r.layers.pop_2025.total).toBe(0);
  });

  it("aborted queries reject with AbortError", async () => {
    const ctl = new AbortController();
    ctl.abort();
    await expect(runQuery(manifest, src(), { ...BRUSSELS, radiusKm: 50, layers: ["pop_2025"] }, ctl.signal))
      .rejects.toThrow();
  });
});
