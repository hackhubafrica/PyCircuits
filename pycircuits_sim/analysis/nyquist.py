"""Nyquist response for SISO continuous-time plants.

Pure numpy. Reuses the shared ``evaluate_siso_response`` helper so the
imaginary-axis sweep is identical to the Bode path. Educational tool: the
plot is G(jw) over a positive frequency grid; encirclement counting and
stability conclusions are left to the stability module and the reader.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np

from ..linear_systems import StateSpaceModel
from .plant import evaluate_siso_response, require_continuous, require_siso


@dataclass(frozen=True)
class NyquistResult:
    """Samples of G(jw) parameterized by rad/s frequency."""

    frequencies_rad_s: tuple[float, ...]
    real: tuple[float, ...]
    imaginary: tuple[float, ...]


def nyquist_response(
    model: StateSpaceModel,
    frequencies_rad_s: Sequence[float] | None = None,
) -> NyquistResult:
    """Evaluate G(jw) on a frequency grid for a SISO plant.

    ``frequencies_rad_s`` defaults to a 400-point logarithmic grid from
    1e-3 to 1e3 rad/s. Only positive frequencies are sampled; mirror them
    for the conjugate half of the full Nyquist contour.
    """
    require_continuous(model, "nyquist_response")
    require_siso(model, "nyquist_response")

    if frequencies_rad_s is None:
        frequencies = np.logspace(-3.0, 3.0, 400)
    else:
        frequencies = np.asarray(frequencies_rad_s, dtype=float)
        if (
            frequencies.ndim != 1
            or frequencies.size < 2
            or not np.all(np.isfinite(frequencies))
            or np.any(frequencies <= 0)
        ):
            raise ValueError(
                "frequencies_rad_s must be an increasing sequence of "
                "positive finite values"
            )

    response = evaluate_siso_response(model, frequencies)
    return NyquistResult(
        frequencies_rad_s=tuple(float(value) for value in frequencies),
        real=tuple(float(value) for value in np.real(response)),
        imaginary=tuple(float(value) for value in np.imag(response)),
    )
