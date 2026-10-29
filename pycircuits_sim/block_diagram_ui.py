"""Drag-and-drop block-diagram editor backed by the signal-flow engine.

This is the Stage 2 "block-diagram frontend": a canvas where the user
places control blocks (transfer functions, gains, PID controllers), wires
them together with signed connections, marks the reference entry point and
the output tap, and then composes the result with
:func:`~pycircuits_sim.graph.interconnect_graph`.

The editor keeps its own document model
(:class:`~pycircuits_sim.block_diagram.BlockDiagramDocument`) so node
positions and wire identities survive a save/reopen cycle, and it emits
the same JSON the CLI and the HTTP API consume.
"""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from .block_diagram import BlockDiagramDocument, BlockDiagramEdge, BlockDiagramNode
from .design import PIDGains
from .graph import interconnect_graph
from .interconnect import InterconnectBlock

BLOCK_PALETTE = ("tf", "gain", "pid")

KIND_LABELS = {
    "tf": "Transfer function",
    "gain": "Gain",
    "pid": "PID",
}


def _next_node_id(nodes: list[dict[str, Any]], prefix: str) -> str:
    """Return an unused node id with the given prefix."""
    used = {node["id"] for node in nodes}
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def _default_block(kind: str, name: str) -> dict[str, Any]:
    """Return starter properties for a palette item."""
    if kind == "tf":
        return {"id": name, "kind": "tf", "num": [1.0], "den": [1.0, 1.0]}
    if kind == "gain":
        return {"id": name, "kind": "gain", "k": 1.0}
    return {
        "id": name,
        "kind": "pid",
        "gains": {"kp": 1.0, "ki": 0.0, "kd": 0.0},
        "derivative_filter": 10.0,
    }


def _block_title(block: dict[str, Any]) -> str:
    """Return the one-line label shown inside a canvas node."""
    kind = block.get("kind")
    if kind == "tf":
        num = block.get("num") or []
        den = block.get("den") or []
        return f"{block.get('id')}\n{list(num)} / {list(den)}"
    if kind == "gain":
        return f"{block.get('id')}\nK = {float(block.get('k', 0.0)):g}"
    gains = block.get("gains") or {}
    return (
        f"{block.get('id')}\n"
        f"Kp={float(gains.get('kp', 0.0)):g} "
        f"Ki={float(gains.get('ki', 0.0)):g} "
        f"Kd={float(gains.get('kd', 0.0)):g}"
    )


def _block_to_engine(block: dict[str, Any]) -> InterconnectBlock:
    """Convert a canvas block's properties into an engine block."""
    kind = block["kind"]
    gains_data = block.get("gains")
    gains = None
    if isinstance(gains_data, dict):
        gains = PIDGains(
            kp=float(gains_data.get("kp", 0.0)),
            ki=float(gains_data.get("ki", 0.0)),
            kd=float(gains_data.get("kd", 0.0)),
        )
    return InterconnectBlock(
        id=str(block["id"]),
        kind=kind,
        num=tuple(float(v) for v in block["num"]) if block.get("num") else None,
        den=tuple(float(v) for v in block["den"]) if block.get("den") else None,
        gains=gains,
        derivative_filter=(
            float(block["derivative_filter"])
            if block.get("derivative_filter") is not None
            else None
        ),
        k=float(block["k"]) if block.get("k") is not None else None,
    )


def _engine_to_block(block: InterconnectBlock) -> dict[str, Any]:
    """Convert an engine block back into canvas properties."""
    data: dict[str, Any] = {"id": block.id, "kind": block.kind}
    if block.num is not None:
        data["num"] = list(block.num)
    if block.den is not None:
        data["den"] = list(block.den)
    if block.gains is not None:
        data["gains"] = {
            "kp": block.gains.kp,
            "ki": block.gains.ki,
            "kd": block.gains.kd,
        }
    if block.derivative_filter is not None:
        data["derivative_filter"] = block.derivative_filter
    if block.k is not None:
        data["k"] = block.k
    return data


