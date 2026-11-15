"""Eurostat dissemination API (SDMX 2.1, SDMX-CSV). Tables are cached as csv.gz."""
from __future__ import annotations

import re

import pandas as pd

from ..config import DOWNLOAD_DIR, Config
from ..fetch import fetch


def table(cfg: Config, code: str, key: str = "", *, refresh: bool = False) -> pd.DataFrame:
    """Download a whole Eurostat table (optionally filtered by an SDMX key) as a tidy DataFrame.

    Columns: the table's dimensions (lower case), TIME_PERIOD (int), OBS_VALUE (float), OBS_FLAG.
    """
    base = cfg.source("eurostat_sdmx")
    url = f"{base}/{code}/{key + '/' if key else ''}?format=SDMX-CSV&compressed=true"
    safe_key = re.sub(r"[^A-Za-z0-9_.+-]", "_", key) if key else "all"
    dest = DOWNLOAD_DIR / "eurostat" / f"{code}__{safe_key}.csv.gz"
    fetch(url, dest, refresh=refresh)
    df = pd.read_csv(dest, compression="gzip", dtype={"geo": str, "OBS_FLAG": str})
    df = df.drop(columns=[c for c in ("DATAFLOW", "LAST UPDATE", "CONF_STATUS") if c in df.columns])
    df["TIME_PERIOD"] = df["TIME_PERIOD"].astype(int)
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    return df


def last_update(cfg: Config, code: str, key: str = "") -> str | None:
    """'LAST UPDATE' stamp of a cached table (for DATA_SOURCES.md)."""
    safe_key = re.sub(r"[^A-Za-z0-9_.+-]", "_", key) if key else "all"
    dest = DOWNLOAD_DIR / "eurostat" / f"{code}__{safe_key}.csv.gz"
    if not dest.exists():
        return None
    head = pd.read_csv(dest, compression="gzip", nrows=1)
    return str(head["LAST UPDATE"].iloc[0]) if "LAST UPDATE" in head.columns else None


def nuts3(df: pd.DataFrame, countries: list[str]) -> pd.DataFrame:
    """Keep NUTS 3 rows (5-character codes) of the given countries, excluding extra-regio ZZZ."""
    g = df["geo"]
    m = (g.str.len() == 5) & g.str[:2].isin(countries) & ~g.str.endswith("ZZZ")
    return df[m]
