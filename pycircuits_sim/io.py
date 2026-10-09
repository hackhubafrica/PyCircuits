"""JSON configuration loading and waveform CSV export."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .buck import BuckConfig, SimulationResult
from .closed_loop import ClosedLoopConfig, ClosedLoopResult, PIDConfig, ReferenceStep
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
                raise ValueError(f"row {row_number}: time, current, and voltage must be numbers") from None

            if not all(math.isfinite(value) for value in (time, current, voltage)):
                raise ValueError(f"row {row_number}: waveform values must be finite")
            if time < 0 or (times and time <= times[-1]):
                raise ValueError(f"row {row_number}: time values must be nonnegative and increasing")

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
        writer.writerow(
            ["time_s", "inductor_current_a", "output_voltage_v", "switch_on"]
        )
        for time, current, voltage, switch_on in zip(
            result.time,
            result.inductor_current,
            result.output_voltage,
            result.switch_on,
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
            ):
                writer.writerow(
                    [run.parameter, run.value, time, current, voltage, switch_on]
                )


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
