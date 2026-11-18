"""Load config/radiusstats.yaml and derive years, paths and country lists."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = REPO_ROOT / "pipeline"
DEFAULT_CONFIG = REPO_ROOT / "config" / "radiusstats.yaml"
CACHE_DIR = PIPELINE_ROOT / "cache"
DOWNLOAD_DIR = CACHE_DIR / "downloads"
WORK_DIR = CACHE_DIR / "work"


@dataclass
class Config:
    raw: dict[str, Any]
    path: Path
    build_countries: list[str] = field(init=False)

    def __post_init__(self) -> None:
        bc = self.raw["build_countries"]
        cov = list(self.raw["coverage"])
        # YAML 1.1 reads a bare NO as false ("the Norway problem"): require quoted codes
        for name, codes in (("coverage", cov), ("build_countries", [] if bc == "all" else bc),
                            ("euro_area", self.raw["euro_area"]), ("currencies", list(self.raw["currencies"])),
                            ("country_names", list(self.raw["country_names"]))):
            bad = [c for c in codes if not isinstance(c, str)]
            if bad:
                raise ValueError(f"{name}: non-string country codes {bad} (quote \"NO\" in the YAML)")
        self.build_countries = cov if bc == "all" else list(bc)
        unknown = set(self.build_countries) - set(cov)
        if unknown:
            raise ValueError(f"build_countries not in coverage: {sorted(unknown)}")

    # --- years -----------------------------------------------------------------
    @property
    def pop_years(self) -> list[int]:
        p = self.raw["population"]
        return [p["latest"]] + [p["latest"] - n for n in p["lags"]]

    @property
    def gdp_years(self) -> list[int]:
        g = self.raw["gdp"]
        return [g["latest"]] + [g["latest"] - n for n in g["lags"]]

    @property
    def gdp_latest(self) -> int:
        return int(self.raw["gdp"]["latest"])

    @property
    def real_base_year(self) -> int:
        return int(self.raw["gdp"]["real_base_year"])

    # --- countries / currencies ------------------------------------------------
    @property
    def coverage(self) -> list[str]:
        return list(self.raw["coverage"])

    @property
    def euro_area(self) -> set[str]:
        return set(self.raw["euro_area"])

    def currency(self, country: str) -> str:
        return "EUR" if country in self.euro_area else self.raw["currencies"][country]

    def _national(self, key: str) -> set[str]:
        return set(self.raw.get("national_sources", {}).get(key, [])) & set(self.build_countries)

    @property
    def national_gdp(self) -> set[str]:
        return self._national("gdp")

    @property
    def national_population(self) -> set[str]:
        return self._national("population")

    @property
    def national_grid(self) -> set[str]:
        return self._national("grid")

    @property
    def non_euro_currencies(self) -> list[str]:
        return [self.raw["currencies"][c] for c in self.coverage if c not in self.euro_area]

    @property
    def country_ids(self) -> dict[str, int]:
        """Stable uint8 IDs for the country raster: 1..N in coverage order. 0 = sea, 255 = not covered."""
        return {c: i + 1 for i, c in enumerate(self.coverage)}

    # --- raster ----------------------------------------------------------------
    @property
    def levels(self) -> list[int]:
        return list(self.raw["raster"]["levels"])

    @property
    def nodata(self) -> float:
        return float(self.raw["raster"]["nodata"])

    @property
    def output_dir(self) -> Path:
        return REPO_ROOT / self.raw["output"]["dir"]

    def source(self, key: str) -> str:
        return self.raw["sources"][key]


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Config(raw=raw, path=path)
