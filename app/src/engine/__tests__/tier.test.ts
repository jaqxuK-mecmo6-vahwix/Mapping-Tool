import { describe, expect, it } from "vitest";
import { locationTier } from "../tier";
import type { Manifest, QueryResult } from "../types";

const m = {
  years: {
    population: { latest: 2025, compare: [2022, 2020, 2015] },
    gdp: { latest: 2023, compare: [2020, 2018, 2013] },
  },
} as unknown as Manifest;

/** gdp in bn EUR (nominal 2023), population 2025; growth as yearly fractions over 10 years */
function circle(gdpBn: number, pop: number, popG = 0, gdpG = 0, radiusKm = 50, byCountry: Record<string, number> = {}) {
  const l = (total: number, by: Record<string, number> = {}) => ({ total, byCountry: by });
  return {
    params: { radiusKm },
    layers: {
      pop_2025: l(pop), pop_2015: l(pop / (1 + popG) ** 10),
      gdp_nom_eur_2023: l(gdpBn * 1000, byCountry),
      gdp_real_2023: l(gdpBn * 1000), gdp_real_2013: l((gdpBn * 1000) / (1 + gdpG) ** 10),
    },
  } as unknown as QueryResult;
}

describe("location tier", () => {
  it("needs both thresholds; the lower one decides", () => {
    expect(locationTier(m, circle(817, 12.26e6))!.def.tier).toBe("A");      // Paris
    expect(locationTier(m, circle(193, 5.6e6))!.def.tier).toBe("B");        // Barcelona: A population, B GDP
    expect(locationTier(m, circle(123, 1.69e6))!.def.tier).toBe("C");       // Oslo: B GDP, C population
    expect(locationTier(m, circle(46, 0.9e6))!.def.tier).toBe("D");         // Aarhus
    expect(locationTier(m, circle(300, 5e6))!.def.tier).toBe("A");          // thresholds are inclusive
  });
  it("growth sign", () => {
    expect(locationTier(m, circle(301, 7.36e6, 0.011, 0.026))!.label).toBe("A+");  // Madrid
    expect(locationTier(m, circle(301, 7.36e6, 0.011, 0.02))!.label).toBe("A");    // GDP too slow
    expect(locationTier(m, circle(108, 3.8e6, -0.003, 0.018))!.label).toBe("B−");  // Athens
    expect(locationTier(m, circle(200, 4.34e6, 0, 0.009))!.label).toBe("B");       // Rome: flat is not "−"
    expect(locationTier(m, circle(98, 2.76e6, -0.0001, 0.079))!.label).toBe("C");  // Bucharest: −0.01 %/yr is flat
  });
  it("borderline flags the next tier up only when both values are close", () => {
    expect(locationTier(m, circle(98, 2.76e6))!.nearUp?.tier).toBe("B");    // Bucharest
    expect(locationTier(m, circle(123, 1.69e6))!.nearUp).toBeUndefined();   // Oslo: population 15% short
    expect(locationTier(m, circle(817, 12e6))!.nearUp).toBeUndefined();
  });
  it("25 km city tiers", () => {
    const at25 = (gdp: number, pop: number) => locationTier(m, circle(gdp, pop, 0, 0, 25))!;
    expect(at25(221, 4.31e6).def.tier).toBe("A");        // Berlin: B at 50 km, A at 25 km
    expect(at25(209, 2.49e6).def.tier).toBe("B");        // Amsterdam: A at 50 km, B at 25 km
    expect(at25(101, 1.23e6).def.tier).toBe("C");        // Oslo
    expect(at25(26, 0.5e6).def.tier).toBe("C");          // Aarhus, on the line
    expect(at25(24, 0.4e6).def.tier).toBe("D");          // Bergen
    expect(at25(221, 4.31e6).set.title).toBe("City tier");
  });
  it("only for 25 km and 50 km circles", () => {
    expect(locationTier(m, circle(817, 12e6, 0, 0, 49.5))).toBeNull();
    expect(locationTier(m, circle(817, 12e6, 0, 0, 30))).toBeNull();
  });
  it("flags Irish GDP", () => {
    expect(locationTier(m, circle(273, 2.13e6, 0, 0, 50, { IE: 273_000 }))!.irelandDistorted).toBe(true);
    expect(locationTier(m, circle(979, 14e6, 0, 0, 50, { UK: 979_000 }))!.irelandDistorted).toBe(false);
  });
});
