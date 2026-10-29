import unittest

import numpy as np

from pycircuits_sim.design import (
    FopdtFit,
    StateFeedbackResult,
    TuneResult,
    ackermann,
    lqr,
    pid_transfer_function,
    tune_pole_placement,
    ziegler_nichols,
)
from pycircuits_sim.linear_systems import (
    DiscreteStateSpaceModel,
    StateSpaceModel,
    transfer_function_to_state_space,
)
from pycircuits_sim.optional import try_import_scipy

# Second-order teaching plant 1/(s^2+s+1): wn=1, zeta=0.5.
KNOWN = transfer_function_to_state_space([1.0], [1.0, 1.0, 1.0])
# 1/((s+1)(s+2)(s+3)): stable, finite phase crossover -> ultimate-gain ZN.
THIRD_ORDER = transfer_function_to_state_space([1.0], [1.0, 6.0, 11.0, 6.0])
# Controllable canonical plant of s^3+6s^2+11s+6 (ControlKit's CONT3).
CONT3 = StateSpaceModel.from_matrices(
    [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-6.0, -11.0, -6.0]],
    [[0.0], [0.0], [1.0]],
    [[1.0, 0.0, 0.0]],
    [[0.0]],
)
# Undamped oscillator (ControlKit's OSC).
OSC = StateSpaceModel.from_matrices(
    [[0.0, 1.0], [-1.0, 0.0]], [[0.0], [1.0]], [[1.0, 0.0]], [[0.0]]
)
UNCONTROLLABLE = StateSpaceModel.from_matrices(
    [[0.0, 0.0], [0.0, -1.0]], [[1.0], [0.0]], [[1.0, 1.0]], [[0.0]]
)
PENDULUM = transfer_function_to_state_space([1.0], [1.0, 0.0, -9.81])


def _discrete_model() -> DiscreteStateSpaceModel:
    return DiscreteStateSpaceModel.from_matrices([[0.9]], [[0.1]], [[1.0]], [[0.0]], 0.01)


def _mimo_model() -> StateSpaceModel:
    return StateSpaceModel.from_matrices(
        [[0.0, 1.0], [-1.0, -1.0]],
        [[0.0, 0.0], [1.0, 0.5]],
        [[1.0, 0.0]],
        [[0.0, 0.0]],
    )


