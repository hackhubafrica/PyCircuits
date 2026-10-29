import csv
import tempfile
import unittest
from pathlib import Path

from pycircuits_sim.buck import SimulationResult
from pycircuits_sim.io import write_metrics_csv
from pycircuits_sim.metrics import measure_sweep
from pycircuits_sim.sweep import SweepRun


class SweepMetricsTests(unittest.TestCase):
    def test_known_trace_metrics(self) -> None:
        result = SimulationResult(
            time=[float(index) for index in range(10)],
            inductor_current=[0.0, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 3.0, 5.0, 4.0],
            output_voltage=[0.0, 12.0, 10.0, 10.0, 10.0, 10.0, 10.0, 9.0, 11.0, 10.0],
            switch_on=[False] * 10,
        )

        metrics = measure_sweep(
            [SweepRun("inductance", 0.001, result)],
            steady_state_fraction=0.3,
            settling_band=0.1,
        )[0]

        self.assertEqual(metrics.steady_state_output_voltage_v, 10.0)
        self.assertEqual(metrics.peak_output_voltage_v, 12.0)
        self.assertAlmostEqual(metrics.peak_overshoot_percent, 20.0)
        self.assertEqual(metrics.settling_time_s, 2.0)
        self.assertEqual(metrics.output_voltage_ripple_pp_v, 2.0)
        self.assertEqual(metrics.inductor_current_ripple_pp_a, 2.0)

    def test_settling_is_none_when_trace_never_enters_band(self) -> None:
        result = SimulationResult(
            time=[0.0, 1.0, 2.0, 3.0],
            inductor_current=[0.0] * 4,
            output_voltage=[0.0, 10.0, 0.0, 10.0],
            switch_on=[False] * 4,
        )

        metrics = measure_sweep(
            [SweepRun("duty_cycle", 0.5, result)],
            steady_state_fraction=0.5,
        )[0]

        self.assertIsNone(metrics.settling_time_s)

    def test_metrics_csv_has_one_summary_row_per_run(self) -> None:
        result = SimulationResult(
            time=[0.0, 1.0],
            inductor_current=[0.0, 1.0],
            output_voltage=[0.0, 2.0],
            switch_on=[False, True],
        )
        metrics = measure_sweep(
            [
                SweepRun("duty_cycle", 0.3, result),
                SweepRun("duty_cycle", 0.7, result),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "metrics.csv"
            write_metrics_csv(metrics, output_path)
            with output_path.open(newline="", encoding="utf-8") as metrics_file:
                rows = list(csv.reader(metrics_file))

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0:2], ["parameter", "value"])


if __name__ == "__main__":
    unittest.main()
