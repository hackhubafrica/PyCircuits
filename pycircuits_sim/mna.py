"""Fixed-step transient modified nodal analysis for linear circuits."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .buck import _step_count


GROUND_NODES = {"0", "gnd", "ground"}
PASSIVE_TYPES = {"resistor", "capacitor", "inductor"}
SOURCE_TYPES = {"voltage_source", "current_source"}


@dataclass(frozen=True)
class Component:
    name: str
    kind: str
    p: str
    n: str
    value: float = 0.0
    initial: float = 0.0
    waveform: str = "dc"
    offset: float = 0.0
    amplitude: float = 0.0
    frequency: float = 0.0
    phase: float = 0.0
    ron: float = 1e-3
    roff: float = 1e6
    control_points: tuple[tuple[float, float], ...] = ()
    threshold: float = 0.5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Component:
        kind = data.get("type")
        if kind not in PASSIVE_TYPES | SOURCE_TYPES | {"switch"}:
            raise ValueError(f"unsupported component type: {kind!r}")
        name = data.get("name")
        p = data.get("p")
        n = data.get("n")
        if not all(isinstance(item, str) and item for item in (name, p, n)):
            raise ValueError("each component requires nonempty name, p, and n strings")

        if kind in PASSIVE_TYPES:
            value = _finite_number(data.get("value"), f"{name}.value")
            if value <= 0:
                raise ValueError(f"{name}.value must be greater than zero")
            initial = _finite_number(data.get("initial", 0.0), f"{name}.initial")
            if kind == "capacitor" and initial < 0:
                raise ValueError(f"{name}.initial capacitor voltage cannot be negative")
            return cls(name=name, kind=kind, p=p, n=n, value=value, initial=initial)

        if kind in SOURCE_TYPES:
            waveform_data = data.get("waveform", {})
            if not isinstance(waveform_data, dict):
                raise ValueError(f"{name}.waveform must be an object")
            waveform = waveform_data.get("type", "dc")
            if waveform not in {"dc", "sine"}:
                raise ValueError(f"{name}: waveform type must be dc or sine")
            value = _finite_number(data.get("value", 0.0), f"{name}.value")
            offset = _finite_number(waveform_data.get("offset", value), f"{name}.offset")
            amplitude = _finite_number(
                waveform_data.get("amplitude", 0.0), f"{name}.amplitude"
            )
            frequency = _finite_number(
                waveform_data.get("frequency", 0.0), f"{name}.frequency"
            )
            phase = _finite_number(waveform_data.get("phase", 0.0), f"{name}.phase")
            if waveform == "sine" and frequency <= 0:
                raise ValueError(f"{name}.frequency must be positive for a sine source")
            return cls(
                name=name,
                kind=kind,
                p=p,
                n=n,
                value=value,
                waveform=waveform,
                offset=offset,
                amplitude=amplitude,
                frequency=frequency,
                phase=phase,
            )

        ron = _finite_number(data.get("ron", 1e-3), f"{name}.ron")
        roff = _finite_number(data.get("roff", 1e6), f"{name}.roff")
        threshold = _finite_number(data.get("threshold", 0.5), f"{name}.threshold")
        raw_points = data.get("control_points")
        if not isinstance(raw_points, list) or len(raw_points) < 2:
            raise ValueError(f"{name}.control_points must contain at least two [time, value] pairs")
        points: list[tuple[float, float]] = []
        for point in raw_points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"{name}.control_points entries must be [time, value]")
            point_time = _finite_number(point[0], f"{name}.control_points time")
            point_value = _finite_number(point[1], f"{name}.control_points value")
            if point_time < 0 or (points and point_time <= points[-1][0]):
                raise ValueError(f"{name}.control_points times must be nonnegative and increasing")
            points.append((point_time, point_value))
        if ron <= 0 or roff <= 0:
            raise ValueError(f"{name}.ron and {name}.roff must be greater than zero")
        return cls(
            name=name,
            kind=kind,
            p=p,
            n=n,
            ron=ron,
            roff=roff,
            threshold=threshold,
            control_points=tuple(points),
        )


@dataclass(frozen=True)
class MNAConfig:
    time_step: float
    stop_time: float
    components: tuple[Component, ...]
    max_steps: int = 2_000_000

    def __post_init__(self) -> None:
        for name in ("time_step", "stop_time"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least one")
        if _step_count(self.stop_time, self.time_step) > self.max_steps:
            raise ValueError("requested simulation exceeds max_steps")
        names = [component.name for component in self.components]
        if len(set(names)) != len(names):
            raise ValueError("component names must be unique")
        if not self.components:
            raise ValueError("circuit must contain at least one component")


@dataclass(frozen=True)
class CircuitResult:
    time: list[float]
    node_voltages: dict[str, list[float]]
    component_currents: dict[str, list[float]]
    switch_states: dict[str, list[bool]]


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def load_mna_config(data: dict[str, Any]) -> MNAConfig:
    """Create a validated circuit config from a JSON-compatible object."""
    if not isinstance(data, dict):
        raise ValueError("MNA config must be an object")
    raw_components = data.get("components")
    if not isinstance(raw_components, list):
        raise ValueError("MNA config requires a components array")
    components = tuple(Component.from_dict(item) for item in raw_components)
    config = MNAConfig(
        time_step=_finite_number(data.get("time_step"), "time_step"),
        stop_time=_finite_number(data.get("stop_time"), "stop_time"),
        components=components,
        max_steps=int(data.get("max_steps", 2_000_000)),
    )
    node_names = {
        node
        for component in components
        for node in (component.p, component.n)
        if node.lower() not in GROUND_NODES
    }
    if not node_names:
        raise ValueError("circuit must have at least one non-ground node")
    return config


def _node_voltage(solution: np.ndarray, node: str, node_index: dict[str, int]) -> float:
    if node.lower() in GROUND_NODES:
        return 0.0
    return float(solution[node_index[node]])


def _source_value(component: Component, time: float) -> float:
    if component.waveform == "dc":
        return component.offset
    return component.offset + component.amplitude * math.sin(
        2.0 * math.pi * component.frequency * time + component.phase
    )


def _control_value(component: Component, time: float) -> float:
    points = component.control_points
    if time <= points[0][0]:
        return points[0][1]
    if time >= points[-1][0]:
        return points[-1][1]
    for (left_time, left_value), (right_time, right_value) in zip(points, points[1:]):
        if left_time <= time <= right_time:
            fraction = (time - left_time) / (right_time - left_time)
            return left_value + fraction * (right_value - left_value)
    raise RuntimeError("control interpolation interval not found")


def simulate_mna(config: MNAConfig) -> CircuitResult:
    """Simulate a linear RLC circuit with PWL resistive switches.

    Capacitors and inductors use backward-Euler companion models. Ideal voltage
    sources and inductors add branch-current unknowns to the MNA system. Switches
    are finite-resistance PWL devices controlled by interpolated control points.
    """
    node_names = sorted(
        {
            node
            for component in config.components
            for node in (component.p, component.n)
            if node.lower() not in GROUND_NODES
        }
    )
    node_index = {node: index for index, node in enumerate(node_names)}
    branch_components = [
        component
        for component in config.components
        if component.kind in {"voltage_source", "inductor"}
    ]
    branch_index = {
        component.name: len(node_names) + index
        for index, component in enumerate(branch_components)
    }
    system_size = len(node_names) + len(branch_components)
    step_count = _step_count(config.stop_time, config.time_step)

    times = [0.0]
    node_traces = {node: [0.0] for node in node_names}
    current_traces = {component.name: [0.0] for component in config.components}
    switch_traces = {
        component.name: [
            _control_value(component, 0.0) >= component.threshold
        ]
        for component in config.components
        if component.kind == "switch"
    }
    capacitor_history = {
        component.name: component.initial
        for component in config.components
        if component.kind == "capacitor"
    }
    inductor_history = {
        component.name: component.initial
        for component in config.components
        if component.kind == "inductor"
    }
    branch_solution = {component.name: 0.0 for component in branch_components}

    for step_index in range(step_count):
        time = min((step_index + 1) * config.time_step, config.stop_time)
        step_size = time - times[-1]
        matrix = np.zeros((system_size, system_size), dtype=float)
        rhs = np.zeros(system_size, dtype=float)

        def stamp_conductance(p: str, n: str, conductance: float) -> None:
            if p.lower() not in GROUND_NODES:
                pi = node_index[p]
                matrix[pi, pi] += conductance
            if n.lower() not in GROUND_NODES:
                ni = node_index[n]
                matrix[ni, ni] += conductance
            if p.lower() not in GROUND_NODES and n.lower() not in GROUND_NODES:
                pi = node_index[p]
                ni = node_index[n]
                matrix[pi, ni] -= conductance
                matrix[ni, pi] -= conductance

        def stamp_branch(p: str, n: str, branch: int) -> None:
            if p.lower() not in GROUND_NODES:
                pi = node_index[p]
                matrix[pi, branch] += 1.0
                matrix[branch, pi] += 1.0
            if n.lower() not in GROUND_NODES:
                ni = node_index[n]
                matrix[ni, branch] -= 1.0
                matrix[branch, ni] -= 1.0

        for component in config.components:
            if component.kind == "resistor":
                stamp_conductance(component.p, component.n, 1.0 / component.value)
            elif component.kind == "capacitor":
                conductance = component.value / step_size
                stamp_conductance(component.p, component.n, conductance)
                history_current = conductance * capacitor_history[component.name]
                if component.p.lower() not in GROUND_NODES:
                    rhs[node_index[component.p]] += history_current
                if component.n.lower() not in GROUND_NODES:
                    rhs[node_index[component.n]] -= history_current
            elif component.kind == "inductor":
                branch = branch_index[component.name]
                stamp_branch(component.p, component.n, branch)
                resistance = component.value / step_size
                matrix[branch, branch] -= resistance
                rhs[branch] -= resistance * inductor_history[component.name]
            elif component.kind == "voltage_source":
                branch = branch_index[component.name]
                stamp_branch(component.p, component.n, branch)
                rhs[branch] += _source_value(component, time)
            elif component.kind == "current_source":
                source_current = _source_value(component, time)
                if component.p.lower() not in GROUND_NODES:
                    rhs[node_index[component.p]] -= source_current
                if component.n.lower() not in GROUND_NODES:
                    rhs[node_index[component.n]] += source_current
            elif component.kind == "switch":
                is_on = _control_value(component, time) >= component.threshold
                resistance = component.ron if is_on else component.roff
                stamp_conductance(component.p, component.n, 1.0 / resistance)
                switch_traces[component.name].append(is_on)

        try:
            solution = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                f"MNA system is singular at t={time:g} s; check for floating nodes "
                "or ideal-source loops"
            ) from exc

        times.append(time)
        for node in node_names:
            node_traces[node].append(_node_voltage(solution, node, node_index))

        for component in config.components:
            voltage_drop = _node_voltage(solution, component.p, node_index) - _node_voltage(
                solution, component.n, node_index
            )
            if component.kind == "resistor":
                current = voltage_drop / component.value
            elif component.kind == "capacitor":
                current = component.value / step_size * (
                    voltage_drop - capacitor_history[component.name]
                )
                capacitor_history[component.name] = voltage_drop
            elif component.kind == "inductor":
                current = float(solution[branch_index[component.name]])
                inductor_history[component.name] = current
            elif component.kind == "switch":
                is_on = switch_traces[component.name][-1]
                resistance = component.ron if is_on else component.roff
                current = voltage_drop / resistance
            else:
                current = float(solution[branch_index[component.name]])
            current_traces[component.name].append(current)

        for component in branch_components:
            branch_solution[component.name] = float(solution[branch_index[component.name]])

    return CircuitResult(times, node_traces, current_traces, switch_traces)