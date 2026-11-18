"""Independent spot checks of circle totals (`./run.sh xcheck`), for VALIDATION.md.

Deliberately shares no code with the browser engine: every 1 km cell in the circle's bounding box is
sampled at 10 x 10 points, each point is projected to WGS84 with pyproj and its geodesic distance to
the centre computed on the WGS84 ellipsoid (pyproj.Geod); the cell contributes value x inside-fraction.
Uses the level-1 (1 km) COGs only. Prints a table and writes data/build/xcheck.json.
"""
from __future__ import annotations

import json
import sys

import numpy as np
from pyproj import Geod, Transformer

from . import cog
from .config import load_config

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
    rows = []
    print(f"{'place':10} {'r_km':>5} {'population':>14} {'GDP EUR m':>12}")
    for name, (lat, lon) in PLACES.items():
        for r in RADII:
            t = circle_total(arrs, m["grid"], m["nodata"], lat, lon, r, to3035, to4326, geod)
            rows.append({"place": name, "lat": lat, "lon": lon, "radius_km": r, **{keys[k]: v for k, v in t.items()}})
            print(f"{name:10} {r:5d} {t['pop']:14,.0f} {t['gdp_nom_eur']:12,.0f}")
    (out / "xcheck.json").write_text(json.dumps({"method": __doc__.strip(), "sub_samples": SUB, "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
