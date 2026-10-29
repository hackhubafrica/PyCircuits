"""General signal-flow-graph interconnections for block-diagram canvases.

The chain-oriented :class:`~pycircuits_sim.interconnect.InterconnectSpec`
describes an ordered forward path plus optional parallel and feedback
chains. A block-diagram editor needs arbitrary topology: any number of
blocks, any number of connections, signed summing junctions, and a
reference that may enter at any block.

This module adds that general model:

* :class:`GraphNode` -- one block plus its canvas position.
* :class:`GraphEdge` -- a signed connection between two blocks.
* :class:`GraphSpec` -- the whole canvas.
* :func:`interconnect_graph` -- compose the graph and run the same Phase 1
  analysis the chain engine runs.

Composition happens in the state-space domain: every block becomes a
linear realization, the canvas edges form a static feedback matrix, and
the resulting closed system is reduced to a single transfer function.
Negative feedback is expressed as an edge with a negative gain. The chain
engine keeps its own simpler implementation so existing results stay
bit-identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .analysis.plant import siso_polynomials
from .interconnect import (
    InterconnectBlock,
    InterconnectResult,
    analyze_composite,
    block_transfer_function,
)
from .ir import IrMixin
from .linear_systems import transfer_function_to_state_space

MAX_GRAPH_NODES = 12
MAX_GRAPH_EDGES = 32


@dataclass(frozen=True)
class GraphNode(IrMixin):
    """One block on the canvas.

    ``position`` is the ``(x, y)`` canvas coordinate used by the editor;
    it never affects the computed transfer function.
    """

    id: str
    block: InterconnectBlock
    position: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("every graph node requires a nonempty id")
        x, y = self.position
        object.__setattr__(self, "position", (float(x), float(y)))


@dataclass(frozen=True)
class GraphEdge(IrMixin):
    """A signed connection from one node's output to another's input.

    ``gain`` carries both the scale and the sign: ``1.0`` is a plain
    connection, ``-1.0`` is negative feedback, and ``2.0`` scales the
    signal. Several edges may target the same node; their contributions
    are summed.
    """

    source: str
    target: str
    gain: float = 1.0
    label: str = ""

    def __post_init__(self) -> None:
        for name in ("source", "target"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"every graph edge requires a nonempty {name}")
        if isinstance(self.gain, bool) or not isinstance(self.gain, (int, float)):
            raise ValueError("edge gain must be a finite number")
        if not np.isfinite(float(self.gain)):
            raise ValueError("edge gain must be a finite number")
        object.__setattr__(self, "gain", float(self.gain))


@dataclass(frozen=True)
class GraphSpec(IrMixin):
    """An arbitrary signal-flow graph drawn on the block-diagram canvas.

    ``nodes`` are the blocks, ``edges`` are the connections. The reference
    signal enters the node named by ``input_node``; the composite output is
    taken from the node named by ``output_node``. A node's input is the sum
    of every incoming edge contribution (each scaled by its edge gain, whose
    sign carries the summing-junction sign) plus the reference injection
    when the node is ``input_node``.

    The graph may contain cycles: negative feedback is an edge with a
    negative gain. A cycle made only of algebraic (feedthrough) blocks
    must be solvable; otherwise the canvas is ill-posed and rejected.
    """

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    input_node: str
    output_node: str | None = None
    stop_time: float = 10.0
    time_step: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        if not self.nodes:
            raise ValueError("a graph needs at least one node")
        if len(self.nodes) > MAX_GRAPH_NODES:
            raise ValueError(
                f"a graph may hold at most {MAX_GRAPH_NODES} nodes; got {len(self.nodes)}"
            )
        if len(self.edges) > MAX_GRAPH_EDGES:
            raise ValueError(
                f"a graph may hold at most {MAX_GRAPH_EDGES} edges; got {len(self.edges)}"
            )
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("graph node ids must be unique")
        known = set(ids)
        if self.input_node not in known:
            raise ValueError(f"unknown input node '{self.input_node}'")
        if self.output_node is None:
            object.__setattr__(self, "output_node", self.input_node)
        elif self.output_node not in known:
            raise ValueError(f"unknown output node '{self.output_node}'")
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(
                    f"edge '{edge.source}'->'{edge.target}' refers to an unknown source node"
                )
            if edge.target not in known:
                raise ValueError(
                    f"edge '{edge.source}'->'{edge.target}' refers to an unknown target node"
                )
        for name, value in (
            ("stop_time", self.stop_time),
            ("time_step", self.time_step),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive number")
            if not float(value) > 0:
                raise ValueError(f"{name} must be a positive number")

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Node ids in canvas order."""
        return tuple(node.id for node in self.nodes)

    def node(self, node_id: str) -> GraphNode:
        """Return the node with ``node_id``."""
        for candidate in self.nodes:
            if candidate.id == node_id:
                return candidate
        raise KeyError(node_id)


