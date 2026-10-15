"""Bode magnitude/phase with gain and phase margins for SISO plants.

Pure numpy core: margins are found by interpolating the existing
``frequency_response`` data (magnitude crossing 0 dB, phase crossing -180
degrees), matching the conventions of python-control's ``ct.margin``. When
the optional ``pycircuits-sim[control]`` extra is installed, ``ct.margin``
is preferred for the scalar margins and the numpy values are kept as a
cross-check in the result. Units: gain margin linear (and dB), phase margin
degrees, crossover frequencies rad/s. Educational tool.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np

from ..linear_systems import StateSpaceModel
from ..optional import try_import_control
from .plant import require_continuous, require_siso

MIN_DECIBELS = -320.0


@dataclass(frozen=True)
class MarginResult:
    """Bode samples plus classical margin verdicts.

    ``gain_margin`` is linear (1/|G| at the phase crossover); None means no
    finite phase crossover exists. ``phase_margin_deg`` is None when there is
    no gain crossover.
    """

    frequencies_rad_s: tuple[float, ...]
    magnitude_db: tuple[float, ...]
    phase_deg: tuple[float, ...]
    gain_margin: float | None
    gain_margin_db: float | None
    phase_margin_deg: float | None
    gain_crossover_rad_s: float | None
    phase_crossover_rad_s: float | None


def _finite(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _interpolated_crossing(
    grid: np.ndarray, values: np.ndarray, level: float
) -> float | None:
    """First grid interval crossing ``level``; interpolate in log of grid.

    Requires a strict sign change across the interval (a value that merely
    touches the level without changing sign is not a crossover), which keeps
    degenerate plants such as 1/(s^2 - k^2) - whose phase is constantly
    +/-180 degrees - from reporting a spurious phase crossover.
    """
    shifted = values - level
    for index in range(shifted.size - 1):
        a, b = float(shifted[index]), float(shifted[index + 1])
        if (a >= 0.0 and b < 0.0) or (a < 0.0 and b >= 0.0):
            if a == b:
                continue
            fraction = a / (a - b)
            log_grid = np.log(grid[index : index + 2])
            return float(
                math.exp(log_grid[0] + fraction * (log_grid[1] - log_grid[0]))
            )
    return None


def _value_at(grid: np.ndarray, values: np.ndarray, point: float) -> float:
    return float(np.interp(point, grid, values))


def _numpy_margins(
    frequencies: np.ndarray, magnitude_db: np.ndarray, phase_deg: np.ndarray
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    gain_crossover = _interpolated_crossing(frequencies, magnitude_db, 0.0)
    phase_crossover = _interpolated_crossing(frequencies, phase_deg, -180.0)

    gain_margin = gain_margin_db = phase_margin = None
    if phase_crossover is not None:
        magnitude_db_at_pc = _value_at(frequencies, magnitude_db, phase_crossover)
        gain_margin = 10.0 ** (-magnitude_db_at_pc / 20.0)
        gain_margin_db = -magnitude_db_at_pc
    if gain_crossover is not None:
        phase_margin = _value_at(frequencies, phase_deg, gain_crossover) + 180.0
    return (
        _finite(gain_margin),
        _finite(gain_margin_db),
        _finite(phase_margin),
        _finite(gain_crossover),
        _finite(phase_crossover),
    )


def _control_margins(
    model: StateSpaceModel,
) -> tuple[float | None, float | None, float | None, float | None, float | None] | None:
    """Scalar margins from python-control when the optional extra exists."""
    control = try_import_control()
    if control is None:
        return None
    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    try:
        gm, pm, wcg, wcp = control.margin(control.ss(A, B, C, D))
    except Exception:
        return None
    gm_value = _finite(gm)
    gm_db = _finite(20.0 * math.log10(gm_value)) if gm_value is not None and gm_value > 0 else None
    return gm_value, gm_db, _finite(pm), _finite(wcg), _finite(wcp)


def bode_margins(
    model: StateSpaceModel,
    frequencies_rad_s: Sequence[float] | None = None,
) -> MarginResult:
    """Compute Bode magnitude/phase and gain/phase margins for a SISO plant.

    ``frequencies_rad_s`` defaults to a 400-point logarithmic grid from
    1e-3 to 1e3 rad/s. Margins are None when the corresponding crossover does
    not exist on the grid (for example, a plant with no finite phase
    crossover has infinite gain margin).
    """
    require_continuous(model, "bode_margins")
    require_siso(model, "bode_margins")

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

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    identity = np.eye(model.state_count, dtype=complex)
    magnitude_db: list[float] = []
    phase_deg: list[float] = []
    for frequency in frequencies:
        try:
            transfer = C @ np.linalg.solve(1j * frequency * identity - A, B) + D
        except np.linalg.LinAlgError as error:
            raise ValueError(
                f"frequency response solve failed at {frequency:g} rad/s"
            ) from error
        value = complex(transfer.item())
        magnitude_db.append(
            max(MIN_DECIBELS, 20.0 * math.log10(max(abs(value), 1e-16)))
        )
        phase_deg.append(math.degrees(math.atan2(value.imag, value.real)))

    unwrapped = np.degrees(np.unwrap(np.radians(np.asarray(phase_deg))))
    magnitude_array = np.asarray(magnitude_db)
    computed = _numpy_margins(frequencies, magnitude_array, unwrapped)
    preferred = _control_margins(model)
    if preferred is not None and any(value is not None for value in preferred):
        gm, gm_db, pm, wcg, wcp = preferred
    else:
        gm, gm_db, pm, wcg, wcp = computed

    return MarginResult(
        frequencies_rad_s=tuple(float(value) for value in frequencies),
        magnitude_db=tuple(magnitude_db),
        phase_deg=tuple(float(value) for value in unwrapped),
        gain_margin=gm,
        gain_margin_db=gm_db,
        phase_margin_deg=pm,
        gain_crossover_rad_s=wcg,
        phase_crossover_rad_s=wcp,
    )

