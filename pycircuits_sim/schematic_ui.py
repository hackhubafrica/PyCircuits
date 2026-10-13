"""First-pass drag-and-drop schematic editor backed by the MNA netlist engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from .mna import Component, MNAConfig, simulate_mna
from .schematic import (
    COMPONENT_KINDS,
    default_component,
    editor_from_document,
    schematic_document,
    validate_editor_netlist,
)


KIND_LABELS = {
    "resistor": "Resistor",
    "capacitor": "Capacitor",
    "inductor": "Inductor",
    "diode": "Diode",
    "voltage_source": "Voltage source",
    "current_source": "Current source",
    "switch": "PWL switch",
    "junction": "Junction",
    "ground": "Ground",
}


def _new_node_id(nodes: list[dict[str, Any]], prefix: str) -> str:
    used = {node["id"] for node in nodes}
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def _component_title(component: dict[str, Any]) -> str:
    name = component.get("name", "?")
    kind = component.get("type")
    value = component.get("value")
    if kind == "resistor":
        if value is not None:
            suffix = "k" if abs(float(value)) >= 1000 else ""
            shown = float(value) / 1000 if suffix else float(value)
            return f"{name}\n{shown:g}{suffix} ohm"
    elif kind == "capacitor" and value is not None:
        return f"{name}\n{float(value) * 1e6:g} uF"
    elif kind == "inductor" and value is not None:
        return f"{name}\n{float(value) * 1e3:g} mH"
    elif kind in {"voltage_source", "current_source"} and value is not None:
        unit = "V" if kind == "voltage_source" else "A"
        return f"{name}\n{float(value):g} {unit}"
    return f"{name}\n{KIND_LABELS.get(kind, kind)}"


def _next_node_id(nodes: list[dict[str, Any]], prefix: str) -> str:
    used = {node["id"] for node in nodes}
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def _node_content(node: dict[str, Any]) -> str:
    if node["kind"] in COMPONENT_KINDS:
        return _component_title(node["component"])
    return "GND" if node["kind"] == "ground" else "Junction"


def _make_canvas_state(
    nodes: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    selected_id: str | None,
    timestamp: int | None = None,
) -> StreamlitFlowState:
    flow_nodes = [
        StreamlitFlowNode(
            id=node["id"],
            pos=tuple(node.get("position", [100, 100])),
            data={"content": _node_content(node)},
            source_position="right",
            target_position="left",
            selected=node["id"] == selected_id,
            draggable=True,
            selectable=True,
            connectable=True,
            style={"width": "150px", "fontSize": "14px", "borderRadius": "4px"},
        )
        for node in nodes
    ]
    flow_edges = [
        StreamlitFlowEdge(
            id=wire["id"],
            source=wire["source"],
            target=wire["target"],
            edge_type="straight",
            deletable=True,
            style={"strokeWidth": 2},
        )
        for wire in wires
    ]
    state_kwargs = {"selected_id": selected_id}
    if timestamp is not None:
        state_kwargs["timestamp"] = timestamp
    return StreamlitFlowState(flow_nodes, flow_edges, **state_kwargs)


def _edit_component(component: dict[str, Any], key: str) -> dict[str, Any]:
    edited = dict(component)
    kind = component["type"]
    edited["name"] = st.text_input("Reference", component.get("name", "X1"), key=f"{key}_name")
    if kind in {"resistor", "capacitor", "inductor"}:
        edited["value"] = st.number_input(
            {"resistor": "Resistance (ohm)", "capacitor": "Capacitance (F)", "inductor": "Inductance (H)"}[kind],
            min_value=1e-12,
            value=float(component.get("value", 1.0)),
            format="%.8g",
            key=f"{key}_value",
        )
        if kind in {"capacitor", "inductor"}:
            edited["initial"] = st.number_input(
                "Initial voltage (V)" if kind == "capacitor" else "Initial current (A)",
                value=float(component.get("initial", 0.0)),
                format="%.8g",
                key=f"{key}_initial",
            )
    elif kind == "diode":
        edited["saturation_current"] = st.number_input("Saturation current (A)", min_value=1e-18, value=float(component.get("saturation_current", 1e-12)), format="%.3e", key=f"{key}_is")
        edited["ideality_factor"] = st.number_input("Ideality factor", min_value=0.1, value=float(component.get("ideality_factor", 1.0)), step=0.1, key=f"{key}_n")
        edited["thermal_voltage"] = st.number_input("Thermal voltage (V)", min_value=1e-4, value=float(component.get("thermal_voltage", 0.02585)), format="%.5g", key=f"{key}_vt")
    elif kind in {"voltage_source", "current_source"}:
        edited["value"] = st.number_input("DC value (V)" if kind == "voltage_source" else "DC value (A)", value=float(component.get("value", 0.0)), format="%.8g", key=f"{key}_value")
        waveform = dict(component.get("waveform", {}))
        waveform_type = st.selectbox("Waveform", ["dc", "sine"], index=0 if waveform.get("type", "dc") == "dc" else 1, key=f"{key}_waveform")
        if waveform_type == "sine":
            waveform["type"] = "sine"
            waveform["offset"] = st.number_input("Offset", value=float(waveform.get("offset", component.get("value", 0.0))), key=f"{key}_offset")
            waveform["amplitude"] = st.number_input("Amplitude", min_value=0.0, value=float(waveform.get("amplitude", 1.0)), key=f"{key}_amplitude")
            waveform["frequency"] = st.number_input("Frequency (Hz)", min_value=0.001, value=float(waveform.get("frequency", 50.0)), key=f"{key}_frequency")
            waveform["phase"] = st.number_input("Phase (rad)", value=float(waveform.get("phase", 0.0)), key=f"{key}_phase")
        else:
            waveform = {"type": "dc", "offset": float(edited["value"])}
        edited["waveform"] = waveform
    elif kind == "switch":
        edited["ron"] = st.number_input("On resistance (ohm)", min_value=1e-9, value=float(component.get("ron", 1e-3)), format="%.5g", key=f"{key}_ron")
        edited["roff"] = st.number_input("Off resistance (ohm)", min_value=1e-3, value=float(component.get("roff", 1e6)), format="%.5g", key=f"{key}_roff")
        edited["threshold"] = st.number_input("Control threshold", value=float(component.get("threshold", 0.5)), key=f"{key}_threshold")
        points = st.text_area("PWL control points [[time_s, value], ...]", json.dumps(component.get("control_points", [[0.0, 0.0], [0.001, 1.0]])), key=f"{key}_points")
        try:
            edited["control_points"] = json.loads(points)
        except json.JSONDecodeError as error:
            st.error(f"Invalid PWL JSON: {error.msg}")
    return edited


def render_schematic_editor() -> None:
    """Render palette, canvas, property inspector, validation, and MNA outputs."""
    st.markdown("<div class='workbench-kicker'>MNA / Schematic editor</div>", unsafe_allow_html=True)
    st.markdown("<div class='workbench-title'>Circuit canvas</div>", unsafe_allow_html=True)
    st.markdown("<div class='workbench-subtitle'>Place two-terminal parts, connect their terminals, validate the netlist, then simulate it.</div>", unsafe_allow_html=True)

    st.session_state.setdefault("schematic_nodes", [])
    st.session_state.setdefault("schematic_wires", [])
    st.session_state.setdefault("schematic_selected_id", None)
    st.session_state.setdefault("schematic_time_step", 1e-5)
    st.session_state.setdefault("schematic_stop_time", 0.002)

    with st.sidebar:
        st.markdown("<div class='workbench-kicker'>Circuit setup</div>", unsafe_allow_html=True)
        uploaded = st.file_uploader("Open MNA JSON", type=["json"], key="schematic_upload")
        if uploaded is not None:
            import hashlib

            content = uploaded.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            if digest != st.session_state.get("schematic_loaded_digest"):
                try:
                    payload = json.loads(content)
                    nodes, wires = editor_from_document(payload)
                    st.session_state["schematic_nodes"] = nodes
                    st.session_state["schematic_wires"] = wires
                    st.session_state["schematic_time_step"] = float(payload["time_step"])
                    st.session_state["schematic_stop_time"] = float(payload["stop_time"])
                    st.session_state["schematic_loaded_digest"] = digest
                    st.session_state["schematic_result"] = None
                except Exception as error:
                    st.error(f"Could not load circuit: {error}")

        st.subheader("Component palette")
        palette_kind = st.selectbox("Add component", [*COMPONENT_KINDS, "junction", "ground"])
        if st.button("Add to canvas", type="primary", use_container_width=True):
            nodes = st.session_state["schematic_nodes"]
            identifier = _next_node_id(nodes, "GND" if palette_kind == "ground" else "J" if palette_kind == "junction" else "X")
            component = None
            if palette_kind in COMPONENT_KINDS:
                name_prefix = {"resistor": "R", "capacitor": "C", "inductor": "L", "diode": "D", "voltage_source": "V", "current_source": "I", "switch": "S"}[palette_kind]
                count = sum(node.get("kind") == palette_kind for node in nodes) + 1
                component = default_component(palette_kind, f"{name_prefix}{count}")
            nodes.append({"id": identifier, "kind": palette_kind, "component": component, "position": [100 + (len(nodes) % 4) * 190, 100 + (len(nodes) // 4) * 120]})
            st.session_state["schematic_selected_id"] = identifier
            st.session_state["schematic_result"] = None

        st.subheader("Transient solver")
        previous_time_step = st.session_state["schematic_time_step"]
        previous_stop_time = st.session_state["schematic_stop_time"]
        st.session_state["schematic_time_step"] = st.number_input("Timestep (s)", min_value=1e-9, value=float(st.session_state["schematic_time_step"]), format="%.8g", key="schematic_dt")
        st.session_state["schematic_stop_time"] = st.number_input("Stop time (s)", min_value=1e-8, value=float(st.session_state["schematic_stop_time"]), format="%.8g", key="schematic_tstop")
        if (previous_time_step, previous_stop_time) != (st.session_state["schematic_time_step"], st.session_state["schematic_stop_time"]):
            st.session_state["schematic_result"] = None
        st.caption("Port convention: left = p, right = n. Use junctions to branch a net and always place a ground.")

        if st.button("Load RC starter", use_container_width=True):
            starter_nodes = [
                {"id": "V1", "kind": "voltage_source", "component": {"name": "V1", "type": "voltage_source", "value": 5.0}, "position": [100, 180]},
                {"id": "R1", "kind": "resistor", "component": {"name": "R1", "type": "resistor", "value": 1000.0}, "position": [360, 180]},
                {"id": "C1", "kind": "capacitor", "component": {"name": "C1", "type": "capacitor", "value": 1e-6}, "position": [620, 180]},
                {"id": "J1", "kind": "junction", "component": None, "position": [250, 50]},
                {"id": "GND", "kind": "ground", "component": None, "position": [620, 350]},
            ]
            starter_wires = [
                {"id": "w1", "source": "J1", "target": "V1"},
                {"id": "w2", "source": "J1", "target": "R1"},
                {"id": "w3", "source": "V1", "target": "GND"},
                {"id": "w4", "source": "R1", "target": "C1"},
                {"id": "w5", "source": "C1", "target": "GND"},
            ]
            st.session_state["schematic_nodes"] = starter_nodes
            st.session_state["schematic_wires"] = starter_wires
            st.session_state["schematic_selected_id"] = "R1"
            st.session_state["schematic_time_step"] = 1e-5
            st.session_state["schematic_stop_time"] = 0.005
            st.session_state["schematic_result"] = None

    nodes = st.session_state["schematic_nodes"]
    wires = st.session_state["schematic_wires"]
    canvas_col, inspect_col = st.columns([0.72, 0.28], gap="large")
    with canvas_col:
        # Reuse the component's last-sync timestamp instead of the fresh
        # default. A fresh timestamp would always be newer than the frontend's
        # local drag timestamp, causing the canvas to snap dragged nodes back to
        # their stale positions on the rerun that follows a drag. Persisting the
        # timestamp lets the frontend's `l <= args.timestamp` guard fail after a
        # drag so the new position is preserved.
        current_state = _make_canvas_state(
            nodes,
            wires,
            selected_id=st.session_state.get("schematic_selected_id"),
            timestamp=st.session_state.get("schematic_flow_timestamp"),
        )
        edited_state = streamlit_flow(
            "pycircuits_schematic_canvas",
            current_state,
            height=600,
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
            style={"width": "100%", "border": "1px solid #d7dfd7", "borderRadius": "4px"},
        )
        st.session_state["schematic_flow_timestamp"] = edited_state.timestamp
        previous = {node["id"]: node for node in nodes}
        updated_nodes = []
        for flow_node in edited_state.nodes:
            old_node = previous.get(flow_node.id)
            if old_node is None:
                continue
            node_copy = dict(old_node)
            node_copy["position"] = [flow_node.position["x"], flow_node.position["y"]]
            updated_nodes.append(node_copy)
        updated_edges = [
            {"id": edge.id, "source": edge.source, "target": edge.target}
            for edge in edited_state.edges
        ]
        if len(updated_nodes) == len(nodes):
            st.session_state["schematic_nodes"] = updated_nodes
        if updated_edges != wires:
            st.session_state["schematic_result"] = None
        st.session_state["schematic_wires"] = updated_edges
        if edited_state.selected_id in {node["id"] for node in nodes}:
            st.session_state["schematic_selected_id"] = edited_state.selected_id

    nodes = st.session_state["schematic_nodes"]
    wires = st.session_state["schematic_wires"]
    with inspect_col:
        st.markdown("#### Properties")
        component_nodes = [node for node in nodes if node["kind"] in COMPONENT_KINDS]
        if component_nodes:
            id_to_label = {node["id"]: f"{node['component'].get('name', node['id'])} · {KIND_LABELS[node['kind']]}" for node in component_nodes}
            choices = list(id_to_label)
            selected = st.session_state.get("schematic_selected_id")
            default_index = choices.index(selected) if selected in choices else 0
            selected = st.selectbox("Selected component", choices, index=default_index, format_func=lambda item: id_to_label[item])
            st.session_state["schematic_selected_id"] = selected
            selected_node = next(node for node in component_nodes if node["id"] == selected)
            original_component = dict(selected_node["component"])
            updated_component = _edit_component(selected_node["component"], f"schem_{selected}")
            selected_node["component"] = updated_component
            selected_node["kind"] = updated_component["type"]
            if updated_component != original_component:
                st.session_state["schematic_result"] = None
            if st.button("Remove selected component", use_container_width=True):
                st.session_state["schematic_nodes"] = [node for node in nodes if node["id"] != selected]
                st.session_state["schematic_wires"] = [wire for wire in wires if wire["source"] != selected and wire["target"] != selected]
                st.session_state["schematic_selected_id"] = None
                st.session_state["schematic_result"] = None
        else:
            st.info("Add a component from the palette to edit its properties.")

        if wires:
            wire_ids = [wire["id"] for wire in wires]
            remove_wire = st.selectbox("Wire", wire_ids, format_func=lambda wire_id: f"{next(w['source'] for w in wires if w['id'] == wire_id)} → {next(w['target'] for w in wires if w['id'] == wire_id)}")
            if st.button("Remove selected wire", use_container_width=True):
                st.session_state["schematic_wires"] = [wire for wire in wires if wire["id"] != remove_wire]
                st.session_state["schematic_result"] = None

        try:
            document = schematic_document(nodes, wires, st.session_state["schematic_time_step"], st.session_state["schematic_stop_time"])
            st.success(f"Netlist valid · {len(document['components'])} components · {len(wires)} wires")
            st.download_button("Save netlist JSON", json.dumps(document, indent=2), file_name="pycircuits_schematic.json", mime="application/json", use_container_width=True)
            if st.button("Run circuit simulation", type="primary", use_container_width=True):
                config = MNAConfig(
                    time_step=st.session_state["schematic_time_step"],
                    stop_time=st.session_state["schematic_stop_time"],
                    components=tuple(Component.from_dict(item) for item in document["components"]),
                )
                st.session_state["schematic_result"] = simulate_mna(config)
                st.session_state["schematic_error"] = None
        except Exception as error:
            st.warning(f"Netlist needs attention: {error}")
            if st.button("Run circuit simulation", type="primary", use_container_width=True, disabled=True):
                pass

    result = st.session_state.get("schematic_result")
    if result is not None:
        st.markdown("#### Simulation outputs")
        voltage_col, current_col = st.columns(2)
        voltage_fig = go.Figure()
        for node_name, trace in result.node_voltages.items():
            voltage_fig.add_trace(go.Scatter(x=result.time, y=trace, name=f"V({node_name})"))
        voltage_fig.update_layout(title="Node voltages", xaxis_title="Time (s)", yaxis_title="Voltage (V)", height=360)
        current_fig = go.Figure()
        for component_name, trace in result.component_currents.items():
            current_fig.add_trace(go.Scatter(x=result.time, y=trace, name=component_name))
        current_fig.update_layout(title="Component currents", xaxis_title="Time (s)", yaxis_title="Current (A)", height=360)
        voltage_col.plotly_chart(voltage_fig, use_container_width=True)
        current_col.plotly_chart(current_fig, use_container_width=True)
        st.download_button("Download simulation CSV", _result_csv(result), file_name="schematic_waveforms.csv", mime="text/csv")


def _result_csv(result: Any) -> str:
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    columns = ["time_s", *[f"node_voltage_{name}_v" for name in result.node_voltages], *[f"current_{name}_a" for name in result.component_currents]]
    writer.writerow(columns)
    for index, time in enumerate(result.time):
        writer.writerow([time, *[trace[index] for trace in result.node_voltages.values()], *[trace[index] for trace in result.component_currents.values()]])
    return output.getvalue()
