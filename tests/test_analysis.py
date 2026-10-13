import math
import unittest

import numpy as np

from pycircuits_sim.analysis import (
    MarginResult,
    NyquistResult,
    PlantReport,
    RootLocusResult,
    StepMetrics,
    StabilityReport,
    analyze_stability,
    bode_margins,
    normalize_plant,
    nyquist_response,
    root_locus,
    step_metrics,
)
from pycircuits_sim.linear_systems import (
    StateSpaceModel,
    simulate_state_space,
    transfer_function_to_state_space,
)
from pycircuits_sim.optional import try_import_control

# Second-order teaching plant 1/(s^2+s+1): wn=1, zeta=0.5.
KNOWN = transfer_function_to_state_space([1.0], [1.0, 1.0, 1.0])


def unit_step(model, time_step: float, stop_time: float):
    return simulate_state_space(model, time_step, stop_time, lambda _t: (1.0,))


def _discrete_model():
    from pycircuits_sim.linear_systems import DiscreteStateSpaceModel

    return DiscreteStateSpaceModel.from_matrices(
        [[0.9]], [[0.1]], [[1.0]], [[0.0]], 0.01
    )


class PlantNormalizationTests(unittest.TestCase):
    def test_normalize_second_order_transfer_function(self) -> None:
        report = normalize_plant(KNOWN)
        self.assertIsInstance(report, PlantReport)
        self.assertEqual(report.numerator, (1.0,))
        self.assertEqual(len(report.denominator), 3)
        self.assertAlmostEqual(report.denominator[0], 1.0, places=12)
        self.assertAlmostEqual(report.denominator[1], 1.0, places=12)
        self.assertAlmostEqual(report.denominator[2], 1.0, places=12)
        poles = sorted(report.poles, key=lambda z: z.real)
        self.assertEqual(len(poles), 2)
        self.assertAlmostEqual(poles[0].real, -0.5, places=8)
        self.assertAlmostEqual(poles[1].real, -0.5, places=8)
        self.assertAlmostEqual(poles[0].imag, -math.sqrt(3.0) / 2.0, places=6)
        self.assertAlmostEqual(poles[1].imag, math.sqrt(3.0) / 2.0, places=6)
        self.assertEqual(report.zeros, ())
        self.assertAlmostEqual(report.dc_gain, 1.0, places=9)
        self.assertEqual(report.order, 2)
        self.assertEqual((report.input_count, report.output_count), (1, 1))

    def test_normalize_state_space_round_trip(self) -> None:
        model = StateSpaceModel.from_matrices(
            [[0.0, 1.0], [-1.0, -1.0]], [[0.0], [1.0]], [[1.0, 0.0]], [[0.0]]
        )
        report = normalize_plant(model)
        real_parts = sorted(p.real for p in report.poles)
        self.assertAlmostEqual(real_parts[0], -0.5, places=5)
        self.assertAlmostEqual(real_parts[1], -0.5, places=5)

    def test_normalize_reports_zeros_and_dc_gain(self) -> None:
        model = transfer_function_to_state_space([1.0, 2.0], [1.0, 3.0, 2.0])
        report = normalize_plant(model)
        self.assertEqual(len(report.zeros), 1)
        self.assertAlmostEqual(report.zeros[0].real, -2.0, places=8)
        self.assertAlmostEqual(report.dc_gain, 1.0, places=8)

    def test_normalize_integrator_has_no_dc_gain(self) -> None:
        integrator = transfer_function_to_state_space([1.0], [1.0, 0.0])
        report = normalize_plant(integrator)
        self.assertIsNone(report.dc_gain)

    def test_normalize_mimo_omits_transfer_function(self) -> None:
        model = StateSpaceModel.from_matrices(
            [[0.0, 1.0], [-1.0, -1.0]],
            [[0.0, 0.0], [1.0, 0.5]],
            [[1.0, 0.0]],
            [[0.0, 0.0]],
        )
        report = normalize_plant(model)
        self.assertIsNone(report.numerator)
        self.assertIsNone(report.dc_gain)
        self.assertEqual(report.zeros, ())

    def test_normalize_rejects_discrete_and_invalid_models(self) -> None:
        with self.assertRaisesRegex(ValueError, "continuous-time"):
            normalize_plant(_discrete_model())
        with self.assertRaisesRegex(ValueError, "StateSpaceModel"):
            normalize_plant("not a model")