def _make_canvas_state(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    input_node: str | None,
    output_node: str | None,
    selected_id: str | None,
    timestamp: int | None = None,
) -> StreamlitFlowState:
    """Build the flow-component state from the canvas document."""
    flow_nodes = [
        StreamlitFlowNode(
            id=node["id"],
            pos=tuple(node.get("position", [100, 100])),
            data={"content": _block_title(node["block"])},
            node_type="input"
            if node["id"] == input_node
            else ("output" if node["id"] == output_node else "default"),
            source_position="right",
            target_position="left",
            selected=node["id"] == selected_id,
            draggable=True,
            selectable=True,
            connectable=True,
            deletable=True,
            style={"width": "150px", "fontSize": "13px", "borderRadius": "4px"},
        )
        for node in nodes
    ]
    flow_edges = [
        StreamlitFlowEdge(
            id=edge["id"],
            source=edge["source"],
            target=edge["target"],
            edge_type="straight",
            label=edge.get("label", ""),
            label_show_bg=True,
            deletable=True,
            style={"strokeWidth": 2},
        )
        for edge in edges
    ]
    state_kwargs: dict[str, Any] = {"selected_id": selected_id}
    if timestamp is not None:
        state_kwargs["timestamp"] = timestamp
    return StreamlitFlowState(flow_nodes, flow_edges, **state_kwargs)


def _document_from_canvas(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    input_node: str,
    output_node: str,
    stop_time: float,
    time_step: float | None,
) -> BlockDiagramDocument:
    """Build a validated document from the canvas state."""
    return BlockDiagramDocument(
        nodes=tuple(
            BlockDiagramNode(
                id=node["id"],
                block=_block_to_engine(node["block"]),
                position=tuple(node.get("position", (0.0, 0.0))),
                label=str(node.get("label", "")),
            )
            for node in nodes
        ),
        edges=tuple(
            BlockDiagramEdge(
                id=edge["id"],
                source=edge["source"],
                target=edge["target"],
                gain=float(edge.get("gain", 1.0)),
                label=str(edge.get("label", "")),
            )
            for edge in edges
        ),
        input_node=input_node,
        output_node=output_node,
        stop_time=stop_time,
        time_step=time_step,
    )


