"""Validation of a finished build (`radiusstats-validate`).

1. Region check: allocations per region reproduce the source table within 0.1 %
   (source tables are re-read from the cached downloads, independently of the build's allocation).
2. Raster check: every 1 km COG cell equals the sum of the cell-table allocations in it.
3. Pyramid check: every level of every data layer has the same total as level 1.
4. Country check: per-country totals read from the COGs (via the country raster) match national
   figures within 1 %: Eurostat national population (demo_r_pjanaggr3 at country level) and national
   accounts (nama_10_gdp, minus extra-regio GDP) for nominal EUR and PPS; UK population against the
   ONS UK total. Real GDP growth is compared with national chain-linked volumes (threshold 0.3 pp p.a.)
   where national GDP is the sum of the mapped regions (not NO: offshore; not UK: no Eurostat series).
Writes data/build/validation_report.json and exits non-zero if a check fails.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from . import cog, gdp
from .config import WORK_DIR, load_config
from .population import regional_population
from .report import Report
from .sources import eurostat, national

REGION_TOL = 0.001
COUNTRY_TOL = 0.01
REAL_GROWTH_TOL_PP = 0.3


def cagr(v_end: float, v_start: float, n: int) -> float:
    return (v_end / v_start) ** (1.0 / n) - 1.0


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    out = cfg.output_dir
    manifest = json.loads((out / "manifest.json").read_text())
    rep = Report()
    cells = pd.read_parquet(WORK_DIR / "cells.parquet")
    built = [c["code"] for c in manifest["countries"] if c["built"]]

    # --- sources, re-read ---------------------------------------------------------------------------
    pop_src = eurostat.table(cfg, "demo_r_pjanaggr3", "A.NR.T.TOTAL.")
    pop_reg = regional_population(cfg)
    gdp_src = eurostat.table(cfg, "nama_10r_3gdp")
    real_src = pd.read_parquet(WORK_DIR / "real_gdp_nuts3.parquet")  # derived (volume method), see report
    nat = eurostat.table(cfg, "nama_10_gdp", "A.CP_MEUR+CP_MPPS_EU27_2020+CLV20_MEUR.B1GQ.")
    nat_mnac = eurostat.table(cfg, "nama_10_gdp", "A.CP_MNAC.B1GQ.CH")
    ppp = national.ppp(cfg)

    def source_regions(layer: dict, regions: pd.Index) -> pd.Series:
        y = layer["year"]
        if layer["kind"] == "population":
            s = pop_reg[pop_reg["year"] == y].drop_duplicates("geo").set_index("geo")["value"]
        elif layer["measure"] == "real":
            s = real_src[str(y)]
        else:
            s = gdp.nominal(cfg, y, layer["source_unit"])
        return s[~s.index.duplicated()].reindex(regions)

    country_raster = cog.read_level(out, manifest["layers"]["country"]["levels"]["1"]).astype(np.int32)
    id_to_code = {c["id"]: c["code"] for c in manifest["countries"]}
    per_country: dict[str, dict[str, float]] = {}

    for lid, layer in manifest["layers"].items():
        if layer["kind"] not in ("population", "gdp"):
            continue
        alloc = pd.read_parquet(WORK_DIR / "alloc" / f"{lid}.parquet")

        # 1. regions
        got = alloc.groupby("region")["value"].sum()
        src = source_regions(layer, got.index)
        rel = ((got - src).abs() / src.abs().clip(lower=1e-9))
        worst = rel.max()
        rep.check(f"regions_within_0.1pct:{lid}", bool(worst <= REGION_TOL) and not src.isna().any(),
                  regions=len(got), worst_region=str(rel.idxmax()), worst_rel_diff=float(worst),
                  missing_in_source=int(src.isna().sum()))

        # 2. raster == cell table
        arr = cog.read_level(out, layer["levels"]["1"]).astype(np.float64)
        nd = manifest["nodata"]
        per_row = alloc.groupby("i")["value"].sum().reindex(cells.index, fill_value=0).to_numpy()
        expect = np.zeros_like(arr)
        np.add.at(expect, (cells["row"].to_numpy(), cells["col"].to_numpy()), per_row)
        a = np.where(arr == nd, 0, arr)
        diff = np.abs(a - expect)
        # data layers keep 12 mantissa bits (config raster.mantissa_bits): <= 1.2e-4 relative per cell
        tol = 2.0 ** -(int(cfg.raw["raster"].get("mantissa_bits", 23)) + 1)
        ok = bool(np.all(diff <= (tol + 1e-6) * np.abs(expect) + 1e-3))
        rep.check(f"raster_equals_cells:{lid}", ok, max_abs_diff=float(diff.max()))

        # 3. pyramid totals
        t1 = a.sum()
        worst_lv = 0.0
        for lv, f in layer["levels"].items():
            b = cog.read_level(out, f).astype(np.float64)
            worst_lv = max(worst_lv, abs(np.where(b == nd, 0, b).sum() - t1) / max(abs(t1), 1e-9))
        # each level is rounded to 12 mantissa bits on its own; few, large coarse cells -> up to ~5e-6
        pyr_tol = 1e-6 if int(cfg.raw["raster"].get("mantissa_bits", 23)) >= 23 else 2e-5
        rep.check(f"pyramid_totals:{lid}", worst_lv < pyr_tol, levels=len(layer["levels"]), max_rel_diff=worst_lv,
                  tolerance=pyr_tol)

        # per-country totals from the raster
        per_country[lid] = {}
        for cid in np.unique(country_raster):
            code = id_to_code.get(int(cid))
            if code in built:
                per_country[lid][code] = float(a[country_raster == cid].sum())

    # 4. country totals vs national figures
    zzz = gdp_src[gdp_src["geo"].str.endswith("ZZZ") & (gdp_src["geo"].str.len() == 5)]
    uk_mid = national.uk_population_total_midyear(cfg) if "UK" in built else None

    excl = tuple(cfg.raw.get("excluded_nuts_prefixes", []))

    def excluded_total(c: str, y: int, layer: dict) -> float:
        """Regions deliberately not mapped (e.g. French outermost regions) are in national totals."""
        if not excl:
            return 0.0
        if layer["kind"] == "population":
            t = pop_src[(pop_src["TIME_PERIOD"] == y) & (pop_src["geo"].str.len() == 5)]
        else:
            t = gdp_src[(gdp_src["TIME_PERIOD"] == y) & (gdp_src["unit"] == layer["source_unit"])
                        & (gdp_src["geo"].str.len() == 5)]
        t = t[t["geo"].str.startswith(excl) & (t["geo"].str[:2] == c)].drop_duplicates("geo")
        return float(t["OBS_VALUE"].sum())

    def extra_regio(c: str, y: int, unit: str) -> float:
        z = zzz[(zzz["geo"].str[:2] == c) & (zzz["TIME_PERIOD"] == y) & (zzz["unit"] == unit)]["OBS_VALUE"]
        return float(z.iloc[0]) if len(z) and pd.notna(z.iloc[0]) else 0.0

    # PPS has no layer: country EUR x the manifest's national factor
    G = manifest["years"]["gdp"]["latest"]
    f = manifest["pps_per_eur"]["factors"]
    per_country["gdp_pps (derived)"] = {c: v * f.get(c, float("nan")) for c, v in per_country[f"gdp_nom_eur_{G}"].items()}
    country_layers = {**manifest["layers"], "gdp_pps (derived)": {"kind": "gdp", "measure": "pps", "year": G,
                                                                  "source_unit": "MIO_PPS_EU27_2020"}}
    for c in built:
        for lid, layer in country_layers.items():
            if lid not in per_country:
                continue
            y, v = layer["year"], per_country[lid].get(c, 0.0)
            if layer["kind"] == "population":
                if c == "UK":
                    ref = pd.Series([national.jan1_from_midyear(uk_mid, y)])
                    label = "ONS MYEB5 UK total, mean of mid-years"
                else:
                    ref = pop_src[(pop_src["geo"] == c) & (pop_src["TIME_PERIOD"] == y)]["OBS_VALUE"]
                    label = "demo_r_pjanaggr3 (country)"
            elif layer["measure"] in ("nominal", "pps"):
                unit = "CP_MEUR" if layer["measure"] == "nominal" else "CP_MPPS_EU27_2020"
                nat_ref = nat[(nat["geo"] == c) & (nat["TIME_PERIOD"] == y) & (nat["unit"] == unit)]["OBS_VALUE"]
                if c in ("UK", "NO"):
                    src = gdp.nominal(cfg, y, layer["source_unit"])
                    ref = pd.Series([float(src[src.index.str[:2] == c].sum())])
                    label = f"{c} national source, sum of regions (no Eurostat total excluding offshore/extra-regio)"
                elif c == "CH":
                    if layer["measure"] == "nominal":
                        ref, label = nat_ref, "nama_10_gdp CP_MEUR"
                    else:
                        mnac = nat_mnac[nat_mnac["TIME_PERIOD"] == y]["OBS_VALUE"]
                        ref = mnac / ppp.loc["CH", y]
                        label = "nama_10_gdp CP_MNAC / prc_ppp_ind PPP"
                else:
                    # same release as the regional data: the country row of nama_10r_3gdp
                    reg = gdp_src[(gdp_src["geo"] == c) & (gdp_src["TIME_PERIOD"] == y)
                                  & (gdp_src["unit"] == layer["source_unit"])]["OBS_VALUE"]
                    ref = reg - extra_regio(c, y, layer["source_unit"])
                    label = f"nama_10r_3gdp country total {layer['source_unit']} minus extra-regio"
                    if len(nat_ref) and len(ref) and pd.notna(ref.iloc[0]):
                        rep.note("national_accounts_vintage", country=c, layer=lid, regional_table=float(reg.iloc[0]),
                                 nama_10_gdp=float(nat_ref.iloc[0]),
                                 rel_diff=round(float(reg.iloc[0]) / float(nat_ref.iloc[0]) - 1, 5),
                                 detail="Regional accounts are not yet revised to the latest national accounts.")
            else:
                continue
            if ref.empty or pd.isna(ref.iloc[0]):
                rep.check(f"country_total:{c}:{lid}", False, detail=f"no reference in {label}")
                continue
            r = float(ref.iloc[0])
            ex = excluded_total(c, y, layer)
            if ex:
                r -= ex
                label += f" minus unmapped regions {list(excl)} ({ex:,.0f})"
            rep.check(f"country_total_within_1pct:{c}:{lid}", abs(v - r) / r <= COUNTRY_TOL,
                      grid=round(v, 1), reference=r, rel_diff=round((v - r) / r, 5), source=label)

        # real growth vs national chain-linked volumes
        if c in ("UK", "NO"):
            continue
        gy = manifest["years"]["gdp"]
        latest = gy["latest"]
        clv = nat[(nat["geo"] == c) & (nat["unit"] == "CLV20_MEUR")].set_index("TIME_PERIOD")["OBS_VALUE"]
        for y0 in gy["compare"]:
            n = latest - y0
            g_grid = cagr(per_country[f"gdp_real_{latest}"][c], per_country[f"gdp_real_{y0}"][c], n)
            g_nat = cagr(clv[latest], clv[y0], n)
            pp = 100 * (g_grid - g_nat)
            rep.check(f"real_growth_vs_national:{c}:{y0}-{latest}", abs(pp) <= REAL_GROWTH_TOL_PP,
                      grid_pct_pa=round(100 * g_grid, 3), national_pct_pa=round(100 * g_nat, 3), diff_pp=round(pp, 3))

    rep.write(out / "validation_report.json", extra={"countries": built})
    failed = [c for c in rep.checks if not c["ok"]]
    print(f"\n{len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
