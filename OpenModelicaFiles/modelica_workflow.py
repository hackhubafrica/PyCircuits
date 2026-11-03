#!/usr/bin/env python3
"""Prepare and deploy SISO linearized Modelica plants to an ESP32."""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .modelica_parser import parse_linearized_model

DEFAULT_PROJECT_DIR = Path(__file__).resolve().parent / "PlantHILProject"
MAX_STATES = 16
MAX_SAMPLE_PERIOD_US = 1_000_000
MAX_SIMULATION_SAMPLES = 1_000_000
MAX_MCU_FLOAT = float(np.finfo(np.float32).max)


class WorkflowError(ValueError):
    """A validation or external-tool failure with a user-facing message."""


@dataclass(frozen=True)
class StateSpacePlant:
    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    D: np.ndarray

    @property
    def state_count(self) -> int:
        return int(self.A.shape[0])


def load_deployable_plant(model_path: Path) -> StateSpacePlant:
    """Load and validate the first supported MCU model profile: SISO LTI."""
    try:
        A, B, C, D = parse_linearized_model(model_path)
    except (OSError, ValueError) as error:
        raise WorkflowError(f"Could not parse {model_path}: {error}") from error

    if any(matrix is None for matrix in (A, B, C, D)):
        missing = [
            name for name, matrix in zip("ABCD", (A, B, C, D)) if matrix is None
        ]
        raise WorkflowError(
            "The Modelica file must declare numeric A, B, C, and D matrices; "
            f"missing: {', '.join(missing)}. Export/linearize the OMEdit model "
            "to a state-space .mo file before deployment."
        )

    if A is None or B is None or C is None or D is None:
        raise WorkflowError("The Modelica state-space matrices could not be loaded.")
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise WorkflowError(f"A must be square; got shape {A.shape}.")
    state_count = A.shape[0]
    if not 1 <= state_count <= MAX_STATES:
        raise WorkflowError(
            f"The ESP32 profile supports 1 to {MAX_STATES} states; "
            f"the model has {state_count}."
        )
    expected_shapes = {
        "B": (state_count, 1),
        "C": (1, state_count),
        "D": (1, 1),
    }
    for name, matrix, expected in (
        ("B", B, expected_shapes["B"]),
        ("C", C, expected_shapes["C"]),
        ("D", D, expected_shapes["D"]),
    ):
        if matrix.shape != expected:
            raise WorkflowError(
                f"{name} must have shape {expected} for the supported "
                f"single-input/single-output profile; got {matrix.shape}."
            )
    for name, matrix in (("A", A), ("B", B), ("C", C), ("D", D)):
        if not np.all(np.isfinite(matrix)):
            raise WorkflowError(f"{name} contains a non-finite value.")
        if np.any(np.abs(matrix) > MAX_MCU_FLOAT):
            raise WorkflowError(
                f"{name} contains values outside the ESP32 float32 range."
            )
    return StateSpacePlant(A=A, B=B, C=C, D=D)


def _cpp_float(value: float) -> str:
    formatted = f"{float(value):.9g}"
    if "." not in formatted and "e" not in formatted.lower():
        formatted += ".0"
    return f"{formatted}f"


def render_model_header(plant: StateSpacePlant) -> str:
    """Render the portable SISO matrices consumed by the PlatformIO firmware."""
    n = plant.state_count
    a_rows = ",\n".join(
        "    {" + ", ".join(_cpp_float(value) for value in row) + "}"
        for row in plant.A
    )
    b_values = ", ".join(_cpp_float(value) for value in plant.B[:, 0])
    c_values = ", ".join(_cpp_float(value) for value in plant.C[0, :])
    return (
        "#pragma once\n"
        "#include <stdint.h>\n\n"
        f"static constexpr uint8_t MODEL_STATE_COUNT = {n};\n"
        "static constexpr float MODEL_A[MODEL_STATE_COUNT][MODEL_STATE_COUNT] = {\n"
        f"{a_rows}\n"
        "};\n"
        "static constexpr float MODEL_B[MODEL_STATE_COUNT] = {"
        f"{b_values}"
        "};\n"
        "static constexpr float MODEL_C[MODEL_STATE_COUNT] = {"
        f"{c_values}"
        "};\n"
        f"static constexpr float MODEL_D = {_cpp_float(plant.D[0, 0])};\n"
    )


