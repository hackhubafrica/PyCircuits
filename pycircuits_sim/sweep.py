"""One-parameter-at-a-time simulation sweeps."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import math

from .buck import BuckConfig, SimulationResult, simulate_buck
from .ir import IrMixin


SWEEPABLE_PARAMETERS = {
    "inductance",
    "capacitance",
    "load_resistance",
    "duty_cycle",
}


@dataclass(frozen=True)
class SweepRun(IrMixin):
    parameter: str
    value: float
    result: SimulationResult


def run_parameter_sweep(
    base_config: BuckConfig,
    parameter: str,
    values: Sequence[float],
) -> list[SweepRun]:
    """Run the same circuit while varying one supported parameter."""
    if parameter not in SWEEPABLE_PARAMETERS:
        supported = ", ".join(sorted(SWEEPABLE_PARAMETERS))
        raise ValueError(f"unsupported sweep parameter {parameter!r}; choose from {supported}")
    if isinstance(values, (str, bytes)) or len(values) < 2:
        raise ValueError("a parameter sweep requires at least two values")

    checked_values: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("sweep values must be numbers")
        if not math.isfinite(value):
            raise ValueError("sweep values must be finite")
        checked_values.append(float(value))

    if len(set(checked_values)) != len(checked_values):
        raise ValueError("sweep values must be unique")

    runs = []
    for value in checked_values:
        config = replace(base_config, **{parameter: value})
        runs.append(SweepRun(parameter, value, simulate_buck(config)))
    return runs