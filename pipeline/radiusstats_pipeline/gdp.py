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
from .sources import eurostat, national


def _gdp3(cfg: Config) -> pd.DataFrame:
    df = eurostat.table(cfg, "nama_10r_3gdp")
    return df.rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": "value"})


def eurostat_countries(cfg: Config) -> list[str]:
    """Built countries whose regional GDP comes from Eurostat (the rest use national sources)."""
    return [c for c in cfg.build_countries if c not in cfg.national_gdp]


_providers_cache: dict[tuple[int, str], national.RegionalGDP] = {}


def providers(cfg: Config, report=None) -> dict[str, national.RegionalGDP]:
    out = {}
    for c in cfg.build_countries:
        if c in cfg.national_gdp:
            key = (id(cfg), c)
            if key not in _providers_cache:
                _providers_cache[key] = national.PROVIDERS[c](cfg, report or _NullReport())
            out[c] = _providers_cache[key]
    return out


class _NullReport:
    def __getattr__(self, name):
        return lambda *a, **k: None


def convert_nac(cfg: Config, country: str, nac: pd.Series, year: int, unit: str) -> pd.Series:
    """Million NAC -> `unit` (MIO_NAC, MIO_EUR at the annual average rate, MIO_PPS_EU27_2020 via PPP)."""
    if unit == "MIO_NAC":
        return nac
    if unit == "MIO_EUR":
        if country in cfg.euro_area:
            return nac
        return nac / national.nac_per_eur(cfg).loc[cfg.currency(country), year]
    if unit == "MIO_PPS_EU27_2020":
        return nac / national.ppp(cfg).loc[country, year]
    raise ValueError(unit)


def nominal(cfg: Config, year: int, unit: str, report=None) -> pd.Series:
    """NUTS 3 GDP at current prices for `year` in `unit` (MIO_EUR, MIO_PPS_EU27_2020, MIO_NAC)."""
    df = eurostat.nuts3(_gdp3(cfg), eurostat_countries(cfg))
    parts = [df[(df["unit"] == unit) & (df["year"] == year)].set_index("geo")["value"].dropna()]
    for c, p in providers(cfg, report).items():
        if year not in p.nac.columns:
            if report is not None:
                report.gap("national_gdp_year_missing", country=c, year=year, source=p.source)
            continue
        parts.append(convert_nac(cfg, c, p.nac[year].dropna(), year, unit))
    return pd.concat(parts)


def pps_per_eur(cfg: Config, year: int, report) -> dict[str, float]:
    """Per country: PPS (EU27_2020) per EUR of GDP in `year`. Checks that the ratio is the same in every
    region of a country (it is: Eurostat applies national PPPs), so circle PPS = sum of country EUR x factor."""
    eur = nominal(cfg, year, "MIO_EUR")
    pps = nominal(cfg, year, "MIO_PPS_EU27_2020")
    eur, pps = eur[~eur.index.duplicated()], pps[~pps.index.duplicated()]
    r = (pps / eur).dropna()
    out = {}
    for c, g in r.groupby(r.index.str[:2]):
        spread = float(g.max() / g.min() - 1)
        report.check(f"pps_ratio_constant_within_country:{c}", spread < 1e-3, spread=spread)
        out[c] = float(pps[pps.index.str[:2] == c].sum() / eur[eur.index.str[:2] == c].sum())
    return out


def extra_regio(cfg: Config, year: int, unit: str = "MIO_EUR") -> pd.Series:
    df = _gdp3(cfg)
    m = df["geo"].str.endswith("ZZZ") & df["geo"].str[:2].isin(eurostat_countries(cfg)) & (df["geo"].str.len() == 5)
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
        out = out[(out["geo"].str.len() == 5) & out["geo"].str[:2].isin(eurostat_countries(cfg))]
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
    g3 = eurostat.nuts3(_gdp3(cfg), eurostat_countries(cfg))
    nac = g3[g3["unit"] == "MIO_NAC"][["geo", "year", "value"]].dropna()
    nac["n2"] = nac["geo"].str[:4]
    n2_nom = nac.groupby(["n2", "year"])["value"].sum()

    vol = eurostat.table(cfg, "nama_10r_2gvagr")
    vol = vol[(vol["na_item"] == "B1GQ") & (vol["unit"] == "I20") & (vol["geo"].str.len() == 4)
              & vol["geo"].str[:2].isin(eurostat_countries(cfg))]
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
    out = out[["geo", "year", "value"]].dropna()

    # NUTS 3 nominal suppressed in a year (e.g. IE062/IE063 in 2018): move the region with its NUTS 2
    # volume index from the nearest year where it is known
    known = out.set_index(["geo", "year"])["value"]
    years_of = out.groupby("geo")["year"].apply(set).to_dict()
    add = []
    for geo, have_y in years_of.items():
        for y in years:
            if y in have_y:
                continue
            n2 = geo[:4]
            yrs = sorted(have_y, key=lambda yy: abs(yy - y))
            yrs = [yy for yy in yrs if (n2, yy) in idx.index and (n2, y) in idx.index]
            if not yrs:
                continue
            y0 = yrs[0]
            add.append({"geo": geo, "year": y, "value": known[(geo, y0)] * idx[(n2, y)] / idx[(n2, y0)]})
            report.fallback("nuts3_nominal_missing_volume_from_nuts2", region=geo, year=y, from_year=y0,
                            detail="Regional nominal GDP suppressed; NUTS 2 volume growth used.")
    if add:
        out = pd.concat([out, pd.DataFrame(add)], ignore_index=True)
    return out


