"""Heat-map raster tiles (Web Mercator PNG in one PMTiles file per layer) for the map display.

Density = layer value per km² of the 1 km cell. Colours use a log scale between the 2nd and 99.5th
percentiles of positive densities; the legend breaks go into manifest.json. Zero / nodata cells are
transparent. Tiles stop at `max_zoom` (8 ≈ 400 m/px at 50°N); MapLibre over-zooms beyond that.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
from PIL import Image
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds

from .grid import GridSpec

WEB = 20037508.342789244
TILE = 256

# perceptually uniform ramp (approximation of "magma"/"inferno" family), dark -> bright
RAMP = np.array([
    [252, 253, 191], [254, 186, 128], [248, 118, 92], [222, 73, 104],
    [182, 54, 121], [140, 41, 129], [100, 26, 128], [59, 15, 112],
], dtype=np.float64)[::-1]


def colorize(density: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """RGBA uint8 image; log scale between lo and hi; <= 0 / NaN transparent."""
    h, w = density.shape
    out = np.zeros((h, w, 4), np.uint8)
    ok = np.isfinite(density) & (density > 0)
    if not ok.any():
        return out
    t = (np.log10(np.clip(density[ok], lo, hi)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    pos = t * (len(RAMP) - 1)
    i0 = np.floor(pos).astype(int).clip(0, len(RAMP) - 2)
    f = (pos - i0)[:, None]
    rgb = RAMP[i0] * (1 - f) + RAMP[i0 + 1] * f
    out[ok, :3] = rgb.round().astype(np.uint8)
    out[ok, 3] = 255
    return out


def _tile_range(bounds_3857, z):
    n = 2 ** z
    x0, y0, x1, y1 = bounds_3857
    tx0 = max(0, int((x0 + WEB) / (2 * WEB) * n))
    tx1 = min(n - 1, int((x1 + WEB) / (2 * WEB) * n))
    ty0 = max(0, int((WEB - y1) / (2 * WEB) * n))
    ty1 = min(n - 1, int((WEB - y0) / (2 * WEB) * n))
    return tx0, tx1, ty0, ty1


def build_pmtiles(path: Path, arr: np.ndarray, grid: GridSpec, nodata: float, *, max_zoom: int = 8,
                  min_zoom: int = 3, name: str = "") -> dict:
    """Write PNG tiles of the density of `arr` (1 km layer) and return legend info."""
    dens = np.where(arr == nodata, np.nan, arr).astype(np.float32)  # per km² (1 km cells)
    pos = dens[np.isfinite(dens) & (dens > 0)]
    lo = float(np.percentile(pos, 2)) if pos.size else 1.0
    hi = float(np.percentile(pos, 99.5)) if pos.size else 10.0
    lo = max(lo, hi / 1e5)

    src_crs, dst_crs = CRS.from_epsg(3035), CRS.from_epsg(3857)
    b3857 = transform_bounds(src_crs, dst_crs, grid.xmin, grid.ymin, grid.xmax, grid.ymax, densify_pts=51)
    b4326 = transform_bounds(src_crs, CRS.from_epsg(4326), grid.xmin, grid.ymin, grid.xmax, grid.ymax, densify_pts=51)
    path.parent.mkdir(parents=True, exist_ok=True)
    n_tiles = 0
    with open(path, "wb") as f:
        w = Writer(f)
        for z in range(min_zoom, max_zoom + 1):
            n = 2 ** z
            size = 2 * WEB / n
            res_m = size / TILE
            tx0, tx1, ty0, ty1 = _tile_range(b3857, z)
            for tx in range(tx0, tx1 + 1):
                for ty in range(ty0, ty1 + 1):
                    left = -WEB + tx * size
                    top = WEB - ty * size
                    dst = np.full((TILE, TILE), np.nan, np.float32)
                    reproject(dens, dst, src_transform=grid.transform(1), src_crs=src_crs, src_nodata=np.nan,
                              dst_transform=from_bounds(left, top - size, left + size, top, TILE, TILE),
                              dst_crs=dst_crs, dst_nodata=np.nan,
                              resampling=Resampling.average if res_m > 700 else Resampling.nearest)
                    rgba = colorize(dst, lo, hi)
                    if rgba[..., 3].max() == 0:
                        continue
                    buf = io.BytesIO()
                    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
                    w.write_tile(zxy_to_tileid(z, tx, ty), buf.getvalue())
                    n_tiles += 1
        cx, cy = (b4326[0] + b4326[2]) / 2, (b4326[1] + b4326[3]) / 2
        w.finalize(
            {"tile_type": TileType.PNG, "tile_compression": Compression.NONE,
             "min_lon_e7": int(b4326[0] * 1e7), "min_lat_e7": int(b4326[1] * 1e7),
             "max_lon_e7": int(b4326[2] * 1e7), "max_lat_e7": int(b4326[3] * 1e7),
             "center_zoom": min_zoom + 2, "center_lon_e7": int(cx * 1e7), "center_lat_e7": int(cy * 1e7)},
            {"name": name, "attribution": "RadiusStats Europe (Eurostat, GISCO)"},
        )
    return {"min": lo, "max": hi, "tiles": n_tiles, "min_zoom": min_zoom, "max_zoom": max_zoom,
            "ramp": [[int(c) for c in rgb] for rgb in RAMP]}
