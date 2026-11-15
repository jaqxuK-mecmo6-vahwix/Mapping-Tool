"""GISCO 1 km grid (NUTS codes and land share per cell) and the Census 2021 population grid."""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ..config import DOWNLOAD_DIR, WORK_DIR, Config
from ..fetch import fetch

NUTS_VERSIONS = (2024, 2021, 2016)
GRID_COLS = ["X_LLC", "Y_LLC", "CNTR_ID", "LAND_PC"] + [f"NUTS{v}_3" for v in NUTS_VERSIONS]
_ID_RE = r"N(?P<y>-?\d+)E(?P<x>-?\d+)$"


def grid_path(cfg: Config):
    return fetch(cfg.source("gisco_grid"), DOWNLOAD_DIR / "gisco" / "grid_1km.parquet")


def census_zip_path(cfg: Config):
    return fetch(cfg.source("census_grid"), DOWNLOAD_DIR / "gisco" / "Eurostat_Census-GRID_2021_V3.zip")


def load_grid(cfg: Config) -> pd.DataFrame:
    """All cells of the GISCO 1 km grid: x, y (lower-left, EPSG:3035 metres), cntr (list string),
    land (0..1), nuts{V} for V in NUTS_VERSIONS ('' or one or more NUTS 3 codes joined by '-')."""
    cache = WORK_DIR / "grid_1km_slim_v2.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    t = pq.read_table(grid_path(cfg), columns=GRID_COLS).to_pandas()
    df = pd.DataFrame({
        "x": t["X_LLC"].astype(np.int32),
        "y": t["Y_LLC"].astype(np.int32),
        "cntr": t["CNTR_ID"].fillna("").astype(str),
        "land": (t["LAND_PC"].fillna(0) / 100.0).clip(0, 1).astype(np.float32),
        **{f"nuts{v}": t[f"NUTS{v}_3"].fillna("").astype(str) for v in NUTS_VERSIONS},
    })
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df


def load_census_country(cfg: Config, country: str, report) -> pd.DataFrame:
    """Census 2021 total population for one country's reporting, per cell: x, y, pop.

    Uses the per-country files inside the V3 zip, so cells shared by two countries are split
    exactly as each national statistical institute reported them.
    """
    cache = WORK_DIR / f"census2021_T_{country}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    zpath = census_zip_path(cfg)
    with zipfile.ZipFile(zpath) as z:
        inner = zipfile.ZipFile(io.BytesIO(z.read(cfg.source("census_country_member"))))
        name = f"CENSUS_GRID_N_{country}_2021.csv"
        if name not in inner.namelist():
            raise FileNotFoundError(f"{name} not in census zip (country not covered by census grid)")
        chunks = []
        with inner.open(name) as f:
            for ch in pd.read_csv(f, usecols=["STAT", "SPATIAL", "OBS_VALUE"], chunksize=2_000_000,
                                  dtype={"STAT": str, "SPATIAL": str}, encoding="utf-8-sig"):
                chunks.append(ch[ch["STAT"] == "T"])
    d = pd.concat(chunks, ignore_index=True)
    d["OBS_VALUE"] = pd.to_numeric(d["OBS_VALUE"], errors="coerce")

    unalloc = d["SPATIAL"].str.contains("unallocated", case=False)
    if unalloc.any():
        report.note("census_unallocated", country=country, population=float(d.loc[unalloc, "OBS_VALUE"].sum()),
                    detail="No cell; absorbed by rescaling to NUTS 3 totals.")
    d = d[~unalloc]
    bad = d["OBS_VALUE"].isna() | (d["OBS_VALUE"] < 0)
    if bad.any():
        report.note("census_missing_values", country=country, cells=int(bad.sum()),
                    detail="Confidential/not-available T set to 0 before rescaling.")
    d.loc[bad, "OBS_VALUE"] = 0

    xy = d["SPATIAL"].str.extract(_ID_RE)
    out = pd.DataFrame({"x": xy["x"].astype(np.int32), "y": xy["y"].astype(np.int32),
                        "pop": d["OBS_VALUE"].astype(np.float64)})
    out = out.groupby(["x", "y"], as_index=False)["pop"].sum()
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache)
    return out
