"""Fixed-step buck converter simulation using backward Euler integration."""

from __future__ import annotations

from dataclasses import dataclass
import math
from .ir import IrMixin


def _step_count(stop_time: float, time_step: float) -> int:
    ratio = stop_time / time_step
    nearest_integer = round(ratio)
    if nearest_integer > 0 and math.isclose(
        ratio, nearest_integer, rel_tol=1e-12, abs_tol=0.0
    ):
        return nearest_integer
    return math.ceil(ratio)


@dataclass(frozen=True)
class BuckConfig(IrMixin):
    input_voltage: float
    duty_cycle: float
    switching_frequency: float
    inductance: float
    capacitance: float
    load_resistance: float
    time_step: float
    stop_time: float
    initial_current: float = 0.0
    initial_voltage: float = 0.0
    max_steps: int = 10_000_000

    def __post_init__(self) -> None:
        positive_values = {
            "switching_frequency": self.switching_frequency,
            "inductance": self.inductance,
            "capacitance": self.capacitance,
            "load_resistance": self.load_resistance,
            "time_step": self.time_step,
            "stop_time": self.stop_time,
        }
        for name, value in positive_values.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite value greater than zero")

        nonnegative_values = {
            "input_voltage": self.input_voltage,
            "initial_current": self.initial_current,
            "initial_voltage": self.initial_voltage,
        }
        for name, value in nonnegative_values.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"{name} must be a finite value greater than or equal to zero"
                )

        if not math.isfinite(self.duty_cycle) or not 0 <= self.duty_cycle <= 1:
            raise ValueError("duty_cycle must be between zero and one")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least one")
        if _step_count(self.stop_time, self.time_step) > self.max_steps:
            raise ValueError("requested simulation exceeds max_steps")


@dataclass(frozen=True)
class SimulationResult(IrMixin):
    time: list[float]
    inductor_current: list[float]
    output_voltage: list[float]
    switch_on: list[bool]


class BuckPlant:
    """Stateful ideal buck power stage advanced one simulation step at a time."""

    def __init__(self, config: BuckConfig):
        self.config = config
        self.inductor_current = config.initial_current
        self.output_voltage = config.initial_voltage

    def step(self, time: float, step_size: float, duty_cycle: float) -> bool:
        """Advance the circuit by one step and return the sampled switch state."""
        config = self.config
        period = 1.0 / config.switching_frequency
        phase = (time % period) / period
        switch_on = phase < duty_cycle

        inductance_scale = step_size / config.inductance
        capacitance_scale = step_size / config.capacitance
        load_term = capacitance_scale / config.load_resistance
        source_current = (
            self.inductor_current + inductance_scale * config.input_voltage
            if switch_on
            else self.inductor_current
        )
        determinant = 1.0 + load_term + inductance_scale * capacitance_scale

        next_current = (
            source_current * (1.0 + load_term)
            - inductance_scale * self.output_voltage
        ) / determinant
        next_voltage = (
            self.output_voltage + capacitance_scale * source_current
        ) / determinant

        if not switch_on and next_current < 0:
            next_current = 0.0
            next_voltage = self.output_voltage / (1.0 + load_term)

        self.inductor_current = next_current
        self.output_voltage = next_voltage
        return switch_on


def simulate_buck(config: BuckConfig) -> SimulationResult:
    """Simulate an ideal-switch, ideal-diode buck converter."""
    step_count = _step_count(config.stop_time, config.time_step)
    plant = BuckPlant(config)

    times = [0.0]
    currents = [plant.inductor_current]
    voltages = [plant.output_voltage]
    switch_states = [config.duty_cycle > 0]

    for step_index in range(step_count):
        step_start = step_index * config.time_step
        step_size = min(config.time_step, config.stop_time - step_start)
        plant.step(step_start, step_size, config.duty_cycle)
        times.append(min(step_start + step_size, config.stop_time))
        currents.append(plant.inductor_current)
        voltages.append(plant.output_voltage)
        period = 1.0 / config.switching_frequency
        end_phase = (times[-1] % period) / period
        switch_states.append(end_phase < config.duty_cycle)

    return SimulationResult(times, currents, voltages, switch_states)