class StabilityTests(unittest.TestCase):
    def test_poles_of_second_order(self) -> None:
        report = analyze_stability(KNOWN)
        self.assertIsInstance(report, StabilityReport)
        poles = sorted(report.poles, key=lambda z: z.imag)
        self.assertEqual(len(poles), 2)
        self.assertAlmostEqual(poles[0].real, -0.5, delta=1e-8)
        self.assertAlmostEqual(poles[1].real, -0.5, delta=1e-8)
        self.assertAlmostEqual(poles[0].imag, -math.sqrt(3.0) / 2.0, delta=1e-6)
        self.assertAlmostEqual(poles[1].imag, math.sqrt(3.0) / 2.0, delta=1e-6)
        self.assertTrue(report.bibo_stable)
        self.assertTrue(report.lyapunov_asymptotic)
        self.assertIn("open left half-plane", report.bibo_reason)

    def test_integrator_not_bibo_stable(self) -> None:
        integrator = transfer_function_to_state_space([1.0], [1.0, 0.0])
        report = analyze_stability(integrator)
        self.assertFalse(report.bibo_stable)
        self.assertFalse(report.lyapunov_asymptotic)
        self.assertIn("imaginary axis", report.bibo_reason)

    def test_unstable_pendulum_reported_unstable(self) -> None:
        pendulum = transfer_function_to_state_space([1.0], [1.0, 0.0, -9.81])
        report = analyze_stability(pendulum)
        self.assertFalse(report.bibo_stable)
        self.assertFalse(report.lyapunov_asymptotic)
        self.assertIn("positive real part", report.bibo_reason)
        self.assertGreater(report.max_real_pole, 3.0)


class StepMetricsTests(unittest.TestCase):
    def test_second_order_step_overshoot_matches_zeta(self) -> None:
        # zeta=0.5 predicts ~16.3% overshoot.
        result = unit_step(KNOWN, time_step=0.001, stop_time=20.0)
        metrics = step_metrics(result.time, result.outputs["y1"])
        self.assertIsInstance(metrics, StepMetrics)
        self.assertIsNotNone(metrics.overshoot_percent)
        self.assertAlmostEqual(metrics.overshoot_percent, 16.3, delta=1.0)
        self.assertAlmostEqual(metrics.steady_state, 1.0, delta=0.01)
        self.assertIsNotNone(metrics.settling_time_s)
        self.assertLess(metrics.settling_time_s, 12.0)

    def test_first_order_rise_time_matches_theory(self) -> None:
        first_order = transfer_function_to_state_space([1.0], [1.0, 1.0])
        result = unit_step(first_order, time_step=0.001, stop_time=10.0)
        metrics = step_metrics(result.time, result.outputs["y1"])
        # 10-90% rise time of 1/(s+1) is ln(9) ~= 2.197 s.
        self.assertAlmostEqual(metrics.rise_time_s, math.log(9.0), delta=0.05)
        self.assertAlmostEqual(metrics.overshoot_percent, 0.0, delta=0.1)
        self.assertAlmostEqual(metrics.peak, 1.0, delta=0.01)

    def test_step_metrics_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            step_metrics([0.0, 2.0, 1.0], [0.0, 1.0, 0.5])
        with self.assertRaisesRegex(ValueError, "equal-length"):
            step_metrics([0.0, 1.0], [0.0])
        with self.assertRaisesRegex(ValueError, "settling_band"):
            step_metrics([0.0, 1.0], [0.0, 1.0], settling_band=1.5)


class MarginTests(unittest.TestCase):
    def test_second_order_open_loop_has_no_phase_crossover(self) -> None:
        margins = bode_margins(KNOWN)
        self.assertIsInstance(margins, MarginResult)
        # 1/(s^2+s+1) phase never crosses -180 deg, so gain margin is None.
        self.assertIsNone(margins.gain_margin)
        self.assertIsNone(margins.phase_crossover_rad_s)
        self.assertIsNotNone(margins.phase_margin_deg)
        self.assertGreater(margins.phase_margin_deg, 40.0)
        self.assertEqual(len(margins.frequencies_rad_s), 400)

    def test_integrator_loop_margins_match_theory(self) -> None:
        # G(s)=4/(s+1)^3: phase crosses -180 deg at w=sqrt(3) where
        # |G(j*sqrt(3))| = 4/2^3 = 0.5, so gain margin is exactly 2.
        plant = transfer_function_to_state_space([4.0], [1.0, 3.0, 3.0, 1.0])
        margins = bode_margins(plant)
        self.assertAlmostEqual(margins.phase_crossover_rad_s, math.sqrt(3.0), delta=0.02)
        self.assertAlmostEqual(margins.gain_margin, 2.0, delta=0.02)
        self.assertAlmostEqual(margins.gain_margin_db, 20.0 * math.log10(2.0), delta=0.2)
        # Gain crossover solves (1+w^2)^{3/2} = 4.
        expected_wc = math.sqrt(4.0 ** (2.0 / 3.0) - 1.0)
        self.assertAlmostEqual(margins.gain_crossover_rad_s, expected_wc, delta=0.02)
        expected_pm = 180.0 - 3.0 * math.degrees(math.atan(expected_wc))
        self.assertAlmostEqual(margins.phase_margin_deg, expected_pm, delta=1.0)

    def test_margins_reject_mimo_and_discrete(self) -> None:
        mimo = StateSpaceModel.from_matrices(
            [[0.0, 1.0], [-1.0, -1.0]],
            [[0.0, 0.0], [1.0, 0.5]],
            [[1.0, 0.0]],
            [[0.0, 0.0]],
        )
        with self.assertRaisesRegex(ValueError, "SISO"):
            bode_margins(mimo)
        with self.assertRaisesRegex(ValueError, "continuous-time"):
            bode_margins(_discrete_model())


