import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from pycircuits_sim.io import WaveformData
from pycircuits_sim.plotting import plot_waveforms


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


if __name__ == "__main__":
    unittest.main()