def _realize(
    block_id: str, num: tuple[float, ...], den: tuple[float, ...]
) -> tuple[np.ndarray, ...]:
    """Realize one block transfer function.

    Returns ``(A, B, C, D)`` where the state matrices may be empty for a
    static block (denominator of degree zero). Improper blocks are
    rejected: the canvas engine needs a well-posed feedthrough-free
    realization, so a PID needs a derivative filter.
    """
    den = tuple(float(value) for value in den)
    num = tuple(float(value) for value in num)
    if len(num) > len(den):
        raise ValueError(
            f"block '{block_id}': the graph engine needs proper blocks; "
            "give the PID a derivative filter to remove the differentiator"
        )
    if len(den) <= 1:
        gain = float(num[0]) / float(den[0]) if den else 0.0
        return (
            np.zeros((0, 0)),
            np.zeros((0, 1)),
            np.zeros((1, 0)),
            np.array([[gain]]),
        )
    model = transfer_function_to_state_space(list(num), list(den))
    return (
        np.asarray(model.A, dtype=float),
        np.asarray(model.B, dtype=float),
        np.asarray(model.C, dtype=float),
        np.asarray(model.D, dtype=float),
    )


def _assemble(blocks: list[np.ndarray], row_sizes: list[int], col_sizes: list[int]) -> np.ndarray:
    """Place per-node blocks into a global matrix using cumulative offsets."""
    rows = sum(row_sizes)
    cols = sum(col_sizes)
    out = np.zeros((rows, cols), dtype=float)
    row_offset = 0
    for index, block in enumerate(blocks):
        col_offset = sum(col_sizes[:index])
        out[
            row_offset : row_offset + row_sizes[index],
            col_offset : col_offset + col_sizes[index],
        ] = block
        row_offset += row_sizes[index]
    return out


def _aggregate(
    spec: GraphSpec,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[int]]:
    """Build the block-diagonal realization of every node.

    Returns ``(A, B, C, D, offsets)`` where ``offsets[i]`` is the index of
    node ``i``'s first state in the stacked state vector.
    """
    per_node: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for node in spec.nodes:
        num, den = block_transfer_function(node.block)
        per_node.append(_realize(node.id, num, den))

    count = len(spec.nodes)
    state_sizes = [matrices[0].shape[0] for matrices in per_node]
    offsets: list[int] = []
    running = 0
    for size in state_sizes:
        offsets.append(running)
        running += size

    A = _assemble([matrices[0] for matrices in per_node], state_sizes, state_sizes)
    B = _assemble([matrices[1] for matrices in per_node], state_sizes, [1] * count)
    C = _assemble([matrices[2] for matrices in per_node], [1] * count, state_sizes)
    D = _assemble([matrices[3] for matrices in per_node], [1] * count, [1] * count)
    return A, B, C, D, offsets


def _edge_matrix(spec: GraphSpec) -> np.ndarray:
    """Build the node-to-node connection matrix ``K``.

    ``K[target, source]`` is the total gain flowing from ``source``'s output
    into ``target``'s input.
    """
    index = {node.id: position for position, node in enumerate(spec.nodes)}
    K = np.zeros((len(spec.nodes), len(spec.nodes)), dtype=float)
    for edge in spec.edges:
        K[index[edge.target], index[edge.source]] += edge.gain
    return K