class PIDTransferFunctionTests(unittest.TestCase):
    def test_plain_parallel_pid_coefficients(self) -> None:
        num, den = pid_transfer_function(1.2, 0.4, 0.2)
        self.assertEqual(num, (0.2, 1.2, 0.4))
        self.assertEqual(den, (1.0, 0.0))

    def test_derivative_filter_realization(self) -> None:
        num, den = pid_transfer_function(1.2, 0.4, 0.2, derivative_filter=10.0)
        self.assertEqual(num, (1.2 + 0.2 * 10.0, 1.2 * 10.0 + 0.4, 0.4 * 10.0))
        self.assertEqual(den, (1.0, 10.0, 0.0))

    def test_rejects_nonfinite_gains(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            pid_transfer_function(float("inf"), 0.0, 0.0)


class ZieglerNicholsTests(unittest.TestCase):
    def test_ultimate_on_third_order_plant(self) -> None:
        result = ziegler_nichols(THIRD_ORDER)
        self.assertIsInstance(result, TuneResult)
        self.assertEqual(result.method, "ziegler_nichols")
        self.assertEqual(result.variant, "ultimate")
        self.assertIsNotNone(result.ku)
        self.assertIsNotNone(result.pu)
        self.assertGreater(result.ku, 0.0)
        self.assertGreater(result.pu, 0.0)
        self.assertGreater(result.gains.kp, 0.0)
        # Classic table: P = 0.5 Ku, PI = 0.45 Ku, PID = 0.6 Ku.
        assert result.p_gains is not None and result.pi_gains is not None
        self.assertAlmostEqual(result.p_gains.kp, 0.5 * result.ku, places=9)
        self.assertAlmostEqual(result.pi_gains.kp, 0.45 * result.ku, places=9)
        self.assertAlmostEqual(result.gains.kp, 0.6 * result.ku, places=9)
        self.assertAlmostEqual(result.gains.ki, 0.6 * result.ku / (result.pu / 2.0), places=9)
        self.assertAlmostEqual(result.gains.kd, 0.6 * result.ku * (result.pu / 8.0), places=9)
        self.assertIsNone(result.fopdt)
        self.assertIn("ultimate", result.message)

    def test_reaction_curve_fallback_on_second_order(self) -> None:
        # 1/(s^2+s+1) has no phase crossover -> FOPDT reaction-curve method.
        result = ziegler_nichols(KNOWN)
        self.assertEqual(result.variant, "reaction_curve")
        self.assertIsInstance(result.fopdt, FopdtFit)
        self.assertGreater(result.fopdt.dead_time_s, 0.0)
        self.assertGreater(result.fopdt.time_constant_s, 0.0)
        self.assertGreater(result.fopdt.gain, 0.0)
        self.assertGreater(result.gains.kp, 0.0)
        self.assertGreater(result.gains.ki, 0.0)
        self.assertGreater(result.gains.kd, 0.0)
        self.assertIsNone(result.ku)
        self.assertIsNone(result.pu)
        self.assertIn("reaction curve", result.message)
        # Table: Kp = 1.2 tau/(K theta), Ki = Kp/(2 theta), Kd = Kp*theta/2.
        fit = result.fopdt
        expected_kp = 1.2 * fit.time_constant_s / (fit.gain * fit.dead_time_s)
        self.assertAlmostEqual(result.gains.kp, expected_kp, places=9)
        self.assertAlmostEqual(result.gains.ki, expected_kp / (2.0 * fit.dead_time_s), places=9)
        self.assertAlmostEqual(result.gains.kd, expected_kp * (0.5 * fit.dead_time_s), places=9)

    def test_unusable_plant_raises_readable_error(self) -> None:
        # Unstable pendulum: no finite Ku, no bounded reaction curve.
        with self.assertRaises(ValueError) as caught:
            ziegler_nichols(PENDULUM)
        message = str(caught.exception).lower()
        self.assertIn("phase-crossover", message)
        self.assertIn("reaction curve", message)
        self.assertIn("pole placement", message)

    def test_rejects_discrete_and_mimo(self) -> None:
        with self.assertRaisesRegex(ValueError, "continuous-time"):
            ziegler_nichols(_discrete_model())
        with self.assertRaisesRegex(ValueError, "SISO"):
            ziegler_nichols(_mimo_model())


class PolePlacementTests(unittest.TestCase):
    def test_pd_mapping_matches_theory(self) -> None:
        # Desired s^2+4s+5 on plant 1/(s^2+s+1): Kd=(4-1)/1=3,
        # Kp=(5-1)/1=4, Ki=0 (ControlKit's accepted values).
        result = tune_pole_placement(KNOWN, [-2.0 + 1.0j, -2.0 - 1.0j])
        self.assertIsInstance(result, TuneResult)
        self.assertEqual(result.method, "pole_placement")
        self.assertAlmostEqual(result.gains.ki, 0.0, delta=1e-9)
        self.assertAlmostEqual(result.gains.kp, 4.0, delta=1e-6)
        self.assertAlmostEqual(result.gains.kd, 3.0, delta=1e-6)
        self.assertIsNotNone(result.state_feedback_k)
        self.assertIn("PD", result.message)
        # Ackermann K must place the poles: eig(A - BK) = desired.
        assert result.state_feedback_k is not None
        k = np.asarray(result.state_feedback_k, dtype=float)
        a = np.asarray(KNOWN.A, dtype=float)
        b = np.asarray(KNOWN.B, dtype=float)
        closed = np.sort_complex(np.linalg.eigvals(a - b @ k))
        want = np.sort_complex(np.array([-2.0 + 1.0j, -2.0 - 1.0j]))
        np.testing.assert_allclose(closed, want, atol=1e-6)

    def test_three_poles_on_second_order_plant_rejected(self) -> None:
        # Ackermann needs exactly `order` poles; PID (3-pole) mapping on a
        # 2nd-order plant would need an integrator state, so this is rejected
        # exactly as ControlKit rejected it.
        with self.assertRaisesRegex(ValueError, "exactly 2"):
            tune_pole_placement(KNOWN, [-4.0 + 2.0j, -4.0 - 2.0j, -5.0])

    def test_third_order_plant_reports_only_state_feedback(self) -> None:
        result = tune_pole_placement(THIRD_ORDER, [-2.0, -3.0 + 1.0j, -3.0 - 1.0j])
        # No PID mapping for order-3 plants; gains zeroed, K still valid.
        self.assertEqual((result.gains.kp, result.gains.ki, result.gains.kd), (0.0, 0.0, 0.0))
        self.assertIsNotNone(result.state_feedback_k)
        self.assertIn("Use K for state feedback", result.message)

    def test_wrong_pole_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 3"):
            tune_pole_placement(CONT3, [-1.0, -2.0])

    def test_uncontrollable_plant_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "controllable"):
            tune_pole_placement(UNCONTROLLABLE, [-1.0, -2.0])

    def test_rejects_discrete_and_empty_poles(self) -> None:
        with self.assertRaisesRegex(ValueError, "continuous-time"):
            tune_pole_placement(_discrete_model(), [-1.0])
        with self.assertRaisesRegex(ValueError, "at least one"):
            tune_pole_placement(KNOWN, [])


