import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from pycircuits_sim.analysis import bode_margins, nyquist_response, root_locus
from pycircuits_sim.io import WaveformData
from pycircuits_sim.linear_systems import transfer_function_to_state_space
from pycircuits_sim.plotting import (
    plot_bode_margins,
    plot_nyquist,
    plot_root_locus,
    plot_waveforms,
)

PLANT = transfer_function_to_state_space([1.0], [1.0, 3.0, 2.0])


class WaveformPlotTests(unittest.TestCase):
    def test_plot_saves_image_with_three_signal_panels(self) -> None:
        waveforms = WaveformData(
            time=[0.0, 0.0001, 0.0002],
            inductor_current=[0.0, 0.3, 0.2],
            output_voltage=[0.0, 1.1, 1.8],
            switch_on=[True, False, True],
        )
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "plots" / "waveforms.png"
            figure, axes = plot_waveforms(waveforms, output_path=output_path)
            try:
                self.assertGreater(output_path.stat().st_size, 0)
                self.assertEqual(len(axes), 3)
            finally:
                import matplotlib.pyplot as plt

                plt.close(figure)


class AnalysisPlotTests(unittest.TestCase):
    def _save(self, plotter, result) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "plot.png"
            figure = plotter(result, output_path=output_path)
            try:
                self.assertGreater(output_path.stat().st_size, 0)
            finally:
                import matplotlib.pyplot as plt

                plt.close(figure)

    def test_bode_margins_plot_saves(self) -> None:
        self._save(plot_bode_margins, bode_margins(PLANT))

    def test_nyquist_plot_saves(self) -> None:
        self._save(plot_nyquist, nyquist_response(PLANT))

    def test_root_locus_plot_saves(self) -> None:
        self._save(plot_root_locus, root_locus(PLANT, n_gains=40))

    def test_plots_require_output_or_show(self) -> None:
        with self.assertRaisesRegex(ValueError, "output_path or set show"):
            plot_bode_margins(bode_margins(PLANT))


if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()