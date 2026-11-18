"""Independent spot checks of circle totals (`./run.sh xcheck`), for VALIDATION.md.

Deliberately shares no code with the browser engine: every 1 km cell in the circle's bounding box is
sampled at 10 x 10 points, each point is projected to WGS84 with pyproj and its geodesic distance to
the centre computed on the WGS84 ellipsoid (pyproj.Geod); the cell contributes value x inside-fraction.
Uses the level-1 (1 km) COGs only. Prints a table and writes data/build/xcheck.json.

Plausibility against official figures: for each circle, the official totals (Eurostat / ONS / BFS / SSB,
re-read from the cached source tables) of the regions lying ENTIRELY inside the circle give a lower
bound, and those of all regions the circle touches give an upper bound. Region membership of 1 km cells
comes from the GISCO grid (or the ONS LAD boundaries for the UK); a cell is inside if its four corners
are, and touched if its nearest point could be.
"""
from __future__ import annotations

import json
import sys

import numpy as np
from pyproj import Geod, Transformer

import pandas as pd

from . import cog, gdp
from .config import WORK_DIR, load_config
from .population import regional_population

PLACES = {
    "Paris": (48.8566, 2.3522), "London": (51.5074, -0.1278), "Zurich": (47.3769, 8.5417),
    "Oslo": (59.9139, 10.7522), "Warsaw": (52.2297, 21.0122), "Basel": (47.5596, 7.5886),
    "Brussels": (50.8467, 4.3525),
}
RADII = (25, 50, 100)
SUB = 10


def circle_total(arrs: dict[str, np.ndarray], grid: dict, nodata: float, lat: float, lon: float, r_km: float,
                 to3035: Transformer, to4326: Transformer, geod: Geod) -> dict[str, float]:
    cx, cy = to3035.transform(lon, lat)
    size = grid["cell_m"]
    pad = r_km * 1000 * 1.2 + 2 * size
    c0 = int(np.floor((cx - pad - grid["xmin"]) / size)); c1 = int(np.ceil((cx + pad - grid["xmin"]) / size))
    r0 = int(np.floor((grid["ymax"] - (cy + pad)) / size)); r1 = int(np.ceil((grid["ymax"] - (cy - pad)) / size))
    first = next(iter(arrs.values()))
    c0, r0 = max(c0, 0), max(r0, 0)
    c1, r1 = min(c1, first.shape[1]), min(r1, first.shape[0])
    rows, cols = np.mgrid[r0:r1, c0:c1]
    off = (np.arange(SUB) + 0.5) / SUB
    # sample point coordinates (cells x SUB x SUB)
    xs = grid["xmin"] + (cols[..., None, None] + off[None, None, None, :]) * size
    ys = grid["ymax"] - (rows[..., None, None] + off[None, None, :, None]) * size
    xs, ys = np.broadcast_arrays(xs, ys)
    lo, la = to4326.transform(xs.ravel(), ys.ravel())
    _, _, d = geod.inv(np.full(lo.shape, lon), np.full(lo.shape, lat), lo, la)
    frac = (d <= r_km * 1000).reshape(xs.shape).mean(axis=(-1, -2))
    out = {}
    for k, a in arrs.items():
        v = a[r0:r1, c0:c1].astype(np.float64)
        v = np.where(v == nodata, 0, v)
        out[k] = float((v * frac).sum())
    return out


