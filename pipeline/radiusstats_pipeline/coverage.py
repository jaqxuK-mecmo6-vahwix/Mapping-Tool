"""Grey-out mask for the map: land of countries NOT in this build (GISCO 1:3M). Sea stays clear."""
from __future__ import annotations

import json
from pathlib import Path

from shapely import set_precision
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from .config import DOWNLOAD_DIR, Config
from .fetch import fetch

COUNTRIES_URL = "https://gisco-services.ec.europa.eu/distribution/v2/countries/geojson/CNTR_RG_03M_2024_4326.geojson"
MASK_BOX = (-36.0, 23.0, 49.0, 74.0)   # lon/lat, just larger than the map's max bounds


def build_mask(cfg: Config, out: Path, report) -> dict:
    src = fetch(COUNTRIES_URL, DOWNLOAD_DIR / "gisco" / "CNTR_RG_03M_2024_4326.geojson")
    gj = json.loads(src.read_text())
    keep = set(cfg.build_countries)
    present = {f["properties"].get("CNTR_ID") for f in gj["features"]}
    if keep - present:
        report.gap("coverage_mask_country_missing", countries=sorted(keep - present))
    others = [shape(f["geometry"]) for f in gj["features"] if f["properties"].get("CNTR_ID") not in keep]
    mask = unary_union(others).intersection(box(*MASK_BOX))
    # French outermost regions and other excluded far territories of covered countries are greyed too
    if "FR" in keep:
        fr = unary_union([shape(f["geometry"]) for f in gj["features"] if f["properties"].get("CNTR_ID") == "FR"])
        mask = mask.union(fr.difference(box(-32, 26, 46, 72)))
    mask = set_precision(mask.simplify(0.002, preserve_topology=True), 0.0001)  # ~10 m
    feat = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"role": "outside-coverage"}, "geometry": mapping(mask)}]}
    out.write_text(json.dumps(feat, separators=(",", ":")))
    return {"url": out.name, "countries": sorted(keep), "source": COUNTRIES_URL}