def _live_nodes(spec: GraphSpec) -> set[str]:
    """Return the node ids that can influence the composite.

    A node matters only when the reference can reach it *and* it can reach
    the output. Nodes outside that set (an unconnected block, or a branch
    that is never fed) contribute nothing but would still add spurious
    poles to the state-space realization, so they are pruned.
    """
    successors: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
    for edge in spec.edges:
        successors[edge.source].append(edge.target)

    def walk(start: str, graph: dict[str, list[str]]) -> set[str]:
        seen = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbour in graph[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        return seen

    forward = walk(spec.input_node, successors)
    reverse: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
    for edge in spec.edges:
        reverse[edge.target].append(edge.source)
    backward = walk(spec.output_node, reverse)
    live = forward & backward
    # The reference and the tap must survive the pruning; a node that the
    # reference cannot reach (or that cannot reach the tap) is dead weight.
    live.add(spec.input_node)
    live.add(spec.output_node)
    return live


def _prune(spec: GraphSpec) -> GraphSpec:
    """Return a copy of ``spec`` without the dead nodes."""
    live = _live_nodes(spec)
    if len(live) == len(spec.nodes):
        return spec
    nodes = tuple(node for node in spec.nodes if node.id in live)
    edges = tuple(edge for edge in spec.edges if edge.source in live and edge.target in live)
    return GraphSpec(
        nodes,
        edges,
        spec.input_node,
        spec.output_node,
        stop_time=spec.stop_time,
        time_step=spec.time_step,
    )


def _compose(spec: GraphSpec) -> tuple[np.ndarray, np.ndarray]:
    """Compose the graph into one transfer function.

    Every node is realized in state space and the canvas edges become a
    static feedback matrix ``K``. With ``u = K y + e r`` and
    ``y = C x + D u`` the node inputs are eliminated through
    ``(I - K D) u = K C x + e r``, which leaves a single closed system.

    Returns the numerator and monic denominator of the composite.
    """
    spec = _prune(spec)
    A, B, C, D, _offsets = _aggregate(spec)
    count = len(spec.nodes)
    index = {node.id: position for position, node in enumerate(spec.nodes)}
    K = _edge_matrix(spec)

    selector_in = np.zeros(count, dtype=float)
    selector_in[index[spec.input_node]] = 1.0
    selector_out = np.zeros(count, dtype=float)
    selector_out[index[spec.output_node]] = 1.0

    M = np.eye(count, dtype=float) - K @ D
    if abs(np.linalg.det(M)) < 1e-12:
        raise ValueError(
            "the canvas contains an algebraic loop that is not well-posed "
            "(a cycle of feedthrough blocks with unit loop gain); "
            "break the loop or add a dynamic block"
        )
    M_inv = np.linalg.inv(M)

    A_closed = A + B @ M_inv @ K @ C
    B_closed = B @ M_inv @ selector_in
    C_closed = selector_out @ (C + D @ M_inv @ K @ C)
    D_closed = float(selector_out @ D @ M_inv @ selector_in)

    if A_closed.shape[0] == 0:
        return np.array([D_closed]), np.array([1.0])

    numerator, denominator = siso_polynomials(
        A_closed,
        B_closed.reshape(-1, 1),
        C_closed.reshape(1, -1),
        np.array([[D_closed]], dtype=float),
    )
    return numerator, denominator


def interconnect_graph(spec: GraphSpec) -> InterconnectResult:
    """Compose an arbitrary signal-flow graph and analyze the result.

    The graph is reduced to a single transfer function and then handed to
    the same Phase 1 analysis the chain engine uses, so stability, margins,
    Nyquist, root locus, and the unit-step response are reported exactly as
    they are for :func:`~pycircuits_sim.interconnect.interconnect`.
    """
    numerator, denominator = _compose(spec)
    return analyze_composite(
        numerator,
        denominator,
        stop_time=float(spec.stop_time),
        time_step=(float(spec.time_step) if spec.time_step is not None else None),
    )
