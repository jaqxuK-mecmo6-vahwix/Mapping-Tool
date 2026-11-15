"""Validation of a finished build (`radiusstats-validate`).

1. Region check: allocations per NUTS 3 region reproduce the source table within 0.1 %
   (source tables are re-read independently of the build code path).
2. Raster check: every 1 km COG cell equals the sum of the cell-table allocations in it.
3. Pyramid check: every level of every data layer has the same total as level 1.
4. Country check: per-country totals read from the COGs (via the country raster) match national
   figures within 1 %: Eurostat national population (demo_r_pjanaggr3 at country level) and national
   accounts (nama_10_gdp) for nominal EUR and PPS. Real GDP growth is compared with national
   chain-linked volumes (reported, threshold 0.3 pp p.a.).
Writes data/build/validation_report.json and exits non-zero if a check fails.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from . import cog
from .config import WORK_DIR, load_config
from .report import Report
from .sources import eurostat

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
    gdp_src = eurostat.table(cfg, "nama_10r_3gdp")
    real_src = pd.read_parquet(WORK_DIR / "real_gdp_nuts3.parquet")  # derived (volume method), see report
    nat = eurostat.table(cfg, "nama_10_gdp", "A.CP_MEUR+CP_MPPS_EU27_2020+CLV20_MEUR.B1GQ.")

    def source_regions(layer: dict, regions: pd.Index) -> pd.Series:
        y = layer["year"]
        if layer["kind"] == "population":
            s = pop_src[pop_src["TIME_PERIOD"] == y].set_index("geo")["OBS_VALUE"]
        elif layer["measure"] == "real":
            s = real_src[str(y)]
        else:
            g = gdp_src[(gdp_src["TIME_PERIOD"] == y) & (gdp_src["unit"] == layer["source_unit"])]
            s = g.set_index("geo")["OBS_VALUE"]
        return s.reindex(regions)

    country_raster = cog.read(out / manifest["layers"]["country"]["levels"]["1"]["url"])
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
        arr = cog.read(out / layer["levels"]["1"]["url"]).astype(np.float64)
        nd = manifest["nodata"]
        per_row = alloc.groupby("i")["value"].sum().reindex(cells.index, fill_value=0).to_numpy()
        expect = np.zeros_like(arr)
        np.add.at(expect, (cells["row"].to_numpy(), cells["col"].to_numpy()), per_row)
        a = np.where(arr == nd, 0, arr)
        diff = np.abs(a - expect)
        ok = bool(np.all(diff <= 1e-6 * np.maximum(1.0, np.abs(expect)) + 1e-3))
        rep.check(f"raster_equals_cells:{lid}", ok, max_abs_diff=float(diff.max()))

        # 3. pyramid totals
        t1 = a.sum()
        worst_lv = 0.0
        for lv, f in layer["levels"].items():
            b = cog.read(out / f["url"]).astype(np.float64)
            worst_lv = max(worst_lv, abs(np.where(b == nd, 0, b).sum() - t1) / max(abs(t1), 1e-9))
        rep.check(f"pyramid_totals:{lid}", worst_lv < 1e-6, levels=len(layer["levels"]), max_rel_diff=worst_lv)

        # per-country totals from the raster
        per_country[lid] = {}
        for cid in np.unique(country_raster):
            code = id_to_code.get(int(cid))
            if code in built:
                per_country[lid][code] = float(a[country_raster == cid].sum())

    # 4. country totals vs national figures
    for c in built:
        for lid, layer in manifest["layers"].items():
            if lid not in per_country:
                continue
            y, v = layer["year"], per_country[lid].get(c, 0.0)
            if layer["kind"] == "population":
                ref = pop_src[(pop_src["geo"] == c) & (pop_src["TIME_PERIOD"] == y)]["OBS_VALUE"]
                label = "demo_r_pjanaggr3 (country)"
            elif layer["measure"] == "nominal":
                ref = nat[(nat["geo"] == c) & (nat["TIME_PERIOD"] == y) & (nat["unit"] == "CP_MEUR")]["OBS_VALUE"]
                label = "nama_10_gdp CP_MEUR"
            elif layer["measure"] == "pps":
                ref = nat[(nat["geo"] == c) & (nat["TIME_PERIOD"] == y) & (nat["unit"] == "CP_MPPS_EU27_2020")]["OBS_VALUE"]
                label = "nama_10_gdp CP_MPPS_EU27_2020"
            else:
                continue
            if ref.empty or pd.isna(ref.iloc[0]):
                rep.check(f"country_total:{c}:{lid}", False, detail=f"no reference in {label}")
                continue
            r = float(ref.iloc[0])
            rep.check(f"country_total_within_1pct:{c}:{lid}", abs(v - r) / r <= COUNTRY_TOL,
                      grid=round(v, 1), reference=r, rel_diff=round((v - r) / r, 5), source=label)

        # real growth vs national chain-linked volumes
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