def simulate_plant(
    plant: StateSpacePlant,
    *,
    duration: float,
    sample_period: float,
    input_value: float,
) -> tuple[list[float], list[float], list[float], list[np.ndarray]]:
    """Run a zero-initialized fixed-step RK4 SISO simulation."""
    if not math.isfinite(duration) or duration <= 0:
        raise WorkflowError("Simulation duration must be finite and positive.")
    if not math.isfinite(input_value):
        raise WorkflowError("Simulation input must be finite.")
    step_us = _positive_period_us(sample_period)
    step = step_us / 1_000_000.0
    if duration / step > MAX_SIMULATION_SAMPLES:
        raise WorkflowError(
            f"Simulation is limited to {MAX_SIMULATION_SAMPLES} samples."
        )
    times = [0.0]
    inputs = [input_value]
    initial_state = np.zeros(plant.state_count, dtype=float)
    states = [initial_state]
    outputs = [
        float(plant.C[0, :] @ initial_state + plant.D[0, 0] * input_value)
    ]
    if not math.isfinite(outputs[0]):
        raise WorkflowError("Simulation output became non-finite at t=0.")

    def derivative(state: np.ndarray) -> np.ndarray:
        return plant.A @ state + plant.B[:, 0] * input_value

    while times[-1] < duration:
        current = states[-1]
        next_time = min(duration, times[-1] + step)
        dt = next_time - times[-1]
        k1 = derivative(current)
        k2 = derivative(current + 0.5 * dt * k1)
        k3 = derivative(current + 0.5 * dt * k2)
        k4 = derivative(current + dt * k3)
        next_state = current + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        if not np.all(np.isfinite(next_state)):
            raise WorkflowError(
                f"Simulation became non-finite at t={times[-1] + dt:g} seconds."
            )
        times.append(next_time)
        inputs.append(input_value)
        states.append(next_state)
        output = float(plant.C[0, :] @ next_state + plant.D[0, 0] * input_value)
        if not math.isfinite(output):
            raise WorkflowError("Simulation output became non-finite.")
        outputs.append(output)
    return times, inputs, outputs, states


def _write_simulation_csv(
    output_path: Path,
    plant: StateSpacePlant,
    *,
    duration: float,
    sample_period: float,
    input_value: float,
) -> None:
    times, inputs, outputs, states = simulate_plant(
        plant,
        duration=duration,
        sample_period=sample_period,
        input_value=input_value,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["time_s", "input", "output", *[
            f"x{index + 1}" for index in range(plant.state_count)
        ]])
        for time_s, input_value, output, state in zip(times, inputs, outputs, states):
            writer.writerow([time_s, input_value, output, *state.tolist()])


def _validate_io_pin(pin: int, name: str) -> None:
    if name == "ADC_PIN" and 32 <= pin <= 39:
        return
    if name == "PWM_PIN" and 0 <= pin <= 33 and pin not in {
        0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 15
    }:
        return
    if name == "ADC_PIN":
        raise WorkflowError("ADC_PIN must be an ESP32 ADC1 GPIO (32-39).")
    raise WorkflowError(
        "PWM_PIN must be a usable ESP32 output GPIO (0-33), excluding pins "
        "reserved for flash, UART, or boot strapping."
    )


