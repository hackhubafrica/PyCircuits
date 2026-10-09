import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from pycircuits_sim import (
    BuckConfig,
    ClosedLoopConfig,
    PIDConfig,
    ReferenceStep,
    simulate_closed_loop,
)
from pycircuits_sim.io import load_closed_loop_config, write_closed_loop_csv
from pycircuits_sim.plotting import plot_closed_loop


def make_config(**controller_overrides: float) -> ClosedLoopConfig:
    plant = BuckConfig(
        input_voltage=12.0,
        duty_cycle=0.3,
        switching_frequency=10_000.0,
        inductance=0.001,
        capacitance=0.0001,
        load_resistance=10.0,
        time_step=0.000001,
        stop_time=0.006,
    )
    controller_values = {
        "kp": 0.12,
        "ki": 50.0,
        "kd": 0.00005,
        "sample_time": 0.0001,
        "duty_min": 0.0,
        "duty_max": 0.8,
    }
    controller_values.update(controller_overrides)
    return ClosedLoopConfig(
        plant=plant,
        controller=PIDConfig(**controller_values),
        reference=ReferenceStep(0.0, 5.0, 0.001),
    )


class ClosedLoopBuckTests(unittest.TestCase):
    def test_controller_tracks_reference_and_respects_limits(self) -> None:
        result = simulate_closed_loop(make_config())

        self.assertGreater(result.output_voltage[-1], 0.0)
        self.assertLess(result.output_voltage[-1], 8.0)
        self.assertGreater(max(result.duty_cycle), 0.0)
        self.assertLessEqual(max(result.duty_cycle), 0.8)
        self.assertGreaterEqual(min(result.duty_cycle), 0.0)
        self.assertEqual(len(result.reference_voltage), len(result.time))
        self.assertEqual(len(result.error), len(result.time))

    def test_duty_and_pid_terms_are_held_between_controller_ticks(self) -> None:
        result = simulate_closed_loop(make_config(kd=0.0))
        controller_steps = 100

        for sample_index in range(2, len(result.time)):
            if sample_index % controller_steps != 1:
                self.assertEqual(
                    result.duty_cycle[sample_index],
                    result.duty_cycle[sample_index - 1],
                )
                self.assertEqual(
                    result.proportional_term[sample_index],
                    result.proportional_term[sample_index - 1],
                )

    def test_controller_sample_must_align_to_plant_timestep(self) -> None:
        with self.assertRaisesRegex(ValueError, "integer multiple"):
            make_config(sample_time=0.0000015)

    def test_csv_and_plot_include_controller_signals(self) -> None:
        result = simulate_closed_loop(make_config())
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "closed.csv"
            plot_path = Path(directory) / "closed.png"
            write_closed_loop_csv(result, csv_path)
            figure, axes = plot_closed_loop(result, output_path=plot_path)
            try:
                with csv_path.open(newline="", encoding="utf-8") as csv_file:
                    rows = list(csv.reader(csv_file))
                self.assertEqual(
                    rows[0],
                    [
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
                    ],
                )
                self.assertEqual(len(rows), len(result.time) + 1)
                self.assertGreater(plot_path.stat().st_size, 0)
                self.assertEqual(len(axes), 4)
            finally:
                import matplotlib.pyplot as plt

                plt.close(figure)


if __name__ == "__main__":
    unittest.main()