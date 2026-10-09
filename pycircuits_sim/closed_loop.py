"""Sampled PID control of the buck converter plant."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .buck import BuckConfig, BuckPlant, SimulationResult, _step_count


@dataclass(frozen=True)
class PIDConfig:
    kp: float
    ki: float
    kd: float
    sample_time: float
    duty_min: float = 0.0
    duty_max: float = 0.95

    def __post_init__(self) -> None:
        for name in ("kp", "ki", "kd"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(self.sample_time) or self.sample_time <= 0:
            raise ValueError("sample_time must be finite and greater than zero")
        if not math.isfinite(self.duty_min) or not 0 <= self.duty_min <= 1:
            raise ValueError("duty_min must be between zero and one")
        if not math.isfinite(self.duty_max) or not 0 <= self.duty_max <= 1:
            raise ValueError("duty_max must be between zero and one")
        if self.duty_min >= self.duty_max:
            raise ValueError("duty_min must be less than duty_max")


@dataclass(frozen=True)
class ReferenceStep:
    initial_voltage: float
    final_voltage: float
    step_time: float

    def __post_init__(self) -> None:
        for name in ("initial_voltage", "final_voltage"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(self.step_time) or self.step_time < 0:
            raise ValueError("step_time must be finite and nonnegative")

    def at(self, time: float) -> float:
        return self.initial_voltage if time < self.step_time else self.final_voltage


@dataclass(frozen=True)
class ClosedLoopConfig:
    plant: BuckConfig
    controller: PIDConfig
    reference: ReferenceStep

    def __post_init__(self) -> None:
        if self.reference.step_time > self.plant.stop_time:
            raise ValueError("reference step_time cannot exceed simulation stop_time")
        ratio = self.controller.sample_time / self.plant.time_step
        integer_ratio = round(ratio)
        if integer_ratio < 1 or not math.isclose(
            ratio, integer_ratio, rel_tol=1e-10, abs_tol=1e-12
        ):
            raise ValueError(
                "controller sample_time must be an integer multiple of plant time_step"
            )


@dataclass(frozen=True)
class ClosedLoopResult:
    time: list[float]
    inductor_current: list[float]
    output_voltage: list[float]
    switch_on: list[bool]
    reference_voltage: list[float]
    error: list[float]
    proportional_term: list[float]
    integral_term: list[float]
    derivative_term: list[float]
    duty_cycle: list[float]


def simulate_closed_loop(config: ClosedLoopConfig) -> ClosedLoopResult:
    """Run a buck stage with a sampled PID and held PWM duty command.

    The derivative acts on measured output voltage, avoiding a derivative kick
    when the reference changes. Integral accumulation uses conditional
    anti-windup at the configured duty limits.
    """
    plant_config = config.plant
    controller = config.controller
    controller_steps = round(controller.sample_time / plant_config.time_step)
    step_count = _step_count(plant_config.stop_time, plant_config.time_step)
    plant = BuckPlant(plant_config)

    integral_state = 0.0
    previous_measurement = plant.output_voltage

    def update_controller(
        setpoint: float,
        measurement: float,
        prior_measurement: float,
        prior_integral: float,
    ) -> tuple[float, float, tuple[float, float, float]]:
        control_error = setpoint - measurement
        p_term = controller.kp * control_error
        d_term = -controller.kd * (measurement - prior_measurement) / controller.sample_time
        candidate_integral = prior_integral + (
            controller.ki * control_error * controller.sample_time
        )
        unconstrained = p_term + candidate_integral + d_term
        if not (
            unconstrained > controller.duty_max and control_error > 0
        ) and not (
            unconstrained < controller.duty_min and control_error < 0
        ):
            prior_integral = candidate_integral
        terms = (p_term, prior_integral, d_term)
        command = min(
            controller.duty_max,
            max(controller.duty_min, sum(terms)),
        )
        return command, prior_integral, terms

    initial_reference = config.reference.at(0.0)
    held_duty, integral_state, held_terms = update_controller(
        initial_reference,
        plant.output_voltage,
        previous_measurement,
        integral_state,
    )

    time = [0.0]
    current = [plant.inductor_current]
    voltage = [plant.output_voltage]
    reference = [initial_reference]
    error = [reference[0] - voltage[0]]
    proportional = [held_terms[0]]
    integral = [held_terms[1]]
    derivative = [held_terms[2]]
    duty = [held_duty]
    switch_on = [False]

    for step_index in range(step_count):
        step_start = step_index * plant_config.time_step
        step_size = min(
            plant_config.time_step,
            plant_config.stop_time - step_start,
        )
        if step_index > 0 and step_index % controller_steps == 0:
            setpoint = config.reference.at(step_start)
            held_duty, integral_state, held_terms = update_controller(
                setpoint,
                plant.output_voltage,
                previous_measurement,
                integral_state,
            )
            previous_measurement = plant.output_voltage

        active_switch = plant.step(step_start, step_size, held_duty)
        sample_time = min(step_start + step_size, plant_config.stop_time)
        sample_reference = config.reference.at(sample_time)

        time.append(sample_time)
        current.append(plant.inductor_current)
        voltage.append(plant.output_voltage)
        reference.append(sample_reference)
        error.append(sample_reference - plant.output_voltage)
        proportional.append(held_terms[0])
        integral.append(held_terms[1])
        derivative.append(held_terms[2])
        duty.append(held_duty)
        switch_on.append(active_switch)

    return ClosedLoopResult(
        time=time,
        inductor_current=current,
        output_voltage=voltage,
        switch_on=switch_on,
        reference_voltage=reference,
        error=error,
        proportional_term=proportional,
        integral_term=integral,
        derivative_term=derivative,
        duty_cycle=duty,
    )