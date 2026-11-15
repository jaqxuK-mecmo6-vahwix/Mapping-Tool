"""Write Cloud-Optimized GeoTIFFs (one file per pyramid level, no GDAL-averaged overviews)."""
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


def read(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1)
