"""JSON configuration loading and waveform CSV export."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .block_diagram import BlockDiagramDocument, BlockDiagramEdge, BlockDiagramNode
from .buck import BuckConfig, SimulationResult
from .closed_loop import ClosedLoopConfig, ClosedLoopResult, PIDConfig, ReferenceStep
from .design import PIDGains
from .design.state_feedback import StateFeedbackResult
from .interconnect import InterconnectBlock, InterconnectSpec
from .metrics import RunMetrics
from .mna import CircuitResult, MNAConfig, load_mna_config
from .sweep import SweepRun


@dataclass(frozen=True)
class WaveformData:
    time: list[float]
    inductor_current: list[float]
    output_voltage: list[float]
    switch_on: list[bool]


def load_config(path: str | Path) -> BuckConfig:
    """Load a buck-converter configuration from a JSON file."""
    with Path(path).open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError("configuration JSON must contain an object")
    return BuckConfig(**data)


def load_sweep_config(path: str | Path) -> tuple[BuckConfig, str, list[float]]:
    """Load a base circuit and parameter values from a sweep JSON file."""
    with Path(path).open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError("sweep configuration JSON must contain an object")
    if not {"base_config", "parameter", "values"}.issubset(data):
        raise ValueError("sweep config requires base_config, parameter, and values")
    if not isinstance(data["base_config"], dict):
        raise ValueError("base_config must contain an object")
    if not isinstance(data["parameter"], str):
        raise ValueError("parameter must be a string")
    if not isinstance(data["values"], list):
        raise ValueError("values must be a JSON array")
    return BuckConfig(**data["base_config"]), data["parameter"], data["values"]


def load_closed_loop_config(path: str | Path) -> ClosedLoopConfig:
    """Load plant, PID, and reference-step settings from JSON."""
    with Path(path).open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict) or not {
        "plant",
        "controller",
        "reference",
    }.issubset(data):
        raise ValueError("closed-loop config requires plant, controller, and reference")
    if not all(isinstance(data[key], dict) for key in ("plant", "controller", "reference")):
        raise ValueError("plant, controller, and reference must be JSON objects")
    return ClosedLoopConfig(
        plant=BuckConfig(**data["plant"]),
        controller=PIDConfig(**data["controller"]),
        reference=ReferenceStep(**data["reference"]),
    )


def load_mna_config_file(path: str | Path) -> MNAConfig:
    """Load a generic component netlist from JSON."""
    with Path(path).open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    return load_mna_config(data)


def _tuple_matrix(rows) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in rows)


def load_interconnect_spec(path: str | Path) -> InterconnectSpec:
    """Load an interconnection spec from a JSON file.

    Expected shape: {"blocks": [{...}], "forward": [...], "parallel": [...]
    (optional), "feedback": "unity" | "none" | [...], "stop_time": float,
    "time_step": float (optional)}. Block fields mirror InterconnectBlock.
    """
    with Path(path).open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError("interconnect JSON must contain an object")
    raw_blocks = data.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValueError("interconnect config requires a nonempty blocks array")
    blocks: list[InterconnectBlock] = []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            raise ValueError("each block must be an object")
        blocks.append(_block_from_dict(raw))
    forward = data.get("forward")
    parallel = data.get("parallel")
    feedback = data.get("feedback", "unity")
    if not isinstance(forward, list) or not all(isinstance(v, str) for v in forward):
        raise ValueError("forward must be an array of block ids")
    if parallel is not None and (
        not isinstance(parallel, list) or not all(isinstance(v, str) for v in parallel)
    ):
        raise ValueError("parallel must be an array of block ids")
    if isinstance(feedback, list) and not all(isinstance(v, str) for v in feedback):
        raise ValueError("feedback must be 'none', 'unity', or an array of block ids")
    return InterconnectSpec(
        blocks=tuple(blocks),
        forward=tuple(forward),
        parallel=tuple(parallel) if parallel is not None else None,
        feedback=feedback,
        stop_time=float(data.get("stop_time", 10.0)),
        time_step=(float(data["time_step"]) if data.get("time_step") is not None else None),
    )


def _block_from_dict(raw: dict) -> InterconnectBlock:
    """Build one engine block from a JSON object."""
    gains_data = raw.get("gains")
    gains = (
        PIDGains(
            kp=float(gains_data["kp"]),
            ki=float(gains_data["ki"]),
            kd=float(gains_data["kd"]),
        )
        if isinstance(gains_data, dict)
        else None
    )
    return InterconnectBlock(
        id=str(raw.get("id", "")),
        kind=str(raw.get("kind", "")),
        num=tuple(float(v) for v in raw["num"]) if raw.get("num") is not None else None,
        den=tuple(float(v) for v in raw["den"]) if raw.get("den") is not None else None,
        A=_tuple_matrix(raw["A"]) if raw.get("A") is not None else None,
        B=_tuple_matrix(raw["B"]) if raw.get("B") is not None else None,
        C=_tuple_matrix(raw["C"]) if raw.get("C") is not None else None,
        D=_tuple_matrix(raw["D"]) if raw.get("D") is not None else None,
        gains=gains,
        derivative_filter=(
            float(raw["derivative_filter"]) if raw.get("derivative_filter") is not None else None
        ),
        k=float(raw["k"]) if raw.get("k") is not None else None,
    )


def load_block_diagram(path: str | Path) -> BlockDiagramDocument:
    """Load a block-diagram canvas from a JSON file.

    Expected shape: {"nodes": [{"id", "kind", ...block fields,
    "position": [x, y]}], "edges": [{"id", "source", "target", "gain"}],
    "input_node", "output_node", "stop_time", "time_step" (optional)}.
    """
    with Path(path).open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError("block-diagram JSON must contain an object")
    raw_nodes = data.get("nodes")
    raw_edges = data.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("block-diagram config requires a nonempty nodes array")
    if not isinstance(raw_edges, list):
        raise ValueError("block-diagram config requires an edges array")
    nodes: list[BlockDiagramNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ValueError("each node must be an object")
        position = raw.get("position", [0.0, 0.0])
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError("each node requires a two-element position")
        nodes.append(
            BlockDiagramNode(
                id=str(raw.get("id", "")),
                block=_block_from_dict(raw),
                position=(float(position[0]), float(position[1])),
                label=str(raw.get("label", "")),
            )
        )
    edges: list[BlockDiagramEdge] = []
    for index, raw in enumerate(raw_edges, start=1):
        if not isinstance(raw, dict):
            raise ValueError("each edge must be an object")
        edges.append(
            BlockDiagramEdge(
                id=str(raw.get("id", f"e{index}")),
                source=str(raw.get("source", "")),
                target=str(raw.get("target", "")),
                gain=float(raw.get("gain", 1.0)),
                label=str(raw.get("label", "")),
            )
        )
    return BlockDiagramDocument(
        nodes=tuple(nodes),
        edges=tuple(edges),
        input_node=str(data.get("input_node", "")),
        output_node=str(data.get("output_node", "")),
        stop_time=float(data.get("stop_time", 10.0)),
        time_step=(float(data["time_step"]) if data.get("time_step") is not None else None),
    )


def write_state_feedback_csv(result: StateFeedbackResult, path: str | Path) -> None:
    """Write open- and closed-loop step responses to a CSV file.

    Columns: time_s, open_output, closed_output (the traces share a time
    grid, so they are written side by side).
    """
    if len(result.open_step.time_s) != len(result.closed_step.time_s):
        raise ValueError("open- and closed-loop steps must share a time grid")
    with Path(path).open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["time_s", "open_output", "closed_output"])
        writer.writerows(
            zip(
                result.open_step.time_s,
                result.open_step.output,
                result.closed_step.output,
                strict=True,
            )
        )


def read_waveforms_csv(path: str | Path) -> WaveformData:
    """Read and validate waveform samples exported by this simulator."""
    required_fields = {
        "time_s",
        "inductor_current_a",
        "output_voltage_v",
        "switch_on",
    }
    times: list[float] = []
    currents: list[float] = []
    voltages: list[float] = []
    switch_states: list[bool] = []

    with Path(path).open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames is None or not required_fields.issubset(reader.fieldnames):
            missing = required_fields - set(reader.fieldnames or [])
            raise ValueError(f"waveform CSV is missing columns: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            try:
                time = float(row["time_s"])
                current = float(row["inductor_current_a"])
                voltage = float(row["output_voltage_v"])
            except (TypeError, ValueError):
                raise ValueError(
                    f"row {row_number}: time, current, and voltage must be numbers"
                ) from None

            if not all(math.isfinite(value) for value in (time, current, voltage)):
                raise ValueError(f"row {row_number}: waveform values must be finite")
            if time < 0 or (times and time <= times[-1]):
                raise ValueError(
                    f"row {row_number}: time values must be nonnegative and increasing"
                )

            switch_value = (row["switch_on"] or "").strip().lower()
            if switch_value not in {"true", "false"}:
                raise ValueError(f"row {row_number}: switch_on must be true or false")

            times.append(time)
            currents.append(current)
            voltages.append(voltage)
            switch_states.append(switch_value == "true")

    if not times:
        raise ValueError("waveform CSV contains no samples")
    return WaveformData(times, currents, voltages, switch_states)


def write_csv(result: SimulationResult, path: str | Path) -> None:
    """Write time-domain waveforms to a portable CSV file."""
    with Path(path).open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["time_s", "inductor_current_a", "output_voltage_v", "switch_on"])
        for time, current, voltage, switch_on in zip(
            result.time,
            result.inductor_current,
            result.output_voltage,
            result.switch_on,
            strict=True,
        ):
            writer.writerow([time, current, voltage, switch_on])


def write_sweep_csv(runs: list[SweepRun], path: str | Path) -> None:
    """Write sweep traces as long-form rows for analysis in other tools."""
    if not runs:
        raise ValueError("cannot write an empty parameter sweep")
    parameter = runs[0].parameter
    if any(run.parameter != parameter for run in runs):
        raise ValueError("all sweep runs must use the same parameter")

    with Path(path).open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(
            [
                "parameter",
                "value",
                "time_s",
                "inductor_current_a",
                "output_voltage_v",
                "switch_on",
            ]
        )
        for run in runs:
            for time, current, voltage, switch_on in zip(
                run.result.time,
                run.result.inductor_current,
                run.result.output_voltage,
                run.result.switch_on,
                strict=True,
            ):
                writer.writerow([run.parameter, run.value, time, current, voltage, switch_on])


def write_metrics_csv(metrics: list[RunMetrics], path: str | Path) -> None:
    """Write one electrical-measurement summary row per sweep run."""
    if not metrics:
        raise ValueError("cannot write empty sweep metrics")

    with Path(path).open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(
            [
                "parameter",
                "value",
                "steady_state_window_start_s",
                "steady_state_output_voltage_v",
                "peak_output_voltage_v",
                "peak_overshoot_percent",
                "settling_time_s",
                "output_voltage_ripple_pp_v",
                "inductor_current_ripple_pp_a",
            ]
        )
        for result in metrics:
            writer.writerow(
                [
                    result.parameter,
                    result.value,
                    result.steady_state_window_start_s,
                    result.steady_state_output_voltage_v,
                    result.peak_output_voltage_v,
                    result.peak_overshoot_percent,
                    result.settling_time_s,
                    result.output_voltage_ripple_pp_v,
                    result.inductor_current_ripple_pp_a,
                ]
            )


def write_closed_loop_csv(result: ClosedLoopResult, path: str | Path) -> None:
    """Write closed-loop plant and controller signals to a CSV file."""
    fields = [
        "time_s",
        "reference_voltage_v",
        "output_voltage_v",
        "error_v",
        "proportional_term",
        "integral_term",
        "derivative_term",
        "duty_cycle",
        "inductor_current_a",
        "switch_on",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(fields)
        for row in zip(
            result.time,
            result.reference_voltage,
            result.output_voltage,
            result.error,
            result.proportional_term,
            result.integral_term,
            result.derivative_term,
            result.duty_cycle,
            result.inductor_current,
            result.switch_on,
            strict=True,
        ):
            writer.writerow(row)


def write_mna_csv(result: CircuitResult, path: str | Path) -> None:
    """Write node voltages, component currents, and switch states to CSV."""
    fields = ["time_s"]
    fields.extend(f"node_voltage_{node}_v" for node in result.node_voltages)
    fields.extend(f"component_current_{name}_a" for name in result.component_currents)
    fields.extend(f"switch_{name}_on" for name in result.switch_states)
    with Path(path).open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(fields)
        for index, time in enumerate(result.time):
            row: list[float | bool] = [time]
            row.extend(trace[index] for trace in result.node_voltages.values())
            row.extend(trace[index] for trace in result.component_currents.values())
            row.extend(trace[index] for trace in result.switch_states.values())
            writer.writerow(row)
