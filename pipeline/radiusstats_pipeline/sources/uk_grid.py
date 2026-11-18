"""UK 1 km base population (no Census 2021 grid exists for the UK).

WorldPop Global2 constrained 2021 counts at 3 arc-seconds (~100 m) are assigned to ONS local authority
districts (LAD 2023, generalised clipped boundaries) by pixel centre, then summed into EPSG:3035 1 km
cells. The result has one row per (cell, LAD) with the 2021 population of that LAD's part of the cell,
so a cell on an LAD border is split by where people actually live, as with the census per-country
files. Pixels whose centre falls outside every (generalised) LAD polygon - coastal slivers - take the
LAD of the nearest assigned pixel.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window
from scipy.spatial import cKDTree

from ..config import DOWNLOAD_DIR, WORK_DIR, Config
from ..fetch import fetch

CELL = 1000
ROWS_PER_CHUNK = 1024


def lad_boundaries(cfg: Config) -> dict:
    path = fetch(cfg.source("uk_lad_2023"), DOWNLOAD_DIR / "ons" / "LAD_MAY_2023_UK_BGC_V2.geojson")
    gj = json.loads(path.read_text())
    if gj.get("properties", {}).get("exceededTransferLimit"):
        raise RuntimeError("LAD boundary query was truncated")
    return gj


def uk_cells(cfg: Config, report) -> pd.DataFrame:
    """Columns: x, y (lower-left EPSG:3035 m), lad (UK + LAD23CD), pop (WorldPop 2021)."""
    cache = WORK_DIR / "uk_cells_worldpop2021_lad23.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    tif = fetch(cfg.source("worldpop_uk_2021"), DOWNLOAD_DIR / "worldpop" / "gbr_pop_2021_CN_100m_R2025A_v1.tif")
    gj = lad_boundaries(cfg)
    codes = [f["properties"]["LAD23CD"] for f in gj["features"]]
    shapes = [(f["geometry"], i + 1) for i, f in enumerate(gj["features"])]

    xs_all, ys_all, ids_all, pop_all = [], [], [], []
    with rasterio.open(tif) as src:
        nd = src.nodata
        for r0 in range(0, src.height, ROWS_PER_CHUNK):
            win = Window(0, r0, src.width, min(ROWS_PER_CHUNK, src.height - r0))
            a = src.read(1, window=win).astype(np.float64)
            ok = np.isfinite(a) & (a > 0)
            if nd is not None:
                ok &= a != nd
            if not ok.any():
                continue
            tr = src.window_transform(win)
            ids = rasterize(shapes, out_shape=a.shape, transform=tr, fill=0, dtype="uint16")
            rr, cc = np.nonzero(ok)
            lon = tr.c + (cc + 0.5) * tr.a
            lat = tr.f + (rr + 0.5) * tr.e
            xs_all.append(lon)
            ys_all.append(lat)
            ids_all.append(ids[rr, cc])
            pop_all.append(a[rr, cc])
        crs = src.crs
    lon = np.concatenate(xs_all)
    lat = np.concatenate(ys_all)
    lad_id = np.concatenate(ids_all).astype(np.int32)
    pop = np.concatenate(pop_all)
    x, y = warp_transform(crs, "EPSG:3035", lon, lat)
    x, y = np.asarray(x), np.asarray(y)

    orphan = lad_id == 0
    if orphan.any():
        tree = cKDTree(np.c_[x[~orphan], y[~orphan]])
        _, idx = tree.query(np.c_[x[orphan], y[orphan]])
        lad_id[orphan] = lad_id[~orphan][idx]
        report.mapping("uk_pixel_lad_nearest", pixels=int(orphan.sum()), population=float(pop[orphan].sum()),
                       detail="WorldPop pixel centre outside the generalised LAD polygons: nearest LAD.")
    df = pd.DataFrame({
        "x": (np.floor(x / CELL) * CELL).astype(np.int32),
        "y": (np.floor(y / CELL) * CELL).astype(np.int32),
        "lad": np.asarray(["UK" + c for c in codes])[lad_id - 1],
        "pop": pop,
    })
    out = df.groupby(["x", "y", "lad"], as_index=False)["pop"].sum()
    report.note("uk_worldpop_base", pixels=int(len(pop)), cells=int(out[["x", "y"]].drop_duplicates().shape[0]),
                rows=len(out), population_2021=float(out["pop"].sum()), lads=int(out["lad"].nunique()))
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache)
    return out
