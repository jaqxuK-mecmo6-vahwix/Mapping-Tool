"""National regional accounts used where Eurostat's NUTS 3 tables are missing, incomplete or end
before the configured GDP year:

* CH - BFS, GDP by canton (je-d-04.02.06.01, 2011-2024, revised 2026): nominal CHF and real change at
  previous-year prices. Cantons are the Swiss NUTS 3 regions.
* NO - SSB StatBank 09391 (regional accounts by county): value added at basic prices, current NOK, and
  annual volume change. Scaled to GDP at market prices with the national (mainland) ratio. Counties are
  the Norwegian NUTS 3 regions (NUTS 2016 for the counties until 2019, NUTS 2021 for 2020-2023).
* UK - ONS regional GDP by local authority (1998-2024, LAD 2023 boundaries): GDP at current market
  prices and a chained volume index; ONS mid-year population estimates by local authority.

Every function returns values in the source's national currency (million NAC). Region codes are NUTS 3
codes, except for the UK where they are "UK" + the 9-character LAD 2023 code (e.g. UKE06000001).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import DOWNLOAD_DIR, Config
from ..fetch import fetch
from . import eurostat


@dataclass
class RegionalGDP:
    country: str
    nac: pd.DataFrame       # index = region, columns = int years; million NAC at current prices
    volume: pd.DataFrame    # index = region, columns = int years; volume index (any scale, chain-linked)
    source: str


# --- Switzerland (BFS) ----------------------------------------------------------------------------

CH_CANTONS = {
    "Zürich": "CH040", "Bern": "CH021", "Luzern": "CH061", "Uri": "CH062", "Schwyz": "CH063",
    "Obwalden": "CH064", "Nidwalden": "CH065", "Glarus": "CH051", "Zug": "CH066", "Freiburg": "CH022",
    "Solothurn": "CH023", "Basel-Stadt": "CH031", "Basel-Landschaft": "CH032", "Schaffhausen": "CH052",
    "Appenzell A. Rh.": "CH053", "Appenzell I. Rh.": "CH054", "St. Gallen": "CH055",
    "Graubünden": "CH056", "Aargau": "CH033", "Thurgau": "CH057", "Tessin": "CH070", "Waadt": "CH011",
    "Wallis": "CH012", "Neuenburg": "CH024", "Genf": "CH013", "Jura": "CH025",
}


def _bfs_sections(cfg: Config) -> dict[str, pd.DataFrame]:
    path = fetch(cfg.source("bfs_canton_gdp"), DOWNLOAD_DIR / "bfs" / "je-d-04.02.06.01.xlsx")
    raw = pd.read_excel(path, sheet_name="BIP pro Kanton", header=None)
    years = [int(str(v).rstrip("p")) for v in raw.iloc[2, 1:].dropna()]
    heads = {i: str(v) for i, v in raw[0].items() if isinstance(v, str) and ("Preisen" in v)}
    out = {}
    starts = sorted(heads)
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(raw)
        block = raw.iloc[i + 1:end, : len(years) + 1].dropna(subset=[0])
        block = block[block[0].isin(list(CH_CANTONS) + ["Schweiz"])]
        df = block.set_index(0)
        df.columns = years
        df = df.apply(pd.to_numeric, errors="coerce")
        label = heads[i]
        key = "nominal" if label.startswith("In ") else ("real_change" if "Vorjahres" in label else "nominal_change")
        out[key] = df
    missing = set(CH_CANTONS) - set(out["nominal"].index)
    if missing:
        raise RuntimeError(f"BFS table: cantons not found {sorted(missing)}")
    return out


def ch_gdp(cfg: Config, report) -> RegionalGDP:
    s = _bfs_sections(cfg)
    nom = s["nominal"].drop(index="Schweiz").rename(index=CH_CANTONS)
    chg = s["real_change"].drop(index="Schweiz").rename(index=CH_CANTONS)
    vol = pd.DataFrame(index=nom.index, columns=nom.columns, dtype=float)
    first = nom.columns[0]
    vol[first] = 100.0
    for y in nom.columns[1:]:
        vol[y] = vol[y - 1] * (1 + chg[y] / 100.0)
    total = s["nominal"].loc["Schweiz"]
    worst = float(((nom.sum() - total).abs() / total).max())
    report.check("bfs_cantons_sum_to_switzerland", worst < 1e-6, max_rel_diff=worst)
    return RegionalGDP("CH", nom, vol, "BFS je-d-04.02.06.01 (GDP by canton, 2011-2024)")


# --- Norway (SSB) ---------------------------------------------------------------------------------

# county codes of SSB StatBank -> NUTS 3; county structure until 2019 = NUTS 2016, 2020-2023 = NUTS 2021
NO_2016 = {"01": "NO031", "02": "NO012", "03": "NO011", "04": "NO021", "05": "NO022", "06": "NO032",
           "07": "NO033", "08": "NO034", "09": "NO041", "10": "NO042", "11": "NO043", "12": "NO051",
           "14": "NO052", "15": "NO053", "16": "NO060", "17": "NO060", "50": "NO060", "18": "NO071",
           "19": "NO072", "20": "NO073"}
NO_2021 = {"30": "NO082", "03": "NO081", "34": "NO020", "38": "NO091", "42": "NO092", "11": "NO0A1",
           "46": "NO0A2", "15": "NO0A3", "50": "NO060", "18": "NO071", "54": "NO074"}
# NUTS 2016 county -> NUTS 2021 county (for chaining volume growth back across the 2020 reform)
NO_2016_TO_2021 = {"NO031": "NO082", "NO012": "NO082", "NO032": "NO082", "NO011": "NO081",
                   "NO021": "NO020", "NO022": "NO020", "NO033": "NO091", "NO034": "NO091",
                   "NO041": "NO092", "NO042": "NO092", "NO043": "NO0A1", "NO051": "NO0A2",
                   "NO052": "NO0A2", "NO053": "NO0A3", "NO060": "NO060", "NO071": "NO071",
                   "NO072": "NO074", "NO073": "NO074"}
NO_REFORM_YEAR = 2020


def _ssb_09391(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    url = cfg.source("ssb_09391")
    path = fetch(url, DOWNLOAD_DIR / "ssb" / "09391_BNPB_BNPBvolum.csv")
    df = pd.read_csv(path, dtype={"Region": str}, na_values=["."], encoding="utf-8-sig")
    df = df.set_index("Region")
    gva = df[[c for c in df.columns if c.startswith("BNPB ")]].rename(columns=lambda c: int(c.split()[-1]))
    vol = df[[c for c in df.columns if c.startswith("BNPBvolum ")]].rename(columns=lambda c: int(c.split()[-1]))
    return gva.astype(float), vol.astype(float)


def no_gdp(cfg: Config, report) -> RegionalGDP:
    """Regional shares and volume changes from SSB; the level of mainland GDP (all NUTS 3 regions, i.e.
    excluding the continental shelf and Svalbard) from Eurostat where published (nama_10r_3gdp NO0
    minus NO0B), carried forward with SSB county value added after Eurostat's last year."""
    gva, chg = _ssb_09391(cfg)
    years = list(gva.columns)
    g3 = eurostat.table(cfg, "nama_10r_3gdp")
    g3 = g3[(g3["unit"] == "MIO_NAC")].pivot_table(index="geo", columns="TIME_PERIOD", values="OBS_VALUE")
    mainland_es = (g3.loc["NO0"] - g3.loc["NO0B"].fillna(0)).dropna() if "NO0" in g3.index else pd.Series(dtype=float)

    def by_nuts(year: int) -> pd.Series:
        m = NO_2016 if year < NO_REFORM_YEAR else NO_2021
        s = gva[year].reindex(list(m)).fillna(0.0)
        return s.groupby(s.index.map(m)).sum()

    county = {y: by_nuts(y) for y in years}
    have = [y for y in years if y in mainland_es.index and county[y].sum() > 0]
    if not have:
        raise RuntimeError("no overlap between SSB 09391 and Eurostat NO0 to calibrate the GDP level")
    k = {y: mainland_es[y] / county[y].sum() for y in have}   # GDP (market prices) / GVA (basic prices)
    last = max(have)
    nom = {}
    for y in years:
        ky = k.get(y, k[last] if y > last else k[min(have)])
        if y not in k:
            report.fallback("no_gdp_level_carried", year=y, ratio_year=last if y > last else min(have),
                            detail="Mainland GDP/GVA ratio of the nearest Eurostat year applied to SSB county GVA.")
        nom[y] = county[y] * ky
    nom_df = pd.DataFrame(nom)   # NUTS 2016 rows filled for < 2020, NUTS 2021 rows for >= 2020

    # volume index in NUTS 2021 regions: 2020 = 100, forward with the new counties' volume change,
    # backward across the reform with the GVA-weighted change of the old counties they were formed from
    regs = sorted(set(NO_2021.values()))
    vol = pd.DataFrame(index=regs, columns=years, dtype=float)
    vol[NO_REFORM_YEAR] = 100.0
    g_new = chg.reindex(list(NO_2021))
    g_new.index = g_new.index.map(NO_2021)
    for y in range(NO_REFORM_YEAR + 1, max(years) + 1):
        vol[y] = vol[y - 1] * (1 + g_new[y].reindex(regs) / 100.0)
    vol[NO_REFORM_YEAR - 1] = vol[NO_REFORM_YEAR] / (1 + g_new[NO_REFORM_YEAR].reindex(regs) / 100.0)
    old_codes = list(NO_2016)
    for y in range(NO_REFORM_YEAR - 1, min(years), -1):
        # growth from y-1 to y in old counties, weighted with nominal GVA in y-1
        g_old = chg[y].reindex(old_codes)
        w_old = gva[y - 1].reindex(old_codes).fillna(0.0)
        ok = g_old.notna() & (w_old > 0)
        t = pd.DataFrame({"g": g_old[ok], "w": w_old[ok]})
        t["n21"] = t.index.map(NO_2016).map(NO_2016_TO_2021)
        g = t.groupby("n21").apply(lambda d: np.average(d["g"], weights=d["w"]), include_groups=False)
        g = g.reindex(regs)
        if g.isna().any():
            avg = float(np.average(t["g"], weights=t["w"]))
            report.fallback("no_volume_change_missing", year=y, regions=g.index[g.isna()].tolist(),
                            used_pct=round(avg, 2), detail="County merger year: average change of all counties used.")
            g = g.fillna(avg)
        vol[y - 1] = vol[y] / (1 + g / 100.0)
    report.note("no_gdp_method", eurostat_calibration_years=have, ratio_last=round(k[last], 4),
                detail="SSB 09391 county value added (basic prices) scaled to Eurostat mainland GDP "
                       "(NO0 - NO0B); volumes chained from SSB county volume change.")
    return RegionalGDP("NO", nom_df, vol, "SSB StatBank 09391 (regional accounts by county), level from Eurostat")


