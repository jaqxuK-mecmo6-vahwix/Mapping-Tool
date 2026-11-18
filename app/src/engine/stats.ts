/** Growth rates, currency conversion and the summaries shown in the results panel. */
import type { FxTable, Manifest, QueryResult } from "./types";

/** Compound annual growth rate: (end/start)^(1/n) − 1. NaN if undefined. */
export function cagr(end: number, start: number, years: number): number {
  if (!(start > 0) || !(end >= 0) || years <= 0) return NaN;
  return Math.pow(end / start, 1 / years) - 1;
}

/** Absolute change per year: (end − start)/n. */
export function absPerYear(end: number, start: number, years: number): number {
  return years > 0 ? (end - start) / years : NaN;
}

export interface Growth {
  fromYear: number;
  toYear: number;
  years: number;
  absPerYear: number;   // same unit as the level (persons, or million EUR)
  pctPerYear: number;   // CAGR as a fraction (0.012 = 1.2 % p.a.)
}

function growth(end: number, start: number, toYear: number, fromYear: number): Growth {
  const n = toYear - fromYear;
  return { fromYear, toYear, years: n, absPerYear: absPerYear(end, start, n), pctPerYear: cagr(end, start, n) };
}

export interface PopulationSummary {
  year: number;
  total: number;
  growth: Growth[];
  byCountry: Record<string, number>;
}

export function populationSummary(m: Manifest, r: QueryResult): PopulationSummary {
  const y = m.years.population;
  const latest = r.layers[`pop_${y.latest}`];
  return {
    year: y.latest,
    total: latest.total,
    growth: y.compare.map((c) => growth(latest.total, r.layers[`pop_${c}`].total, y.latest, c)),
    byCountry: latest.byCountry,
  };
}

export type GdpMeasure = "nominal" | "pps";

export interface GdpSummary {
  year: number;
  measure: GdpMeasure;
  currency: string;           // "EUR", a national currency, or "PPS"
  totalMillions: number;      // in `currency`
  byCountryMillions: Record<string, number>;
  /** real growth (constant prices, fixed exchange rates); independent of measure and currency */
  realGrowth: Growth[];
  lowConfidence: boolean;
}

/** Units of `currency` per EUR in `year` (1 for EUR). Throws if the rate is missing. */
export function eurRate(fx: FxTable, currency: string, year: number): number {
  if (currency === "EUR") return 1;
  const r = fx.rates[currency]?.[String(year)];
  if (!(r > 0)) throw new Error(`no ${currency} rate for ${year}`);
  return r;
}

/** Convert million EUR to million `currency` at the reference year's annual average rate. */
export function convertEur(millionsEur: number, fx: FxTable, currency: string, year: number): number {
  return millionsEur * eurRate(fx, currency, year);
}

/** Currencies the toggle offers for a point: EUR, plus the national currency in non-euro countries. */
export function currencyOptions(fx: FxTable, pointCountry: string | undefined): string[] {
  if (!pointCountry) return ["EUR"];
  const cur = fx.country_currency[pointCountry];
  return cur && cur !== "EUR" ? ["EUR", cur] : ["EUR"];
}

export function gdpSummary(m: Manifest, fx: FxTable, r: QueryResult, measure: GdpMeasure,
                           currency: string): GdpSummary {
  const g = m.years.gdp;
  const real = (y: number) => r.layers[`gdp_real_${y}`].total;
  const realGrowth = g.compare.map((c) => growth(real(g.latest), real(c), g.latest, c));
  const lowConfidence = r.params.radiusKm < m.low_confidence_gdp_radius_km;

  const l = r.layers[`gdp_nom_eur_${g.latest}`];
  if (measure === "pps") {
    // Eurostat converts regional GDP to PPS with one national factor, so the circle's PPS is the sum of
    // each country's EUR part times that country's factor (no separate PPS raster is needed)
    const f = m.pps_per_eur.factors;
    const byCountryMillions = Object.fromEntries(Object.entries(l.byCountry).map(([k, v]) => [k, v * (f[k] ?? 0)]));
    const totalMillions = Object.values(byCountryMillions).reduce((a, b) => a + b, 0);
    return { year: g.latest, measure, currency: "PPS", totalMillions, byCountryMillions, realGrowth, lowConfidence };
  }
  const rate = eurRate(fx, currency, fx.reference_year);
  return {
    year: g.latest, measure, currency,
    totalMillions: l.total * rate,
    byCountryMillions: Object.fromEntries(Object.entries(l.byCountry).map(([k, v]) => [k, v * rate])),
    realGrowth, lowConfidence,
  };
}