def benchmark_to_national(cfg: Config, real: pd.DataFrame, countries: list[str], report) -> pd.DataFrame:
    """Scale each country's regional real GDP per year so that its growth since the base year equals the
    latest national chain-linked volumes (nama_10_gdp CLV20_MEUR). Regional volume tables lag national
    revisions (e.g. CY, MT: one NUTS 2 region, yet up to 1 pp p.a. apart); ARDECO does the same."""
    B = cfg.real_base_year
    nat = eurostat.table(cfg, "nama_10_gdp", "A.CP_MEUR+CP_MPPS_EU27_2020+CLV20_MEUR.B1GQ.")
    clv = nat[nat["unit"] == "CLV20_MEUR"].pivot_table(index="geo", columns="TIME_PERIOD", values="OBS_VALUE")
    out = real.copy()
    for c in countries:
        rows = out.index.str[:2] == c
        if c not in clv.index or not rows.any():
            report.gap("benchmark_national_clv_missing", country=c)
            continue
        f = {}
        for y in cfg.gdp_years:
            if y == B:
                continue
            reg_growth = out.loc[rows, y].sum() / out.loc[rows, B].sum()
            nat_growth = clv.loc[c, y] / clv.loc[c, B]
            f[y] = nat_growth / reg_growth
            out.loc[rows, y] *= f[y]
        report.note("real_gdp_benchmarked", country=c, factors={str(k): round(float(v), 5) for k, v in f.items()})
    return out


def real(cfg: Config, report) -> pd.DataFrame:
    """Real GDP by NUTS 3 for cfg.gdp_years: DataFrame index=geo, columns=years, mio EUR at base-year
    prices and base-year exchange rates."""
    B = cfg.real_base_year
    years = sorted(set(cfg.gdp_years) | {B})
    v = _ardeco_volume(cfg, report)
    if v is None:
        v = _nuts2_deflator_volume(cfg, years, report)
    V = v.pivot_table(index="geo", columns="year", values="value")

    es = eurostat.nuts3(_gdp3(cfg), eurostat_countries(cfg))
    nac_B = es[(es["unit"] == "MIO_NAC") & (es["year"] == B)].set_index("geo")["value"].dropna()
    eur_B = es[(es["unit"] == "MIO_EUR") & (es["year"] == B)].set_index("geo")["value"].dropna()
    # EUR per unit of national currency in year B, per country (= Eurostat's own annual average rate)
    c = eur_B.index.str[:2]
    eur_per_nac = (eur_B.groupby(c).sum() / nac_B.groupby(nac_B.index.str[:2]).sum())

    out = pd.DataFrame(index=V.index)
    for y in cfg.gdp_years:
        if y not in V.columns or B not in V.columns:
            raise RuntimeError(f"volume index missing for year {y} or base {B}")
        rate = pd.Series(V.index.str[:2], index=V.index).map(eur_per_nac)
        out[y] = nac_B.reindex(V.index) * V[y] / V[B] * rate
    out = benchmark_to_national(cfg, out, eurostat_countries(cfg), report)

    # national sources: base-year nominal x own volume index, at the base-year exchange rate
    for c, p in providers(cfg, report).items():
        if B not in p.nac.columns or B not in p.volume.columns:
            raise RuntimeError(f"{c}: base year {B} missing in {p.source}")
        base = p.nac[B].dropna()
        vol = p.volume.reindex(base.index)
        eur = 1.0 if c in cfg.euro_area else 1.0 / national.nac_per_eur(cfg).loc[cfg.currency(c), B]
        part = pd.DataFrame(index=base.index)
        for y in cfg.gdp_years:
            if y not in vol.columns:
                raise RuntimeError(f"{c}: volume index for {y} missing in {p.source}")
            part[y] = base * vol[y] / vol[B] * eur
        out = pd.concat([out, part])
        report.note("real_gdp_source", country=c, source=p.source)
    bad = out.isna().any(axis=1)
    if bad.any():
        report.gap("real_gdp_incomplete", regions=sorted(out.index[bad].tolist()))
    return out
