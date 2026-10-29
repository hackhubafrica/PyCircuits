import unittest

from pycircuits_sim.design import PIDGains
from pycircuits_sim.graph import (
    MAX_GRAPH_NODES,
    GraphEdge,
    GraphNode,
    GraphSpec,
    interconnect_graph,
)
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
# The graph engine needs proper blocks, so its controller carries a
# derivative filter that removes the differentiator.
FILTERED_CONTROLLER = InterconnectBlock(id="c", kind="pid", gains=GAINS, derivative_filter=10.0)
# A PI controller (kd = 0) is already proper: its padded numerator is
# (0, kp, ki) over (1, 0), a first-order integrator with a zero.
PI_CONTROLLER = InterconnectBlock(id="c", kind="pid", gains=PIDGains(kp=1.2, ki=0.4, kd=0.0))


def _approx_tuple(values, expected, places: int = 9) -> None:
    actual = tuple(values)
    if len(actual) != len(expected):
        raise AssertionError(f"length {len(actual)} != {len(expected)}: {actual}")
    for got, want in zip(actual, expected, strict=True):
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
        filtered = InterconnectBlock(id="c", kind="pid", gains=GAINS, derivative_filter=10.0)
        result = interconnect(
            InterconnectSpec(blocks=(filtered, MOTOR), forward=("c", "g"), feedback="unity")
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
            InterconnectBlock(id=f"k{i}", kind="gain", k=1.0) for i in range(MAX_BLOCKS + 1)
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
                InterconnectSpec(blocks=(big1, big2), forward=("b1", "b2"), feedback="none")
            )

    def test_improper_composite_rejected(self) -> None:
        improper = InterconnectBlock(id="d", kind="tf", num=(1.0, 1.0), den=(1.0,))
        with self.assertRaisesRegex(ValueError, "improper"):
            interconnect(InterconnectSpec(blocks=(improper,), forward=("d",), feedback="none"))

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
                InterconnectSpec(blocks=(InterconnectBlock(id="t", kind="tf"),), forward=("t",))
            )
        with self.assertRaisesRegex(ValueError, "needs A, B, and C"):
            interconnect(
                InterconnectSpec(blocks=(InterconnectBlock(id="s", kind="ss"),), forward=("s",))
            )
        with self.assertRaisesRegex(ValueError, "needs gains"):
            interconnect(
                InterconnectSpec(blocks=(InterconnectBlock(id="p", kind="pid"),), forward=("p",))
            )
        with self.assertRaisesRegex(ValueError, "finite k"):
            interconnect(
                InterconnectSpec(blocks=(InterconnectBlock(id="k", kind="gain"),), forward=("k",))
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
            InterconnectSpec(blocks=(CONTROLLER, MOTOR), forward=("c", "g"), feedback="unity")
        )
        self.assertTrue(result.stability.bibo_stable)
        self.assertEqual(len(result.margins.frequencies_rad_s), 400)
        self.assertEqual(len(result.nyquist.real), 400)
        self.assertGreaterEqual(len(result.root_locus.branches), 1)
        self.assertEqual(len(result.step.output), len(result.step.time_s))
        self.assertIsNotNone(result.plant.numerator)
        self.assertEqual(result.plant.order, 3)


