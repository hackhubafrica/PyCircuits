"""State-space and transfer-function plant simulation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .buck import _step_count


@dataclass(frozen=True)
class StateSpaceModel:
    """Continuous-time LTI model: x_dot = A x + B u, y = C x + D u."""

    A: tuple[tuple[float, ...], ...]
    B: tuple[tuple[float, ...], ...]
    C: tuple[tuple[float, ...], ...]
    D: tuple[tuple[float, ...], ...]

    @classmethod
    def from_matrices(
        cls,
        A: Sequence[Sequence[float]],
        B: Sequence[Sequence[float]],
        C: Sequence[Sequence[float]],
        D: Sequence[Sequence[float]],
    ) -> StateSpaceModel:
        arrays = {
            "A": _matrix(A, "A"),
            "B": _matrix(B, "B"),
            "C": _matrix(C, "C"),
            "D": _matrix(D, "D"),
        }
        state_count = arrays["A"].shape[0]
        if state_count == 0 or arrays["A"].shape[1] != state_count:
            raise ValueError("A must be a nonempty square matrix")
        input_count = arrays["B"].shape[1]
        output_count = arrays["C"].shape[0]
        if input_count == 0 or output_count == 0:
            raise ValueError("model must have at least one input and output")
        if arrays["B"].shape[0] != state_count:
            raise ValueError("B row count must match the state count")
        if arrays["C"].shape[1] != state_count:
            raise ValueError("C column count must match the state count")
        if arrays["D"].shape != (output_count, input_count):
            raise ValueError("D shape must be (output_count, input_count)")
        return cls(*(_as_tuple(arrays[name]) for name in ("A", "B", "C", "D")))

    @property
    def state_count(self) -> int:
        return len(self.A)

    @property
    def input_count(self) -> int:
        return len(self.B[0])

    @property
    def output_count(self) -> int:
        return len(self.C)


@dataclass(frozen=True)
class DiscreteStateSpaceModel:
    """Discrete-time LTI model: x[k+1] = A x[k] + B u[k]."""

    A: tuple[tuple[float, ...], ...]
    B: tuple[tuple[float, ...], ...]
    C: tuple[tuple[float, ...], ...]
    D: tuple[tuple[float, ...], ...]
    sample_time: float

    @classmethod
    def from_matrices(
        cls,
        A: Sequence[Sequence[float]],
        B: Sequence[Sequence[float]],
        C: Sequence[Sequence[float]],
        D: Sequence[Sequence[float]],
        sample_time: float,
    ) -> DiscreteStateSpaceModel:
        continuous_shape = StateSpaceModel.from_matrices(A, B, C, D)
        if not math.isfinite(sample_time) or sample_time <= 0:
            raise ValueError("sample_time must be finite and greater than zero")
        return cls(
            continuous_shape.A,
            continuous_shape.B,
            continuous_shape.C,
            continuous_shape.D,
            float(sample_time),
        )

    @property
    def state_count(self) -> int:
        return len(self.A)

    @property
    def input_count(self) -> int:
        return len(self.B[0])

    @property
    def output_count(self) -> int:
        return len(self.C)


@dataclass(frozen=True)
class LinearSimulationResult:
    time: list[float]
    inputs: dict[str, list[float]]
    states: dict[str, list[float]]
    outputs: dict[str, list[float]]


@dataclass(frozen=True)
class FrequencyResponseResult:
    frequencies_hz: list[float]
    response: list[list[list[complex]]]
    poles: list[complex]

    @property
    def magnitude_db(self) -> list[list[list[float]]]:
        return [
            [
                [20.0 * math.log10(max(abs(value), 1e-15)) for value in output_row]
                for output_row in frequency_slice
            ]
            for frequency_slice in self.response
        ]

    @property
    def phase_deg(self) -> list[list[list[float]]]:
        return [
            [
                [math.degrees(math.atan2(value.imag, value.real)) for value in output_row]
                for output_row in frequency_slice
            ]
            for frequency_slice in self.response
        ]


@dataclass(frozen=True)
class LinearPIDConfig:
    kp: float
    ki: float
    kd: float
    sample_time: float
    output_min: float = 0.0
    output_max: float = 1.0

    def __post_init__(self) -> None:
        for name in ("kp", "ki", "kd"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(self.sample_time) or self.sample_time <= 0:
            raise ValueError("sample_time must be finite and greater than zero")
        if not math.isfinite(self.output_min) or not math.isfinite(self.output_max):
            raise ValueError("controller output limits must be finite")
        if self.output_min >= self.output_max:
            raise ValueError("output_min must be less than output_max")


@dataclass(frozen=True)
class StepReference:
    initial: float
    final: float
    step_time: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.initial, self.final, self.step_time)):
            raise ValueError("reference values must be finite")
        if self.step_time < 0:
            raise ValueError("step_time must be nonnegative")

    def at(self, time: float) -> float:
        return self.initial if time < self.step_time else self.final


@dataclass(frozen=True)
class LinearClosedLoopResult:
    time: list[float]
    reference: list[float]
    output: list[float]
    error: list[float]
    control: list[float]
    proportional_term: list[float]
    integral_term: list[float]
    derivative_term: list[float]
    states: dict[str, list[float]]


def load_linear_plant(path: str | Path) -> tuple[StateSpaceModel | DiscreteStateSpaceModel, dict[str, Any]]:
    """Load a continuous/discrete state-space or proper transfer-function plant."""
    with Path(path).open(encoding="utf-8") as plant_file:
        data = json.load(plant_file)
    if not isinstance(data, dict):
        raise ValueError("linear plant JSON must contain an object")
    plant_type = data.get("type")
    if plant_type == "state_space":
        model = StateSpaceModel.from_matrices(
            data.get("A"), data.get("B"), data.get("C"), data.get("D")
        )
    elif plant_type == "discrete_state_space":
        model = DiscreteStateSpaceModel.from_matrices(
            data.get("A"), data.get("B"), data.get("C"), data.get("D"),
            data.get("sample_time"),
        )
    elif plant_type == "transfer_function":
        model = transfer_function_to_state_space(
            data.get("numerator"), data.get("denominator")
        )
    else:
        raise ValueError("plant type must be state_space, discrete_state_space, or transfer_function")
    return model, data


def _matrix(values: Sequence[Sequence[float]], name: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a rectangular numeric matrix") from error
    if result.ndim != 2 or not result.size:
        raise ValueError(f"{name} must be a nonempty two-dimensional matrix")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} entries must all be finite")
    return result


def _as_tuple(matrix: np.ndarray) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in matrix)


def transfer_function_to_state_space(
    numerator: Sequence[float], denominator: Sequence[float]
) -> StateSpaceModel:
    """Convert a proper SISO polynomial transfer function to controllable form.

    Coefficients are in descending powers of s. Improper functions and
    denominator polynomials with a zero leading coefficient are rejected.
    """
    num = np.asarray(numerator, dtype=float)
    den = np.asarray(denominator, dtype=float)
    if num.ndim != 1 or den.ndim != 1 or num.size == 0 or den.size < 2:
        raise ValueError("numerator and denominator must be nonempty 1-D arrays; denominator degree >= 1")
    if not np.all(np.isfinite(num)) or not np.all(np.isfinite(den)):
        raise ValueError("transfer-function coefficients must all be finite")
    if den[0] == 0:
        raise ValueError("denominator leading coefficient must be nonzero")
    num = num / den[0]
    den = den / den[0]
    if num.size > den.size:
        raise ValueError("improper transfer functions are not supported")

    order = den.size - 1
    padded_num = np.pad(num, (order + 1 - num.size, 0))
    A = np.zeros((order, order), dtype=float)
    A[0, :] = -den[1:]
    if order > 1:
        A[1:, :-1] = np.eye(order - 1)
    B = np.zeros((order, 1), dtype=float)
    B[0, 0] = 1.0
    D = np.array([[padded_num[0]]], dtype=float)
    C = (padded_num[1:] - den[1:] * padded_num[0]).reshape(1, order)
    return StateSpaceModel.from_matrices(A, B, C, D)


def logarithmic_frequency_grid(
    minimum_hz: float,
    maximum_hz: float,
    points_per_decade: int = 30,
) -> list[float]:
    """Create a logarithmically spaced frequency grid in hertz."""
    if not math.isfinite(minimum_hz) or minimum_hz <= 0:
        raise ValueError("minimum_hz must be finite and greater than zero")
    if not math.isfinite(maximum_hz) or maximum_hz <= minimum_hz:
        raise ValueError("maximum_hz must be finite and greater than minimum_hz")
    if points_per_decade < 2:
        raise ValueError("points_per_decade must be at least two")
    decade_count = math.log10(maximum_hz / minimum_hz)
    point_count = max(2, int(math.ceil(decade_count * points_per_decade)) + 1)
    return np.logspace(
        math.log10(minimum_hz), math.log10(maximum_hz), point_count
    ).tolist()


def frequency_response(
    model: StateSpaceModel,
    frequencies_hz: Sequence[float],
) -> FrequencyResponseResult:
    """Compute continuous-time MIMO response H(jw)=C(jwI-A)^-1 B + D.

    Frequencies are supplied in hertz. Response slices are ordered as
    ``response[frequency][output][input]``. Poles are the eigenvalues of A.
    """
    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError("frequencies_hz must be a nonempty one-dimensional sequence")
    if not np.all(np.isfinite(frequencies)) or np.any(frequencies <= 0):
        raise ValueError("frequencies_hz values must be finite and greater than zero")

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    identity = np.eye(model.state_count, dtype=complex)
    response: list[list[list[complex]]] = []
    for frequency in frequencies:
        omega = 2.0 * math.pi * frequency
        try:
            transfer = C @ np.linalg.solve(1j * omega * identity - A, B) + D
        except np.linalg.LinAlgError as error:
            raise ValueError(f"frequency response solve failed at {frequency:g} Hz") from error
        response.append(
            [[complex(value) for value in row] for row in transfer.tolist()]
        )

    poles = [complex(value) for value in np.linalg.eigvals(A)]
    poles.sort(key=lambda value: (value.real, value.imag))
    return FrequencyResponseResult(frequencies.tolist(), response, poles)


def discrete_frequency_response(
    model: DiscreteStateSpaceModel,
    frequencies_hz: Sequence[float],
) -> FrequencyResponseResult:
    """Compute discrete MIMO response H(exp(jwTs)) below Nyquist."""
    frequencies = np.asarray(frequencies_hz, dtype=float)
    nyquist_hz = 0.5 / model.sample_time
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError("frequencies_hz must be a nonempty one-dimensional sequence")
    if (
        not np.all(np.isfinite(frequencies))
        or np.any(frequencies <= 0)
        or np.any(frequencies >= nyquist_hz)
    ):
        raise ValueError(f"discrete frequencies must be greater than zero and below Nyquist ({nyquist_hz:g} Hz)")

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    identity = np.eye(model.state_count, dtype=complex)
    response: list[list[list[complex]]] = []
    for frequency in frequencies:
        z = np.exp(2j * math.pi * frequency * model.sample_time)
        try:
            transfer = C @ np.linalg.solve(z * identity - A, B) + D
        except np.linalg.LinAlgError as error:
            raise ValueError(f"discrete frequency response solve failed at {frequency:g} Hz") from error
        response.append([[complex(value) for value in row] for row in transfer.tolist()])
    poles = [complex(value) for value in np.linalg.eigvals(A)]
    poles.sort(key=lambda value: (abs(value), value.real, value.imag))
    return FrequencyResponseResult(frequencies.tolist(), response, poles)


def simulate_state_space(
    model: StateSpaceModel,
    time_step: float,
    stop_time: float,
    input_signal: Callable[[float], Sequence[float]],
    initial_state: Sequence[float] | None = None,
    max_steps: int = 2_000_000,
) -> LinearSimulationResult:
    """Simulate a continuous-time LTI plant using fixed-step backward Euler.

    Inputs are sampled at each timestep endpoint and held over the preceding
    integration interval. Initial outputs use the input at t=0.
    """
    if not math.isfinite(time_step) or time_step <= 0:
        raise ValueError("time_step must be finite and greater than zero")
    if not math.isfinite(stop_time) or stop_time <= 0:
        raise ValueError("stop_time must be finite and greater than zero")
    step_count = _step_count(stop_time, time_step)
    if step_count > max_steps:
        raise ValueError("requested simulation exceeds max_steps")

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    states = np.zeros(model.state_count, dtype=float) if initial_state is None else np.asarray(initial_state, dtype=float)
    if states.shape != (model.state_count,) or not np.all(np.isfinite(states)):
        raise ValueError("initial_state must have one finite value per state")

    times = [0.0]
    state_traces = {f"x{index + 1}": [float(value)] for index, value in enumerate(states)}
    input_traces = {f"u{index + 1}": [] for index in range(model.input_count)}
    output_traces = {f"y{index + 1}": [] for index in range(model.output_count)}

    def sample_input(time: float) -> np.ndarray:
        values = np.asarray(input_signal(time), dtype=float)
        if values.shape != (model.input_count,) or not np.all(np.isfinite(values)):
            raise ValueError(f"input_signal must return {model.input_count} finite values")
        return values

    initial_input = sample_input(0.0)
    for index, value in enumerate(initial_input):
        input_traces[f"u{index + 1}"].append(float(value))
    initial_output = C @ states + D @ initial_input
    for index, value in enumerate(initial_output):
        output_traces[f"y{index + 1}"].append(float(value))

    identity = np.eye(model.state_count)
    for step_index in range(step_count):
        time = min((step_index + 1) * time_step, stop_time)
        step_size = time - times[-1]
        input_values = sample_input(time)
        try:
            next_states = np.linalg.solve(
                identity - step_size * A,
                states + step_size * B @ input_values,
            )
        except np.linalg.LinAlgError as error:
            raise ValueError(f"backward-Euler state solve failed at t={time:g} s") from error
        output_values = C @ next_states + D @ input_values

        times.append(time)
        states = next_states
        for index, value in enumerate(states):
            state_traces[f"x{index + 1}"].append(float(value))
        for index, value in enumerate(input_values):
            input_traces[f"u{index + 1}"].append(float(value))
        for index, value in enumerate(output_values):
            output_traces[f"y{index + 1}"].append(float(value))

    return LinearSimulationResult(times, input_traces, state_traces, output_traces)


def simulate_discrete_state_space(
    model: DiscreteStateSpaceModel,
    stop_time: float,
    input_signal: Callable[[float], Sequence[float]],
    initial_state: Sequence[float] | None = None,
    max_steps: int = 2_000_000,
) -> LinearSimulationResult:
    """Simulate a discrete-time plant, sampling inputs once per model period."""
    if not math.isfinite(stop_time) or stop_time <= 0:
        raise ValueError("stop_time must be finite and greater than zero")
    step_count = int(math.floor(stop_time / model.sample_time + 1e-12))
    if step_count > max_steps:
        raise ValueError("requested simulation exceeds max_steps")

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    states = np.zeros(model.state_count, dtype=float) if initial_state is None else np.asarray(initial_state, dtype=float)
    if states.shape != (model.state_count,) or not np.all(np.isfinite(states)):
        raise ValueError("initial_state must have one finite value per state")

    def sample_input(time: float) -> np.ndarray:
        values = np.asarray(input_signal(time), dtype=float)
        if values.shape != (model.input_count,) or not np.all(np.isfinite(values)):
            raise ValueError(f"input_signal must return {model.input_count} finite values")
        return values

    times = [0.0]
    state_traces = {f"x{index + 1}": [float(value)] for index, value in enumerate(states)}
    input_traces = {f"u{index + 1}": [] for index in range(model.input_count)}
    output_traces = {f"y{index + 1}": [] for index in range(model.output_count)}
    for sample_index in range(step_count + 1):
        time = sample_index * model.sample_time
        input_values = sample_input(time)
        output_values = C @ states + D @ input_values
        if sample_index > 0:
            times.append(time)
            for index, value in enumerate(states):
                state_traces[f"x{index + 1}"].append(float(value))
        for index, value in enumerate(input_values):
            input_traces[f"u{index + 1}"].append(float(value))
        for index, value in enumerate(output_values):
            output_traces[f"y{index + 1}"].append(float(value))
        if sample_index < step_count:
            states = A @ states + B @ input_values

    return LinearSimulationResult(times, input_traces, state_traces, output_traces)


def simulate_discrete_state_space_pid(
    model: DiscreteStateSpaceModel,
    controller: LinearPIDConfig,
    reference: StepReference,
    stop_time: float,
    initial_state: Sequence[float] | None = None,
    max_steps: int = 2_000_000,
) -> LinearClosedLoopResult:
    """Run sampled PID feedback against a discrete-time SISO plant."""
    if model.input_count != 1 or model.output_count != 1:
        raise ValueError("PID feedback currently supports SISO plants only")
    if not math.isclose(model.D[0][0], 0.0, abs_tol=1e-15):
        raise ValueError("PID feedback currently requires D=0 to avoid an algebraic loop")
    if reference.step_time > stop_time:
        raise ValueError("reference step_time cannot exceed simulation stop_time")
    if not math.isfinite(stop_time) or stop_time <= 0:
        raise ValueError("stop_time must be finite and greater than zero")
    ratio = controller.sample_time / model.sample_time
    controller_steps = round(ratio)
    if controller_steps < 1 or not math.isclose(ratio, controller_steps, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("controller sample_time must be an integer multiple of plant sample_time")

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    states = np.zeros(model.state_count, dtype=float) if initial_state is None else np.asarray(initial_state, dtype=float)
    if states.shape != (model.state_count,) or not np.all(np.isfinite(states)):
        raise ValueError("initial_state must have one finite value per state")
    step_count = int(math.floor(stop_time / model.sample_time + 1e-12))
    if step_count > max_steps:
        raise ValueError("requested simulation exceeds max_steps")

    integral_state = 0.0
    previous_output = float((C @ states)[0])
    derivative_reference_output = previous_output
    control = min(controller.output_max, max(controller.output_min, controller.kp * (reference.at(0.0) - previous_output)))
    p_term = controller.kp * (reference.at(0.0) - previous_output)
    i_term = 0.0
    d_term = 0.0
    times: list[float] = []
    references: list[float] = []
    outputs: list[float] = []
    errors: list[float] = []
    controls: list[float] = []
    p_terms: list[float] = []
    i_terms: list[float] = []
    d_terms: list[float] = []
    state_traces = {f"x{index + 1}": [] for index in range(model.state_count)}

    for sample_index in range(step_count + 1):
        time = sample_index * model.sample_time
        output_value = float((C @ states)[0])
        if sample_index > 0 and sample_index % controller_steps == 0:
            error_value = reference.at(time) - output_value
            p_term = controller.kp * error_value
            d_term = -controller.kd * (output_value - derivative_reference_output) / controller.sample_time
            candidate_integral = integral_state + controller.ki * error_value * controller.sample_time
            candidate = p_term + candidate_integral + d_term
            if not ((candidate > controller.output_max and error_value > 0) or (candidate < controller.output_min and error_value < 0)):
                integral_state = candidate_integral
            i_term = integral_state
            control = min(controller.output_max, max(controller.output_min, p_term + i_term + d_term))
            derivative_reference_output = output_value

        reference_value = reference.at(time)
        times.append(time)
        references.append(reference_value)
        outputs.append(output_value)
        errors.append(reference_value - output_value)
        controls.append(control)
        p_terms.append(p_term)
        i_terms.append(i_term)
        d_terms.append(d_term)
        for index, value in enumerate(states):
            state_traces[f"x{index + 1}"].append(float(value))
        if sample_index < step_count:
            states = A @ states + B[:, 0] * control

    return LinearClosedLoopResult(times, references, outputs, errors, controls, p_terms, i_terms, d_terms, state_traces)


def simulate_state_space_pid(
    model: StateSpaceModel,
    controller: LinearPIDConfig,
    reference: StepReference,
    time_step: float,
    stop_time: float,
    initial_state: Sequence[float] | None = None,
    max_steps: int = 2_000_000,
) -> LinearClosedLoopResult:
    """Close a sampled PID loop around a SISO state-space plant."""
    if model.input_count != 1 or model.output_count != 1:
        raise ValueError("the initial PID loop supports SISO plants only")
    if not math.isclose(model.D[0][0], 0.0, abs_tol=1e-15):
        raise ValueError(
            "PID feedback currently requires D=0 to avoid an algebraic loop"
        )
    if reference.step_time > stop_time:
        raise ValueError("reference step_time cannot exceed simulation stop_time")
    if not math.isfinite(time_step) or time_step <= 0:
        raise ValueError("time_step must be finite and greater than zero")
    ratio = controller.sample_time / time_step
    controller_steps = round(ratio)
    if controller_steps < 1 or not math.isclose(ratio, controller_steps, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("controller sample_time must be an integer multiple of time_step")
    step_count = _step_count(stop_time, time_step)
    if step_count > max_steps:
        raise ValueError("requested simulation exceeds max_steps")

    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    states = np.zeros(model.state_count, dtype=float) if initial_state is None else np.asarray(initial_state, dtype=float)
    if states.shape != (model.state_count,) or not np.all(np.isfinite(states)):
        raise ValueError("initial_state must have one finite value per state")

    identity = np.eye(model.state_count)
    integral_state = 0.0
    previous_output = float((C @ states)[0])
    proportional_value = controller.kp * (reference.at(0.0) - previous_output)
    integral_value = 0.0
    derivative_value = 0.0
    control_value = min(
        controller.output_max,
        max(controller.output_min, proportional_value),
    )

    times = [0.0]
    references = [reference.at(0.0)]
    outputs = [previous_output]
    errors = [references[0] - previous_output]
    controls = [control_value]
    proportional = [proportional_value]
    integral = [integral_value]
    derivative = [derivative_value]
    state_traces = {f"x{index + 1}": [float(value)] for index, value in enumerate(states)}

    for step_index in range(step_count):
        step_start = step_index * time_step
        if step_index > 0 and step_index % controller_steps == 0:
            setpoint = reference.at(step_start)
            error_value = setpoint - previous_output
            proportional_value = controller.kp * error_value
            derivative_value = -controller.kd * (previous_output - derivative_reference_output) / controller.sample_time
            candidate_integral = integral_state + controller.ki * error_value * controller.sample_time
            candidate_control = proportional_value + candidate_integral + derivative_value
            if not (
                candidate_control > controller.output_max and error_value > 0
            ) and not (
                candidate_control < controller.output_min and error_value < 0
            ):
                integral_state = candidate_integral
            integral_value = integral_state
            control_value = min(
                controller.output_max,
                max(controller.output_min, proportional_value + integral_value + derivative_value),
            )
            derivative_reference_output = previous_output

        if step_index == 0:
            derivative_reference_output = previous_output

        time = min((step_index + 1) * time_step, stop_time)
        step_size = time - times[-1]
        input_vector = np.array([control_value])
        try:
            states = np.linalg.solve(
                identity - step_size * A,
                states + step_size * B @ input_vector,
            )
        except np.linalg.LinAlgError as error:
            raise ValueError(f"backward-Euler state solve failed at t={time:g} s") from error
        output_value = float((C @ states + D @ input_vector)[0])
        reference_value = reference.at(time)

        times.append(time)
        references.append(reference_value)
        outputs.append(output_value)
        errors.append(reference_value - output_value)
        controls.append(control_value)
        proportional.append(proportional_value)
        integral.append(integral_value)
        derivative.append(derivative_value)
        for index, value in enumerate(states):
            state_traces[f"x{index + 1}"].append(float(value))
        previous_output = output_value

    return LinearClosedLoopResult(
        times,
        references,
        outputs,
        errors,
        controls,
        proportional,
        integral,
        derivative,
        state_traces,
    )