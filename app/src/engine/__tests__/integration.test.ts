/**
 * Engine against the real pipeline output in ../data/build (full build: EU-27, UK, CH, NO).
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
const full = has && manifest.countries.every((c) => c.built);
const src = () => new CogSource(pathToFileURL(BUILD).toString(), (u) => fromFile(fileURLToPath(u)));

const BRUSSELS = { lat: 50.8467, lon: 4.3525 };
const MALTA = { lat: 35.92, lon: 14.42 };

describe.skipIf(!full)("query engine on the full build", () => {
  it("an isolated country (Malta) gives the same total at every pyramid level", async () => {
    const layers = layersFor(manifest, "population");
    const ref = await runQuery({ ...manifest, levels_km: [1] }, src(), { ...MALTA, radiusKm: 60, layers });
    expect(ref.layers.pop_2025.total).toBeGreaterThan(4.5e5);
    expect(Object.keys(ref.layers.pop_2025.byCountry).filter((c) => ref.layers.pop_2025.byCountry[c] > 0)).toEqual(["MT"]);
    for (const lv of manifest.levels_km.filter((l) => l > 1 && l <= 8)) {
      const r = await runQuery({ ...manifest, levels_km: [lv] }, src(), { ...MALTA, radiusKm: 60, layers });
      expect(r.level).toBe(lv);
      // each level is stored with 12 mantissa bits (pipeline raster.mantissa_bits): <= 2^-13 per cell
      for (const l of layers) expect(Math.abs(r.layers[l].total - ref.layers[l].total) / ref.layers[l].total).toBeLessThan(2 ** -13);
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

  it("partial coverage at the Croatian-Serbian border (Serbia is not covered)", async () => {
    const r = await runQuery(manifest, src(), { lat: 45.35, lon: 19.0, radiusKm: 30, layers: ["pop_2025"] });
    expect(r.coveredShare).toBeGreaterThan(0.2);
    expect(r.coveredShare).toBeLessThan(0.9);
    const belgrade = await runQuery(manifest, src(), { lat: 44.82, lon: 20.46, radiusKm: 5, layers: ["pop_2025"] });
    expect(belgrade.pointCountry).toBeUndefined();
  });

  it("cross-border circle (Basel 25 km) splits by country", async () => {
    const r = await runQuery(manifest, src(), { lat: 47.5596, lon: 7.5886, radiusKm: 25, layers: ["pop_2025"] });
    const bc = r.layers.pop_2025.byCountry;
    for (const c of ["CH", "DE", "FR"]) expect(bc[c]).toBeGreaterThan(5e4);
    expect(r.pointCountry).toBe("CH");
  });

  it("UK and non-euro currencies: London in GBP, Zurich in CHF, Oslo in NOK", async () => {
    for (const [lat, lon, cc, cur] of [[51.5074, -0.1278, "UK", "GBP"], [47.3769, 8.5417, "CH", "CHF"],
                                        [59.9139, 10.7522, "NO", "NOK"]] as const) {
      const r = await runQuery(manifest, src(), { lat, lon, radiusKm: 25, layers: layersFor(manifest, "gdp") });
      expect(r.pointCountry).toBe(cc);
      const eur = gdpSummary(manifest, fx, r, "nominal", "EUR");
      const nat = gdpSummary(manifest, fx, r, "nominal", cur);
      expect(eur.totalMillions).toBeGreaterThan(5e4);
      expect(nat.totalMillions / eur.totalMillions).toBeCloseTo(fx.rates[cur][String(fx.reference_year)], 9);
      expect(nat.realGrowth).toEqual(eur.realGrowth);
      const pps = gdpSummary(manifest, fx, r, "pps", "EUR");
      expect(pps.totalMillions).toBeGreaterThan(0);
    }
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

  // Independent reference: pipeline `./run.sh xcheck` (pyproj geodesic distance on a 10x10 sample of
  // every 1 km cell), pop_2025 of the full build; see VALIDATION.md.
  const REF: [string, number, number, number, number][] = (has && existsSync(BUILD + "xcheck.json"))
    ? JSON.parse(readFileSync(BUILD + "xcheck.json", "utf8")).rows
        .map((r: Record<string, number | string>) => [r.place, r.lat, r.lon, r.radius_km, r.pop_2025])
    : [];
  it.skipIf(!REF.length).each(REF)("%s %d km matches an independent geodesic computation within 0.1 %%", async (_n, lat, lon, r, ref) => {
    const q = await runQuery(manifest, src(), { lat, lon, radiusKm: r, layers: ["pop_2025"] });
    expect(Math.abs(q.layers.pop_2025.total - ref) / ref).toBeLessThan(0.001);
  });

  it("a circle over the open Atlantic returns zeros, not an error", async () => {
    const r = await runQuery(manifest, src(), { lat: 40.0, lon: -20.0, radiusKm: 50, layers: ["pop_2025"] });
    expect(r.layers.pop_2025.total).toBe(0);
  });

  it("aborted queries reject with AbortError", async () => {
    const ctl = new AbortController();
    ctl.abort();
    await expect(runQuery(manifest, src(), { ...BRUSSELS, radiusKm: 50, layers: ["pop_2025"] }, ctl.signal))
      .rejects.toThrow();
  });
});
