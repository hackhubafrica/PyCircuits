import unittest

from pycircuits_sim.design import PIDGains
from pycircuits_sim.interconnect import (
    MAX_BLOCKS,
    InterconnectBlock,
    InterconnectResult,
    InterconnectSpec,
    interconnect,
)

# ControlKit's DC-motor-like plant 4 / (s^2 + 12 s).
MOTOR = InterconnectBlock(id="g", kind="tf", num=(4.0,), den=(1.0, 12.0, 0.0))
GAINS = PIDGains(kp=1.2, ki=0.4, kd=0.2)
CONTROLLER = InterconnectBlock(id="c", kind="pid", gains=GAINS)


def _approx_tuple(values, expected, places: int = 9) -> None:
    actual = tuple(values)
    if len(actual) != len(expected):
        raise AssertionError(f"length {len(actual)} != {len(expected)}: {actual}")
    for got, want in zip(actual, expected):
        if round(abs(got - want), places) != 0:
            raise AssertionError(f"{actual} != {expected}")


class InterconnectAlgebraTests(unittest.TestCase):
    def test_pid_loop_matches_hand_computed_closed_loop(self) -> None:
        # series(pid, plant) + unity feedback must equal the hand-derived
        # T = N / (D + N) with N = 0.8s^2+4.8s+1.6 and D = s^3+12s^2.
        # The slow closed-loop pole needs a long horizon to settle.
        result = interconnect(
            InterconnectSpec(
                blocks=(CONTROLLER, MOTOR),
                forward=("c", "g"),
                feedback="unity",
                stop_time=100.0,
            )
        )
        self.assertIsInstance(result, InterconnectResult)
        _approx_tuple(result.composite_num, [0.8, 4.8, 1.6])
        _approx_tuple(result.composite_den, [1.0, 12.8, 4.8, 1.6])
        # Type-1 unity loop: settled step output must be exactly 1.
        self.assertAlmostEqual(result.step.output[-1], 1.0, delta=0.01)

    def test_parallel_sum_algebra(self) -> None:
        # 1/(s+1) + 2/(s+2) = (3s+4)/(s^2+3s+2), open loop.
        result = interconnect(
            InterconnectSpec(
                blocks=(
                    InterconnectBlock(id="a", kind="tf", num=(1.0,), den=(1.0, 1.0)),
                    InterconnectBlock(id="b", kind="tf", num=(2.0,), den=(1.0, 2.0)),
                ),
                forward=("a",),
                parallel=("b",),
                feedback="none",
            )
        )
        _approx_tuple(result.composite_num, [3.0, 4.0])
        _approx_tuple(result.composite_den, [1.0, 3.0, 2.0])

    def test_gain_block_unity_feedback(self) -> None:
        # feedback(100, 1) = 100/101, a static composite.
        result = interconnect(
            InterconnectSpec(
                blocks=(InterconnectBlock(id="k", kind="gain", k=100.0),),
                forward=("k",),
                feedback="unity",
            )
        )
        self.assertEqual(len(result.composite_den), 1)
        self.assertAlmostEqual(result.composite_num[0], 100.0 / 101.0, places=9)
        self.assertAlmostEqual(result.plant.dc_gain, 100.0 / 101.0, places=9)
        self.assertAlmostEqual(result.step.output[-1], 100.0 / 101.0, places=6)

    def test_feedback_path_chain(self) -> None:
        # T = G/(1+G*H) with G=1/(s+1), H=2: 1/(s+3).
        result = interconnect(
            InterconnectSpec(
                blocks=(
                    InterconnectBlock(id="g", kind="tf", num=(1.0,), den=(1.0, 1.0)),
                    InterconnectBlock(id="h", kind="gain", k=2.0),
                ),
                forward=("g",),
                feedback=("h",),
            )
        )
        _approx_tuple(result.composite_num, [1.0])
        _approx_tuple(result.composite_den, [1.0, 3.0])

    def test_open_loop_series_without_feedback(self) -> None:
        result = interconnect(
            InterconnectSpec(
                blocks=(
                    InterconnectBlock(id="a", kind="tf", num=(1.0,), den=(1.0, 1.0)),
                    InterconnectBlock(id="b", kind="tf", num=(1.0,), den=(1.0, 2.0)),
                ),
                forward=("a", "b"),
                feedback="none",
            )
        )
        _approx_tuple(result.composite_num, [1.0])
        _approx_tuple(result.composite_den, [1.0, 3.0, 2.0])

    def test_state_space_block_contributes_transfer_function(self) -> None:
        # Controllable canonical 1/(s^2+s+1) as an ss block in a unity loop
        # with a proportional gain of 1: T = 1/(s^2+s+2).
        plant = InterconnectBlock(
            id="p",
            kind="ss",
            A=((0.0, 1.0), (-1.0, -1.0)),
            B=((0.0,), (1.0,)),
            C=((1.0, 0.0),),
            D=((0.0,),),
        )
        result = interconnect(
            InterconnectSpec(
                blocks=(InterconnectBlock(id="k", kind="gain", k=1.0), plant),
                forward=("k", "p"),
                feedback="unity",
            )
        )
        _approx_tuple(result.composite_num, [1.0])
        _approx_tuple(result.composite_den, [1.0, 1.0, 2.0])

    def test_pid_block_derivative_filter(self) -> None:
        # PD with filter N on the derivative term changes the loop
        # polynomial; verify the filter is threaded through and the loop
        # stays stable.
        filtered = InterconnectBlock(
            id="c", kind="pid", gains=GAINS, derivative_filter=10.0
        )
        result = interconnect(
            InterconnectSpec(
                blocks=(filtered, MOTOR), forward=("c", "g"), feedback="unity"
            )
        )
        # C = ((Kp+Kd*N)s^2 + (Kp*N+Ki)s + Ki*N) / (s(s+N)); with the plant
        # 4/(s^2+12s) the closed loop is order 4.
        self.assertEqual(len(result.composite_den), 5)
        self.assertLess(result.stability.max_real_pole, 0.0)