def render_firmware_config(
    *,
    mode: str,
    sample_period_us: int,
    telemetry_interval_us: int,
    virtual_input: float,
    adc_pin: int | None,
    pwm_pin: int | None,
    input_min: float,
    input_max: float,
    output_min: float,
    output_max: float,
) -> str:
    if mode not in {"virtual", "io"}:
        raise WorkflowError("Mode must be 'virtual' or 'io'.")
    if not 1 <= sample_period_us <= MAX_SAMPLE_PERIOD_US:
        raise WorkflowError(
            f"Sample period must be between 1 and {MAX_SAMPLE_PERIOD_US} "
            "microseconds."
        )
    if not sample_period_us <= telemetry_interval_us <= MAX_SAMPLE_PERIOD_US:
        raise WorkflowError(
            "Telemetry interval must be at least one sample period and no more "
            f"than {MAX_SAMPLE_PERIOD_US} microseconds."
        )
    values = {
        "virtual input": virtual_input,
        "input minimum": input_min,
        "input maximum": input_max,
        "output minimum": output_min,
        "output maximum": output_max,
    }
    for label, value in values.items():
        if not math.isfinite(value):
            raise WorkflowError(f"{label.capitalize()} must be finite.")
        if abs(value) > MAX_MCU_FLOAT:
            raise WorkflowError(
                f"{label.capitalize()} exceeds the ESP32 float32 range."
            )
    if input_min >= input_max:
        raise WorkflowError("Input minimum must be less than input maximum.")
    if output_min >= output_max:
        raise WorkflowError("Output minimum must be less than output maximum.")

    configured = mode == "io" and adc_pin is not None and pwm_pin is not None
    if mode == "io" and not configured:
        raise WorkflowError(
            "Real-I/O mode requires both --adc-pin and --pwm-pin; "
            "outputs remain disabled otherwise."
        )
    if configured:
        _validate_io_pin(adc_pin, "ADC_PIN")
        _validate_io_pin(pwm_pin, "PWM_PIN")
        if adc_pin == pwm_pin:
            raise WorkflowError("ADC and PWM pins must be different.")

    mode_virtual = 1 if mode == "virtual" else 0
    return (
        "#pragma once\n"
        "#include <stdint.h>\n\n"
        f"#define MODEL_MODE_VIRTUAL {mode_virtual}\n"
        f"#define IO_CONFIG_VALID {1 if configured else 0}\n"
        f"#define SAMPLE_PERIOD_US {sample_period_us}UL\n"
        f"#define TELEMETRY_INTERVAL_US {telemetry_interval_us}UL\n"
        f"#define VIRTUAL_INPUT_VALUE {_cpp_float(virtual_input)}\n"
        f"#define ADC_PIN {adc_pin if configured else -1}\n"
        f"#define PWM_PIN {pwm_pin if configured else -1}\n"
        f"#define INPUT_MIN {_cpp_float(input_min)}\n"
        f"#define INPUT_MAX {_cpp_float(input_max)}\n"
        f"#define OUTPUT_MIN {_cpp_float(output_min)}\n"
        f"#define OUTPUT_MAX {_cpp_float(output_max)}\n"
    )


