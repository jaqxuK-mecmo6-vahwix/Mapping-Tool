/** Geodesic circle on the WGS84 ellipsoid, EPSG:3035 projection and pyramid-level choice. */
import proj4 from "proj4";
import geodesic from "geographiclib-geodesic";
import type { Manifest, Window } from "./types";

export const EPSG3035 =
  "+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs";
const toLaea = proj4("EPSG:4326", EPSG3035);

const geod = geodesic.Geodesic.WGS84;

/** [x, y] in EPSG:3035 metres from [lon, lat]. */
export function project(lon: number, lat: number): [number, number] {
  return toLaea.forward([lon, lat]) as [number, number];
}

export function unproject(x: number, y: number): [number, number] {
  return toLaea.inverse([x, y]) as [number, number];
}

/** Vertices [lon, lat] of the geodesic circle (points at geodesic distance r from the centre). */
export function geodesicCircle(lat: number, lon: number, radiusKm: number, n = 360): [number, number][] {
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const r = geod.Direct(lat, lon, (360 * i) / n, radiusKm * 1000);
    pts.push([r.lon2!, r.lat2!]);
  }
  return pts;
}

/** Geodesic distance in km (used by tests and spot checks). */
export function geodesicDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  return geod.Inverse(lat1, lon1, lat2, lon2).s12! / 1000;
}

/**
 * Cell budget per query. The spec allows roughly 50k–250k cells; 100k keeps the worst-case download
 * near 1 MB for the visible layer group on 4G (~3 bytes per compressed populated cell × 4–6 layers).
 * Revisit with measured byte counts from the full European build.
 */
export const MAX_CELLS = 100_000;

/** Pick the finest pyramid level whose cell count for the circle stays <= maxCells. */
export function chooseLevel(radiusKm: number, levelsKm: number[], maxCells = MAX_CELLS): number {
  const sorted = [...levelsKm].sort((a, b) => a - b);
  for (const lv of sorted) {
    if ((Math.PI * radiusKm * radiusKm) / (lv * lv) <= maxCells) return lv;
  }
  return sorted[sorted.length - 1];
}

/** Circle polygon in fractional pixel coordinates (col, row) of a pyramid level. */
export function polygonToPixels(polyLonLat: [number, number][], m: Manifest, level: number): [number, number][] {
  const size = m.grid.cell_m * level;
  return polyLonLat.map(([lon, lat]) => {
    const [x, y] = project(lon, lat);
    return [(x - m.grid.xmin) / size, (m.grid.ymax - y) / size];
  });
}

/** Pixel window enclosing the polygon, clamped to the grid. Null if fully outside. */
export function windowFor(poly: [number, number][], m: Manifest, level: number): Window | null {
  let minC = Infinity, maxC = -Infinity, minR = Infinity, maxR = -Infinity;
  for (const [c, r] of poly) {
    minC = Math.min(minC, c); maxC = Math.max(maxC, c);
    minR = Math.min(minR, r); maxR = Math.max(maxR, r);
  }
  const W = m.grid.width / level, H = m.grid.height / level;
  const col0 = Math.max(0, Math.floor(minC)), col1 = Math.min(W, Math.ceil(maxC));
  const row0 = Math.max(0, Math.floor(minR)), row1 = Math.min(H, Math.ceil(maxR));
  if (col1 <= col0 || row1 <= row0) return null;
  return { level, row0, col0, width: col1 - col0, height: row1 - row0 };
}
