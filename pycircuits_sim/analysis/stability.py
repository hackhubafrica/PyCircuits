"""Stability verdicts for continuous-time state-space plants.

Pure numpy. Ports ControlKit's analysis: a BIBO verdict (poles in the open
left half-plane, with explicit handling of right-half-plane poles, repeated
j-omega poles, and integrators) and a Lyapunov asymptotic-stability verdict
(eigenvalues of A), both with human-readable reasons. Educational tool, not
a proof assistant.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..linear_systems import StateSpaceModel
from .plant import normalize_plant, require_continuous

TOL = 1e-9


@dataclass(frozen=True)
class StabilityReport:
    """BIBO and Lyapunov stability verdicts with explanatory reasons."""

    poles: tuple[complex, ...]
    zeros: tuple[complex, ...]
    eigenvalues: tuple[complex, ...]
    bibo_stable: bool
    bibo_reason: str
    lyapunov_asymptotic: bool
    lyapunov_reason: str
    max_real_pole: float | None
    max_real_eig: float | None


def analyze_stability(model: StateSpaceModel) -> StabilityReport:
    """Judge BIBO and Lyapunov stability of a continuous LTI plant.

    BIBO stability requires every pole in the open left half-plane; poles on
    the imaginary axis (including integrators) are not BIBO-stable.
    Lyapunov asymptotic stability requires every eigenvalue of A to have a
    negative real part. For state-space models poles and eigenvalues of A
    coincide; both are reported for parity with classical analysis tooling.
    """
    require_continuous(model, "analyze_stability")
    report = normalize_plant(model)
    poles = np.asarray(report.poles, dtype=complex)
    eigenvalues = poles.copy()
    pole_re = np.real(poles)
    eig_re = np.real(eigenvalues)

    jw = poles[np.abs(pole_re) <= TOL]
    on_axis_complex = jw[np.abs(np.imag(jw)) > TOL]
    repeated_jw = False
    if on_axis_complex.size:
        rounded = np.round(on_axis_complex, 8)
        _, counts = np.unique(rounded, return_counts=True)
        repeated_jw = bool(np.any(counts > 1))
    origin_pole = bool(np.any(np.abs(jw) <= TOL))

    rhp_poles = bool(np.any(pole_re > TOL))
    olhp_all = bool(np.all(pole_re < -TOL)) if poles.size else True

    bibo_stable = bool(olhp_all)
    if bibo_stable:
        bibo_reason = "All poles lie in the open left half-plane."
    elif rhp_poles:
        bibo_reason = "BIBO unstable: at least one pole has a positive real part."
    elif repeated_jw or origin_pole:
        bibo_reason = (
            "Not BIBO stable: pole(s) on the imaginary axis (including integrators)."
        )
    else:
        bibo_reason = "Not BIBO stable: poles must lie in the open left half-plane."

    lyapunov_as = bool(np.all(eig_re < -TOL)) if eigenvalues.size else True
    if lyapunov_as:
        lyap_reason = (
            "Asymptotically stable (Lyapunov): all eigenvalues of A have "
            "negative real parts."
        )
    elif np.any(eig_re > TOL):
        lyap_reason = "Lyapunov unstable: A has an eigenvalue with positive real part."
    else:
        lyap_reason = (
            "Not asymptotically stable: A has eigenvalue(s) on the imaginary axis."
        )

    return StabilityReport(
        poles=report.poles,
        zeros=report.zeros,
        eigenvalues=tuple(
            sorted(eigenvalues.tolist(), key=lambda z: (z.real, z.imag))
        ),
        bibo_stable=bibo_stable,
        bibo_reason=bibo_reason,
        lyapunov_asymptotic=lyapunov_as,
        lyapunov_reason=lyap_reason,
        max_real_pole=float(np.max(pole_re)) if poles.size else None,
        max_real_eig=float(np.max(eig_re)) if eigenvalues.size else None,
    )
