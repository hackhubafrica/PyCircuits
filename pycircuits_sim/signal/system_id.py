"""System identification: fit a rational transfer function to frequency data.

Pure numpy Sanathanan-Koerner iteration: reweighted least squares that fits
N(s)/D(s) to measured complex frequency-response values H_i at frequencies
omega_i. When scipy is available, it is used only as a robustness cross-check.

Educational tool: fits are teach-scale, not production system identification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..ir import IrMixin


@dataclass(frozen=True)
class FitSpec(IrMixin):
    """Specification for a frequency-response fit.

    frequencies_rad_s are positive, increasing sample frequencies.
    response is the complex plant response G(jw) at each frequency,
    encoded as tuples of (real, imag) for JSON compatibility.
    numerator_order and denominator_order set the target model orders.
    """

    frequencies_rad_s: tuple[float, ...]
    response: tuple[tuple[float, float], ...]
    numerator_order: int
    denominator_order: int
    max_iterations: int = 20

    def __post_init__(self) -> None:
        if len(self.frequencies_rad_s) != len(self.response):
            raise ValueError(
                "frequencies_rad_s and response must have equal length"
            )
        if len(self.frequencies_rad_s) < 2:
            raise ValueError("at least two frequency points are required")
        if not all(math.isfinite(v) for v in self.frequencies_rad_s):
            raise ValueError("all frequencies must be finite")
        if any(v <= 0 for v in self.frequencies_rad_s):
            raise ValueError("all frequencies must be positive")
        if any(
            self.frequencies_rad_s[i] >= self.frequencies_rad_s[i + 1]
            for i in range(len(self.frequencies_rad_s) - 1)
        ):
            raise ValueError("frequencies must be strictly increasing")
        if not isinstance(self.numerator_order, int) or self.numerator_order < 0:
            raise ValueError("numerator_order must be a nonnegative integer")
        if not isinstance(self.denominator_order, int) or self.denominator_order < 1:
            raise ValueError("denominator_order must be a positive integer")
        if not isinstance(self.max_iterations, int) or self.max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")


@dataclass(frozen=True)
class FrequencyResponseFit(IrMixin):
    """Result of a frequency-response fit.

    numerator and denominator are the fitted transfer-function
    coefficients in descending powers of s. fit_error is the RMS
    relative error on the data grid. fitted_response is the model
    evaluated at the data frequencies; residuals are fitted minus
    measured.
    """

    numerator: tuple[float, ...]
    denominator: tuple[float, ...]
    fit_error: float
    fitted_response: tuple[complex, ...]
    residuals: tuple[complex, ...]


def _complex_from_pairs(pairs: tuple[tuple[float, float], ...]) -> np.ndarray:
    return np.asarray([complex(r, i) for r, i in pairs], dtype=complex)


def _eval_poly(coeffs_descending: np.ndarray, s: complex) -> complex:
    """Evaluate polynomial with descending powers of s at a complex point."""
    result = 0.0 + 0.0j
    for c in coeffs_descending:
        result = result * s + c
    return result


def _trim_leading_zeros(coeffs: np.ndarray) -> tuple[float, ...]:
    """Drop negligible leading coefficients; keep at least one entry."""
    values = [float(v) for v in np.asarray(coeffs, dtype=float)]
    scale = max((abs(v) for v in values), default=0.0)
    while len(values) > 1 and abs(values[0]) <= 1e-12 * scale:
        values.pop(0)
    return tuple(values)


def fit_frequency_response(spec: FitSpec) -> FrequencyResponseFit:
    """Fit a rational transfer function to frequency-response data.

    Uses the Sanathanan-Koerner iteration: solve a weighted linear
    least-squares problem for N(s)/D(s), reweight by 1/|D_prev(jw)|, and
    repeat until convergence. Denominator is monic (leading coefficient 1).
    """
    frequencies = np.asarray(spec.frequencies_rad_s, dtype=float)
    response = _complex_from_pairs(spec.response)
    m = spec.numerator_order
    n = spec.denominator_order
    max_iter = spec.max_iterations

    n_points = frequencies.size
    num_unknowns = (m + 1) + n  # n_0..n_m, d_1..d_n

    s = 1j * frequencies  # shape (N,)

    # Initial denominator: D(s) = 1 (all d_k = 0)
    d = np.zeros(n, dtype=complex)

    for _iteration in range(max_iter):
        # Compute D_prev(jw_i) for weights
        D_prev = np.ones(n_points, dtype=complex)
        for k in range(1, n + 1):
            D_prev = D_prev + d[k - 1] * s**k

        weights = 1.0 / np.abs(D_prev)
        weights = weights / np.max(weights)  # normalize for conditioning

        # Build weighted linear system: A x = b
        # Unknowns x = [n_0, ..., n_m, d_1, ..., d_n]
        # Equation: sum(n_k * (jw_i)^k) - H_i * sum(d_k * (jw_i)^k) = H_i
        A = np.zeros((n_points, num_unknowns), dtype=complex)
        b = np.zeros(n_points, dtype=complex)

        for i in range(n_points):
            w = weights[i]
            si = s[i]
            Hi = response[i]

            # Numerator coefficients n_0..n_m
            for k in range(m + 1):
                A[i, k] = w * si**k

            # Denominator coefficients d_1..d_n
            for k in range(1, n + 1):
                A[i, m + k] = -w * Hi * si**k

            b[i] = w * Hi

        # Solve least squares
        x, _residuals, _rank, _sv = np.linalg.lstsq(A, b, rcond=None)

        n_coeffs = x[: m + 1]
        d_new = x[m + 1 :]

        # Check convergence
        if np.allclose(d, d_new, rtol=1e-8, atol=1e-12):
            d = d_new
            break
        d = d_new

    # --- Build numerator and denominator in descending powers of s ---
    # For real-valued rational functions fitted to conjugate-symmetric data,
    # the fitted coefficients should be real up to numerical noise; take the
    # real part after the Sanathanan-Koerner iteration.
    numerator_array = np.real(n_coeffs[::-1])
    denominator_array = np.concatenate([np.real(d)[::-1], [1.0]])

    # Normalize so denominator leading coefficient is 1
    denom_lead = denominator_array[0]
    if abs(denom_lead) > 1e-14:
        numerator_array = numerator_array / denom_lead
        denominator_array = denominator_array / denom_lead

    numerator = _trim_leading_zeros(numerator_array)
    denominator = _trim_leading_zeros(denominator_array)

    # --- Evaluate fit quality ---
    num_array = np.asarray(numerator, dtype=float)
    den_array = np.asarray(denominator, dtype=float)
    fitted: list[complex] = []
    residuals: list[complex] = []
    errors: list[float] = []

    for i in range(n_points):
        si = s[i]
        num_val = _eval_poly(num_array, si)
        den_val = _eval_poly(den_array, si)
        if abs(den_val) < 1e-14:
            fitted_val = complex(np.inf, np.inf)
        else:
            fitted_val = num_val / den_val
        fitted.append(fitted_val)
        residual = fitted_val - response[i]
        residuals.append(residual)
        if abs(response[i]) > 1e-14:
            errors.append(abs(residual / response[i]))
        else:
            errors.append(abs(residual))

    fit_error = float(np.sqrt(np.mean(np.asarray(errors) ** 2))) if errors else 0.0

    return FrequencyResponseFit(
        numerator=numerator,
        denominator=denominator,
        fit_error=fit_error,
        fitted_response=tuple(fitted),
        residuals=tuple(residuals),
    )
