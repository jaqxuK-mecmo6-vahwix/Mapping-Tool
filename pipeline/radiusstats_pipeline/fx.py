"""Annual average exchange rates (national currency per EUR) from Eurostat ert_bil_eur_a."""
from __future__ import annotations

from .config import Config
from .sources import eurostat


def build_fx(cfg: Config, report) -> dict:
    df = eurostat.table(cfg, "ert_bil_eur_a")
    df = df[(df["statinfo"] == "AVG") & (df["unit"] == "NAC")]
    first = min(cfg.gdp_years + cfg.pop_years)
    rates: dict[str, dict[str, float]] = {}
    for cur in sorted(set(cfg.non_euro_currencies)):
        s = df[(df["currency"] == cur) & (df["TIME_PERIOD"] >= first)].set_index("TIME_PERIOD")["OBS_VALUE"].dropna()
        rates[cur] = {str(int(y)): float(v) for y, v in s.sort_index().items()}
        need = [cfg.gdp_latest, cfg.real_base_year]
        for y in need:
            if str(y) not in rates[cur]:
                report.gap("fx_missing", currency=cur, year=y)
    return {
        "source": "Eurostat ert_bil_eur_a (ECB euro reference rates, annual average), units of currency per 1 EUR",
        "last_update": eurostat.last_update(cfg, "ert_bil_eur_a"),
        "reference_year": cfg.gdp_latest,
        "real_base_year": cfg.real_base_year,
        "euro_area": sorted(cfg.euro_area),
        "country_currency": {c: cfg.currency(c) for c in cfg.coverage},
        "rates": rates,
    }
