from __future__ import annotations

import control as ct
import numpy as np

from app.engine.util import ControlError, cplx_list, fnum, matrix_to_lists, tf_coeffs


def _as_2d(name: str, data) -> np.ndarray:
    try:
        arr = np.asarray(data, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ControlError(f"Matrix {name} must contain finite numbers.") from exc
    if arr.ndim == 1:
        arr = arr.reshape((1, -1)) if name in {"C", "D"} else arr.reshape((-1, 1))
    if arr.ndim != 2:
        raise ControlError(f"Matrix {name} must be 2-D.")
    if not np.isfinite(arr).all():
        raise ControlError(f"Matrix {name} contains non-finite values.")
    return arr


def build_system(spec) -> ct.StateSpace | ct.TransferFunction:
    form = spec.form
    if form == "tf":
        if spec.num is None or spec.den is None:
            raise ControlError("Transfer-function plants need numerator and denominator coefficients.")
        num = np.asarray(spec.num, dtype=float).flatten()
        den = np.asarray(spec.den, dtype=float).flatten()
        if num.size == 0 or den.size == 0:
            raise ControlError("Numerator and denominator must be non-empty.")
        if not np.isfinite(num).all() or not np.isfinite(den).all():
            raise ControlError("Polynomial coefficients must be finite.")
        if np.allclose(den, 0):
            raise ControlError("Denominator cannot be identically zero.")
        if den[0] == 0:
            den = np.trim_zeros(den, "f")
            if den.size == 0:
                raise ControlError("Denominator cannot be identically zero.")
        try:
            sys = ct.tf(num, den)
        except Exception as exc:
            raise ControlError(f"Could not build transfer function: {exc}") from exc
    elif form == "ss":
        if spec.A is None or spec.B is None or spec.C is None:
            raise ControlError("State-space plants need A, B, and C matrices.")
        A = _as_2d("A", spec.A)
        B = _as_2d("B", spec.B)
        C = _as_2d("C", spec.C)
        D = _as_2d("D", spec.D) if spec.D is not None else np.zeros((C.shape[0], B.shape[1]))
        n = A.shape[0]
        if A.shape[1] != n:
            raise ControlError("A must be square.")
        if B.shape[0] != n:
            raise ControlError("B must have the same number of rows as A.")
        if C.shape[1] != n:
            raise ControlError("C must have the same number of columns as A.")
        if D.shape != (C.shape[0], B.shape[1]):
            raise ControlError("D shape must be (outputs × inputs).")
        try:
            sys = ct.ss(A, B, C, D)
        except Exception as exc:
            raise ControlError(f"Could not build state-space model: {exc}") from exc
    else:
        raise ControlError("Plant form must be 'tf' or 'ss'.")

    n_in = int(getattr(sys, "ninputs", 1) or 1)
    n_out = int(getattr(sys, "noutputs", 1) or 1)
    if n_in != 1 or n_out != 1:
        raise ControlError("ControlLens currently analyzes SISO plants only.")
    return sys


def to_tf(sys) -> ct.TransferFunction:
    try:
        return ct.tf(sys)
    except Exception as exc:
        raise ControlError(f"Could not convert plant to transfer function: {exc}") from exc


def to_ss(sys) -> ct.StateSpace:
    try:
        return ct.ss(sys)
    except Exception as exc:
        raise ControlError(f"Could not convert plant to state-space: {exc}") from exc


def dc_gain(sys) -> float | None:
    try:
        g = ct.dcgain(sys)
        return fnum(np.squeeze(g))
    except Exception:
        return None


def normalize_payload(sys) -> dict:
    tf_sys = to_tf(sys)
    ss_sys = to_ss(sys)
    num, den = tf_coeffs(tf_sys)
    poles = cplx_list(ct.poles(sys))
    zeros = cplx_list(ct.zeros(sys))
    return {
        "num": num,
        "den": den,
        "A": matrix_to_lists(ss_sys.A),
        "B": matrix_to_lists(ss_sys.B),
        "C": matrix_to_lists(ss_sys.C),
        "D": matrix_to_lists(ss_sys.D),
        "poles": poles,
        "zeros": zeros,
        "dc_gain": dc_gain(sys),
        "order": int(np.asarray(ss_sys.A).shape[0]),
        "ninputs": 1,
        "noutputs": 1,
    }
