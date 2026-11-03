from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from OpenModelicaFiles.modelica_parser import (
    parse_linearized_initial_state,
    parse_linearized_model,
)
from OpenModelicaFiles.modelica_workflow import (
    WorkflowError,
    linearize_model,
    load_deployable_plant,
    main,
    render_firmware_config,
    render_model_header,
    simulate_plant,
)
from pycircuits_sim.hardware.telemetry import (
    encode_input_command,
    parse_telemetry_line,
)


MODEL_TEXT = """\
model DeployablePlant
  parameter Integer n = 2 "number of states";
  parameter Integer m = 1 "number of inputs";
  parameter Integer p = 1 "number of outputs";
  parameter Real x0[n] = {0.25, -0.5};
  parameter Real A[n, n] = [-1.0, 0.0; 0.0, -2.0];
  parameter Real B[n, m] = {1.0; 0.5};
  parameter Real C[p, n] = [1.0, 0.0];
  parameter Real D[p, m] = zeros(p, m);
end DeployablePlant;
"""


class ModelicaParserTests(unittest.TestCase):
    def test_reads_modelica_matrix_literals_and_zero_dimensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plant.mo"
            path.write_text(MODEL_TEXT, encoding="utf-8")

            matrices = parse_linearized_model(path)
            initial_state = parse_linearized_initial_state(path, 2)
            plant = load_deployable_plant(path)

        A, B, C, D = matrices
        np.testing.assert_array_equal(A, [[-1.0, 0.0], [0.0, -2.0]])
        np.testing.assert_array_equal(B, [[1.0], [0.5]])
        np.testing.assert_array_equal(C, [[1.0, 0.0]])
        np.testing.assert_array_equal(D, [[0.0]])
        np.testing.assert_array_equal(initial_state, [0.25, -0.5])
        _, _, outputs, states = simulate_plant(
            plant,
            duration=0.01,
            sample_period=0.01,
            input_value=0.0,
        )
        np.testing.assert_array_equal(states[0], [0.25, -0.5])
        self.assertEqual(outputs[0], 0.25)

    def test_missing_initial_state_defaults_to_zero(self):
        source = MODEL_TEXT.replace("  parameter Real x0[n] = {0.25, -0.5};\n", "")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plant.mo"
            path.write_text(source, encoding="utf-8")

            initial_state = parse_linearized_initial_state(path, 2)

        np.testing.assert_array_equal(initial_state, [0.0, 0.0])

    def test_normalizes_single_state_linearizer_matrices(self):
        source = """\
model OneState
  parameter Integer n = 1 "number of states";
  parameter Integer m = 1 "number of inputs";
  parameter Integer p = 1 "number of outputs";
  parameter Real x0[n] = {0};
  parameter Real A[n, n] = [-20];
  parameter Real B[n, m] = [20];
  parameter Real C[p, n] = [1];
  parameter Real D[p, m] = [0];
end OneState;
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "one_state.mo"
            path.write_text(source, encoding="utf-8")
            plant = load_deployable_plant(path)

        self.assertEqual(plant.A.shape, (1, 1))
        self.assertEqual(plant.B.shape, (1, 1))
        self.assertEqual(plant.C.shape, (1, 1))
        self.assertEqual(plant.D.shape, (1, 1))

    def test_rejects_non_deployable_zero_input_linearization(self):
        content = MODEL_TEXT.replace("m = 1", "m = 0")
        content = content.replace("{1.0; 0.5}", "zeros(n, m)")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "no_input.mo"
            path.write_text(content, encoding="utf-8")

            with self.assertRaisesRegex(WorkflowError, "B must have shape"):
                load_deployable_plant(path)


class FirmwareGenerationTests(unittest.TestCase):
    def test_generates_model_and_safe_virtual_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plant.mo"
            path.write_text(MODEL_TEXT, encoding="utf-8")
            plant = load_deployable_plant(path)

        model_header = render_model_header(plant)
        config = render_firmware_config(
            mode="virtual",
            sample_period_us=1_000,
            telemetry_interval_us=100_000,
            virtual_input=1.0,
            adc_pin=None,
            pwm_pin=None,
            input_min=0.0,
            input_max=3.3,
            output_min=0.0,
            output_max=3.3,
        )
        self.assertIn("MODEL_STATE_COUNT = 2", model_header)
        self.assertIn("1.0f", model_header)
        self.assertIn("MODEL_X0[MODEL_STATE_COUNT] = {0.25f, -0.5f}", model_header)
        self.assertIn("#define MODEL_MODE_VIRTUAL 1", config)
        self.assertIn("#define IO_CONFIG_VALID 0", config)
        self.assertIn("#define PWM_PIN -1", config)

    def test_real_io_requires_valid_distinct_pins(self):
        options = {
            "mode": "io",
            "sample_period_us": 1_000,
            "telemetry_interval_us": 100_000,
            "virtual_input": 0.0,
            "adc_pin": None,
            "pwm_pin": None,
            "input_min": 0.0,
            "input_max": 3.3,
            "output_min": 0.0,
            "output_max": 3.3,
        }
        with self.assertRaisesRegex(WorkflowError, "requires both"):
            render_firmware_config(**options)

        options.update(adc_pin=32, pwm_pin=32)
        with self.assertRaisesRegex(WorkflowError, "different"):
            render_firmware_config(**options)
        options.update(adc_pin=34, pwm_pin=6)
        with self.assertRaisesRegex(WorkflowError, "reserved"):
            render_firmware_config(**options)

    def test_prepare_only_writes_headers_without_platformio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "plant.mo"
            model_path.write_text(MODEL_TEXT, encoding="utf-8")
            project = root / "pio"
            source = project / "src"
            source.mkdir(parents=True)

            result = main([
                "deploy",
                "--model",
                str(model_path),
                "--project-dir",
                str(project),
                "--prepare-only",
            ])

            self.assertEqual(result, 0)
            self.assertTrue((source / "plant_model.h").is_file())
            self.assertTrue((source / "firmware_config.h").is_file())

    def test_simulate_writes_state_and_output_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "plant.mo"
            model_path.write_text(MODEL_TEXT, encoding="utf-8")
            output_path = root / "simulation.csv"

            result = main([
                "simulate",
                "--model",
                str(model_path),
                "--duration",
                "0.02",
                "--sample-period",
                "0.01",
                "--output",
                str(output_path),
            ])

            self.assertEqual(result, 0)
            rows = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows[0], "time_s,input,output,x1,x2")
            self.assertEqual(len(rows), 4)

    def test_linearize_exports_supported_omc_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "graphical_plant.mo"
            source.write_text("model GraphicalPlant end GraphicalPlant;", encoding="utf-8")
            output = root / "generated" / "linearized.mo"

            def fake_run(command, *, cwd, **kwargs):
                artifact = Path(cwd) / "GraphicalPlant_linearized_model.mo"
                artifact.write_text(MODEL_TEXT, encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                patch("OpenModelicaFiles.modelica_workflow.shutil.which", return_value="/usr/bin/omc"),
                patch("OpenModelicaFiles.modelica_workflow.subprocess.run", side_effect=fake_run),
            ):
                result = linearize_model(
                    source,
                    model_class="GraphicalPlant",
                    output_path=output,
                )

            self.assertEqual(result, output)
            self.assertEqual(output.read_text(encoding="utf-8"), MODEL_TEXT)


class TelemetryProtocolTests(unittest.TestCase):
    def test_validates_firmware_telemetry_and_encodes_input_command(self):
        message = parse_telemetry_line(
            b'{"type":"telemetry","timestamp_us":1234,"input":0.5,'
            b'"output":1.0,"mode":"virtual","states":[0.25,-0.5]}\n'
        )
        self.assertEqual(message["states"], [0.25, -0.5])
        self.assertEqual(
            encode_input_command(2.0),
            b'{"type": "set_input", "value": 2.0}\n',
        )

    def test_rejects_malformed_or_non_finite_telemetry(self):
        with self.assertRaisesRegex(ValueError, "Invalid telemetry"):
            parse_telemetry_line(b"not-json")
        with self.assertRaisesRegex(ValueError, "finite"):
            parse_telemetry_line(
                b'{"type":"telemetry","timestamp_us":1,"input":NaN,'
                b'"output":0,"mode":"virtual","states":[0]}\n'
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            encode_input_command(float("nan"))


if __name__ == "__main__":
    unittest.main()
