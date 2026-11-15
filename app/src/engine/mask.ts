/**
 * Fractional cell coverage of a convex polygon (the projected geodesic circle) on a pixel window.
 *
 * Each cell row is sampled at 4 sub-rows (16 for circles under 20 cells radius); on each sub-row the polygon is an interval [a, b]
 * (the projected circle is convex). A cell's weight is the share of its 4×4 sub-cell centres inside
 * the polygon. Cells entirely inside get exactly 1 without per-cell work; only edge cells are
 * effectively supersampled.
 */
import type { Window } from "./types";

export const SUB = 4;
/** Below this radius (in cells) edge cells are sampled 16×16: area error < 1 % even at 1–2 cells. */
export const FINE_SUB_RADIUS_CELLS = 20;

export function subsamplingFor(radiusCells: number): number {
  return radiusCells < FINE_SUB_RADIUS_CELLS ? 16 : SUB;
}

/** Interval [a, b] where the horizontal line y crosses the polygon, or null. */
export function rowInterval(poly: [number, number][], y: number): [number, number] | null {
  let a = Infinity, b = -Infinity;
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % n];
    if ((y1 <= y && y < y2) || (y2 <= y && y < y1)) {
      const x = x1 + ((y - y1) * (x2 - x1)) / (y2 - y1);
      if (x < a) a = x;
      if (x > b) b = x;
    }
  }
  return a <= b ? [a, b] : null;
}

/** Count of sub-column centres j + (m+0.5)/sub, m = 0..sub-1, inside [a, b]. */
function subCount(j: number, a: number, b: number, sub: number): number {
  // m ranges where a <= j + (m + 0.5)/sub <= b
  const lo = Math.max(0, Math.ceil((a - j) * sub - 0.5));
  const hi = Math.min(sub - 1, Math.floor((b - j) * sub - 0.5));
  return hi >= lo ? hi - lo + 1 : 0;
}

/**
 * Weights (0..1) per cell of the window, row-major, length width*height.
 * `poly` is in pixel coordinates of the same level as the window.
 */
export function coverageWeights(poly: [number, number][], win: Window, sub = SUB): Float32Array {
  const { row0, col0, width, height } = win;
  const w = new Float32Array(width * height);
  const inv = 1 / (sub * sub);
  for (let r = 0; r < height; r++) {
    const rowBase = r * width;
    for (let k = 0; k < sub; k++) {
      const y = row0 + r + (k + 0.5) / sub;
      const iv = rowInterval(poly, y);
      if (!iv) continue;
      const [a, b] = iv;
      const cFirst = Math.max(col0, Math.floor(a));
      const cLast = Math.min(col0 + width - 1, Math.floor(b));
      for (let c = cFirst; c <= cLast; c++) {
        // interior cells: every sub-centre is inside
        const n = c >= a && c + 1 <= b ? sub : subCount(c, a, b, sub);
        if (n) w[rowBase + (c - col0)] += n * inv;
      }
    }
  }
  return w;
}

/** Number of cells touched (weight > 0) and the effective cell count (sum of weights). */
export function weightStats(w: Float32Array): { touched: number; effective: number } {
  let touched = 0, effective = 0;
  for (let i = 0; i < w.length; i++) {
    if (w[i] > 0) { touched++; effective += w[i]; }
  }
  return { touched, effective };
}

/**
 * Weighted sum of a raster window, split by country id.
 * Values equal to `nodata` (or negative) count as 0. Accumulates in float64.
 */
export function weightedSumByCountry(
  values: ArrayLike<number>, weights: Float32Array, country: ArrayLike<number>, nodata: number,
): { total: number; byId: Map<number, number> } {
  const byId = new Map<number, number>();
  let total = 0;
  for (let i = 0; i < weights.length; i++) {
    const wt = weights[i];
    if (wt === 0) continue;
    const v = values[i];
    if (v === nodata || !(v > 0)) continue;
    const x = v * wt;
    total += x;
    const id = country[i];
    byId.set(id, (byId.get(id) ?? 0) + x);
  }
  return { total, byId };
}
