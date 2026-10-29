import tempfile
import unittest
from pathlib import Path

from pycircuits_sim import BuckConfig, simulate_buck
from pycircuits_sim.io import read_waveforms_csv, write_csv


def make_config(**overrides: float) -> BuckConfig:
    values = {
        "input_voltage": 12.0,
        "duty_cycle": 0.5,
        "switching_frequency": 10_000.0,
        "inductance": 0.001,
        "capacitance": 0.0001,
        "load_resistance": 10.0,
        "time_step": 0.000001,
        "stop_time": 0.005,
    }
    values.update(overrides)
    return BuckConfig(**values)


class BuckSimulationTests(unittest.TestCase):
    def test_output_rises_toward_duty_scaled_input(self) -> None:
        result = simulate_buck(make_config())

        self.assertGreater(result.output_voltage[-1], 4.5)
        self.assertLess(result.output_voltage[-1], 6.5)
        self.assertGreater(max(result.inductor_current), 0.0)
        self.assertEqual(len(result.time), len(result.output_voltage))
        self.assertEqual(len(result.switch_on), len(result.time))

    def test_zero_duty_discharges_output_and_blocks_negative_current(self) -> None:
        result = simulate_buck(
            make_config(
                duty_cycle=0.0,
                initial_current=0.0,
                initial_voltage=5.0,
                stop_time=0.001,
            )
        )

        self.assertLess(result.output_voltage[-1], 5.0)
        self.assertGreaterEqual(min(result.inductor_current), 0.0)
        self.assertFalse(any(result.switch_on))

    def test_invalid_duty_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duty_cycle"):
            make_config(duty_cycle=1.1)

    def test_csv_export_has_named_columns_and_samples(self) -> None:
        result = simulate_buck(make_config(stop_time=0.00001))
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "waveforms.csv"
            write_csv(result, output_path)
            lines = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            lines[0],
            "time_s,inductor_current_a,output_voltage_v,switch_on",
        )
        self.assertEqual(len(lines), len(result.time) + 1)

    def test_waveform_csv_reader_round_trips_export(self) -> None:
        result = simulate_buck(make_config(stop_time=0.00001))
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "waveforms.csv"
            write_csv(result, output_path)
            waveforms = read_waveforms_csv(output_path)

        self.assertEqual(waveforms.time, result.time)
        self.assertEqual(waveforms.inductor_current, result.inductor_current)
        self.assertEqual(waveforms.output_voltage, result.output_voltage)
        self.assertEqual(waveforms.switch_on, result.switch_on)

    def test_waveform_csv_reader_rejects_invalid_switch_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "bad.csv"
            output_path.write_text(
                "time_s,inductor_current_a,output_voltage_v,switch_on\n0,0,0,maybe\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "row 2: switch_on"):
                read_waveforms_csv(output_path)


if __name__ == "__main__":
    unittest.main()
