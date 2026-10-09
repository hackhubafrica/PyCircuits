import csv
import tempfile
import unittest
from pathlib import Path

from pycircuits_sim.io import write_mna_csv
from pycircuits_sim.mna import load_mna_config, simulate_mna


def make_config(components: list[dict], time_step: float = 0.001, stop_time: float = 0.003):
    return load_mna_config(
        {
            "time_step": time_step,
            "stop_time": stop_time,
            "components": components,
        }
    )


class MNATransientTests(unittest.TestCase):
    def test_resistor_divider_with_voltage_source(self) -> None:
        config = make_config(
            [
                {"name": "V1", "type": "voltage_source", "p": "in", "n": "0", "value": 12},
                {"name": "R1", "type": "resistor", "p": "in", "n": "out", "value": 1000},
                {"name": "R2", "type": "resistor", "p": "out", "n": "0", "value": 1000},
            ]
        )

        result = simulate_mna(config)

        self.assertAlmostEqual(result.node_voltages["in"][-1], 12.0)
        self.assertAlmostEqual(result.node_voltages["out"][-1], 6.0)
        self.assertAlmostEqual(result.component_currents["R1"][-1], 0.006)

    def test_backward_euler_rc_step(self) -> None:
        config = make_config(
            [
                {"name": "V1", "type": "voltage_source", "p": "in", "n": "0", "value": 10},
                {"name": "R1", "type": "resistor", "p": "in", "n": "out", "value": 1000},
                {"name": "C1", "type": "capacitor", "p": "out", "n": "0", "value": 0.000001},
            ],
            time_step=0.001,
        )

        result = simulate_mna(config)

        self.assertAlmostEqual(result.node_voltages["out"][1], 5.0)
        self.assertAlmostEqual(result.node_voltages["out"][2], 7.5)

    def test_backward_euler_inductor_current_rise(self) -> None:
        config = make_config(
            [
                {"name": "V1", "type": "voltage_source", "p": "in", "n": "0", "value": 10},
                {"name": "R1", "type": "resistor", "p": "in", "n": "coil", "value": 10},
                {"name": "L1", "type": "inductor", "p": "coil", "n": "0", "value": 0.01},
            ],
            time_step=0.001,
        )

        result = simulate_mna(config)

        self.assertAlmostEqual(result.component_currents["L1"][1], 0.5)
        self.assertAlmostEqual(result.component_currents["L1"][-1], 0.875)

    def test_pwl_switch_changes_resistive_state(self) -> None:
        config = make_config(
            [
                {"name": "V1", "type": "voltage_source", "p": "in", "n": "0", "value": 10},
                {"name": "R1", "type": "resistor", "p": "in", "n": "out", "value": 1000},
                {
                    "name": "S1",
                    "type": "switch",
                    "p": "out",
                    "n": "0",
                    "ron": 0.1,
                    "roff": 1e9,
                    "threshold": 0.5,
                    "control_points": [[0.0, 0.0], [0.001, 0.0], [0.0011, 1.0]],
                },
            ],
            time_step=0.0001,
            stop_time=0.002,
        )

        result = simulate_mna(config)

        self.assertFalse(result.switch_states["S1"][5])
        self.assertTrue(result.switch_states["S1"][12])
        self.assertGreater(result.node_voltages["out"][5], 9.9)
        self.assertLess(result.node_voltages["out"][12], 0.01)

    def test_sine_voltage_source_and_csv_export(self) -> None:
        config = make_config(
            [
                {
                    "name": "VAC",
                    "type": "voltage_source",
                    "p": "ac",
                    "n": "ground",
                    "waveform": {
                        "type": "sine",
                        "offset": 0.0,
                        "amplitude": 10.0,
                        "frequency": 50.0,
                    },
                }
            ],
            time_step=0.001,
            stop_time=0.01,
        )

        result = simulate_mna(config)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mna.csv"
            write_mna_csv(result, output)
            with output.open(newline="", encoding="utf-8") as csv_file:
                rows = list(csv.reader(csv_file))

        self.assertAlmostEqual(result.node_voltages["ac"][5], 10.0)
        self.assertEqual(rows[0][0:2], ["time_s", "node_voltage_ac_v"])
        self.assertEqual(len(rows), len(result.time) + 1)

    def test_singular_floating_network_has_actionable_error(self) -> None:
        config = make_config(
            [{"name": "R1", "type": "resistor", "p": "a", "n": "b", "value": 1000}]
        )

        with self.assertRaisesRegex(ValueError, "singular.*floating nodes"):
            simulate_mna(config)


if __name__ == "__main__":
    unittest.main()