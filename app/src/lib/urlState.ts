/** Shareable URL state in the hash: #lat=50.85&lon=4.35&r=50&layer=pop&m=nom&cur=EUR */

export type LayerKey = "population" | "gdp";
export type Measure = "nominal" | "pps";

export interface AppState {
  lat?: number;
  lon?: number;
  radiusKm: number;
  layer: LayerKey;
  measure: Measure;
  currency: string;
}

export const DEFAULT_STATE: AppState = { radiusKm: 50, layer: "population", measure: "nominal", currency: "EUR" };
export const RADIUS_MIN = 1;
export const RADIUS_MAX = 500;

export function clampRadius(r: number): number {
  if (!Number.isFinite(r)) return DEFAULT_STATE.radiusKm;
  return Math.min(RADIUS_MAX, Math.max(RADIUS_MIN, Math.round(r * 10) / 10));
}

export function parseHash(hash: string): AppState {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const num = (k: string) => (p.has(k) ? Number(p.get(k)) : NaN);
  const lat = num("lat"), lon = num("lon");
  const ok = Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  const cur = (p.get("cur") ?? "EUR").toUpperCase();
  return {
    lat: ok ? lat : undefined,
    lon: ok ? lon : undefined,
    radiusKm: p.has("r") ? clampRadius(num("r")) : DEFAULT_STATE.radiusKm,
    layer: p.get("layer") === "gdp" ? "gdp" : "population",
    measure: p.get("m") === "pps" ? "pps" : "nominal",
    currency: /^[A-Z]{3}$/.test(cur) ? cur : "EUR",
  };
}

export function toHash(s: AppState): string {
  const p = new URLSearchParams();
  if (s.lat !== undefined && s.lon !== undefined) {
    p.set("lat", s.lat.toFixed(5));
    p.set("lon", s.lon.toFixed(5));
  }
  p.set("r", String(s.radiusKm));
  p.set("layer", s.layer === "gdp" ? "gdp" : "pop");
  p.set("m", s.measure === "pps" ? "pps" : "nom");
  p.set("cur", s.currency);
  return "#" + p.toString();
}
