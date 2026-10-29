"""Post-processing measurements for simulated waveform runs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

from .ir import IrMixin
from .sweep import SweepRun


@dataclass(frozen=True)
class RunMetrics(IrMixin):
    parameter: str
    value: float
    steady_state_window_start_s: float
    steady_state_output_voltage_v: float
    peak_output_voltage_v: float
    peak_overshoot_percent: float | None
    settling_time_s: float | None
    output_voltage_ripple_pp_v: float
    inductor_current_ripple_pp_a: float


def measure_sweep(
    runs: list[SweepRun],
    steady_state_fraction: float = 0.1,
    settling_band: float = 0.02,
) -> list[RunMetrics]:
    """Measure final-window ripple, peak overshoot, and settling time per run.

    Steady-state voltage is estimated as the mean of the final fraction of
    samples. Settling time is the start of the final uninterrupted interval
    inside the configured band around that estimate.
    """
    if not runs:
        raise ValueError("cannot measure an empty parameter sweep")
    if not math.isfinite(steady_state_fraction) or not 0 < steady_state_fraction <= 1:
        raise ValueError("steady_state_fraction must be greater than zero and at most one")
    if not math.isfinite(settling_band) or not 0 < settling_band < 1:
        raise ValueError("settling_band must be greater than zero and less than one")

    parameter = runs[0].parameter
    if any(run.parameter != parameter for run in runs):
        raise ValueError("all runs must use the same sweep parameter")

    measurements = []
    for run in runs:
        result = run.result
        sample_count = len(result.time)
        if (
            sample_count == 0
            or len(result.output_voltage) != sample_count
            or len(result.inductor_current) != sample_count
        ):
            raise ValueError("each run must have aligned, nonempty waveform samples")

        window_start = min(
            sample_count - 1,
            int(sample_count * (1.0 - steady_state_fraction)),
        )
        steady_voltages = result.output_voltage[window_start:]
        steady_currents = result.inductor_current[window_start:]
        steady_voltage = fmean(steady_voltages)
        peak_voltage = max(result.output_voltage)
        overshoot = (
            max(0.0, peak_voltage - steady_voltage) / abs(steady_voltage) * 100.0
            if steady_voltage != 0
            else None
        )

        band_radius = abs(steady_voltage) * settling_band
        lower_bound = steady_voltage - band_radius
        upper_bound = steady_voltage + band_radius
        last_outside = next(
            (
                index
                for index in range(sample_count - 1, -1, -1)
                if not lower_bound <= result.output_voltage[index] <= upper_bound
            ),
            None,
        )
        if last_outside is None:
            settling_time = result.time[0]
        elif last_outside + 1 < sample_count:
            settling_time = result.time[last_outside + 1]
        else:
            settling_time = None

        measurements.append(
            RunMetrics(
                parameter=run.parameter,
                value=run.value,
                steady_state_window_start_s=result.time[window_start],
                steady_state_output_voltage_v=steady_voltage,
                peak_output_voltage_v=peak_voltage,
                peak_overshoot_percent=overshoot,
                settling_time_s=settling_time,
                output_voltage_ripple_pp_v=max(steady_voltages) - min(steady_voltages),
                inductor_current_ripple_pp_a=max(steady_currents) - min(steady_currents),
            )
        )
    return measurements