class AckermannTests(unittest.TestCase):
    DESIRED = [-2.0 + 0.0j, -3.0 + 1.0j, -3.0 - 1.0j]

    def test_places_poles_and_reports_steps(self) -> None:
        result = ackermann(CONT3, self.DESIRED)
        self.assertIsInstance(result, StateFeedbackResult)
        self.assertEqual(result.method, "ackermann")
        k = np.asarray(result.closed_loop_k, dtype=float)
        self.assertEqual(k.shape, (1, 3))
        a = np.asarray(CONT3.A, dtype=float)
        b = np.asarray(CONT3.B, dtype=float)
        closed = np.sort_complex(np.linalg.eigvals(a - b @ k))
        want = np.sort_complex(np.asarray(self.DESIRED, dtype=complex))
        np.testing.assert_allclose(closed, want, atol=1e-6)
        self.assertEqual(result.order, 3)
        self.assertEqual(result.controllability_rank, 3)
        self.assertIsNotNone(result.nbar)
        self.assertEqual(len(result.open_step.output), len(result.open_step.time_s))
        self.assertGreater(len(result.closed_step.output), 10)
        self.assertGreater(len(result.open_step.output), 10)
        self.assertEqual(len(result.desired_poles or ()), 3)
        # Closed-loop poles equal the desired poles.
        np.testing.assert_allclose(
            np.sort_complex(np.asarray(result.closed_loop_poles)),
            want,
            atol=1e-6,
        )

    def test_nbar_closed_loop_reaches_unit_reference(self) -> None:
        result = ackermann(CONT3, self.DESIRED)
        assert result.nbar is not None
        # Settled closed-loop step must be ~1 thanks to the N-bar pre-gain.
        self.assertAlmostEqual(result.closed_step.output[-1], 1.0, delta=0.05)

    def test_wrong_pole_count_and_uncontrollable_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 3"):
            ackermann(CONT3, [-1.0, -2.0])
        with self.assertRaisesRegex(ValueError, "controllable"):
            ackermann(UNCONTROLLABLE, [-1.0, -2.0])

    def test_complex_result_without_symmetry_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "conjugate"):
            ackermann(CONT3, [-1.0 + 1.0j, -2.0, -3.0])

    def test_rejects_discrete_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "continuous-time"):
            ackermann(_discrete_model(), [-1.0])


class LqrTests(unittest.TestCase):
    def test_numpy_lqr_stabilizes_oscillator(self) -> None:
        result = lqr(OSC, [1.0, 1.0], 1.0)
        self.assertEqual(result.method, "lqr")
        k = np.asarray(result.closed_loop_k, dtype=float)
        self.assertEqual(k.shape, (1, 2))
        self.assertIsNotNone(result.s)
        self.assertEqual(len(result.s), 2)
        self.assertEqual(result.q, (1.0, 1.0))
        self.assertEqual(result.r, 1.0)
        self.assertTrue(all(p.real < 0 for p in result.closed_loop_poles))
        self.assertIsNotNone(result.nbar)

    def test_numpy_lqr_solves_care(self) -> None:
        # Verify A^T P + P A - P B R^-1 B^T P + Q = 0 for the numpy solver.
        result = lqr(OSC, [1.0, 1.0], 1.0)
        assert result.s is not None
        p = np.asarray(result.s, dtype=float)
        a = np.asarray(OSC.A, dtype=float)
        b = np.asarray(OSC.B, dtype=float)
        q = np.diag([1.0, 1.0])
        residual = a.T @ p + p @ a - p @ b @ b.T @ p + q
        self.assertLess(float(np.max(np.abs(residual))), 1e-8)

    def test_lqr_bigger_r_smaller_gain(self) -> None:
        def norm_k(r: float) -> float:
            result = lqr(OSC, [1.0, 1.0], r)
            return float(np.linalg.norm(np.asarray(result.closed_loop_k)))

        self.assertLess(norm_k(100.0), norm_k(0.1))

    def test_lqr_bad_inputs_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Q must have 2"):
            lqr(OSC, [1.0, 1.0, 1.0], 1.0)
        with self.assertRaisesRegex(ValueError, "positive"):
            lqr(OSC, [0.0, 0.0], 1.0)
        with self.assertRaisesRegex(ValueError, "positive"):
            lqr(OSC, [1.0, 1.0], 0.0)
        with self.assertRaisesRegex(ValueError, "controllable"):
            lqr(UNCONTROLLABLE, [1.0, 1.0], 1.0)

    def test_rejects_discrete_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "continuous-time"):
            lqr(_discrete_model(), [1.0], 1.0)


@unittest.skipUnless(try_import_scipy() is not None, "scipy not installed")
class ScipyLqrFastPathTests(unittest.TestCase):
    def test_scipy_and_numpy_lqr_agree(self) -> None:
        from pycircuits_sim.design.state_feedback import _lqr_numpy, _lqr_scipy

        a = np.asarray(OSC.A, dtype=float)
        b = np.asarray(OSC.B, dtype=float)
        q = np.diag([1.0, 1.0])
        scipy_pair = _lqr_scipy(a, b, q, 1.0)
        self.assertIsNotNone(scipy_pair)
        assert scipy_pair is not None
        k_numpy, p_numpy = _lqr_numpy(a, b, q, 1.0)
        k_scipy, p_scipy = scipy_pair
        np.testing.assert_allclose(k_numpy, k_scipy, atol=1e-6)
        np.testing.assert_allclose(p_numpy, p_scipy, atol=1e-6)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