def _document_to_canvas(
    document: BlockDiagramDocument,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a document into the canvas node and edge lists."""
    nodes = [
        {
            "id": node.id,
            "block": _engine_to_block(node.block),
            "position": [node.position[0], node.position[1]],
            "label": node.label,
        }
        for node in document.nodes
    ]
    edges = [
        {
            "id": edge.id,
            "source": edge.source,
            "target": edge.target,
            "gain": edge.gain,
            "label": edge.label,
        }
        for edge in document.edges
    ]
    return nodes, edges


def _document_payload(document: BlockDiagramDocument) -> dict[str, Any]:
    """Return the JSON payload the editor saves and the CLI reads."""
    return {
        "nodes": [
            {
                "id": node.id,
                "kind": node.block.kind,
                "num": list(node.block.num) if node.block.num is not None else None,
                "den": list(node.block.den) if node.block.den is not None else None,
                "gains": (
                    {
                        "kp": node.block.gains.kp,
                        "ki": node.block.gains.ki,
                        "kd": node.block.gains.kd,
                    }
                    if node.block.gains is not None
                    else None
                ),
                "derivative_filter": node.block.derivative_filter,
                "k": node.block.k,
                "position": [node.position[0], node.position[1]],
                "label": node.label,
            }
            for node in document.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "gain": edge.gain,
                "label": edge.label,
            }
            for edge in document.edges
        ],
        "input_node": document.input_node,
        "output_node": document.output_node,
        "stop_time": document.stop_time,
        "time_step": document.time_step,
    }


def _canvas_to_document(
    payload: dict[str, Any],
) -> BlockDiagramDocument:
    """Rebuild a document from a saved JSON payload."""
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("block-diagram payload requires a nonempty nodes array")
    if not isinstance(raw_edges, list):
        raise ValueError("block-diagram payload requires an edges array")
    nodes = []
    for raw in raw_nodes:
        position = raw.get("position", [0.0, 0.0])
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError("each node requires a two-element position")
        nodes.append(
            BlockDiagramNode(
                id=str(raw.get("id", "")),
                block=_block_to_engine(raw),
                position=(float(position[0]), float(position[1])),
                label=str(raw.get("label", "")),
            )
        )
    edges = [
        BlockDiagramEdge(
            id=str(raw.get("id", f"e{index}")),
            source=str(raw.get("source", "")),
            target=str(raw.get("target", "")),
            gain=float(raw.get("gain", 1.0)),
            label=str(raw.get("label", "")),
        )
        for index, raw in enumerate(raw_edges, start=1)
    ]
    return BlockDiagramDocument(
        nodes=tuple(nodes),
        edges=tuple(edges),
        input_node=str(payload.get("input_node", "")),
        output_node=str(payload.get("output_node", "")),
        stop_time=float(payload.get("stop_time", 10.0)),
        time_step=(float(payload["time_step"]) if payload.get("time_step") is not None else None),
    )


def _edit_block(block: dict[str, Any], key: str) -> dict[str, Any]:
    """Render the property editor for one canvas block."""
    edited = dict(block)
    kind = block["kind"]
    if kind == "tf":
        num_text = st.text_area(
            "Numerator (descending powers of s)",
            json.dumps(list(block.get("num") or [1.0])),
            key=f"{key}_num",
        )
        den_text = st.text_area(
            "Denominator (descending powers of s)",
            json.dumps(list(block.get("den") or [1.0])),
            key=f"{key}_den",
        )
        try:
            edited["num"] = [float(v) for v in json.loads(num_text)]
            edited["den"] = [float(v) for v in json.loads(den_text)]
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            st.error(f"Invalid coefficient list: {error}")
    elif kind == "gain":
        edited["k"] = st.number_input(
            "Gain",
            value=float(block.get("k", 1.0)),
            format="%.8g",
            key=f"{key}_k",
        )
    else:
        gains = dict(block.get("gains") or {})
        gains["kp"] = st.number_input(
            "Kp", value=float(gains.get("kp", 0.0)), format="%.8g", key=f"{key}_kp"
        )
        gains["ki"] = st.number_input(
            "Ki", value=float(gains.get("ki", 0.0)), format="%.8g", key=f"{key}_ki"
        )
        gains["kd"] = st.number_input(
            "Kd", value=float(gains.get("kd", 0.0)), format="%.8g", key=f"{key}_kd"
        )
        edited["gains"] = gains
        edited["derivative_filter"] = st.number_input(
            "Derivative filter cutoff (1/s)",
            min_value=1e-6,
            value=float(block.get("derivative_filter") or 10.0),
            format="%.8g",
            key=f"{key}_nf",
        )
        st.caption("A derivative filter keeps the PID proper so the engine can compose it.")
    return edited


def _starter_canvas() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return a starter closed-loop diagram (plant + PID feedback)."""
    nodes = [
        {
            "id": "P1",
            "block": {"id": "P1", "kind": "tf", "num": [1.0], "den": [1.0, 4.0]},
            "position": [320, 140],
            "label": "Plant",
        },
        {
            "id": "C1",
            "block": {
                "id": "C1",
                "kind": "pid",
                "gains": {"kp": 2.0, "ki": 0.5, "kd": 0.0},
                "derivative_filter": 10.0,
            },
            "position": [80, 140],
            "label": "Controller",
        },
    ]
    edges = [
        {"id": "e1_C1_P1", "source": "C1", "target": "P1", "gain": 1.0, "label": ""},
        {"id": "e2_P1_C1", "source": "P1", "target": "C1", "gain": -1.0, "label": "-"},
    ]
    return nodes, edges


def render_block_diagram_editor() -> None:
    """Render the palette, canvas, inspector, and analysis outputs."""
    st.markdown(
        "<div class='workbench-kicker'>Control / Block diagram</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='workbench-title'>Block-diagram canvas</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='workbench-subtitle'>Place blocks, wire them with signed "
        "connections, then compose the diagram into a single transfer "
        "function.</div>",
        unsafe_allow_html=True,
    )

    st.session_state.setdefault("bd_nodes", [])
    st.session_state.setdefault("bd_edges", [])
    st.session_state.setdefault("bd_input", "")
    st.session_state.setdefault("bd_output", "")
    st.session_state.setdefault("bd_selected", None)
    st.session_state.setdefault("bd_stop_time", 10.0)
    st.session_state.setdefault("bd_time_step", None)
    st.session_state.setdefault("bd_result", None)

    with st.sidebar:
        st.markdown("<div class='workbench-kicker'>Diagram setup</div>", unsafe_allow_html=True)
        uploaded = st.file_uploader("Open block-diagram JSON", type=["json"], key="bd_upload")
        if uploaded is not None:
            import hashlib

            content = uploaded.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            if digest != st.session_state.get("bd_loaded_digest"):
                try:
                    document = _canvas_to_document(json.loads(content))
                    nodes, edges = _document_to_canvas(document)
                    st.session_state["bd_nodes"] = nodes
                    st.session_state["bd_edges"] = edges
                    st.session_state["bd_input"] = document.input_node
                    st.session_state["bd_output"] = document.output_node
                    st.session_state["bd_stop_time"] = document.stop_time
                    st.session_state["bd_time_step"] = document.time_step
                    st.session_state["bd_loaded_digest"] = digest
                    st.session_state["bd_result"] = None
                except Exception as error:
                    st.error(f"Could not load diagram: {error}")

        st.subheader("Block palette")
        palette_kind = st.selectbox(
            "Add block", list(BLOCK_PALETTE), format_func=lambda k: KIND_LABELS[k]
        )
        if st.button("Add to canvas", type="primary", use_container_width=True):
            nodes = st.session_state["bd_nodes"]
            prefix = {"tf": "G", "gain": "K", "pid": "C"}[palette_kind]
            identifier = _next_node_id(nodes, prefix)
            nodes.append(
                {
                    "id": identifier,
                    "block": _default_block(palette_kind, identifier),
                    "position": [
                        120 + (len(nodes) % 4) * 220,
                        100 + (len(nodes) // 4) * 150,
                    ],
                    "label": "",
                }
            )
            st.session_state["bd_selected"] = identifier
            st.session_state["bd_result"] = None

        st.subheader("Simulation window")
        st.session_state["bd_stop_time"] = st.number_input(
            "Stop time (s)",
            min_value=1e-3,
            value=float(st.session_state["bd_stop_time"]),
            format="%.8g",
            key="bd_tstop",
        )
        st.session_state["bd_time_step"] = (
            st.number_input(
                "Time step (s, 0 = auto)",
                min_value=0.0,
                value=float(st.session_state["bd_time_step"] or 0.0),
                format="%.8g",
                key="bd_dt",
            )
            or None
        )

        if st.button("Load closed-loop starter", use_container_width=True):
            nodes, edges = _starter_canvas()
            st.session_state["bd_nodes"] = nodes
            st.session_state["bd_edges"] = edges
            st.session_state["bd_input"] = "C1"
            st.session_state["bd_output"] = "P1"
            st.session_state["bd_selected"] = "C1"
            st.session_state["bd_result"] = None

    nodes = st.session_state["bd_nodes"]
    edges = st.session_state["bd_edges"]
    canvas_col, inspect_col = st.columns([0.72, 0.28], gap="large")

    with canvas_col:
        # Reuse the component's last-sync timestamp instead of a fresh
        # default: a fresh timestamp is always newer than the frontend's
        # local drag timestamp, which makes the canvas snap dragged nodes
        # back to their stale positions on the rerun after a drag.
        current_state = _make_canvas_state(
            nodes,
            edges,
            input_node=st.session_state.get("bd_input") or None,
            output_node=st.session_state.get("bd_output") or None,
            selected_id=st.session_state.get("bd_selected"),
            timestamp=st.session_state.get("bd_flow_timestamp"),
        )
        edited_state = streamlit_flow(
            "pycircuits_block_diagram_canvas",
            current_state,
            height=560,
            fit_view=True,
            show_controls=True,
            show_minimap=True,
            allow_new_edges=True,
            animate_new_edges=False,
            get_node_on_click=True,
            get_edge_on_click=True,
            pan_on_drag=True,
            allow_zoom=True,
            enable_node_menu=False,
            enable_edge_menu=False,
            style={
                "width": "100%",
                "border": "1px solid #d7dfd7",
                "borderRadius": "4px",
            },
        )
        st.session_state["bd_flow_timestamp"] = edited_state.timestamp
        previous = {node["id"]: node for node in nodes}
        updated_nodes = []
        for flow_node in edited_state.nodes:
            old_node = previous.get(flow_node.id)
            if old_node is None:
                continue
            node_copy = dict(old_node)
            node_copy["position"] = [flow_node.position["x"], flow_node.position["y"]]
            updated_nodes.append(node_copy)
        previous_edges = {edge["id"]: edge for edge in edges}
        updated_edges = []
        for flow_edge in edited_state.edges:
            old_edge = previous_edges.get(flow_edge.id)
            updated_edges.append(
                {
                    "id": flow_edge.id,
                    "source": flow_edge.source,
                    "target": flow_edge.target,
                    "gain": float(old_edge.get("gain", 1.0)) if old_edge else 1.0,
                    "label": str(old_edge.get("label", "")) if old_edge else "",
                }
            )
        if len(updated_nodes) == len(nodes):
            st.session_state["bd_nodes"] = updated_nodes
        if updated_edges != edges:
            st.session_state["bd_result"] = None
        st.session_state["bd_edges"] = updated_edges

    with inspect_col:
        st.markdown("#### Properties")
        if nodes:
            id_to_label = {
                node["id"]: (f"{node['id']} · {KIND_LABELS.get(node['block']['kind'], '?')}")
                for node in nodes
            }
            choices = list(id_to_label)
            selected = st.session_state.get("bd_selected")
            default_index = choices.index(selected) if selected in choices else 0
            selected = st.selectbox(
                "Selected block",
                choices,
                index=default_index,
                format_func=lambda item: id_to_label[item],
            )
            st.session_state["bd_selected"] = selected
            selected_node = next(node for node in nodes if node["id"] == selected)
            original_block = dict(selected_node["block"])
            updated_block = _edit_block(selected_node["block"], f"bd_{selected}")
            selected_node["block"] = updated_block
            if updated_block != original_block:
                st.session_state["bd_result"] = None
            if st.button("Remove selected block", use_container_width=True):
                st.session_state["bd_nodes"] = [node for node in nodes if node["id"] != selected]
                st.session_state["bd_edges"] = [
                    edge
                    for edge in st.session_state["bd_edges"]
                    if edge["source"] != selected and edge["target"] != selected
                ]
                st.session_state["bd_selected"] = None
                st.session_state["bd_result"] = None
        else:
            st.info("Add a block from the palette to edit its properties.")

        st.markdown("#### Diagram")
        node_ids = [node["id"] for node in nodes]
        if node_ids:
            st.session_state["bd_input"] = st.selectbox(
                "Reference enters at",
                node_ids,
                index=node_ids.index(st.session_state["bd_input"])
                if st.session_state["bd_input"] in node_ids
                else 0,
                key="bd_input_sel",
            )
            st.session_state["bd_output"] = st.selectbox(
                "Output tapped at",
                node_ids,
                index=node_ids.index(st.session_state["bd_output"])
                if st.session_state["bd_output"] in node_ids
                else 0,
                key="bd_output_sel",
            )
        else:
            st.session_state["bd_input"] = ""
            st.session_state["bd_output"] = ""

        if st.session_state["bd_edges"]:
            edge_ids = [edge["id"] for edge in st.session_state["bd_edges"]]
            edge_labels = {
                edge["id"]: (
                    f"{edge['source']} → {edge['target']} (gain {float(edge.get('gain', 1.0)):g})"
                )
                for edge in st.session_state["bd_edges"]
            }
            remove_edge = st.selectbox(
                "Connection",
                edge_ids,
                format_func=lambda item: edge_labels[item],
                key="bd_edge_sel",
            )
            st.number_input(
                "Connection gain (sign = summing sign)",
                value=float(
                    next(
                        edge["gain"]
                        for edge in st.session_state["bd_edges"]
                        if edge["id"] == remove_edge
                    )
                ),
                format="%.8g",
                key=f"bd_gain_{remove_edge}",
            )
            if st.button("Remove selected connection", use_container_width=True):
                st.session_state["bd_edges"] = [
                    edge for edge in st.session_state["bd_edges"] if edge["id"] != remove_edge
                ]
                st.session_state["bd_result"] = None

    nodes = st.session_state["bd_nodes"]
    edges = st.session_state["bd_edges"]
    try:
        document = _document_from_canvas(
            nodes,
            edges,
            st.session_state["bd_input"],
            st.session_state["bd_output"],
            float(st.session_state["bd_stop_time"]),
            st.session_state["bd_time_step"],
        )
        st.success(
            f"Diagram valid · {len(document.nodes)} blocks · {len(document.edges)} connections"
        )
        st.download_button(
            "Save block-diagram JSON",
            json.dumps(_document_payload(document), indent=2),
            file_name="pycircuits_block_diagram.json",
            mime="application/json",
            use_container_width=True,
        )
        if st.button("Compose diagram", type="primary", use_container_width=True):
            st.session_state["bd_result"] = interconnect_graph(document.to_graph())
            st.session_state["bd_error"] = None
    except Exception as error:
        st.warning(f"Diagram needs attention: {error}")
        if st.button(
            "Compose diagram",
            type="primary",
            use_container_width=True,
            disabled=True,
        ):
            pass

    result = st.session_state.get("bd_result")
    if result is not None:
        st.markdown("#### Composite analysis")
        num_col, den_col, stab_col = st.columns(3)
        num_col.metric("Numerator", f"{[round(v, 6) for v in result.composite_num]}")
        den_col.metric("Denominator", f"{[round(v, 6) for v in result.composite_den]}")
        stab_col.metric("BIBO stable", str(result.stability.bibo_stable))
        st.caption(result.stability.bibo_reason)
        if result.margins.phase_margin_deg is not None:
            st.write(f"Phase margin: {result.margins.phase_margin_deg:.2f} deg")
        if result.margins.gain_margin is not None:
            st.write(
                f"Gain margin: {result.margins.gain_margin:.4g} "
                f"({result.margins.gain_margin_db:.2f} dB)"
            )
        step = result.step
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=step.time_s, y=step.output, name="Composite output"))
        figure.add_hline(y=1.0, line_dash="dash", line_color="#8a9a92")
        figure.update_layout(
            title="Unit-step response of the composed diagram",
            xaxis_title="Time (s)",
            yaxis_title="Output",
            height=360,
        )
        st.plotly_chart(figure, use_container_width=True)
        st.download_button(
            "Download step response CSV",
            _step_csv(step),
            file_name="block_diagram_step.csv",
            mime="text/csv",
        )


def _step_csv(step: Any) -> str:
    """Return the composite step response as a CSV string."""
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["time_s", "output"])
    for time, value in zip(step.time_s, step.output, strict=False):
        writer.writerow([time, value])
    return output.getvalue()