def region_bounds(cells: pd.DataFrame, region_of_row: pd.DataFrame, official: pd.Series, lat: float, lon: float,
                  r_km: float, to3035: Transformer, to4326: Transformer, geod: Geod) -> tuple[float, float, int, int]:
    """(lower, upper, regions inside, regions touched) from official regional totals."""
    cx, cy = to3035.transform(lon, lat)
    pad = r_km * 1000 * 1.3 + 2000
    near = cells[(cells["x"] > cx - pad) & (cells["x"] < cx + pad) & (cells["y"] > cy - pad) & (cells["y"] < cy + pad)]
    if near.empty:
        return 0.0, 0.0, 0, 0
    xs = near["x"].to_numpy()[:, None] + np.array([0, 1000, 0, 1000])[None, :]
    ys = near["y"].to_numpy()[:, None] + np.array([0, 0, 1000, 1000])[None, :]
    lo, la = to4326.transform(xs.ravel(), ys.ravel())
    _, _, d = geod.inv(np.full(lo.shape, lon), np.full(lo.shape, lat), lo, la)
    d = d.reshape(xs.shape)
    inside = (d.max(axis=1) <= r_km * 1000)
    touched = (d.min(axis=1) <= r_km * 1000 + 710)   # the nearest point of a cell is within half a diagonal
    rr = region_of_row.set_index("i").loc[near.index]
    inside_rows = pd.Series(inside, index=near.index)
    touched_rows = pd.Series(touched, index=near.index)
    regs_touched = set(rr.loc[touched_rows[touched_rows].index, "region"])
    # inside only if every cell of the region (anywhere, not just near) is inside
    all_rows = region_of_row[region_of_row["region"].isin(regs_touched)]
    ins = inside_rows.reindex(all_rows["i"]).fillna(False).to_numpy()
    full = all_rows.assign(ins=ins).groupby("region")["ins"].all()
    regs_inside = set(full[full].index)
    off = official[~official.index.duplicated()]
    return (float(off.reindex(sorted(regs_inside)).sum()), float(off.reindex(sorted(regs_touched)).sum()),
            len(regs_inside), len(regs_touched))


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    out = cfg.output_dir
    m = json.loads((out / "manifest.json").read_text())
    P, G = m["years"]["population"]["latest"], m["years"]["gdp"]["latest"]
    keys = {"pop": f"pop_{P}", "gdp_nom_eur": f"gdp_nom_eur_{G}"}
    arrs = {k: cog.read_level(out, m["layers"][lid]["levels"]["1"]) for k, lid in keys.items()}
    to3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    to4326 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
    geod = Geod(ellps="WGS84")
    cells = pd.read_parquet(WORK_DIR / "cells.parquet", columns=["x", "y"])
    reg_rows = {k: pd.read_parquet(WORK_DIR / "alloc" / f"{lid}.parquet", columns=["i", "region"]).drop_duplicates()
                for k, lid in keys.items()}
    pr = regional_population(cfg, [P])
    official = {"pop": pr[pr["year"] == P].set_index("geo")["value"], "gdp_nom_eur": gdp.nominal(cfg, G, "MIO_EUR")}
    rows = []
    print(f"{'place':10} {'r_km':>5} {'population':>12} {'official bounds':>27} {'GDP EUR m':>10} {'official bounds':>21}")
    for name, (lat, lon) in PLACES.items():
        for r in RADII:
            t = circle_total(arrs, m["grid"], m["nodata"], lat, lon, r, to3035, to4326, geod)
            row = {"place": name, "lat": lat, "lon": lon, "radius_km": r, **{keys[k]: v for k, v in t.items()}}
            line = f"{name:10} {r:5d}"
            for k in keys:
                lo_, hi_, n_in, n_t = region_bounds(cells, reg_rows[k], official[k], lat, lon, r, to3035, to4326, geod)
                ok = lo_ * (1 - 1e-3) <= t[k] <= hi_ * (1 + 1e-3)
                row[f"{k}_bounds"] = {"lower": lo_, "upper": hi_, "regions_inside": n_in, "regions_touched": n_t, "ok": ok}
                line += f" {t[k]:12,.0f} [{lo_:12,.0f} – {hi_:12,.0f}]{'' if ok else ' OUT'}"
            rows.append(row)
            print(line)
    (out / "xcheck.json").write_text(json.dumps({"method": __doc__.strip(), "sub_samples": SUB, "rows": rows}, indent=2))
    bad = [(r["place"], r["radius_km"], k) for r in rows for k in keys if not r[f"{k}_bounds"]["ok"]]
    print(f"\nwithin official-region bounds: {len(rows) * len(keys) - len(bad)}/{len(rows) * len(keys)}" + (f"; outside: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
