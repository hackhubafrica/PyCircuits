import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from pycircuits_sim import BuckConfig, run_parameter_sweep
from pycircuits_sim.io import write_sweep_csv
from pycircuits_sim.plotting import plot_sweep


def make_config() -> BuckConfig:
    return BuckConfig(
        input_voltage=12.0,
        duty_cycle=0.5,
        switching_frequency=10_000.0,
        inductance=0.001,
        capacitance=0.0001,
        load_resistance=10.0,
        time_step=0.000001,
        stop_time=0.001,
    )


class ParameterSweepTests(unittest.TestCase):
    def test_sweep_runs_aligned_distinct_traces(self) -> None:
        runs = run_parameter_sweep(
            make_config(), "inductance", [0.0005, 0.001, 0.002]
        )

        self.assertEqual(len(runs), 3)
        self.assertEqual(runs[0].result.time, runs[1].result.time)
        self.assertNotEqual(
            runs[0].result.inductor_current,
            runs[-1].result.inductor_current,
        )

    def test_sweep_rejects_unsupported_parameter(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported sweep parameter"):
            run_parameter_sweep(make_config(), "switching_frequency", [8_000, 10_000])

    def test_sweep_exports_csv_and_overlay_plot(self) -> None:
        runs = run_parameter_sweep(make_config(), "duty_cycle", [0.3, 0.5, 0.7])
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "sweep.csv"
            image_path = Path(directory) / "sweep.png"
            write_sweep_csv(runs, csv_path)
            figure, axes = plot_sweep(runs, output_path=image_path)
            try:
                with csv_path.open(newline="", encoding="utf-8") as sweep_file:
                    rows = list(csv.reader(sweep_file))
                self.assertEqual(len(rows), 1 + sum(len(run.result.time) for run in runs))
                self.assertGreater(image_path.stat().st_size, 0)
                self.assertEqual(len(axes), 2)
                self.assertEqual(len(axes[0].lines), len(runs))
            finally:
                import matplotlib.pyplot as plt

                plt.close(figure)


if __name__ == "__main__":
    unittest.main()