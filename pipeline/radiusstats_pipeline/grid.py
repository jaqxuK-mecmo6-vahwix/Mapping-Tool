"""The EPSG:3035 raster grid all layers share."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rasterio.transform import Affine


@dataclass(frozen=True)
class GridSpec:
    xmin: int      # metres, EPSG:3035, left edge
    ymax: int      # metres, top edge
    width: int     # cells at level 1 (1 km)
    height: int
    cell: int = 1000

    @property
    def xmax(self) -> int:
        return self.xmin + self.width * self.cell

    @property
    def ymin(self) -> int:
        return self.ymax - self.height * self.cell

    def transform(self, level: int = 1) -> Affine:
        c = self.cell * level
        return Affine(c, 0, self.xmin, 0, -c, self.ymax)

    def shape(self, level: int = 1) -> tuple[int, int]:
        assert self.width % level == 0 and self.height % level == 0
        return self.height // level, self.width // level

    def index(self, x_llc: np.ndarray, y_llc: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Row/col of 1 km cells given lower-left corners; also a mask of cells inside the grid."""
        col = (np.asarray(x_llc, dtype=np.int64) - self.xmin) // self.cell
        row = (self.ymax - (np.asarray(y_llc, dtype=np.int64) + self.cell)) // self.cell
        inside = (col >= 0) & (col < self.width) & (row >= 0) & (row < self.height)
        return row, col, inside

    def to_dict(self) -> dict:
        return {"crs": "EPSG:3035", "xmin": self.xmin, "ymax": self.ymax, "xmax": self.xmax, "ymin": self.ymin,
                "width": self.width, "height": self.height, "cell_m": self.cell}


def extent_for(xs: np.ndarray, ys: np.ndarray, pad_km: int, align_km: int, cell: int = 1000) -> GridSpec:
    """Smallest grid containing all cells (lower-left corners xs, ys) plus padding, with origin and
    size aligned to `align_km` so every pyramid level divides the grid exactly."""
    a = align_km * 1000
    pad = pad_km * 1000
    x0 = int(np.floor((xs.min() - pad) / a) * a)
    y0 = int(np.floor((ys.min() - pad) / a) * a)
    x1 = int(np.ceil((xs.max() + cell + pad) / a) * a)
    y1 = int(np.ceil((ys.max() + cell + pad) / a) * a)
    return GridSpec(xmin=x0, ymax=y1, width=(x1 - x0) // cell, height=(y1 - y0) // cell, cell=cell)
