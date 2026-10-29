"""Step-response metrics for simulated output traces.

Pure numpy. Ports ControlKit's ``ct.step_info``-style measurements: rise
time (10% to 90% of the final value), settling time (last exit from a
relative band around the final value), overshoot percentage, peak, and peak
time. Definitions match python-control closely but are computed directly on
``simulate_state_space`` output traces. Educational tool.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..ir import IrMixin


@dataclass(frozen=True)
class StepMetrics(IrMixin):
    """Classical step-response measurements, all in seconds where timed."""

    rise_time_s: float | None
    settling_time_s: float | None
    overshoot_percent: float | None
    peak: float | None
    peak_time_s: float | None
    steady_state: float | None


def _crossing_time(
    times: np.ndarray, values: np.ndarray, level: float, rising: bool
) -> float | None:
    """First time the trace crosses ``level``, linearly interpolated."""
    for index in range(values.size - 1):
        a, b = float(values[index]), float(values[index + 1])
        if rising and a < level <= b:
            fraction = (level - a) / (b - a) if b != a else 0.0
            return float(times[index] + fraction * (times[index + 1] - times[index]))
        if not rising and a > level >= b:
            fraction = (a - level) / (a - b) if a != b else 0.0
            return float(times[index] + fraction * (times[index + 1] - times[index]))
    return None


def step_metrics(
    times: Sequence[float],
    values: Sequence[float],
    settling_band: float = 0.02,
) -> StepMetrics:
    """Measure rise time, settling time, overshoot, and peak of a trace.

    The steady state is the final sample. Rise time spans the 10% to 90%
    crossings of the final value. Settling time is the last exit from
    ``settling_band`` (relative) around the final value; None means the trace
    never re-entered the band. Overshoot is relative to the final value and
    None only when that value is zero.
    """
    t = np.asarray(times, dtype=float)
    y = np.asarray(values, dtype=float)
    if t.ndim != 1 or y.ndim != 1 or t.size != y.size or t.size < 2:
        raise ValueError(
            "times and values must be equal-length 1-D sequences of at least two samples"
        )
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        raise ValueError("times and values must contain only finite samples")
    if np.any(np.diff(t) <= 0):
        raise ValueError("times must be strictly increasing")
    if not math.isfinite(settling_band) or not 0 < settling_band < 1:
        raise ValueError("settling_band must be greater than zero and less than one")

    steady = float(y[-1])
    peak_index = int(np.argmax(np.abs(y)))
    peak = float(y[peak_index])
    peak_time = float(t[peak_index])

    overshoot: float | None = None
    if steady != 0.0:
        overshoot = max(0.0, (abs(peak) - abs(steady)) / abs(steady) * 100.0)

    rise_time: float | None = None
    if steady != 0.0:
        lower = 0.1 * steady
        upper = 0.9 * steady
        if steady > 0:
            t_low = _crossing_time(t, y, lower, rising=True)
            t_high = _crossing_time(t, y, upper, rising=True)
        else:
            t_low = _crossing_time(t, y, lower, rising=False)
            t_high = _crossing_time(t, y, upper, rising=False)
        if t_low is not None and t_high is not None:
            rise_time = t_high - t_low

    band_radius = abs(steady) * settling_band
    lower_bound = steady - band_radius
    upper_bound = steady + band_radius
    last_outside = None
    for index in range(y.size - 1, -1, -1):
        if not lower_bound <= y[index] <= upper_bound:
            last_outside = index
            break
    if last_outside is None:
        settling_time: float | None = float(t[0])
    elif last_outside + 1 < y.size:
        settling_time = float(t[last_outside + 1])
    else:
        settling_time = None

    return StepMetrics(
        rise_time_s=rise_time,
        settling_time_s=settling_time,
        overshoot_percent=overshoot,
        peak=peak,
        peak_time_s=peak_time,
        steady_state=steady,
    )
