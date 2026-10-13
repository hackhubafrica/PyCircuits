from __future__ import annotations

import math
from typing import Any

import numpy as np


MAX_POINTS = 1800


class ControlError(Exception):
    """Readable control-theory or modeling error."""


def fnum(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def cplx(z: Any) -> dict[str, float]:
    c = complex(z)
    return {"re": float(c.real), "im": float(c.imag)}


def cplx_list(vals) -> list[dict[str, float]]:
    arr = np.atleast_1d(np.asarray(vals, dtype=complex)).flatten()
    return [cplx(z) for z in arr]


def as_float_list(arr) -> list[float | None]:
    flat = np.atleast_1d(np.asarray(arr, dtype=float)).flatten()
    return [fnum(v) for v in flat]


def downsample(*arrays, max_n: int = MAX_POINTS):
    if not arrays:
        return arrays
    n = len(np.atleast_1d(arrays[0]))
    if n <= max_n:
        return tuple(np.atleast_1d(a) for a in arrays)
    idx = np.linspace(0, n - 1, max_n).astype(int)
    return tuple(np.atleast_1d(a)[idx] for a in arrays)


def matrix_to_lists(m) -> list[list[float | None]]:
    a = np.atleast_2d(np.asarray(m, dtype=float))
    return [[fnum(v) for v in row] for row in a]


def tf_coeffs(sys) -> tuple[list[float | None], list[float | None]]:
    num, den = sys.num[0][0], sys.den[0][0]
    return as_float_list(num), as_float_list(den)
