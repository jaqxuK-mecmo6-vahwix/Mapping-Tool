"""Cell table and yearly population.

The *cell table* has one row per (1 km cell, country) with the Census 2021 population of that
country's part of the cell (`base`) and the cell's NUTS 3 codes in the 2024, 2021 and 2016 NUTS
versions (from the GISCO grid). Regional statistics are allocated to cells in the NUTS version the
source table uses for that year, so no correspondence approximation is needed: Eurostat back-casts
most series to NUTS 2024, but some early years are still published in older versions.

Every yearly layer is produced by rescaling `base` within each NUTS 3 region so that the region's
cells sum exactly to that year's regional total.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .config import Config
from .sources import eurostat, gisco, national, uk_grid
from .sources.gisco import NUTS_VERSIONS


@dataclass
class CellTable:
    cc: pd.DataFrame                     # x, y, country, base, land, nuts2024, nuts2021, nuts2016
    report: object
    excluded: tuple[str, ...] = ()
    _assign: dict[tuple[str, int], pd.DataFrame] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.cc)

    def assignment(self, country: str, version: int) -> pd.DataFrame:
        """Rows (i = cc row index, region, share) of `country`'s cells in NUTS `version`.
        Cells on a NUTS 3 border are split equally; cells without a code of their own country get the
        code of the nearest cell that has exactly one."""
        key = (country, version)
        if key in self._assign:
            return self._assign[key]
        sub = self.cc[self.cc["country"] == country]
        cand = sub[f"nuts{version}"].str.split("-").apply(lambda l: [s for s in l if s.startswith(country)])
        k = cand.str.len()
        orphan = k == 0
        if orphan.any():
            ref = sub[k == 1]
            if ref.empty:
                raise RuntimeError(f"no NUTS {version} codes at all for {country}")
            _, idx = cKDTree(np.c_[ref["x"], ref["y"]]).query(np.c_[sub.loc[orphan, "x"], sub.loc[orphan, "y"]])
            cand.loc[orphan] = [[v] for v in cand[k == 1].iloc[idx].str[0].to_numpy()]
            self.report.mapping("cell_nuts3_nearest_neighbour", country=country, nuts_version=version,
                                cells=int(orphan.sum()), population_2021=float(sub.loc[orphan, "base"].sum()),
                                detail="Census cell without a NUTS 3 code of its own country in the GISCO grid.")
        a = pd.DataFrame({"i": sub.index.repeat(cand.str.len()), "region": np.concatenate(cand.to_numpy())})
        a["share"] = 1.0 / a.groupby("i")["region"].transform("size")
        if version == 2024:
            split = (k > 1).sum()
            if split:
                self.report.note("cell_split_between_nuts3", country=country, cells=int(split),
                                 population_2021=float(sub.loc[k > 1, "base"].sum()),
                                 detail="Cell on a NUTS 3 border: allocated equally to the regions.")
        self._assign[key] = a
        return a

    def regions(self, country: str, version: int) -> set[str]:
        return set(self.assignment(country, version)["region"])


def build_cell_table(cfg: Config, grid_df: pd.DataFrame, report) -> CellTable:
    excluded = tuple(cfg.raw.get("excluded_nuts_prefixes", []))
    parts = []
    for c in cfg.build_countries:
        if c in cfg.national_grid:
            parts.append(_national_grid_cells(cfg, c, grid_df, report))
            continue
        cen = gisco.load_census_country(cfg, c, report)
        m = cen.merge(grid_df, on=["x", "y"], how="left")
        no_grid = m["land"].isna()
        if no_grid.any():
            report.gap("census_cell_not_in_gisco_grid", country=c, cells=int(no_grid.sum()),
                       population=float(m.loc[no_grid, "pop"].sum()), detail="NUTS code by nearest neighbour.")
        for v in NUTS_VERSIONS:
            m[f"nuts{v}"] = m[f"nuts{v}"].fillna("")
        m["land"] = m["land"].fillna(0).astype(np.float32)
        m["country"] = c
        m = m.rename(columns={"pop": "base"})
        if excluded:
            codes = m["nuts2024"].str.split("-").apply(lambda l: [s for s in l if s.startswith(c)])
            drop = codes.apply(lambda l: bool(l) and all(s.startswith(excluded) for s in l)).to_numpy()
            if drop.any():
                report.note("excluded_regions", country=c, population_2021=float(m.loc[drop, "base"].sum()),
                            prefixes=list(excluded))
                m = m[~drop]
        parts.append(m[["x", "y", "country", "base", "land"] + [f"nuts{v}" for v in NUTS_VERSIONS]])
        report.note("census_base", country=c, cells=len(m), population_2021=float(m["base"].sum()))
    cc = pd.concat(parts, ignore_index=True)
    return CellTable(cc=cc, report=report, excluded=excluded)


def _national_grid_cells(cfg: Config, c: str, grid_df: pd.DataFrame, report) -> pd.DataFrame:
    """Cell rows for a country without a census grid (UK): one row per (cell, local authority);
    the region code is written into every NUTS-version column, so allocation is version-independent."""
    if c != "UK":
        raise NotImplementedError(f"no national grid source for {c}")
    u = uk_grid.uk_cells(cfg, report)
    m = u.merge(grid_df[["x", "y", "land"]], on=["x", "y"], how="left")
    no_grid = m["land"].isna()
    if no_grid.any():
        report.gap("national_cell_not_in_gisco_grid", country=c, cells=int(no_grid.sum()),
                   population=float(m.loc[no_grid, "pop"].sum()), detail="Kept with land share 0.")
    m["land"] = m["land"].fillna(0).astype(np.float32)
    out = pd.DataFrame({"x": m["x"], "y": m["y"], "country": c, "base": m["pop"].astype(np.float64),
                        "land": m["land"]})
    for v in NUTS_VERSIONS:
        out[f"nuts{v}"] = m["lad"].to_numpy()
    report.note("national_base", country=c, rows=len(out), population_2021=float(out["base"].sum()),
                source="WorldPop 2021 constrained 100 m, by ONS LAD 2023")
    return out


def choose_version(ct: CellTable, country: str, codes: set[str]) -> tuple[int, set[str]]:
    """NUTS version to allocate a source table with: the newest version whose regions are ALL in the
    table; otherwise the version with the most matching regions. (Eurostat sometimes publishes a
    year under several NUTS versions at once, so extra codes are expected and ignored.)"""
    for v in NUTS_VERSIONS:
        regs = ct.regions(country, v)
        if regs <= codes:
            return v, regs
    best = max(NUTS_VERSIONS, key=lambda v: len(codes & ct.regions(country, v)))
    return best, ct.regions(country, best)


def allocate(ct: CellTable, totals: pd.Series, weights: np.ndarray, *, what: str, year: int, report,
             countries: list[str] | None = None, detail: list | None = None) -> np.ndarray:
    """Allocate regional `totals` (index = NUTS 3 codes, any version) to the cell table rows in
    proportion to `weights` (aligned with ct.cc). Returns values aligned with ct.cc.
    If `detail` is a list, per-(row, region) allocations are appended to it (for validation)."""
    out = np.zeros(len(ct.cc), dtype=np.float64)
    w_all = np.asarray(weights, dtype=np.float64)
    for c in countries or sorted(ct.cc["country"].unique()):
        t = totals[totals.index.str[:2] == c]
        if ct.excluded:
            t = t[~t.index.str.startswith(ct.excluded)]   # deliberately unmapped regions (see config)
        if t.empty:
            report.gap(f"{what}_country_missing", year=year, country=c)
            continue
        v, regs = choose_version(ct, c, set(t.index))
        if v != NUTS_VERSIONS[0]:
            report.mapping(f"{what}_nuts_version", year=year, country=c, nuts_version=v,
                           detail=f"Source uses NUTS {v} codes for this year; allocated with the grid's NUTS {v} cell codes.")
        other_versions = set().union(*(ct.regions(c, ov) for ov in NUTS_VERSIONS if ov != v))
        extra = sorted(set(t.index) - regs)
        dup = [r for r in extra if r in other_versions]
        if dup:
            report.note(f"{what}_other_version_codes_ignored", year=year, country=c, nuts_version=v, regions=dup)
        complete = regs <= set(t.index)
        for r in extra:
            if r in other_versions:
                continue
            val = float(t[r])
            if complete or not (val > 0) or r.endswith("XXX"):
                # the chosen version is complete, so this is an older-NUTS duplicate, an empty region
                # (e.g. Svalbard) or "not regionalised": nothing is lost
                report.note(f"{what}_extra_code_ignored", year=year, region=r, nuts_version=v, value=val)
            else:
                report.gap(f"{what}_region_without_cells", year=year, region=r, nuts_version=v, value=val)
        t = t[t.index.isin(regs)]
        for r in sorted(regs - set(t.index)):
            report.gap(f"{what}_region_missing_in_source", year=year, region=r, nuts_version=v,
                       detail="Cells of this region get 0 for this year.")
        a = ct.assignment(c, v)
        i = a["i"].to_numpy()
        w = w_all[i] * a["share"].to_numpy()
        reg = a["region"].to_numpy()
        wsum = pd.Series(w).groupby(reg).transform("sum").to_numpy()
        tot = pd.Series(reg).map(t).fillna(0).to_numpy(dtype=np.float64)
        val = np.zeros(len(a))
        ok = wsum > 0
        val[ok] = tot[ok] * w[ok] / wsum[ok]
        zero_w = (~ok) & (tot > 0)
        if zero_w.any():
            fw = ct.cc["land"].to_numpy(dtype=np.float64)[i] * a["share"].to_numpy() + 1e-9
            fws = pd.Series(np.where(zero_w, fw, 0.0)).groupby(reg).transform("sum").to_numpy()
            val[zero_w] = tot[zero_w] * fw[zero_w] / fws[zero_w]
            report.fallback(f"{what}_region_without_weight", year=year, regions=sorted(set(reg[zero_w])),
                            detail="Spread by land area instead.")
        np.add.at(out, i, val)
        if detail is not None:
            detail.append(pd.DataFrame({"i": i, "region": reg, "value": val, "nuts_version": v}))
    return out


def regional_population(cfg: Config, years: list[int] | None = None) -> pd.DataFrame:
    """Population on 1 January by region: Eurostat NUTS 3 (any NUTS version) and, for countries with a
    national source, that source (UK: ONS by local authority). Columns geo, year, value."""
    es = [c for c in cfg.build_countries if c not in cfg.national_population]
    df = eurostat.table(cfg, "demo_r_pjanaggr3", "A.NR.T.TOTAL.")
    df = eurostat.nuts3(df, es)
    parts = [df.rename(columns={"TIME_PERIOD": "year", "OBS_VALUE": "value"})[["geo", "year", "value"]].dropna()]
    if "UK" in cfg.national_population:
        ys = sorted(set(years or (cfg.pop_years + cfg.gdp_years)))
        parts.append(national.uk_population(cfg, ys))
    return pd.concat(parts, ignore_index=True)


def complete_for(ct: CellTable, country: str, codes: set[str]) -> bool:
    """True if the table covers every region of `country` in at least one NUTS version."""
    return any(ct.regions(country, v) <= codes for v in NUTS_VERSIONS)


def yearly_population(cfg: Config, ct: CellTable, years: list[int], report,
                      details: dict[int, list] | None = None,
                      weight_only: set[int] | None = None) -> dict[int, np.ndarray]:
    """Allocate each year's regional population to cells. For `weight_only` years (used only as GDP
    weights, never published) a country whose table is incomplete in that year uses the nearest complete
    year instead (e.g. Germany has no NUTS 3 population on 1 January 2013); the within-region
    distribution barely changes in a year, and only relative weights matter for GDP."""
    reg = regional_population(cfg, years)
    weight_only = weight_only or set()
    countries = sorted(ct.cc["country"].unique())
    by_year = {y: g.set_index("geo")["value"] for y, g in reg.groupby("year")}
    out = {}
    for y in sorted(set(years)):
        t = by_year.get(y, pd.Series(dtype=float))
        if t.empty:
            raise RuntimeError(f"No regional population for {y}")
        d = details.setdefault(y, []) if details is not None else None
        if y not in weight_only:
            out[y] = allocate(ct, t, ct.cc["base"].to_numpy(), what="population", year=y, report=report, detail=d)
            continue
        acc = np.zeros(len(ct.cc))
        for c in countries:
            use = y
            for dy in (0, 1, -1, 2, -2, 3, -3):
                tc = by_year.get(y + dy, pd.Series(dtype=float))
                tc = tc[tc.index.str[:2] == c]
                if not tc.empty and complete_for(ct, c, set(tc.index)):
                    use = y + dy
                    break
            if use != y:
                report.fallback("population_weight_year", country=c, year=y, used_year=use,
                                detail="Regional population incomplete for this year; GDP weights use the nearest complete year.")
            tc = by_year[use]
            acc += allocate(ct, tc[tc.index.str[:2] == c], ct.cc["base"].to_numpy(), what="population_weight",
                            year=use, report=report, countries=[c])
        out[y] = acc
    return out


def series_breaks(cfg: Config, report) -> dict[str, list[int]]:
    """Years in which Eurostat flags a break in series ('b') for a country's population (any NUTS 3 row
    or the country row), within the span of the configured years. Growth across such a year partly
    reflects a revision (e.g. a census rebasing), not change; the app warns about it."""
    df = eurostat.table(cfg, "demo_r_pjanaggr3", "A.NR.T.TOTAL.")
    years = cfg.pop_years
    lo, hi = min(years), max(years)
    es = [c for c in cfg.build_countries if c not in cfg.national_population]
    m = (df["OBS_FLAG"].fillna("").str.contains("b") & df["geo"].str[:2].isin(es)
         & df["TIME_PERIOD"].between(lo + 1, hi) & df["geo"].str.len().isin([2, 5]))
    out: dict[str, list[int]] = {}
    for (c, y), g in df[m].groupby([df["geo"].str[:2], "TIME_PERIOD"]):
        out.setdefault(c, []).append(int(y))
        report.note("population_series_break", country=c, year=int(y), rows_flagged=len(g),
                    detail="Eurostat flag 'b' (break in time series).")
    return {c: sorted(v) for c, v in sorted(out.items())}
