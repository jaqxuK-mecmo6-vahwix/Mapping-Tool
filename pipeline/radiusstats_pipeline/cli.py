"""One command: `radiusstats-build`. Downloads are cached; outputs are rewritten atomically."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import cog, gdp, pyramid
from .config import WORK_DIR, Config, load_config
from .fetch import download_index
from .coverage import build_mask
from .fx import build_fx
from .heat import build_pmtiles
from .grid import GridSpec, extent_for
from .population import CellTable, allocate, build_cell_table, series_breaks, yearly_population
from .report import Report
from .sources import eurostat, gisco

SEA, NOT_COVERED = 0, 255


def country_and_land(cfg: Config, grid: GridSpec, grid_df: pd.DataFrame, cells: pd.DataFrame,
                     row: np.ndarray, col: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """uint8 country raster (0 sea, 255 land outside the built coverage) and float32 land share."""
    shape = grid.shape(1)
    ids = cfg.country_ids
    r, c, inside = grid.index(grid_df["x"].to_numpy(), grid_df["y"].to_numpy())
    g = grid_df[inside]
    r, c = r[inside], c[inside]

    land = np.zeros(shape, np.float32)
    land[r, c] = g["land"].to_numpy()

    country = np.zeros(shape, np.uint8)
    # land with a GISCO country code: first built country in CNTR_ID, else "not covered"
    built = set(cfg.build_countries)
    first_built = g["cntr"].str.split("-").apply(lambda l: next((x for x in l if x in built), None))
    is_land = (g["land"].to_numpy() > 0) | first_built.notna().to_numpy()
    code = first_built.map(ids).fillna(NOT_COVERED).astype(np.uint8).to_numpy()
    country[r[is_land], c[is_land]] = code[is_land]

    # cells with census population: country with the largest census population in the cell wins
    cc = cells.assign(_r=row, _c=col).groupby(["_r", "_c", "country"], as_index=False)["base"].sum()
    cc = cc.sort_values("base", ascending=False).drop_duplicates(["_r", "_c"])
    country[cc["_r"].to_numpy(), cc["_c"].to_numpy()] = cc["country"].map(ids).to_numpy().astype(np.uint8)
    return country, land


def rasterise(shape, row, col, values, covered: np.ndarray, nodata: float) -> np.ndarray:
    acc = np.zeros(shape, np.float64)
    np.add.at(acc, (row, col), values)
    out = acc.astype(np.float32)
    out[~covered & (acc == 0)] = nodata
    return out


def write_layer(cfg: Config, stack: cog.LevelStack, layer_id: str, arr: np.ndarray, kind: str,
                report: Report, land: np.ndarray | None = None) -> dict:
    """Build the pyramid of one layer and write every level into its band of the level stack.
    Returns the manifest `levels` entry (url and size are filled in when the stack is finished)."""
    levels = cfg.levels
    pyr = pyramid.build(arr, levels, kind, nodata=cfg.nodata, land=land)
    bits = int(cfg.raw["raster"].get("mantissa_bits", 23))
    band = stack.band_of(layer_id)
    files = {}
    for lv, a in pyr.items():
        if kind == "sum":
            a = pyramid.keep_mantissa_bits(a, bits, cfg.nodata)
        stack.write(layer_id, lv, a)
        files[str(lv)] = {"band": band, "width": a.shape[1], "height": a.shape[0]}
    if kind == "sum":
        t0 = pyramid.total(pyr[1], cfg.nodata)
        worst = max(abs(pyramid.total(a, cfg.nodata) - t0) / max(abs(t0), 1e-9) for a in pyr.values())
        report.check(f"pyramid_sum_conserved:{layer_id}", worst < 1e-6, total=round(t0, 3), max_rel_diff=worst)
    return files


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build RadiusStats Europe rasters.")
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--clean-work", action="store_true", help="drop derived caches (downloads are kept)")
    args = ap.parse_args(argv)

    t_start = time.time()
    cfg = load_config(args.config)
    if args.clean_work and WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    report = Report()
    out_dir = cfg.output_dir
    stage = out_dir.with_name(out_dir.name + ".staging")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    print(f"== countries: {cfg.build_countries}; population years {cfg.pop_years}; GDP years {cfg.gdp_years}")
    grid_df = gisco.load_grid(cfg)
    ct = build_cell_table(cfg, grid_df, report)
    cells = ct.cc

    max_level = max(cfg.levels)
    grid = extent_for(cells["x"].to_numpy(), cells["y"].to_numpy(), cfg.raw["raster"]["pad_km"], max_level)
    print(f"== grid {grid.width}x{grid.height} km, origin ({grid.xmin}, {grid.ymax})")
    row, col, inside = grid.index(cells["x"].to_numpy(), cells["y"].to_numpy())
    assert inside.all()
    shape = grid.shape(1)

    country, land = country_and_land(cfg, grid, grid_df, cells, row, col)
    covered = (country != SEA) & (country != NOT_COVERED)
    layers: dict[str, dict] = {}
    row_values: dict[str, np.ndarray] = {}

    G = cfg.gdp_latest
    bands = ([f"pop_{y}" for y in sorted(cfg.pop_years)] + [f"gdp_nom_eur_{G}"]
             + [f"gdp_real_{y}" for y in cfg.gdp_years] + ["country", "land", "land_covered"])
    stack = cog.LevelStack(WORK_DIR / "stack", grid, cfg.levels, bands, cfg.nodata)

    alloc_dir = WORK_DIR / "alloc"
    if alloc_dir.exists():
        shutil.rmtree(alloc_dir)
    alloc_dir.mkdir(parents=True)

    def emit(layer_id: str, values: np.ndarray, meta: dict, detail: list) -> None:
        row_values[layer_id] = values
        pd.concat(detail, ignore_index=True).to_parquet(alloc_dir / f"{layer_id}.parquet")
        arr = rasterise(shape, row, col, values, covered, cfg.nodata)
        files = write_layer(cfg, stack, layer_id, arr, "sum", report)
        layers[layer_id] = {**meta, "levels": files, "total": float(values.sum())}
        print(f"   wrote {layer_id}: total {values.sum():,.1f}")

    # --- population -------------------------------------------------------------------------------
    # GDP years need same-year population weights, so population is built for both sets of years
    pop_detail: dict[int, list] = {}
    pop_by_year = yearly_population(cfg, ct, cfg.pop_years + cfg.gdp_years, report, details=pop_detail,
                                    weight_only=set(cfg.gdp_years) - set(cfg.pop_years))
    for y in sorted(cfg.pop_years):
        emit(f"pop_{y}", pop_by_year[y], {"kind": "population", "year": y, "unit": "persons", "date": f"{y}-01-01"},
             pop_detail[y])
    for y in sorted(set(cfg.gdp_years) - set(cfg.pop_years)):
        row_values[f"popw_{y}"] = pop_by_year[y]   # weights only, not published

    # --- GDP ---------------------------------------------------------------------------------------

    tot = gdp.nominal(cfg, G, "MIO_EUR", report)
    det: list = []
    v = allocate(ct, tot, pop_by_year[G], what="gdp_nominal", year=G, report=report, detail=det)
    emit(f"gdp_nom_eur_{G}", v, {"kind": "gdp", "measure": "nominal", "year": G, "source_unit": "MIO_EUR",
                                 "unit": "million EUR", "prices": "current"}, det)
    zzz = gdp.extra_regio(cfg, G, "MIO_EUR")
    if not zzz.empty:
        report.note("extra_regio_excluded", unit="MIO_EUR", year=G, value=float(zzz.sum()), regions=zzz.index.tolist())
    # PPS = EUR x one national factor (Eurostat converts regional GDP with national PPPs), so no PPS layer:
    # the app multiplies each country's EUR sum by its factor
    pps_per_eur = gdp.pps_per_eur(cfg, G, report)

    real = gdp.real(cfg, report)
    for y in cfg.gdp_years:
        det = []
        v = allocate(ct, real[y].dropna(), pop_by_year[y], what="gdp_real", year=y, report=report, detail=det)
        emit(f"gdp_real_{y}", v, {"kind": "gdp", "measure": "real", "year": y,
                                  "unit": f"million EUR, {cfg.real_base_year} prices and exchange rates",
                                  "prices": "constant"}, det)
    real.rename(columns=str).to_parquet(WORK_DIR / "real_gdp_nuts3.parquet")

    # --- country + land ------------------------------------------------------------------------------
    # coarse-level country = the country with most population in the 2x2 block (land decides empty blocks)
    pop_latest = rasterise(shape, row, col, pop_by_year[cfg.pop_years[0]], covered, 0.0)
    cweight = np.maximum(pop_latest, 0).astype(np.float64) + 1e-6 * land
    layers["country"] = {"kind": "country", "levels": write_layer(cfg, stack, "country", country, "country",
                                                                  report, land=cweight)}
    layers["land"] = {"kind": "land", "levels": write_layer(cfg, stack, "land", land, "mean", report)}
    # land share that lies in built (covered) countries; mean-aggregated so coarse cells stay exact
    land_cov = np.where(covered, land, 0).astype(np.float32)
    layers["land_covered"] = {"kind": "land", "levels": write_layer(cfg, stack, "land_covered", land_cov,
                                                                    "mean", report)}

    # --- one multi-band COG per level -------------------------------------------------------------
    level_files = stack.finish(stage, int(cfg.raw["raster"]["blocksize"]))
    for meta in layers.values():
        for lv, f in meta["levels"].items():
            f.update(url=level_files[int(lv)]["url"], bytes=level_files[int(lv)]["bytes"])
    print("   level files: " + ", ".join(f"L{lv} {f['bytes'] / 1e6:.1f} MB" for lv, f in level_files.items()))

    # --- cell table with every layer's row values, for the validation script ----------------------
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    cells.assign(row=row, col=col, **row_values).to_parquet(WORK_DIR / "cells.parquet")

    # --- map display: heat tiles and coverage mask ------------------------------------------------
    heat = {}
    for key, lid in (("population", f"pop_{cfg.pop_years[0]}"), ("gdp", f"gdp_nom_eur_{cfg.gdp_latest}")):
        arr = rasterise(shape, row, col, row_values[lid], covered, cfg.nodata)
        info = build_pmtiles(stage / "heat" / f"{key}.pmtiles", arr, grid, cfg.nodata, name=f"{key} density")
        unit = "persons per km²" if key == "population" else "million EUR per km²"
        heat[key] = {"url": f"heat/{key}.pmtiles", "layer": lid, "unit": unit, **info}
        print(f"   heat {key}: {info['tiles']} tiles, {info['min']:.3g}–{info['max']:.3g} {unit}")
    mask = build_mask(cfg, stage / "coverage_mask.geojson", report)

    fx = build_fx(cfg, report)
    (stage / "fx.json").write_text(json.dumps(fx, indent=2))

    manifest = {
        "name": "RadiusStats Europe",
        "schema": 2,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grid": grid.to_dict(),
        "levels_km": cfg.levels,
        "nodata": cfg.nodata,
        "years": {"population": {"latest": cfg.pop_years[0], "compare": cfg.pop_years[1:]},
                  "gdp": {"latest": cfg.gdp_years[0], "compare": cfg.gdp_years[1:],
                          "real_base_year": cfg.real_base_year}},
        "countries": [{"id": cfg.country_ids[c], "code": c, "name": cfg.raw["country_names"][c],
                       "currency": cfg.currency(c), "built": c in cfg.build_countries} for c in cfg.coverage],
        "country_codes": {"sea": SEA, "not_covered": NOT_COVERED},
        "low_confidence_gdp_radius_km": cfg.raw["low_confidence_gdp_radius_km"],
        "series_breaks": {"population": series_breaks(cfg, report),
                          "source": "Eurostat demo_r_pjanaggr3 observation flag 'b'"},
        "pps_per_eur": {"year": G, "factors": pps_per_eur,
                        "source": "regional MIO_PPS_EU27_2020 / MIO_EUR (Eurostat); prc_ppp_ind for national sources"},
        "bands": bands,
        "layers": layers,
        "fx": "fx.json",
        "heat": heat,
        "coverage_mask": mask,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2))
    report.write(stage / "build_report.json", extra={
        "countries": cfg.build_countries, "seconds": round(time.time() - t_start, 1),
        "downloads": download_index(),
        "eurostat_last_update": {t: eurostat.last_update(cfg, t, k) for t, k in (
            ("demo_r_pjanaggr3", "A.NR.T.TOTAL."), ("nama_10r_3gdp", ""), ("nama_10r_2gvagr", ""), ("ert_bil_eur_a", ""),
            ("prc_ppp_ind", "A.PPP_EU27_2020.GDP."))},
    })

    if out_dir.exists():
        shutil.rmtree(out_dir)
    stage.replace(out_dir)
    print(f"== done in {time.time() - t_start:.0f}s -> {out_dir}")


if __name__ == "__main__":
    main()
