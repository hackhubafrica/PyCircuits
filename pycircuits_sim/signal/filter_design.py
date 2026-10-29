"""Analog filter design: Butterworth and Chebyshev Type I.

Pure numpy core: pole placement and frequency transformations for low-pass
and high-pass analog filters. When the optional ``pycircuits-sim[control]``
extra is installed, scipy.signal.butter/cheby1 are used as a cross-check.

Educational tool: designs are teach-scale, not production filter designs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..ir import IrMixin
from ..optional import try_import_scipy


@dataclass(frozen=True)
class FilterSpec(IrMixin):
    """Specification for an analog filter design.

    ``filter_type`` selects the prototype: "butterworth" (maximally flat)
    or "chebyshev1" (equiripple passband). ``kind`` selects
    "lowpass" or "highpass". ``cutoff_rad_s`` is the -3 dB corner
    frequency in rad/s. ``ripple_db`` is the passband ripple in dB for
    Chebyshev Type I (ignored for Butterworth).
    """

    filter_type: str
    kind: str
    order: int
    cutoff_rad_s: float
    ripple_db: float = 1.0

    def __post_init__(self) -> None:
        if self.filter_type not in ("butterworth", "chebyshev1"):
            raise ValueError(
                f"unknown filter_type {self.filter_type!r}; "
                "choose 'butterworth' or 'chebyshev1'"
            )
        if self.kind not in ("lowpass", "highpass"):
            raise ValueError(
                f"unknown kind {self.kind!r}; choose 'lowpass' or 'highpass'"
            )
        if not isinstance(self.order, (int, np.integer)) or self.order < 1:
            raise ValueError("order must be a positive integer")
        if not math.isfinite(self.cutoff_rad_s) or self.cutoff_rad_s <= 0:
            raise ValueError("cutoff_rad_s must be finite and greater than zero")
        if self.filter_type == "chebyshev1":
            if not math.isfinite(self.ripple_db) or self.ripple_db <= 0:
                raise ValueError("ripple_db must be finite and greater than zero")
        object.__setattr__(self, "order", int(self.order))
        object.__setattr__(self, "cutoff_rad_s", float(self.cutoff_rad_s))
        object.__setattr__(self, "ripple_db", float(self.ripple_db))


@dataclass(frozen=True)
class FilterDesignResult(IrMixin):
    """Result of an analog filter design.

    ``numerator`` and ``denominator`` are the transfer-function coefficients
    in descending powers of ``s``. ``sos`` is a tuple of second-order
    sections, each as ``(num, den)`` coefficient pairs. The frequency
    response is evaluated on a logarithmic grid for plotting.
    """

    spec: FilterSpec
    numerator: tuple[float, ...]
    denominator: tuple[float, ...]
    sos: tuple[tuple[tuple[float, ...], tuple[float, ...]], ...]
    frequencies_rad_s: tuple[float, ...]
    magnitude_db: tuple[float, ...]
    phase_deg: tuple[float, ...]


def _butterworth_poles(order: int) -> list[complex]:
    poles: list[complex] = []
    for k in range(order):
        angle = (2 * k + order + 1) * math.pi / (2 * order)
        poles.append(complex(math.cos(angle), math.sin(angle)))
    return poles


def _chebyshev1_poles(order: int, ripple_db: float) -> list[complex]:
    epsilon = math.sqrt(10.0 ** (ripple_db / 10.0) - 1.0)
    xi = math.asinh(1.0 / epsilon) / order
    sinh_xi = math.sinh(xi)
    cosh_xi = math.cosh(xi)
    poles: list[complex] = []
    for k in range(order):
        beta = (2 * k + 1) * math.pi / (2 * order)
        real = -sinh_xi * math.sin(beta)
        imag = cosh_xi * math.cos(beta)
        poles.append(complex(real, imag))
    return poles


def _poly_from_poles(poles: list[complex]) -> np.ndarray:
    return np.poly(np.asarray(poles, dtype=complex)).real


def _scale_polynomial_for_cutoff(coeffs: np.ndarray, cutoff: float) -> np.ndarray:
    """Frequency-scale a monic polynomial: P(s) -> P(s/cutoff) * cutoff^n.

    Coefficient of s^(n-k) is multiplied by cutoff^k.
    """
    order = coeffs.size - 1
    scaled = np.zeros(order + 1, dtype=float)
    for k in range(order + 1):
        scaled[k] = coeffs[k] * cutoff ** k
    return scaled


def _sos_from_poles(
    poles: list[complex],
    overall_gain: float,
    order: int,
    kind: str,
) -> tuple[tuple[tuple[float, ...], tuple[float, ...]], ...]:
    remaining = list(poles)
    sections: list[tuple[tuple[float, ...], tuple[float, ...]]] = []
    s_factors_remaining = order if kind == "highpass" else 0

    while remaining:
        pivot = remaining.pop(0)
        if abs(pivot.imag) < 1e-10:
            den = (1.0, -float(pivot.real))
            if kind == "lowpass":
                num = (0.0, 1.0)
            elif s_factors_remaining > 0:
                num = (1.0, 0.0)
                s_factors_remaining -= 1
            else:
                num = (1.0,)
            sections.append((num, den))
        else:
            conj = complex(pivot.real, -pivot.imag)
            match_index = next(
                i for i, p in enumerate(remaining) if abs(p - conj) < 1e-8
            )
            remaining.pop(match_index)
            den = (1.0, -2.0 * pivot.real, abs(pivot) ** 2)
            if kind == "lowpass":
                num = (0.0, 0.0, 1.0)
            elif s_factors_remaining >= 2:
                num = (1.0, 0.0, 0.0)
                s_factors_remaining -= 2
            elif s_factors_remaining == 1:
                num = (0.0, 1.0, 0.0)
                s_factors_remaining -= 1
            else:
                num = (0.0, 0.0, 1.0)
            sections.append((num, den))

    if sections and overall_gain != 1.0:
        first_num, first_den = sections[0]
        scaled_num = tuple(overall_gain * v for v in first_num)
        sections[0] = (scaled_num, first_den)

    return tuple(sections)


def _evaluate_response(
    numerator: np.ndarray, denominator: np.ndarray, frequencies: np.ndarray
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    magnitude_db: list[float] = []
    phase_deg: list[float] = []
    for omega in frequencies:
        s = 1j * omega
        num_val = np.polyval(numerator, s)
        den_val = np.polyval(denominator, s)
        if abs(den_val) < 1e-16:
            magnitude_db.append(-320.0)
            phase_deg.append(0.0)
        else:
            h = num_val / den_val
            magnitude_db.append(20.0 * math.log10(max(abs(h), 1e-16)))
            phase_deg.append(math.degrees(math.atan2(h.imag, h.real)))
    return tuple(magnitude_db), tuple(phase_deg)


def _trim_leading_zeros(coeffs: np.ndarray) -> tuple[float, ...]:
    values = [float(v) for v in np.asarray(coeffs, dtype=float)]
    scale = max((abs(v) for v in values), default=0.0)
    while len(values) > 1 and abs(values[0]) <= 1e-12 * scale:
        values.pop(0)
    return tuple(values)


def design_filter(spec: FilterSpec) -> FilterDesignResult:
    order = spec.order
    cutoff = spec.cutoff_rad_s

    if spec.filter_type == "butterworth":
        poles = _butterworth_poles(order)
    else:
        poles = _chebyshev1_poles(order, spec.ripple_db)

    den_norm = _poly_from_poles(poles)
    den_scaled = _scale_polynomial_for_cutoff(den_norm, cutoff)

    if spec.kind == "lowpass":
        numerator = np.array([cutoff ** order], dtype=float)
        denominator = den_scaled
        overall_gain = float(cutoff ** order)
    else:
        denominator = den_norm[::-1].copy()
        numerator = np.zeros(order + 1, dtype=float)
        numerator[0] = 1.0
        overall_gain = 1.0

    scipy = try_import_scipy()
    if scipy is not None:
        from scipy import signal as scipy_signal
        if spec.filter_type == "butterworth":
            sp_num, sp_den = scipy_signal.butter(
                order, cutoff, analog=True, output="ba"
            )
        else:
            sp_num, sp_den = scipy_signal.cheby1(
                order, spec.ripple_db, cutoff, analog=True, output="ba"
            )
        sp_poles = np.roots(np.asarray(sp_den, dtype=float))
        our_poles = np.roots(denominator)
        sp_sorted = sorted(sp_poles.tolist(), key=lambda p: (p.real, p.imag))
        our_sorted = sorted(our_poles.tolist(), key=lambda p: (p.real, p.imag))
        for sp_p, our_p in zip(sp_sorted, our_sorted, strict=True):
            if abs(sp_p - our_p) > 1e-6:
                raise ValueError(
                    "scipy cross-check failed: pole mismatch in filter design"
                )

    num_trimmed = _trim_leading_zeros(numerator)
    den_trimmed = _trim_leading_zeros(denominator)

    scaled_poles = [p * cutoff for p in poles]
    sos = _sos_from_poles(scaled_poles, overall_gain, order, spec.kind)

    freq_min = max(cutoff / 100.0, 1e-3)
    freq_max = cutoff * 100.0
    frequencies = np.logspace(math.log10(freq_min), math.log10(freq_max), 400)
    num_array = np.asarray(num_trimmed, dtype=float)
    den_array = np.asarray(den_trimmed, dtype=float)
    magnitude_db, phase_deg = _evaluate_response(num_array, den_array, frequencies)

    return FilterDesignResult(
        spec=spec,
        numerator=num_trimmed,
        denominator=den_trimmed,
        sos=sos,
        frequencies_rad_s=tuple(float(v) for v in frequencies),
        magnitude_db=tuple(magnitude_db),
        phase_deg=tuple(phase_deg),
    )
