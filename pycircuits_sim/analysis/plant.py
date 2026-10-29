"""Plant normalization: transfer-function coefficients, poles, zeros, DC gain.

Pure numpy. The transfer-function extraction for SISO plants uses the
Faddeev-LeVerrier recurrence, so no symbolic or optional dependency is
needed. This is an educational reporting layer; it does not replace the
simulation engines and supports continuous-time plants only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..ir import IrMixin
from ..linear_systems import DiscreteStateSpaceModel, StateSpaceModel


@dataclass(frozen=True)
class PlantReport(IrMixin):
    """Normalized description of a continuous-time state-space plant.

    ``numerator`` is None for MIMO plants (only SISO transfer functions are
    reported). Coefficients are in descending powers of ``s``; the
    denominator is monic. Poles/zeros are native Python ``complex`` values.
    ``dc_gain`` is None when A is singular (integrators) or the plant is MIMO.
    """

    numerator: tuple[float, ...] | None
    denominator: tuple[float, ...]
    A: tuple[tuple[float, ...], ...]
    B: tuple[tuple[float, ...], ...]
    C: tuple[tuple[float, ...], ...]
    D: tuple[tuple[float, ...], ...]
    poles: tuple[complex, ...]
    zeros: tuple[complex, ...]
    dc_gain: float | None
    order: int
    input_count: int
    output_count: int


def require_continuous(model, feature: str) -> None:
    """Reject non-StateSpaceModel or discrete plants with a readable error."""
    if isinstance(model, DiscreteStateSpaceModel):
        raise ValueError(
            f"{feature} currently supports continuous-time plants only; "
            "discrete plants are simulated with simulate_discrete_state_space"
        )
    if not isinstance(model, StateSpaceModel):
        raise ValueError(f"{feature} expects a StateSpaceModel plant")


def require_siso(model, feature: str) -> None:
    """Reject MIMO plants for SISO-only analysis features."""
    if model.input_count != 1 or model.output_count != 1:
        raise ValueError(f"{feature} supports SISO plants only")


def siso_polynomials(
    A: np.ndarray, B: np.ndarray, C: np.ndarray, D: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Numerator and monic denominator of G(s) = C (sI - A)^-1 B + D.

    Coefficients are in descending powers of ``s``; the numerator has
    length ``order + 1`` (zero-padded). Uses the Faddeev-LeVerrier
    recurrence, so it is exact for teach-scale systems.
    """
    order = A.shape[0]
    denominator = np.asarray(np.poly(A), dtype=float)
    adjugate = np.zeros((order, order), dtype=float)
    alpha = np.zeros(order + 1, dtype=float)
    alpha[0] = 1.0
    numerator = np.zeros(order + 1, dtype=float)
    identity = np.eye(order)
    for k in range(1, order + 1):
        adjugate = A @ adjugate + alpha[k - 1] * identity
        alpha[k] = -float(np.trace(A @ adjugate)) / k
        numerator[k] = float((C @ adjugate @ B).item())
    numerator += float(D.item()) * denominator
    return numerator, denominator


def _trim_polynomial(coefficients: np.ndarray) -> tuple[float, ...]:
    """Drop negligible leading coefficients; keep at least one entry."""
    values = [float(value) for value in np.asarray(coefficients, dtype=float)]
    scale = max((abs(value) for value in values), default=0.0)
    while len(values) > 1 and abs(values[0]) <= 1e-12 * scale:
        values.pop(0)
    return tuple(values)


def normalize_plant(model: StateSpaceModel) -> PlantReport:
    """Report transfer-function coefficients, poles, zeros, and DC gain.

    SISO plants receive a transfer-function numerator; MIMO plants report
    ``numerator=None`` with an empty zero list. ``dc_gain`` equals
    ``D - C A^-1 B`` and is None when A is singular.
    """
    require_continuous(model, "normalize_plant")
    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)

    poles = [complex(value) for value in np.linalg.eigvals(A)]
    poles.sort(key=lambda value: (value.real, value.imag))

    numerator: tuple[float, ...] | None = None
    zeros: tuple[complex, ...] = ()
    dc_gain: float | None = None
    if model.input_count == 1 and model.output_count == 1:
        numerator_poly, _ = siso_polynomials(A, B, C, D)
        numerator = _trim_polynomial(numerator_poly)
        zero_roots = np.roots(np.asarray(numerator, dtype=float))
        zeros = tuple(
            sorted(
                (complex(value) for value in zero_roots),
                key=lambda value: (value.real, value.imag),
            )
        )
        try:
            solution = np.linalg.solve(A, -B[:, 0])
            # G(0) = C (0 - A)^-1 B + D = -C A^-1 B + D = C solution + D.
            candidate = float(D.item() + (C @ solution).item())
        except np.linalg.LinAlgError:
            candidate = None
        dc_gain = candidate if candidate is not None and np.isfinite(candidate) else None

    return PlantReport(
        numerator=numerator,
        denominator=_trim_polynomial(np.poly(A)),
        A=tuple(tuple(float(v) for v in row) for row in A),
        B=tuple(tuple(float(v) for v in row) for row in B),
        C=tuple(tuple(float(v) for v in row) for row in C),
        D=tuple(tuple(float(v) for v in row) for row in D),
        poles=tuple(poles),
        zeros=zeros,
        dc_gain=dc_gain,
        order=model.state_count,
        input_count=model.input_count,
        output_count=model.output_count,
    )


def evaluate_siso_response(model: StateSpaceModel, omega_rads) -> np.ndarray:
    """Sample G(jw) for a SISO continuous plant on a rad/s frequency grid.

    Returns a complex numpy array aligned with ``omega_rads``. Used by the
    margins and Nyquist modules; educational accuracy only.
    """
    require_continuous(model, "frequency evaluation")
    require_siso(model, "frequency evaluation")
    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    omega = np.asarray(omega_rads, dtype=float)
    if omega.ndim != 1 or omega.size == 0:
        raise ValueError("omega_rads must be a nonempty one-dimensional sequence")
    if not np.all(np.isfinite(omega)) or np.any(omega <= 0):
        raise ValueError("omega_rads values must be finite and greater than zero")

    identity = np.eye(model.state_count, dtype=complex)
    values = np.empty(omega.size, dtype=complex)
    for index, frequency in enumerate(omega):
        try:
            transfer = C @ np.linalg.solve(1j * frequency * identity - A, B) + D
        except np.linalg.LinAlgError as error:
            raise ValueError(f"frequency response solve failed at {frequency:g} rad/s") from error
        values[index] = complex(transfer.item())
    return values