class NyquistTests(unittest.TestCase):
    def test_first_order_nyquist_starts_near_dc_gain(self) -> None:
        first_order = transfer_function_to_state_space([1.0], [1.0, 1.0])
        result = nyquist_response(first_order)
        self.assertIsInstance(result, NyquistResult)
        # G(j*1e-3) ~= 1/(1+j*1e-3): real ~= 1, imag ~= -1e-3.
        self.assertAlmostEqual(result.real[0], 1.0, delta=1e-3)
        self.assertAlmostEqual(result.imaginary[0], -1e-3, delta=1e-4)
        self.assertEqual(
            len(result.real), len(result.imaginary), len(result.frequencies_rad_s)
        )
        # High-frequency end tends to the origin for a strictly proper plant.
        self.assertLess(abs(result.real[-1] + 1j * result.imaginary[-1]), 0.01)

    def test_nyquist_rejects_mimo(self) -> None:
        mimo = StateSpaceModel.from_matrices(
            [[0.0, 1.0], [-1.0, -1.0]],
            [[0.0, 0.0], [1.0, 0.5]],
            [[1.0, 0.0]],
            [[0.0, 0.0]],
        )
        with self.assertRaisesRegex(ValueError, "SISO"):
            nyquist_response(mimo)


class RootLocusTests(unittest.TestCase):
    def test_locus_starts_at_open_loop_poles(self) -> None:
        plant = transfer_function_to_state_space([1.0], [1.0, 1.0, 0.0])
        locus = root_locus(plant, n_gains=100)
        self.assertIsInstance(locus, RootLocusResult)
        self.assertEqual(len(locus.branches), 2)
        self.assertEqual(len(locus.gains), len(locus.branches[0]))
        self.assertEqual(locus.gains[0], 0.0)
        poles = sorted(locus.open_loop_poles, key=lambda z: z.real)
        self.assertAlmostEqual(poles[0].real, -1.0, places=6)
        self.assertAlmostEqual(poles[1].real, 0.0, places=6)
        for branch, pole in zip(locus.branches, locus.open_loop_poles):
            self.assertAlmostEqual(branch[0], pole, places=9)

    def test_locus_branches_head_toward_zeros(self) -> None:
        # (s+2)/(s^2+3s+2): one finite zero at -2; a branch must approach it.
        plant = transfer_function_to_state_space([1.0, 2.0], [1.0, 3.0, 2.0])
        locus = root_locus(plant, gains=[0.0, 1.0, 10.0, 1e3, 1e6])
        self.assertEqual(len(locus.open_loop_zeros), 1)
        endpoint_distances = [
            min(abs(branch[-1] - zero) for zero in locus.open_loop_zeros)
            for branch in locus.branches
        ]
        self.assertLess(min(endpoint_distances), 0.01)

    def test_locus_rejects_mimo(self) -> None:
        mimo = StateSpaceModel.from_matrices(
            [[0.0, 1.0], [-1.0, -1.0]],
            [[0.0, 0.0], [1.0, 0.5]],
            [[1.0, 0.0]],
            [[0.0, 0.0]],
        )
        with self.assertRaisesRegex(ValueError, "SISO"):
            root_locus(mimo)


@unittest.skipUnless(
    try_import_control() is not None, "python-control not installed"
)
class ControlFastPathTests(unittest.TestCase):
    def test_numpy_margins_agree_with_python_control(self) -> None:
        control = try_import_control()
        system = control.ss(
            np.asarray(KNOWN.A),
            np.asarray(KNOWN.B),
            np.asarray(KNOWN.C),
            np.asarray(KNOWN.D),
        )
        _, pm, _, wcp = control.margin(system)
        margins = bode_margins(KNOWN)
        self.assertAlmostEqual(margins.phase_margin_deg, float(pm), delta=0.5)
        self.assertAlmostEqual(margins.gain_crossover_rad_s, float(wcp), rel=0.02)


if __name__ == "__main__":
    unittest.main()

