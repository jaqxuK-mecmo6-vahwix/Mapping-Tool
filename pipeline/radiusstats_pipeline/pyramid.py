"""Pyramid levels. Data layers are SUMMED 2x2 (never averaged) so totals are conserved."""
from __future__ import annotations

import numpy as np


def sum2x2(a: np.ndarray, nodata: float) -> np.ndarray:
    """Sum each 2x2 block. Nodata children count as 0; a parent is nodata only if all 4 children are."""
    h, w = a.shape
    assert h % 2 == 0 and w % 2 == 0, "grid must be aligned to the coarsest level"
    nd = a == nodata
    v = np.where(nd, 0.0, a.astype(np.float64))
    s = v.reshape(h // 2, 2, w // 2, 2).sum(axis=(1, 3))
    all_nd = nd.reshape(h // 2, 2, w // 2, 2).all(axis=(1, 3))
    out = s.astype(np.float32)
    out[all_nd] = nodata
    return out


def mean2x2(a: np.ndarray) -> np.ndarray:
    """Mean of each 2x2 block (for the land-share layer, which is a fraction of cell area)."""
    h, w = a.shape
    return a.astype(np.float64).reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3)).astype(np.float32)


def mode2x2_country(a: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Country of a parent cell = the child country with the largest summed `weight`
    (population, plus a tiny land term so empty land still decides).
    0 (sea) only when no child has a country; 255 (land outside coverage) competes like a country."""
    h, w = a.shape
    blocks = a.reshape(h // 2, 2, w // 2, 2).transpose(0, 2, 1, 3).reshape(h // 2, w // 2, 4)
    lw = weight.astype(np.float64).reshape(h // 2, 2, w // 2, 2).transpose(0, 2, 1, 3).reshape(h // 2, w // 2, 4)
    lw = np.where(blocks > 0, lw + 1e-9, 0.0)
    out = np.zeros((h // 2, w // 2), dtype=np.uint8)
    best = np.zeros((h // 2, w // 2))
    for code in np.unique(blocks):
        if code == 0:
            continue
        wsum = np.where(blocks == code, lw, 0.0).sum(axis=2)
        better = wsum > best
        out[better] = code
        best[better] = wsum[better]
    return out


def build(a: np.ndarray, levels: list[int], kind: str, nodata: float = -1.0,
          land: np.ndarray | None = None) -> dict[int, np.ndarray]:
    """Return {level_km: array} for every level, starting from the 1 km array `a`.

    kind: 'sum' (data layers), 'mean' (land shares), 'country' (uint8 ids; `land` is the 1 km
    weight used to pick a parent's country — the pipeline passes population + 1e-6 × land).
    """
    assert levels[0] == 1 and all(levels[i + 1] == 2 * levels[i] for i in range(len(levels) - 1))
    out = {1: a}
    cur, cur_land = a, land
    for lv in levels[1:]:
        if kind == "sum":
            cur = sum2x2(cur, nodata)
        elif kind == "mean":
            cur = mean2x2(cur)
        elif kind == "country":
            assert cur_land is not None
            cur, cur_land = mode2x2_country(cur, cur_land), sum2x2(cur_land, nodata)
        else:
            raise ValueError(kind)
        out[lv] = cur
    return out


def total(a: np.ndarray, nodata: float) -> float:
    return float(np.where(a == nodata, 0.0, a.astype(np.float64)).sum())


def keep_mantissa_bits(a: np.ndarray, bits: int, nodata: float | None = None) -> np.ndarray:
    """Round float32 values to `bits` mantissa bits (round half up on the magnitude, sign kept).
    Relative error per value <= 2**-(bits+1). nodata and zeros are unchanged."""
    if bits >= 23 or a.dtype != np.float32:
        return a
    drop = 23 - bits
    u = a.view(np.uint32)
    sign = u & np.uint32(0x80000000)
    mag = u & np.uint32(0x7FFFFFFF)
    mag = (mag + np.uint32(1 << (drop - 1))) & np.uint32((0x7FFFFFFF >> drop) << drop)
    out = (sign | mag).view(np.float32)
    if nodata is not None:
        out = np.where(a == nodata, a, out)
    return out