def _run_openmodelica_check(model_path: Path, model_class: str | None) -> None:
    omc = shutil.which("omc")
    if omc is None:
        raise WorkflowError(
            "OpenModelica's 'omc' executable was not found on PATH. "
            "Install OpenModelica or omit --omc-check."
        )
    if model_class is None:
        content = model_path.read_text(encoding="utf-8")
        match = re.search(
            r"^\s*(?:model|block|class)\s+([A-Za-z_]\w*)",
            content,
            re.MULTILINE,
        )
        if match is None:
            raise WorkflowError(
                "Could not infer a Modelica class name; pass --model-class."
            )
        model_class = match.group(1)
    if not re.fullmatch(r"[A-Za-z_]\w*", model_class):
        raise WorkflowError("Model class must be a simple Modelica identifier.")

    model_string = str(model_path.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    with tempfile.TemporaryDirectory(prefix="pycircuits-omc-") as temp_dir:
        script = Path(temp_dir) / "check.mos"
        script.write_text(
            f'loadFile("{model_string}");\n'
            f"checkModel({model_class});\n"
            "getErrorString();\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [omc, str(script)],
            cwd=model_path.resolve().parent,
            check=False,
            capture_output=True,
            text=True,
        )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if (
        result.returncode != 0
        or re.search(r"\b[1-9]\d*\s+errors?\b", output)
        or re.search(r"\bError:", output, re.IGNORECASE)
    ):
        raise WorkflowError(
            "OpenModelica checkModel failed:\n" + (output.strip() or "No output")
        )
    print(output.strip() or f"OpenModelica checkModel passed for {model_class}.")


def _run_platformio(project_dir: Path, *, upload_port: str | None = None) -> None:
    pio = shutil.which("pio")
    if pio is None:
        raise WorkflowError(
            "PlatformIO CLI ('pio') was not found on PATH. Install PlatformIO "
            "Core, then rerun the workflow."
        )
    command = [pio, "run", "--project-dir", str(project_dir)]
    if upload_port is not None:
        command.extend(["--target", "upload", "--upload-port", upload_port])
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=project_dir.parent, check=False)
    if result.returncode != 0:
        action = "upload" if upload_port is not None else "build"
        raise WorkflowError(f"PlatformIO {action} failed with exit code {result.returncode}.")


def _positive_period_us(sample_period: float) -> int:
    if not math.isfinite(sample_period) or sample_period <= 0:
        raise WorkflowError("Sample period must be a finite positive number.")
    sample_period_us = round(sample_period * 1_000_000)
    if not 1 <= sample_period_us <= MAX_SAMPLE_PERIOD_US:
        raise WorkflowError(
            f"Sample period must round to 1..{MAX_SAMPLE_PERIOD_US} microseconds."
        )
    return sample_period_us


def _telemetry_interval_us(interval: float, sample_period_us: int) -> int:
    if not math.isfinite(interval) or interval <= 0:
        raise WorkflowError("Telemetry interval must be a finite positive number.")
    interval_us = round(interval * 1_000_000)
    if not sample_period_us <= interval_us <= MAX_SAMPLE_PERIOD_US:
        raise WorkflowError(
            "Telemetry interval must be at least one sample period and no more "
            f"than {MAX_SAMPLE_PERIOD_US} microseconds."
        )
    return interval_us


def _add_model_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", type=Path, required=True, help="Linearized Modelica .mo file")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=DEFAULT_PROJECT_DIR,
        help="PlatformIO project directory (default: PlantHILProject)",
    )
    parser.add_argument("--mode", choices=("virtual", "io"), default="virtual")
    parser.add_argument("--sample-period", type=float, default=0.001, help="Seconds")
    parser.add_argument(
        "--telemetry-period",
        type=float,
        default=0.1,
        help="Seconds between serial telemetry packets",
    )
    parser.add_argument("--virtual-input", type=float, default=1.0)
    parser.add_argument("--adc-pin", type=int)
    parser.add_argument("--pwm-pin", type=int)
    parser.add_argument("--input-min", type=float, default=0.0)
    parser.add_argument("--input-max", type=float, default=3.3)
    parser.add_argument("--output-min", type=float, default=0.0)
    parser.add_argument("--output-max", type=float, default=3.3)
    parser.add_argument(
        "--omc-check",
        action="store_true",
        help="Also run OpenModelica checkModel() on the input class",
    )
    parser.add_argument("--model-class", help="Class name for --omc-check")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a linearized Modelica .mo model and build safe ESP32 "
            "firmware with PlatformIO."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Check the SISO state-space model")
    validate.add_argument("--model", type=Path, required=True)
    validate.add_argument("--omc-check", action="store_true")
    validate.add_argument("--model-class")

    simulate = commands.add_parser(
        "simulate",
        help="Simulate the supported SISO model on the host and write CSV",
    )
    simulate.add_argument("--model", type=Path, required=True)
    simulate.add_argument("--duration", type=float, default=1.0, help="Seconds")
    simulate.add_argument("--sample-period", type=float, default=0.001, help="Seconds")
    simulate.add_argument("--input", type=float, default=1.0, help="Constant model input")
    simulate.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/modelica_simulation.csv"),
        help="CSV output path",
    )

    deploy = commands.add_parser(
        "deploy",
        help="Generate model headers and build; upload only when --upload is given",
    )
    _add_model_arguments(deploy)
    deploy.add_argument("--prepare-only", action="store_true", help="Generate headers only")
    deploy.add_argument("--upload", action="store_true", help="Explicitly flash firmware")
    deploy.add_argument("--port", help="Serial port; required with --upload")
    monitor = commands.add_parser("monitor", help="Print validated ESP32 telemetry")
    monitor.add_argument("--port", required=True, help="Serial port")
    monitor.add_argument("--baudrate", type=int, default=115200)
    return parser


