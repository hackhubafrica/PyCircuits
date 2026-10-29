"""Block-diagram canvas document: the editor's own model of a canvas.

The signal-flow engine in :mod:`pycircuits_sim.graph` describes *what* the
diagram computes: blocks, signed connections, a reference entry point, and
a tap. It has no notion of wire identity or of where a block sits on the
screen, because those are editor concerns.

This module adds the document layer that sits between the drag-and-drop
editor and the engine:

* :class:`BlockDiagramNode` -- a block plus its canvas position.
* :class:`BlockDiagramEdge` -- a signed connection with a stable id.
* :class:`BlockDiagramDocument` -- the whole canvas, convertible to and
  from a :class:`~pycircuits_sim.graph.GraphSpec`.

The document round-trips through the shared IR, so the editor, the CLI,
and the HTTP API all speak the same JSON -- the "editor emitting the same
JSON" requirement of the Stage 2 block-diagram frontend.
"""

from __future__ import annotations

from dataclasses import dataclass

from .graph import GraphEdge, GraphNode, GraphSpec
from .interconnect import InterconnectBlock
from .ir import IrMixin

__all__ = [
    "BlockDiagramDocument",
    "BlockDiagramEdge",
    "BlockDiagramNode",
    "MAX_BLOCK_DIAGRAM_EDGES",
    "MAX_BLOCK_DIAGRAM_NODES",
]

MAX_BLOCK_DIAGRAM_NODES = 12
MAX_BLOCK_DIAGRAM_EDGES = 32


@dataclass(frozen=True)
class BlockDiagramNode(IrMixin):
    """One block placed on the block-diagram canvas.

    ``position`` is the ``(x, y)`` canvas coordinate the editor stores so
    the diagram reopens where the user left it. It never affects the
    computed transfer function.
    """

    id: str
    block: InterconnectBlock
    position: tuple[float, float] = (0.0, 0.0)
    label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("every block-diagram node requires a nonempty id")
        x, y = self.position
        object.__setattr__(self, "position", (float(x), float(y)))
        object.__setattr__(self, "label", str(self.label))


@dataclass(frozen=True)
class BlockDiagramEdge(IrMixin):
    """A signed connection between two canvas nodes.

    ``gain`` carries the scale *and* the sign of the connection, exactly as
    in :class:`~pycircuits_sim.graph.GraphEdge`: ``1.0`` is a plain wire,
    ``-1.0`` is negative feedback, and any other magnitude scales the
    signal. Several edges may target the same node; their contributions
    are summed, which is how a summing junction is drawn.
    """

    id: str
    source: str
    target: str
    gain: float = 1.0
    label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("every block-diagram edge requires a nonempty id")
        for name in ("source", "target"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"every block-diagram edge requires a nonempty {name}")
        if isinstance(self.gain, bool) or not isinstance(self.gain, (int, float)):
            raise ValueError("edge gain must be a finite number")
        if self.gain != self.gain or self.gain in (float("inf"), float("-inf")):
            raise ValueError("edge gain must be a finite number")
        object.__setattr__(self, "gain", float(self.gain))
        object.__setattr__(self, "label", str(self.label))


@dataclass(frozen=True)
class BlockDiagramDocument(IrMixin):
    """A complete block-diagram canvas.

    ``input_node`` names the node the reference signal enters and
    ``output_node`` names the node the composite output is tapped from.
    ``stop_time``/``time_step`` bound the embedded unit-step simulation
    and are forwarded to the engine untouched.

    A document is *layout-aware*: it keeps node positions and stable edge
    ids so the editor can save and reopen a diagram. :meth:`to_graph` drops
    the layout and yields the engine's :class:`GraphSpec`.
    """

    nodes: tuple[BlockDiagramNode, ...]
    edges: tuple[BlockDiagramEdge, ...]
    input_node: str
    output_node: str
    stop_time: float = 10.0
    time_step: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        if not self.nodes:
            raise ValueError("a block diagram needs at least one node")
        if len(self.nodes) > MAX_BLOCK_DIAGRAM_NODES:
            raise ValueError(
                f"a block diagram may hold at most {MAX_BLOCK_DIAGRAM_NODES} "
                f"nodes; got {len(self.nodes)}"
            )
        if len(self.edges) > MAX_BLOCK_DIAGRAM_EDGES:
            raise ValueError(
                f"a block diagram may hold at most {MAX_BLOCK_DIAGRAM_EDGES} "
                f"edges; got {len(self.edges)}"
            )
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("block-diagram node ids must be unique")
        edge_ids = [edge.id for edge in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("block-diagram edge ids must be unique")
        known = set(node_ids)
        if self.input_node not in known:
            raise ValueError(f"unknown input node '{self.input_node}'")
        if self.output_node not in known:
            raise ValueError(f"unknown output node '{self.output_node}'")
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(
                    f"edge '{edge.id}' refers to an unknown source node '{edge.source}'"
                )
            if edge.target not in known:
                raise ValueError(
                    f"edge '{edge.id}' refers to an unknown target node '{edge.target}'"
                )
            if edge.source == edge.target:
                raise ValueError(f"edge '{edge.id}' cannot connect a node to itself")
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

    def node(self, node_id: str) -> BlockDiagramNode:
        """Return the node with ``node_id``."""
        for candidate in self.nodes:
            if candidate.id == node_id:
                return candidate
        raise KeyError(node_id)

    def to_graph(self) -> GraphSpec:
        """Return the engine spec for this canvas, dropping the layout."""
        return GraphSpec(
            nodes=tuple(
                GraphNode(id=node.id, block=node.block, position=node.position)
                for node in self.nodes
            ),
            edges=tuple(
                GraphEdge(
                    source=edge.source,
                    target=edge.target,
                    gain=edge.gain,
                    label=edge.label,
                )
                for edge in self.edges
            ),
            input_node=self.input_node,
            output_node=self.output_node,
            stop_time=self.stop_time,
            time_step=self.time_step,
        )

    @classmethod
    def from_graph(cls, spec: GraphSpec) -> BlockDiagramDocument:
        """Build a canvas document from an engine spec.

        Edge ids are derived from their endpoints so the round trip is
        deterministic.
        """
        return cls(
            nodes=tuple(
                BlockDiagramNode(
                    id=node.id,
                    block=node.block,
                    position=node.position,
                )
                for node in spec.nodes
            ),
            edges=tuple(
                BlockDiagramEdge(
                    id=f"e{index + 1}_{edge.source}_{edge.target}",
                    source=edge.source,
                    target=edge.target,
                    gain=edge.gain,
                    label=edge.label,
                )
                for index, edge in enumerate(spec.edges)
            ),
            input_node=spec.input_node,
            output_node=spec.output_node or spec.input_node,
            stop_time=spec.stop_time,
            time_step=spec.time_step,
        )
