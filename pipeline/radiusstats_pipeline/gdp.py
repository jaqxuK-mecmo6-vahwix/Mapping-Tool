"""Regional GDP: nominal EUR, PPS, and real (constant prices, fixed base-year exchange rate).

Real GDP for region r and year Y is expressed in EUR at base-year (B) prices:

    real_r,Y = nominal_NAC_r,B * V_r,Y / V_r,B * (EUR per NAC in year B)

where V is a volume index. V comes from ARDECO (SOVGD, NUTS 3) when the API answers; otherwise
from Eurostat NUTS 2 volume indices: each NUTS 3 region is deflated with the implicit GDP deflator of
its NUTS 2 region (nominal_NAC_r,Y / P_n,Y). Exchange rates are frozen at year B, so currency
movements never change growth.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import requests

from .config import DOWNLOAD_DIR, Config
from .fetch import USER_AGENT
from .sources import eurostat


def _gdp3(cfg: Config) -> pd.DataFrame:
    df = eurostat.table(cfg, "nama_10r_3gdp")
    return df.rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": "value"})


def nominal(cfg: Config, year: int, unit: str) -> pd.Series:
    """NUTS 3 GDP at current prices for `year` in `unit` (MIO_EUR, MIO_PPS_EU27_2020, MIO_NAC)."""
    df = eurostat.nuts3(_gdp3(cfg), cfg.build_countries)
    s = df[(df["unit"] == unit) & (df["year"] == year)].set_index("geo")["value"].dropna()
    return s


def extra_regio(cfg: Config, year: int, unit: str = "MIO_EUR") -> pd.Series:
    df = _gdp3(cfg)
    m = df["geo"].str.endswith("ZZZ") & df["geo"].str[:2].isin(cfg.build_countries) & (df["geo"].str.len() == 5)
    return df[m & (df["unit"] == unit) & (df["year"] == year)].set_index("geo")["value"].dropna()


# --- volume indices -------------------------------------------------------------------------------

def _ardeco_volume(cfg: Config, report) -> pd.DataFrame | None:
    """ARDECO SOVGD at NUTS 3 as a tidy frame (geo, year, value) or None if unavailable."""
    url = f"{cfg.source('ardeco_export')}/SOVGD?version=2024&level_id=3&format=csv"
    dest = DOWNLOAD_DIR / "ardeco" / "SOVGD_v2024_l3.csv"
    try:
        if not dest.exists():
            r = requests.get(url, timeout=120, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
        df = pd.read_csv(io.BytesIO(dest.read_bytes()))
        cols = {c.lower(): c for c in df.columns}
        geo = next(cols[c] for c in cols if c in ("territory_id", "nutscode", "nuts_code", "geo"))
        yr = next(cols[c] for c in cols if c in ("year", "time", "time_period"))
        val = next(cols[c] for c in cols if c in ("value", "val", "obs_value"))
        out = pd.DataFrame({"geo": df[geo].astype(str), "year": df[yr].astype(int),
                            "value": pd.to_numeric(df[val], errors="coerce")}).dropna()
        out = out[(out["geo"].str.len() == 5) & out["geo"].str[:2].isin(cfg.build_countries)]
        if out.empty:
            raise ValueError("no NUTS 3 rows for the built countries")
        report.note("real_gdp_source", source="ARDECO SOVGD (NUTS 2024)", url=url)
        return out
    except Exception as e:  # noqa: BLE001 - any failure means: use the documented fallback
        report.fallback("ardeco_unavailable", url=url, error=str(e)[:200],
                        detail="Real GDP from NUTS 3 nominal deflated by the NUTS 2 implicit deflator "
                               "(Eurostat nama_10r_3gdp MIO_NAC + nama_10r_2gvagr B1GQ I20).")
        return None


def _nuts2_deflator_volume(cfg: Config, years: list[int], report) -> pd.DataFrame:
    g3 = eurostat.nuts3(_gdp3(cfg), cfg.build_countries)
    nac = g3[g3["unit"] == "MIO_NAC"][["geo", "year", "value"]].dropna()
    nac["n2"] = nac["geo"].str[:4]
    n2_nom = nac.groupby(["n2", "year"])["value"].sum()

    vol = eurostat.table(cfg, "nama_10r_2gvagr")
    vol = vol[(vol["na_item"] == "B1GQ") & (vol["unit"] == "I20") & (vol["geo"].str.len() == 4)
              & vol["geo"].str[:2].isin(cfg.build_countries)]
    idx = vol.set_index(["geo", "TIME_PERIOD"])["OBS_VALUE"]
    idx.index.names = ["n2", "year"]

    # implicit deflator of the NUTS 2 region: nominal / volume index (scale irrelevant)
    defl = (n2_nom / idx).rename("defl")
    out = nac.join(defl, on=["n2", "year"])
    miss = out["defl"].isna() & out["year"].isin(years)
    if miss.any():
        report.gap("nuts2_volume_missing", rows=int(miss.sum()),
                   regions=sorted(out.loc[miss, "n2"].unique().tolist())[:30])
    out["value"] = out["value"] / out["defl"]
    return out[["geo", "year", "value"]].dropna()


def real(cfg: Config, report) -> pd.DataFrame:
    """Real GDP by NUTS 3 for cfg.gdp_years: DataFrame index=geo, columns=years, mio EUR at base-year
    prices and base-year exchange rates."""
    B = cfg.real_base_year
    years = sorted(set(cfg.gdp_years) | {B})
    v = _ardeco_volume(cfg, report)
    if v is None:
        v = _nuts2_deflator_volume(cfg, years, report)
    V = v.pivot_table(index="geo", columns="year", values="value")

    nac_B = nominal(cfg, B, "MIO_NAC")
    eur_B = nominal(cfg, B, "MIO_EUR")
    # EUR per unit of national currency in year B, per country (= Eurostat's own annual average rate)
    c = eur_B.index.str[:2]
    eur_per_nac = (eur_B.groupby(c).sum() / nac_B.groupby(nac_B.index.str[:2]).sum())

    out = pd.DataFrame(index=V.index)
    for y in cfg.gdp_years:
        if y not in V.columns or B not in V.columns:
            raise RuntimeError(f"volume index missing for year {y} or base {B}")
        rate = pd.Series(V.index.str[:2], index=V.index).map(eur_per_nac)
        out[y] = nac_B.reindex(V.index) * V[y] / V[B] * rate
    bad = out.isna().any(axis=1)
    if bad.any():
        report.gap("real_gdp_incomplete", regions=sorted(out.index[bad].tolist()))
    return out
