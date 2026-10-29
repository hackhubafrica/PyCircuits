"""Schematic-canvas state and conversion to the existing MNA JSON netlist."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .mna import GROUND_NODES, Component, load_mna_config

COMPONENT_KINDS = (
    "resistor",
    "capacitor",
    "inductor",
    "diode",
    "voltage_source",
    "current_source",
    "switch",
)
EDITOR_NODE_KINDS = set(COMPONENT_KINDS) | {"junction", "ground"}


class _DisjointSet:
    def __init__(self, values: Iterable[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def default_component(kind: str, name: str) -> dict[str, Any]:
    """Return valid starter properties for a component palette item."""
    if kind not in COMPONENT_KINDS:
        raise ValueError(f"unsupported schematic component type: {kind}")
    if kind in {"resistor", "capacitor", "inductor"}:
        value = {"resistor": 1000.0, "capacitor": 1e-6, "inductor": 1e-3}[kind]
        return {"name": name, "type": kind, "value": value}
    if kind == "diode":
        return {"name": name, "type": kind}
    if kind in {"voltage_source", "current_source"}:
        value = 12.0 if kind == "voltage_source" else 0.01
        return {"name": name, "type": kind, "value": value}
    return {
        "name": name,
        "type": kind,
        "ron": 1e-3,
        "roff": 1e6,
        "threshold": 0.5,
        "control_points": [[0.0, 0.0], [0.001, 1.0]],
    }


def validate_editor_netlist(
    nodes: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    time_step: float,
    stop_time: float,
) -> dict[str, Any]:
    """Validate a wired canvas and return a simulator-ready MNA JSON object."""
    node_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id")
        kind = node.get("kind")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("every canvas node requires an id")
        if node_id in node_by_id:
            raise ValueError(f"duplicate canvas node id: {node_id}")
        if kind not in EDITOR_NODE_KINDS:
            raise ValueError(f"unsupported canvas node kind: {kind!r}")
        node_by_id[node_id] = node

    if not any(node["kind"] == "ground" for node in nodes):
        raise ValueError("place a ground symbol to provide the circuit reference")

    ports = [f"{node_id}.{side}" for node_id in node_by_id for side in ("p", "n")]
    groups = _DisjointSet(ports)
    ground_roots: set[str] = set()
    connected_ports: set[str] = set()

    for node_id, node in node_by_id.items():
        if node["kind"] in {"ground", "junction"}:
            groups.union(f"{node_id}.p", f"{node_id}.n")
        if node["kind"] == "ground":
            ground_roots.add(groups.find(f"{node_id}.p"))

    for wire_index, wire in enumerate(wires, start=1):
        source = wire.get("source")
        target = wire.get("target")
        if source not in node_by_id or target not in node_by_id:
            raise ValueError(f"wire {wire_index} references a missing canvas node")
        if source == target:
            raise ValueError(f"wire {wire_index} cannot connect a node to itself")
        source_port = f"{source}.n"
        target_port = f"{target}.p"
        groups.union(source_port, target_port)
        connected_ports.add(source_port)
        connected_ports.add(target_port)

    for node_id, node in node_by_id.items():
        if node["kind"] in {"junction", "ground"}:
            continue
        component_data = node.get("component")
        if not isinstance(component_data, dict):
            raise ValueError(f"{node_id}: component properties are missing")
        if f"{node_id}.p" not in connected_ports or f"{node_id}.n" not in connected_ports:
            raise ValueError(f"{component_data.get('name', node_id)} has an unconnected terminal")

    ground_roots = {
        groups.find(f"{node_id}.p")
        for node_id, node in node_by_id.items()
        if node["kind"] == "ground"
    }
    root_names: dict[str, str] = {}
    components: list[dict[str, Any]] = []
    circuit_nodes = [node for node in nodes if node["kind"] not in {"ground", "junction"}]
    if not circuit_nodes:
        raise ValueError("add at least one circuit component")

    for node in circuit_nodes:
        component_data = dict(node["component"])
        p_root = groups.find(f"{node['id']}.p")
        n_root = groups.find(f"{node['id']}.n")
        if p_root == n_root:
            raise ValueError(
                f"{component_data.get('name', node['id'])} is shorted: "
                "both terminals share one node"
            )
        for root in (p_root, n_root):
            if root not in ground_roots and root not in root_names:
                root_names[root] = f"N{len(root_names) + 1}"
        component_data["p"] = "0" if p_root in ground_roots else root_names[p_root]
        component_data["n"] = "0" if n_root in ground_roots else root_names[n_root]
        components.append(component_data)

    payload = {
        "time_step": time_step,
        "stop_time": stop_time,
        "components": components,
    }
    load_mna_config(payload)
    return payload


def schematic_document(
    nodes: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    time_step: float,
    stop_time: float,
) -> dict[str, Any]:
    """Build an MNA-compatible JSON netlist with editor layout metadata."""
    payload = validate_editor_netlist(nodes, wires, time_step, stop_time)
    payload["editor"] = {"nodes": nodes, "wires": wires}
    return payload


def editor_from_document(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load saved editor metadata or lay out an ordinary MNA netlist."""
    editor = payload.get("editor")
    if (
        isinstance(editor, dict)
        and isinstance(editor.get("nodes"), list)
        and isinstance(editor.get("wires"), list)
    ):
        return editor["nodes"], editor["wires"]

    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        raise ValueError("netlist requires a components array")
    nodes: list[dict[str, Any]] = []
    wires: list[dict[str, Any]] = []
    net_nodes: dict[str, str] = {}
    for index, component in enumerate(raw_components):
        Component.from_dict(component)
        component_id = f"component_{index + 1}"
        properties = {key: value for key, value in component.items() if key not in {"p", "n"}}
        nodes.append(
            {
                "id": component_id,
                "kind": component["type"],
                "component": properties,
                "position": [100 + (index % 4) * 220, 100 + (index // 4) * 150],
            }
        )
        for _, net, terminal in (("p", component["p"], "p"), ("n", component["n"], "n")):
            net_key = "0" if net.lower() in GROUND_NODES else net
            if net_key not in net_nodes:
                net_id = "ground_0" if net_key == "0" else f"junction_{len(net_nodes)}"
                net_nodes[net_key] = net_id
                nodes.append(
                    {
                        "id": net_id,
                        "kind": "ground" if net_key == "0" else "junction",
                        "component": None,
                        "position": [40 + len(net_nodes) * 170, 360],
                    }
                )
            net_node = net_nodes[net_key]
            if terminal == "p":
                wires.append(
                    {"id": f"wire_{len(wires) + 1}", "source": net_node, "target": component_id}
                )
            else:
                wires.append(
                    {"id": f"wire_{len(wires) + 1}", "source": component_id, "target": net_node}
                )
    return nodes, wires
