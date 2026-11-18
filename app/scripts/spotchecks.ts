// Engine results for the VALIDATION.md spot checks, compared with the pipeline's independent
// computation (data/build/xcheck.json from `pipeline/run.sh xcheck`). Run from app/:
//   node node_modules/vite-node/vite-node.mjs scripts/spotchecks.ts
// Writes data/build/engine_spotchecks.json and prints a Markdown table.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { fromFile } from "geotiff";
import { layersFor, runQuery } from "../src/engine/query";
import { CogSource } from "../src/engine/source";
import { gdpSummary, populationSummary } from "../src/engine/stats";
import type { FxTable, Manifest } from "../src/engine/types";

const BUILD = fileURLToPath(new URL("../../data/build/", import.meta.url));
const m: Manifest = JSON.parse(readFileSync(BUILD + "manifest.json", "utf8"));
const fx: FxTable = JSON.parse(readFileSync(BUILD + "fx.json", "utf8"));
const xcheck = JSON.parse(readFileSync(BUILD + "xcheck.json", "utf8")).rows as Record<string, number | string>[];
const src = new CogSource(pathToFileURL(BUILD).toString(), (u) => fromFile(fileURLToPath(u)));
const P = m.years.population.latest, G = m.years.gdp.latest;

const rows = [];
for (const x of xcheck) {
  const lat = x.lat as number, lon = x.lon as number, r = x.radius_km as number;
  const q = await runQuery(m, src, { lat, lon, radiusKm: r, layers: [...layersFor(m, "population")] });
  const p = populationSummary(m, q);
  const eur = gdpSummary(m, fx, q, "nominal", "EUR");
  const pps = gdpSummary(m, fx, q, "pps", "EUR");
  const nat = q.pointCountry && fx.country_currency[q.pointCountry] !== "EUR"
    ? gdpSummary(m, fx, q, "nominal", fx.country_currency[q.pointCountry]) : undefined;
  const refPop = x[`pop_${P}`] as number, refGdp = x[`gdp_nom_eur_${G}`] as number;
  rows.push({
    place: x.place, radius_km: r, level_km: q.level, point_country: q.pointCountry,
    covered_share: q.coveredShare,
    population: p.total, population_xcheck: refPop, population_rel_diff: p.total / refPop - 1,
    population_growth: p.growth.map((g) => ({ years: g.years, abs_per_year: g.absPerYear, pct_pa: g.pctPerYear })),
    gdp_eur_m: eur.totalMillions, gdp_eur_xcheck: refGdp, gdp_rel_diff: eur.totalMillions / refGdp - 1,
    gdp_pps_m: pps.totalMillions,
    gdp_national: nat ? { currency: nat.currency, millions: nat.totalMillions } : undefined,
    real_growth: eur.realGrowth.map((g) => ({ years: g.years, pct_pa: g.pctPerYear })),
    by_country_population: q.layers[`pop_${P}`].byCountry,
    ms: q.ms,
  });
}
writeFileSync(BUILD + "engine_spotchecks.json", JSON.stringify({ generated: new Date().toISOString(), rows }, null, 2));

const f0 = (v: number) => Math.round(v).toLocaleString("en-GB");
const pct = (v: number) => `${(100 * v).toFixed(3)} %`;
console.log("| place | r km | population | xcheck | diff | GDP EUR m | xcheck | diff |");
console.log("|---|---:|---:|---:|---:|---:|---:|---:|");
for (const r of rows) {
  console.log(`| ${r.place} | ${r.radius_km} | ${f0(r.population)} | ${f0(r.population_xcheck)} | ${pct(r.population_rel_diff)} | ${f0(r.gdp_eur_m)} | ${f0(r.gdp_eur_xcheck)} | ${pct(r.gdp_rel_diff)} |`);
}
const worst = Math.max(...rows.flatMap((r) => [Math.abs(r.population_rel_diff), Math.abs(r.gdp_rel_diff)]));
console.log(`\nworst relative difference: ${pct(worst)}`);
