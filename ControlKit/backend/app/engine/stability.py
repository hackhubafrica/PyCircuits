from __future__ import annotations

import control as ct
import numpy as np

from app.engine.plant import to_ss
from app.engine.util import cplx_list, fnum


TOL = 1e-9


def _eigs(sys) -> np.ndarray:
    ss = to_ss(sys)
    return np.linalg.eigvals(np.asarray(ss.A, dtype=complex))


def analyze_stability(sys) -> dict:
    poles = np.atleast_1d(ct.poles(sys)).astype(complex)
    zeros = np.atleast_1d(ct.zeros(sys)).astype(complex)
    eigs = _eigs(sys)

    pole_re = np.real(poles)
    eig_re = np.real(eigs)

    on_axis_poles = bool(np.any(np.abs(pole_re) <= TOL) and np.any(np.abs(np.imag(poles[np.abs(pole_re) <= TOL])) > TOL))
    repeated_jw = False
    jw = poles[np.abs(pole_re) <= TOL]
    if jw.size:
        # Repeated jω poles (including origin) are not BIBO-stable.
        rounded = np.round(jw, 8)
        _, counts = np.unique(rounded, return_counts=True)
        repeated_jw = bool(np.any(counts > 1)) or bool(np.any(np.abs(jw) <= TOL) and np.any(np.abs(pole_re) <= TOL))

    rhp_poles = bool(np.any(pole_re > TOL))
    olhp_all = bool(np.all(pole_re < -TOL)) if poles.size else True

    bibo_stable = bool(olhp_all)
    if not bibo_stable:
        if rhp_poles:
            bibo_reason = "BIBO unstable: at least one pole has a positive real part."
        elif repeated_jw or np.any(np.abs(poles) <= TOL):
            bibo_reason = "Not BIBO stable: pole(s) on the imaginary axis (including integrators)."
        else:
            bibo_reason = "Not BIBO stable: poles must lie in the open left half-plane."
    else:
        bibo_reason = "All poles lie in the open left half-plane."

    lyap_as = bool(np.all(eig_re < -TOL)) if eigs.size else True
    if lyap_as:
        lyap_reason = "Asymptotically stable (Lyapunov): all eigenvalues of A have negative real parts."
    elif np.any(eig_re > TOL):
        lyap_reason = "Lyapunov unstable: A has an eigenvalue with positive real part."
    else:
        lyap_reason = "Not asymptotically stable: A has eigenvalue(s) on the imaginary axis."

    return {
        "poles": cplx_list(poles),
        "zeros": cplx_list(zeros),
        "eigenvalues": cplx_list(eigs),
        "bibo_stable": bibo_stable,
        "bibo_reason": bibo_reason,
        "lyapunov_asymptotic": lyap_as,
        "lyapunov_reason": lyap_reason,
        "max_real_pole": fnum(np.max(pole_re)) if poles.size else None,
        "max_real_eig": fnum(np.max(eig_re)) if eigs.size else None,
    }