class GraphAlgebraTests(unittest.TestCase):
    def test_series_graph_matches_product(self) -> None:
        # 2 * 1/(s+1) = 2/(s+1).
        nodes = (
            GraphNode("a", InterconnectBlock(id="a", kind="gain", k=2.0)),
            GraphNode(
                "b",
                InterconnectBlock(id="b", kind="tf", num=(1.0,), den=(1.0, 1.0)),
            ),
        )
        result = interconnect_graph(GraphSpec(nodes, (GraphEdge("a", "b", 1.0),), "a", "b"))
        _approx_tuple(result.composite_num, [2.0])
        _approx_tuple(result.composite_den, [1.0, 1.0])

    def test_negative_feedback_edge_closes_the_loop(self) -> None:
        # G = 2/(s+1) with unity negative feedback: 2/(s+3).
        nodes = (
            GraphNode("a", InterconnectBlock(id="a", kind="gain", k=2.0)),
            GraphNode(
                "b",
                InterconnectBlock(id="b", kind="tf", num=(1.0,), den=(1.0, 1.0)),
            ),
        )
        result = interconnect_graph(
            GraphSpec(
                nodes,
                (GraphEdge("a", "b", 1.0), GraphEdge("b", "a", -1.0)),
                "a",
                "b",
            )
        )
        _approx_tuple(result.composite_num, [2.0])
        _approx_tuple(result.composite_den, [1.0, 3.0])

    def test_graph_matches_chain_engine(self) -> None:
        blocks = (FILTERED_CONTROLLER, MOTOR)
        nodes = tuple(GraphNode(block.id, block) for block in blocks)
        graph_result = interconnect_graph(
            GraphSpec(
                nodes,
                (GraphEdge("c", "g", 1.0), GraphEdge("g", "c", -1.0)),
                "c",
                "g",
                stop_time=100.0,
            )
        )
        chain_result = interconnect(
            InterconnectSpec(
                blocks=blocks,
                forward=("c", "g"),
                feedback="unity",
                stop_time=100.0,
            )
        )
        _approx_tuple(graph_result.composite_num, chain_result.composite_num)
        _approx_tuple(graph_result.composite_den, chain_result.composite_den)
        self.assertAlmostEqual(
            graph_result.step.output[-1], chain_result.step.output[-1], delta=1e-6
        )

    def test_pi_controller_is_proper_in_the_graph_engine(self) -> None:
        # A PI controller has the padded numerator (0, kp, ki); it is a proper
        # first-order block, so the graph engine must accept it and agree
        # with the chain engine.
        blocks = (PI_CONTROLLER, MOTOR)
        nodes = tuple(GraphNode(block.id, block) for block in blocks)
        graph_result = interconnect_graph(
            GraphSpec(
                nodes,
                (GraphEdge("c", "g", 1.0), GraphEdge("g", "c", -1.0)),
                "c",
                "g",
            )
        )
        chain_result = interconnect(
            InterconnectSpec(blocks=blocks, forward=("c", "g"), feedback="unity")
        )
        _approx_tuple(graph_result.composite_num, chain_result.composite_num)
        _approx_tuple(graph_result.composite_den, chain_result.composite_den)
        _approx_tuple(graph_result.composite_num, [4.8, 1.6])
        _approx_tuple(graph_result.composite_den, [1.0, 12.0, 4.8, 1.6])

    def test_summing_junction_adds_parallel_branches(self) -> None:
        # 1/(s+1) + 2/(s+2) = (3s+4)/(s^2+3s+2).
        nodes = (
            GraphNode("src", InterconnectBlock(id="src", kind="gain", k=1.0)),
            GraphNode("a", InterconnectBlock(id="a", kind="tf", num=(1.0,), den=(1.0, 1.0))),
            GraphNode("b", InterconnectBlock(id="b", kind="tf", num=(2.0,), den=(1.0, 2.0))),
            GraphNode("sum", InterconnectBlock(id="sum", kind="gain", k=1.0)),
        )
        result = interconnect_graph(
            GraphSpec(
                nodes,
                (
                    GraphEdge("src", "a", 1.0),
                    GraphEdge("src", "b", 1.0),
                    GraphEdge("a", "sum", 1.0),
                    GraphEdge("b", "sum", 1.0),
                ),
                "src",
                "sum",
            )
        )
        _approx_tuple(result.composite_num, [3.0, 4.0])
        _approx_tuple(result.composite_den, [1.0, 3.0, 2.0])

    def test_unreachable_branch_is_pruned(self) -> None:
        # The 'b' branch is never fed, so it must not add a pole to the
        # composite: 1/(s+1), not 1/(s+1) + 2/(s+2).
        nodes = (
            GraphNode("a", InterconnectBlock(id="a", kind="tf", num=(1.0,), den=(1.0, 1.0))),
            GraphNode("b", InterconnectBlock(id="b", kind="tf", num=(2.0,), den=(1.0, 2.0))),
            GraphNode("sum", InterconnectBlock(id="sum", kind="gain", k=1.0)),
        )
        result = interconnect_graph(
            GraphSpec(
                nodes,
                (GraphEdge("a", "sum", 1.0), GraphEdge("b", "sum", 1.0)),
                "a",
                "sum",
            )
        )
        _approx_tuple(result.composite_num, [1.0])
        _approx_tuple(result.composite_den, [1.0, 1.0])

    def test_improper_pid_block_is_rejected(self) -> None:
        # An unfiltered PID has a differentiator, so its transfer function
        # (0.2 s^2 + 1.2 s + 0.4) / s is improper and cannot be realized
        # as a finite-dimensional state-space system.
        nodes = (GraphNode("c", CONTROLLER), GraphNode("g", MOTOR))
        with self.assertRaisesRegex(ValueError, "derivative"):
            interconnect_graph(
                GraphSpec(
                    nodes,
                    (GraphEdge("c", "g", 1.0), GraphEdge("g", "c", -1.0)),
                    "c",
                    "g",
                )
            )

    def test_edge_gain_scales_the_signal(self) -> None:
        # A gain-3 edge into a 1/(s+1) block gives 3/(s+1).
        nodes = (
            GraphNode("a", InterconnectBlock(id="a", kind="gain", k=1.0)),
            GraphNode(
                "b",
                InterconnectBlock(id="b", kind="tf", num=(1.0,), den=(1.0, 1.0)),
            ),
        )
        result = interconnect_graph(GraphSpec(nodes, (GraphEdge("a", "b", 3.0),), "a", "b"))
        _approx_tuple(result.composite_num, [3.0])
        _approx_tuple(result.composite_den, [1.0, 1.0])

    def test_static_graph_produces_static_composite(self) -> None:
        # 100 in a unity negative loop gives 100/101.
        nodes = (GraphNode("k", InterconnectBlock(id="k", kind="gain", k=100.0)),)
        result = interconnect_graph(GraphSpec(nodes, (GraphEdge("k", "k", -1.0),), "k", "k"))
        self.assertEqual(len(result.composite_den), 1)
        self.assertAlmostEqual(result.composite_num[0], 100.0 / 101.0, places=9)
        self.assertAlmostEqual(result.plant.dc_gain, 100.0 / 101.0, places=9)


