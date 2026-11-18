/**
 * Reading COG windows with geotiff.js over HTTP range requests (or local files in tests).
 * - GeoTIFF handles are opened once per URL; geotiff's block cache keeps recently read tiles.
 * - All layers of a pyramid level live in one pixel-interleaved multi-band COG, so a window costs one
 *   header and one set of tiles for every layer; each layer is a band (`samples: [band]`).
 * - A small LRU of decoded windows answers repeated identical queries (e.g. while toggling layers).
 * - Every read takes an AbortSignal so stale queries are cancelled while the user drags.
 */
import { fromUrl, type GeoTIFF } from "geotiff";
import type { Window } from "./types";

export type Raster = Float32Array | Uint8Array;

/** HTTP range granularity. COG tiles are 64x64 cells (~2-15 KB compressed), so small blocks avoid
 *  downloading neighbouring tiles; geotiff.js merges adjacent blocks into one request. */
export const BLOCK_BYTES = 16 * 1024;

export interface RasterSource {
  read(url: string, win: Window, signal?: AbortSignal, band?: number): Promise<Raster>;
}

type Opener = (url: string) => Promise<GeoTIFF>;

export class CogSource implements RasterSource {
  private tiffs = new Map<string, Promise<GeoTIFF>>();
  private lru = new Map<string, Raster>();

  constructor(
    private baseUrl: string,
    private open: Opener = (u) => fromUrl(u, { cache: true, blockSize: BLOCK_BYTES } as never),
    private maxWindows = 96,
  ) {}

  private tiff(url: string): Promise<GeoTIFF> {
    const full = new URL(url, this.baseUrl).toString();
    let p = this.tiffs.get(full);
    if (!p) {
      p = this.open(full);
      p.catch(() => this.tiffs.delete(full));
      this.tiffs.set(full, p);
    }
    return p;
  }

  async read(url: string, win: Window, signal?: AbortSignal, band = 0): Promise<Raster> {
    const key = `${url}|${band}|${win.row0},${win.col0},${win.width},${win.height}`;
    const hit = this.lru.get(key);
    if (hit) {
      this.lru.delete(key);
      this.lru.set(key, hit);
      return hit;
    }
    const tiff = await this.tiff(url);
    const image = await tiff.getImage(0);
    const data = (await image.readRasters({
      window: [win.col0, win.row0, win.col0 + win.width, win.row0 + win.height],
      samples: [band],
      interleave: true,
      signal,
    })) as unknown as Raster;
    this.lru.set(key, data);
    if (this.lru.size > this.maxWindows) this.lru.delete(this.lru.keys().next().value!);
    return data;
  }
}
