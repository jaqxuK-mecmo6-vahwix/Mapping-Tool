"""Write Cloud-Optimized GeoTIFFs (no GDAL-averaged overviews: every pyramid level is its own file).

The build writes ONE multi-band COG per pyramid level holding every layer as a band
(`LevelStack`), pixel-interleaved: a circle query then costs one header and one set of tiles for all
layers, and neighbouring bands compress better together (~35 % smaller than one file per layer).
`write_cog` (single band) is kept for tests and tools."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.shutil import copy as rio_copy

from .grid import GridSpec


def write_cog(path: Path, arr: np.ndarray, grid: GridSpec, level: int, *, nodata: float | int | None,
              blocksize: int = 256, description: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    assert (h, w) == grid.shape(level), (arr.shape, grid.shape(level))
    is_float = np.issubdtype(arr.dtype, np.floating)
    profile = dict(driver="GTiff", width=w, height=h, count=1, dtype=arr.dtype.name,
                   crs=CRS.from_epsg(3035), transform=grid.transform(level), nodata=nodata)
    tmp = path.with_suffix(".tmp.tif")
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            ds.write(arr, 1)
            if description:
                ds.set_band_description(1, description)
            ds.update_tags(level_km=str(level), aggregation="sum" if is_float else "categorical")
        with mem.open() as src:
            rio_copy(src, tmp, driver="COG", COMPRESS="DEFLATE", LEVEL=9,
                     PREDICTOR="YES",  # floating-point predictor (3) for float32, horizontal (2) for ints
                     BLOCKSIZE=blocksize, OVERVIEWS="NONE", BIGTIFF="NO", NUM_THREADS="ALL_CPUS")
    tmp.replace(path)
    return path


def read(path: Path, band: int = 0) -> np.ndarray:
    """Read one band (0-based) of a COG."""
    with rasterio.open(path) as ds:
        return ds.read(band + 1)


def read_level(out_dir: Path, level_file: dict) -> np.ndarray:
    """Read a manifest level entry ({url, band})."""
    return read(Path(out_dir) / level_file["url"], int(level_file.get("band", 0)))


class LevelStack:
    """Collects bands per pyramid level in uncompressed band-interleaved temp GeoTIFFs on disk (so the
    build never holds all layers in memory), then converts each level to a pixel-interleaved COG."""

    def __init__(self, tmp_dir: Path, grid: GridSpec, levels: list[int], bands: list[str], nodata: float):
        self.tmp_dir, self.grid, self.levels, self.bands, self.nodata = Path(tmp_dir), grid, levels, bands, nodata
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._ds = {}
        for lv in levels:
            h, w = grid.shape(lv)
            self._ds[lv] = rasterio.open(
                self.tmp_dir / f"L{lv}.tif", "w", driver="GTiff", width=w, height=h, count=len(bands),
                dtype="float32", crs=CRS.from_epsg(3035), transform=grid.transform(lv), nodata=nodata,
                tiled=True, blockxsize=256, blockysize=256, interleave="band", BIGTIFF="IF_SAFER")
        self.written: set[str] = set()

    def band_of(self, layer_id: str) -> int:
        return self.bands.index(layer_id)

    def write(self, layer_id: str, level: int, arr: np.ndarray) -> None:
        ds = self._ds[level]
        assert arr.shape == (ds.height, ds.width), (layer_id, level, arr.shape)
        ds.write(arr.astype(np.float32, copy=False), self.band_of(layer_id) + 1)
        ds.set_band_description(self.band_of(layer_id) + 1, layer_id)
        self.written.add(layer_id)

    def finish(self, out_dir: Path, blocksize: int) -> dict[int, dict]:
        missing = set(self.bands) - self.written
        if missing:
            raise RuntimeError(f"bands never written: {sorted(missing)}")
        files = {}
        for lv, ds in self._ds.items():
            ds.close()
            src_path = self.tmp_dir / f"L{lv}.tif"
            dst = Path(out_dir) / "cog" / f"L{lv}.tif"
            dst.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(src_path, "r+") as src:
                src.update_tags(level_km=str(lv), bands=",".join(self.bands))
            with rasterio.open(src_path) as src:
                rio_copy(src, dst, driver="COG", COMPRESS="DEFLATE", LEVEL=9, PREDICTOR="YES",
                         INTERLEAVE="PIXEL", BLOCKSIZE=blocksize, OVERVIEWS="NONE", BIGTIFF="NO",
                         NUM_THREADS="ALL_CPUS")
            src_path.unlink()
            h, w = self.grid.shape(lv)
            files[lv] = {"url": f"cog/L{lv}.tif", "bytes": dst.stat().st_size, "width": w, "height": h}
        return files
