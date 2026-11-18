/** Location tier for a 50 km circle: a screening grade from GDP and population, plus a growth sign.
 *  Thresholds were set from the 50 km totals of 51 European cities (2025 population, 2023 nominal GDP). */
import { cagr } from "./stats";
import type { Manifest, QueryResult } from "./types";

export const TIER_RADIUS_KM = 50;

export interface TierDef { tier: "A" | "B" | "C" | "D"; name: string; minGdpBn: number; minPop: number }

export const TIERS: TierDef[] = [
  { tier: "A", name: "Gateway metro", minGdpBn: 300, minPop: 5_000_000 },
  { tier: "B", name: "Major metro", minGdpBn: 100, minPop: 2_000_000 },
  { tier: "C", name: "Regional centre", minGdpBn: 30, minPop: 1_000_000 },
  { tier: "D", name: "Local market", minGdpBn: 0, minPop: 0 },
];

/** "+": population ≥ 0.8 %/yr and real GDP ≥ 2.5 %/yr; "−": population falling faster than 0.1 %/yr
 *  (smaller changes count as flat). */
export const GROWTH_PLUS = { popPerYear: 0.008, realGdpPerYear: 0.025 };
export const SHRINKING_POP_PER_YEAR = -0.001;
/** Within this fraction below the next tier's threshold counts as borderline. */
export const BORDERLINE = 0.05;
/** Irish GDP is inflated by multinational profits; flag circles where Ireland has this share of GDP. */
export const IE_GDP_SHARE = 0.25;

export interface LocationTier {
  def: TierDef;
  sign: "+" | "−" | "";
  label: string;                 // e.g. "B+"
  gdpBn: number;
  population: number;
  popGrowth: number;             // CAGR over `years`, fraction
  realGdpGrowth: number;         // CAGR over `gdpYears`, fraction
  years: number;
  gdpYears: number;
  /** next tier up, if the circle is within BORDERLINE of both its thresholds */
  nearUp?: TierDef;
  irelandDistorted: boolean;
}


export function locationTier(m: Manifest, r: QueryResult): LocationTier | null {
  if (r.params.radiusKm !== TIER_RADIUS_KM) return null;
  const p = m.years.population, g = m.years.gdp;
  const pop = r.layers[`pop_${p.latest}`], nom = r.layers[`gdp_nom_eur_${g.latest}`];
  // growth over the longest comparison period (10 years with the current configuration)
  const pFrom = Math.min(...p.compare), gFrom = Math.min(...g.compare);
  const pop0 = r.layers[`pop_${pFrom}`], real = r.layers[`gdp_real_${g.latest}`], real0 = r.layers[`gdp_real_${gFrom}`];
  if (!pop || !nom || !pop0 || !real || !real0) return null;

  const gdpBn = nom.total / 1000;            // layer unit: million EUR
  const population = pop.total;
  const i = TIERS.findIndex((t) => gdpBn >= t.minGdpBn && population >= t.minPop);
  const def = TIERS[i];
  const popGrowth = cagr(population, pop0.total, p.latest - pFrom);
  const realGdpGrowth = cagr(real.total, real0.total, g.latest - gFrom);
  const sign = popGrowth < SHRINKING_POP_PER_YEAR ? "−"
    : popGrowth >= GROWTH_PLUS.popPerYear && realGdpGrowth >= GROWTH_PLUS.realGdpPerYear ? "+" : "";
  const up = i > 0 ? TIERS[i - 1] : undefined;
  const nearUp = up && gdpBn >= up.minGdpBn * (1 - BORDERLINE) && population >= up.minPop * (1 - BORDERLINE)
    ? up : undefined;
  const irelandDistorted = nom.total > 0 && (nom.byCountry.IE ?? 0) / nom.total >= IE_GDP_SHARE;
  return {
    def, sign, label: def.tier + sign, gdpBn, population, popGrowth, realGdpGrowth,
    years: p.latest - pFrom, gdpYears: g.latest - gFrom, nearUp, irelandDistorted,
  };
}
