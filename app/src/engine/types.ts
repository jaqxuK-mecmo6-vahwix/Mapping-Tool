/** Shapes of the pipeline's manifest.json / fx.json and of query results. */

export interface LevelFile {
  url: string;
  /** 0-based band in the multi-band level file (all layers of a level share one COG) */
  band?: number;
  bytes: number;
  width: number;
  height: number;
}

export interface LayerMeta {
  kind: "population" | "gdp" | "country" | "land";
  year?: number;
  measure?: "nominal" | "pps" | "real";
  unit?: string;
  levels: Record<string, LevelFile>;
  total?: number;
}

export interface CountryMeta {
  id: number;
  code: string;
  name: string;
  currency: string;
  built: boolean;
}

export interface Manifest {
  name: string;
  schema: number;
  generated: string;
  grid: { crs: "EPSG:3035"; xmin: number; ymax: number; xmax: number; ymin: number; width: number; height: number; cell_m: number };
  levels_km: number[];
  nodata: number;
  years: {
    population: { latest: number; compare: number[] };
    gdp: { latest: number; compare: number[]; real_base_year: number };
  };
  countries: CountryMeta[];
  country_codes: { sea: number; not_covered: number };
  low_confidence_gdp_radius_km: number;
  /** PPS (EU27_2020) per EUR of GDP, per country: circle PPS = sum over countries of EUR x factor */
  pps_per_eur: { year: number; factors: Record<string, number>; source: string };
  layers: Record<string, LayerMeta>;
  fx: string;
  heat?: Partial<Record<"population" | "gdp", HeatMeta>>;
  coverage_mask?: { url: string; countries: string[] };
}

export interface HeatMeta {
  url: string;
  layer: string;
  unit: string;
  min: number;
  max: number;
  ramp: [number, number, number][];
  min_zoom: number;
  max_zoom: number;
}

export interface FxTable {
  reference_year: number;
  real_base_year: number;
  euro_area: string[];
  country_currency: Record<string, string>;
  /** units of currency per 1 EUR, by currency then year */
  rates: Record<string, Record<string, number>>;
}

/** Pixel window at one pyramid level: rows [row0, row0+height), cols [col0, col0+width). */
export interface Window {
  level: number;
  row0: number;
  col0: number;
  width: number;
  height: number;
}

export interface LayerSum {
  total: number;
  byCountry: Record<string, number>;
}

export interface QueryParams {
  lat: number;
  lon: number;
  radiusKm: number;
  layers: string[];
}

export interface QueryResult {
  params: QueryParams;
  level: number;
  cellsInCircle: number;
  /** land area inside the circle, km², split into covered vs not covered */
  landKm2: number;
  coveredLandKm2: number;
  coveredShare: number;
  /** country code at the picked point (undefined = sea or outside coverage) */
  pointCountry?: string;
  layers: Record<string, LayerSum>;
  ms: number;
}