class InterconnectValidationTests(unittest.TestCase):
    def test_duplicate_block_id_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate block id"):
            interconnect(
                InterconnectSpec(
                    blocks=(
                        InterconnectBlock(id="a", kind="gain", k=1.0),
                        InterconnectBlock(id="a", kind="gain", k=2.0),
                    ),
                    forward=("a",),
                    feedback="none",
                )
            )

    def test_unknown_block_id_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown block id"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="a", kind="gain", k=1.0),),
                    forward=("a", "nope"),
                    feedback="none",
                )
            )

    def test_unknown_feedback_id_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown block id"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="a", kind="gain", k=1.0),),
                    forward=("a",),
                    feedback=("ghost",),
                )
            )

    def test_too_many_blocks_rejected(self) -> None:
        blocks = tuple(
            InterconnectBlock(id=f"k{i}", kind="gain", k=1.0)
            for i in range(MAX_BLOCKS + 1)
        )
        with self.assertRaisesRegex(ValueError, "at most"):
            interconnect(InterconnectSpec(blocks=blocks, forward=("k0",)))

    def test_composite_order_limit_enforced(self) -> None:
        # Two order-11 all-pole blocks in series give order 22 > 20.
        den = tuple([1.0] * 12)
        big1 = InterconnectBlock(id="b1", kind="tf", num=(1.0,), den=den)
        big2 = InterconnectBlock(id="b2", kind="tf", num=(1.0,), den=den)
        with self.assertRaisesRegex(ValueError, "exceeds the limit of 20"):
            interconnect(
                InterconnectSpec(
                    blocks=(big1, big2), forward=("b1", "b2"), feedback="none"
                )
            )

    def test_improper_composite_rejected(self) -> None:
        improper = InterconnectBlock(id="d", kind="tf", num=(1.0, 1.0), den=(1.0,))
        with self.assertRaisesRegex(ValueError, "improper"):
            interconnect(
                InterconnectSpec(blocks=(improper,), forward=("d",), feedback="none")
            )

    def test_mimo_state_space_block_rejected(self) -> None:
        mimo = InterconnectBlock(
            id="m",
            kind="ss",
            A=((0.0, 1.0), (-1.0, -1.0)),
            B=((0.0, 0.0), (1.0, 0.5)),
            C=((1.0, 0.0),),
            D=((0.0, 0.0),),
        )
        with self.assertRaisesRegex(ValueError, "SISO"):
            interconnect(InterconnectSpec(blocks=(mimo,), forward=("m",)))

    def test_missing_block_fields_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "needs num and den"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="t", kind="tf"),), forward=("t",)
                )
            )
        with self.assertRaisesRegex(ValueError, "needs A, B, and C"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="s", kind="ss"),), forward=("s",)
                )
            )
        with self.assertRaisesRegex(ValueError, "needs gains"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="p", kind="pid"),), forward=("p",)
                )
            )
        with self.assertRaisesRegex(ValueError, "finite k"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="k", kind="gain"),), forward=("k",)
                )
            )

    def test_empty_forward_path_rejected_at_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "forward path"):
            InterconnectSpec(
                blocks=(InterconnectBlock(id="a", kind="gain", k=1.0),),
                forward=(),
            )

    def test_bad_feedback_value_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "feedback must be"):
            interconnect(
                InterconnectSpec(
                    blocks=(InterconnectBlock(id="a", kind="gain", k=1.0),),
                    forward=("a",),
                    feedback="sometimes",
                )
            )

    def test_unknown_block_kind_rejected_at_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown kind"):
            InterconnectBlock(id="x", kind="voodoo")


class InterconnectAnalysisPayloadTests(unittest.TestCase):
    def test_payload_carries_full_phase1_analysis(self) -> None:
        result = interconnect(
            InterconnectSpec(
                blocks=(CONTROLLER, MOTOR), forward=("c", "g"), feedback="unity"
            )
        )
        self.assertTrue(result.stability.bibo_stable)
        self.assertEqual(len(result.margins.frequencies_rad_s), 400)
        self.assertEqual(len(result.nyquist.real), 400)
        self.assertGreaterEqual(len(result.root_locus.branches), 1)
        self.assertEqual(len(result.step.output), len(result.step.time_s))
        self.assertIsNotNone(result.plant.numerator)
        self.assertEqual(result.plant.order, 3)


if __name__ == "__main__":
    unittest.main()