class GraphAnalysisPayloadTests(unittest.TestCase):
    def test_graph_reports_full_analysis_payload(self) -> None:
        nodes = (GraphNode("c", FILTERED_CONTROLLER), GraphNode("g", MOTOR))
        result = interconnect_graph(
            GraphSpec(
                nodes,
                (GraphEdge("c", "g", 1.0), GraphEdge("g", "c", -1.0)),
                "c",
                "g",
                stop_time=100.0,
            )
        )
        self.assertIsInstance(result, InterconnectResult)
        self.assertTrue(result.stability.bibo_stable)
        self.assertEqual(len(result.margins.frequencies_rad_s), 400)
        self.assertEqual(len(result.nyquist.real), 400)
        self.assertEqual(len(result.step.output), len(result.step.time_s))
        self.assertEqual(result.plant.order, 4)


class GraphValidationTests(unittest.TestCase):
    def test_duplicate_node_id_rejected(self) -> None:
        block = InterconnectBlock(id="a", kind="gain", k=1.0)
        with self.assertRaisesRegex(ValueError, "unique"):
            GraphSpec((GraphNode("a", block), GraphNode("a", block)), (), "a", "a")

    def test_unknown_node_reference_rejected(self) -> None:
        block = InterconnectBlock(id="a", kind="gain", k=1.0)
        with self.assertRaisesRegex(ValueError, "unknown input node"):
            GraphSpec((GraphNode("a", block),), (), "ghost", "a")
        with self.assertRaisesRegex(ValueError, "unknown output node"):
            GraphSpec((GraphNode("a", block),), (), "a", "ghost")

    def test_edge_to_unknown_node_rejected(self) -> None:
        block = InterconnectBlock(id="a", kind="gain", k=1.0)
        with self.assertRaisesRegex(ValueError, "unknown source node"):
            GraphSpec((GraphNode("a", block),), (GraphEdge("ghost", "a", 1.0),), "a", "a")
        with self.assertRaisesRegex(ValueError, "unknown target node"):
            GraphSpec((GraphNode("a", block),), (GraphEdge("a", "ghost", 1.0),), "a", "a")

    def test_too_many_nodes_rejected(self) -> None:
        block = InterconnectBlock(id="a", kind="gain", k=1.0)
        nodes = tuple(GraphNode(f"n{index}", block) for index in range(MAX_GRAPH_NODES + 1))
        with self.assertRaisesRegex(ValueError, "at most"):
            GraphSpec(nodes, (), "n0", "n0")

    def test_empty_graph_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one node"):
            GraphSpec((), (), "a", "a")

    def test_non_finite_edge_gain_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            GraphEdge("a", "b", float("nan"))

    def test_ill_posed_algebraic_loop_rejected(self) -> None:
        # Two unit gains in a positive loop: the sum is not solvable.
        nodes = (
            GraphNode("a", InterconnectBlock(id="a", kind="gain", k=1.0)),
            GraphNode("b", InterconnectBlock(id="b", kind="gain", k=1.0)),
        )
        with self.assertRaisesRegex(ValueError, "algebraic loop"):
            interconnect_graph(
                GraphSpec(
                    nodes,
                    (GraphEdge("a", "b", 1.0), GraphEdge("b", "a", 1.0)),
                    "a",
                    "b",
                )
            )


if __name__ == "__main__":
    unittest.main()