# --- United Kingdom (ONS) -------------------------------------------------------------------------

def uk_code(lad: str) -> str:
    return "UK" + lad


def _ons_gdp_tables(cfg: Config) -> dict[str, pd.DataFrame]:
    path = fetch(cfg.source("ons_gdp_la"), DOWNLOAD_DIR / "ons" / "gdp_la_1998to2024.xlsx")
    out = {}
    for key, sheet in (("nominal", "Table 5"), ("cvm_index", "Table 9")):
        d = pd.read_excel(path, sheet_name=sheet, header=1)
        d = d[d["LA code"].astype(str).str.match(r"^[ENSW]\d{8}$")]
        d = d.set_index(d["LA code"].map(uk_code))
        yrs = [c for c in d.columns if str(c).isdigit()]
        d = d[yrs].apply(pd.to_numeric, errors="coerce")
        d.columns = [int(c) for c in yrs]
        out[key] = d
    return out


def uk_gdp(cfg: Config, report) -> RegionalGDP:
    t = _ons_gdp_tables(cfg)
    return RegionalGDP("UK", t["nominal"], t["cvm_index"],
                       "ONS regional GDP by local authority, 1998-2024 (23 Sep 2026)")


def uk_population_midyear(cfg: Config) -> pd.DataFrame:
    """ONS mid-year estimates by LAD 2023: index = UK+LAD, columns = int years (30 June)."""
    path = fetch(cfg.source("ons_mye_la"), DOWNLOAD_DIR / "ons" / "myeb_2011_2025.xlsx")
    d = pd.read_excel(path, sheet_name="MYEB3", header=1)
    d = d[d["ladcode23"].astype(str).str.match(r"^[ENSW]\d{8}$")].set_index("ladcode23")
    pc = [c for c in d.columns if str(c).startswith("population_")]
    m = d[pc].apply(pd.to_numeric, errors="coerce")
    m.columns = [int(c.split("_")[1]) for c in pc]
    m.index = m.index.map(uk_code)
    return m