def _monitor(port: str, baudrate: int) -> None:
    if baudrate <= 0:
        raise WorkflowError("Baud rate must be a positive integer.")
    try:
        from pycircuits_sim.hardware import HILRunner
    except ImportError as error:
        raise WorkflowError(
            "Telemetry monitoring requires the project and its hardware extra. "
            "Install with 'python -m pip install -e \".[hardware]\"'."
        ) from error

    def show_message(message: dict[str, object]) -> None:
        print(message, flush=True)

    runner = HILRunner(port=port, baudrate=baudrate, on_message=show_message)
    try:
        runner.start()
    except RuntimeError as error:
        raise WorkflowError(str(error)) from error
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "monitor":
            _monitor(args.port, args.baudrate)
            return 0

        model_path = args.model.expanduser().resolve()
        if not model_path.is_file():
            raise WorkflowError(f"Model file does not exist: {model_path}")
        if args.omc_check:
            _run_openmodelica_check(model_path, args.model_class)
        plant = load_deployable_plant(model_path)

        if args.command == "validate":
            print(
                f"Valid SISO state-space model: {plant.state_count} states, "
                "one input, one output."
            )
            return 0
        if args.command == "simulate":
            output_path = args.output.expanduser().resolve()
            _write_simulation_csv(
                output_path,
                plant,
                duration=args.duration,
                sample_period=args.sample_period,
                input_value=args.input,
            )
            print(f"Wrote {output_path}.")
            return 0

        if args.upload and not args.port:
            raise WorkflowError("--upload requires an explicit --port.")
        if args.prepare_only and args.upload:
            raise WorkflowError("--prepare-only cannot be combined with --upload.")

        project_dir = args.project_dir.expanduser().resolve()
        source_dir = project_dir / "src"
        if not source_dir.is_dir():
            raise WorkflowError(
                f"PlatformIO source directory does not exist: {source_dir}"
            )
        sample_period_us = _positive_period_us(args.sample_period)
        telemetry_interval_us = _telemetry_interval_us(
            args.telemetry_period,
            sample_period_us,
        )
        model_header = render_model_header(plant)
        firmware_config = render_firmware_config(
            mode=args.mode,
            sample_period_us=sample_period_us,
            telemetry_interval_us=telemetry_interval_us,
            virtual_input=args.virtual_input,
            adc_pin=args.adc_pin,
            pwm_pin=args.pwm_pin,
            input_min=args.input_min,
            input_max=args.input_max,
            output_min=args.output_min,
            output_max=args.output_max,
        )
        (source_dir / "plant_model.h").write_text(model_header, encoding="utf-8")
        (source_dir / "firmware_config.h").write_text(
            firmware_config,
            encoding="utf-8",
        )
        print(
            f"Prepared {plant.state_count}-state {args.mode} firmware in "
            f"{project_dir}."
        )

        if args.prepare_only:
            return 0
        _run_platformio(
            project_dir,
            upload_port=args.port if args.upload else None,
        )
        return 0
    except (OSError, WorkflowError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
