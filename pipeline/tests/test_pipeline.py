import numpy as np
import pandas as pd
import pytest

from radiusstats_pipeline import cog, pyramid
from radiusstats_pipeline.grid import GridSpec, extent_for
from radiusstats_pipeline.population import CellTable, allocate, choose_version
from radiusstats_pipeline.report import Report
from radiusstats_pipeline.validate import cagr

ND = -1.0


# --- pyramids --------------------------------------------------------------------------------------

def test_sum2x2_conserves_total_and_handles_nodata():
    rng = np.random.default_rng(0)
    a = rng.random((64, 96)).astype(np.float32) * 1000
    a[rng.random(a.shape) < 0.3] = ND
    a[:2, :2] = ND  # a block that is entirely nodata stays nodata
    pyr = pyramid.build(a, [1, 2, 4, 8, 16, 32], "sum", nodata=ND)
    t1 = pyramid.total(a, ND)
    for lv, arr in pyr.items():
        assert arr.shape == (64 // lv, 96 // lv)
        assert pyramid.total(arr, ND) == pytest.approx(t1, rel=1e-6)
    assert pyr[2][0, 0] == ND


def test_sum2x2_is_a_sum_not_a_mean():
    a = np.array([[1, 2], [3, 4]], np.float32)
    assert pyramid.sum2x2(a, ND)[0, 0] == 10


def test_partial_nodata_block_counts_as_zero():
    a = np.array([[ND, 2], [ND, ND]], np.float32)
    assert pyramid.sum2x2(a, ND)[0, 0] == 2


def test_country_mode_uses_weight():
    c = np.array([[1, 1], [2, 0]], np.uint8)
    land = np.array([[0.1, 0.1], [1.0, 0.0]], np.float32)
    assert pyramid.mode2x2_country(c, land)[0, 0] == 2
    assert pyramid.mode2x2_country(np.zeros((2, 2), np.uint8), land)[0, 0] == 0


# --- grid --------------------------------------------------------------------------------------------

def test_extent_aligned_to_coarsest_level():
    g = extent_for(np.array([3_900_000, 4_100_000]), np.array([3_000_000, 3_100_000]), pad_km=64, align_km=32)
    assert g.xmin % 32_000 == 0 and g.ymax % 32_000 == 0
    assert g.width % 32 == 0 and g.height % 32 == 0
    r, c, inside = g.index(np.array([3_900_000]), np.array([3_000_000]))
    assert inside.all()
    # lower-left corner (x, y) -> top-left based row
    assert g.ymax - (r[0] + 1) * 1000 == 3_000_000 and g.xmin + c[0] * 1000 == 3_900_000


# --- allocation --------------------------------------------------------------------------------------

def _table() -> CellTable:
    cc = pd.DataFrame({
        "x": [0, 1000, 2000, 3000], "y": [0, 0, 0, 0], "country": "BE",
        "base": [100.0, 300.0, 50.0, 0.0], "land": [1, 1, 1, 1],
        "nuts2024": ["BE100", "BE100", "BE100-BE211", "BE211"],
        "nuts2021": ["BE100", "BE100", "BE100-BE211", "BE211"],
        "nuts2016": ["BE100", "BE100", "BE999", "BE999"],
    })
    return CellTable(cc=cc, report=Report())


def test_allocate_reproduces_regional_totals():
    ct = _table()
    totals = pd.Series({"BE100": 1000.0, "BE211": 80.0})
    detail = []
    v = allocate(ct, totals, ct.cc["base"].to_numpy(), what="t", year=2025, report=Report(), detail=detail)
    d = pd.concat(detail).groupby("region")["value"].sum()
    assert d["BE100"] == pytest.approx(1000) and d["BE211"] == pytest.approx(80)
    assert v.sum() == pytest.approx(1080)
    # cell 3 is half BE100, half BE211 by base -> BE211's only weight is 25 of cell 3
    assert v[3] == 0.0


def test_allocate_spreads_by_land_when_region_has_no_population():
    ct = _table()
    ct.cc.loc[2, "base"] = 0.0
    v = allocate(ct, pd.Series({"BE100": 10.0, "BE211": 8.0}), ct.cc["base"].to_numpy(), what="t", year=1,
                 report=Report())
    assert v.sum() == pytest.approx(18)
    assert v[3] > 0


def test_choose_version_prefers_newest_complete_and_ignores_duplicates():
    ct = _table()
    assert choose_version(ct, "BE", {"BE100", "BE211", "BE999"})[0] == 2024
    assert choose_version(ct, "BE", {"BE100", "BE999"})[0] == 2016


def test_cagr():
    assert cagr(121, 100, 2) == pytest.approx(0.10)
    assert cagr(100, 100, 5) == 0


# --- COG ---------------------------------------------------------------------------------------------

def test_cog_roundtrip_is_valid(tmp_path):
    from rio_cogeo.cogeo import cog_validate
    g = GridSpec(xmin=3_840_000, ymax=3_200_000, width=512, height=512)
    a = np.zeros((512, 512), np.float32)
    a[100:200, 100:200] = 7.5
    a[:10] = ND
    p = cog.write_cog(tmp_path / "x.tif", a, g, 1, nodata=ND)
    ok, errors, _ = cog_validate(str(p))
    assert ok, errors
    np.testing.assert_array_equal(cog.read(p), a)


def test_keep_mantissa_bits_bounds_the_relative_error_and_keeps_nodata():
    from radiusstats_pipeline.pyramid import keep_mantissa_bits
    rng = np.random.default_rng(1)
    a = (rng.lognormal(0, 3, 10_000)).astype(np.float32)
    a[:5] = [-1.0, 0.0, 1.0, 3.0e-7, 123456.789]
    q = keep_mantissa_bits(a, 12, nodata=-1.0)
    assert q[0] == -1.0 and q[1] == 0.0 and q[2] == 1.0
    ok = a > 0
    rel = np.abs(q[ok].astype(np.float64) - a[ok]) / a[ok]
    assert rel.max() <= 2.0 ** -13 + 1e-12
    # round to nearest: no systematic bias on the sum
    assert abs(q[ok].astype(np.float64).sum() / a[ok].astype(np.float64).sum() - 1) < 1e-5
    assert keep_mantissa_bits(a, 23) is a


def test_uk_population_on_1_january_is_mean_of_mid_years():
    from radiusstats_pipeline.sources.national import jan1_from_midyear
    mid = pd.DataFrame({2024: [100.0, 50.0], 2025: [110.0, 52.0]}, index=["UKa", "UKb"])
    assert jan1_from_midyear(mid, 2025).tolist() == [105.0, 51.0]


def test_norway_county_mappings_are_complete():
    from radiusstats_pipeline.sources.national import NO_2016, NO_2016_TO_2021, NO_2021
    assert set(NO_2016.values()) == set(NO_2016_TO_2021)              # every old region maps forward
    assert set(NO_2016_TO_2021.values()) == set(NO_2021.values())       # onto exactly the 2021 regions
    assert len(set(NO_2021.values())) == 11


def test_swiss_cantons_are_the_26_nuts3_regions():
    from radiusstats_pipeline.sources.national import CH_CANTONS
    assert len(CH_CANTONS) == 26 and len(set(CH_CANTONS.values())) == 26
    assert all(v.startswith("CH0") and len(v) == 5 for v in CH_CANTONS.values())
