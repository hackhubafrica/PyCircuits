import unittest

from pycircuits_sim.schematic import (
    default_component,
    editor_from_document,
    schematic_document,
    validate_editor_netlist,
)


class SchematicNetlistTests(unittest.TestCase):
    def make_rc_schematic(self):
        nodes = [
            {"id": "V1", "kind": "voltage_source", "component": {"name": "V1", "type": "voltage_source", "value": 5.0}, "position": [100, 100]},
            {"id": "R1", "kind": "resistor", "component": {"name": "R1", "type": "resistor", "value": 1000.0}, "position": [300, 100]},
            {"id": "C1", "kind": "capacitor", "component": {"name": "C1", "type": "capacitor", "value": 1e-6}, "position": [500, 100]},
            {"id": "GND", "kind": "ground", "component": None, "position": [500, 300]},
            {"id": "J1", "kind": "junction", "component": None, "position": [200, 300]},
        ]
        wires = [
            {"id": "w1", "source": "V1", "target": "GND"},
            {"id": "w2", "source": "J1", "target": "V1"},
            {"id": "w3", "source": "J1", "target": "R1"},
            {"id": "w4", "source": "R1", "target": "C1"},
            {"id": "w5", "source": "C1", "target": "GND"},
        ]
        return nodes, wires

    def test_canvas_wires_build_mna_nets(self) -> None:
        nodes, wires = self.make_rc_schematic()
        netlist = validate_editor_netlist(nodes, wires, 1e-6, 0.01)

        self.assertEqual(len(netlist["components"]), 3)
        source, resistor, capacitor = netlist["components"]
        self.assertEqual(source["n"], "0")
        self.assertEqual(source["p"], resistor["p"])
        self.assertEqual(resistor["n"], capacitor["p"])
        self.assertEqual(capacitor["n"], "0")

    def test_editor_json_round_trips_layout_and_connections(self) -> None:
        nodes, wires = self.make_rc_schematic()
        document = schematic_document(nodes, wires, 1e-6, 0.01)
        loaded_nodes, loaded_wires = editor_from_document(document)

        self.assertEqual(loaded_nodes, nodes)
        self.assertEqual(loaded_wires, wires)
        self.assertIn("p", document["components"][0])
        self.assertIn("editor", document)

    def test_ordinary_mna_netlist_opens_on_canvas(self) -> None:
        payload = {
            "time_step": 1e-6,
            "stop_time": 0.001,
            "components": [
                {"name": "V1", "type": "voltage_source", "p": "in", "n": "0", "value": 5.0},
                {"name": "R1", "type": "resistor", "p": "in", "n": "0", "value": 1000.0},
            ],
        }

        nodes, wires = editor_from_document(payload)
        rebuilt = validate_editor_netlist(nodes, wires, 1e-6, 0.001)

        self.assertEqual(len(rebuilt["components"]), 2)
        self.assertTrue(any(node["kind"] == "ground" for node in nodes))

    def test_unconnected_and_ungrounded_components_are_rejected(self) -> None:
        nodes = [
            {"id": "R1", "kind": "resistor", "component": default_component("resistor", "R1"), "position": [0, 0]},
            {"id": "GND", "kind": "ground", "component": None, "position": [200, 0]},
        ]
        with self.assertRaisesRegex(ValueError, "unconnected terminal"):
            validate_editor_netlist(nodes, [], 1e-6, 0.001)

        nodes[0]["component"]["value"] = 1000.0
        wires = [
            {"id": "w1", "source": "R1", "target": "GND"},
            {"id": "w2", "source": "GND", "target": "R1"},
        ]
        with self.assertRaisesRegex(ValueError, "shorted"):
            validate_editor_netlist(nodes, wires, 1e-6, 0.001)

    def test_ground_is_required(self) -> None:
        nodes = [{"id": "R1", "kind": "resistor", "component": default_component("resistor", "R1"), "position": [0, 0]}]
        with self.assertRaisesRegex(ValueError, "ground symbol"):
            validate_editor_netlist(nodes, [], 1e-6, 0.001)


if __name__ == "__main__":
    unittest.main()