def uk_population_total_midyear(cfg: Config) -> pd.Series:
    """UK total from the MYEB5 summary table (independent of the LA rows, for validation)."""
    path = fetch(cfg.source("ons_mye_la"), DOWNLOAD_DIR / "ons" / "myeb_2011_2025.xlsx")
    d = pd.read_excel(path, sheet_name="MYEB5", header=1)
    row = d[d["Code"] == "K02000001"].iloc[0]
    return pd.Series({int(c.split("_")[1]): float(row[c]) for c in d.columns if str(c).startswith("population_")})


def jan1_from_midyear(mid: pd.DataFrame | pd.Series, year: int):
    """Population on 1 January `year` = mean of the mid-year estimates of year-1 and year."""
    return (mid[year - 1] + mid[year]) / 2.0


def uk_population(cfg: Config, years: list[int]) -> pd.DataFrame:
    mid = uk_population_midyear(cfg)
    rows = []
    for y in years:
        if y - 1 not in mid.columns or y not in mid.columns:
            raise RuntimeError(f"ONS mid-year estimates for {y - 1} and {y} are needed for 1 January {y}")
        s = jan1_from_midyear(mid, y)
        rows.append(pd.DataFrame({"geo": s.index, "year": y, "value": s.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


PROVIDERS = {"CH": ch_gdp, "NO": no_gdp, "UK": uk_gdp}


def ppp(cfg: Config) -> pd.DataFrame:
    """Eurostat prc_ppp_ind: NAC per PPS (EU27_2020), GDP level; index = geo, columns = years."""
    d = eurostat.table(cfg, "prc_ppp_ind", "A.PPP_EU27_2020.GDP.")
    return d.pivot_table(index="geo", columns="TIME_PERIOD", values="OBS_VALUE")


def nac_per_eur(cfg: Config) -> pd.DataFrame:
    """Eurostat ert_bil_eur_a annual averages: index = currency, columns = years."""
    d = eurostat.table(cfg, "ert_bil_eur_a")
    d = d[(d["statinfo"] == "AVG") & (d["unit"] == "NAC")]
    return d.pivot_table(index="currency", columns="TIME_PERIOD", values="OBS_VALUE")


__all__ = ["RegionalGDP", "PROVIDERS", "ch_gdp", "no_gdp", "uk_gdp", "uk_population", "uk_code", "ppp",
           "nac_per_eur"]
