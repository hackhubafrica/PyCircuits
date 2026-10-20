import json
import os
import tempfile
import unittest
from dataclasses import dataclass

from pycircuits_sim.analysis import (
    analyze_stability,
    bode_margins,
    normalize_plant,
    nyquist_response,
    root_locus,
)
from pycircuits_sim.design import FopdtFit, PIDGains
from pycircuits_sim.interconnect import (
    InterconnectBlock,
    InterconnectSpec,
    interconnect,
)
from pycircuits_sim.ir import (
    IR_VERSION,
    IrError,
    build_ir_schema,
    dumps_ir,
    from_ir,
    load_ir,
    register,
    registry,
    to_ir,
    validate_ir,
)
from pycircuits_sim.linear_systems import transfer_function_to_state_space

# Second-order teaching plant 1/(s^2+s+1): wn=1, zeta=0.5.
KNOWN = transfer_function_to_state_space([1.0], [1.0, 1.0, 1.0])


class IrEnvelopeTests(unittest.TestCase):
    def test_envelope_shape(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        self.assertEqual(payload["ir_version"], IR_VERSION)
        self.assertEqual(payload["kind"], "PIDGains")
        self.assertEqual(payload["data"], {"kp": 1.0, "ki": 0.5, "kd": 0.25})

    def test_mixin_exposes_to_ir_and_from_ir(self):
        gains = PIDGains(2.0, 0.0, 0.0)
        self.assertEqual(gains.to_ir(), to_ir(gains))
        self.assertEqual(PIDGains.from_ir(gains.to_ir()), gains)

    def test_mixin_from_ir_rejects_a_foreign_kind(self):
        payload = to_ir(FopdtFit(1.0, 2.0, 0.5))
        with self.assertRaises(IrError):
            PIDGains.from_ir(payload)

    def test_payload_is_json_serializable(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_dumps_ir_round_trips_through_json(self):
        gains = PIDGains(1.0, 0.5, 0.25)
        self.assertEqual(from_ir(json.loads(dumps_ir(gains))), gains)


class IrRoundTripTests(unittest.TestCase):
    def assert_round_trip(self, value):
        payload = to_ir(value)
        decoded = from_ir(payload)
        self.assertEqual(decoded, value)
        self.assertIs(type(decoded), type(value))
        # The encoded payload must survive a trip through JSON text.
        again = from_ir(json.loads(json.dumps(payload)))
        self.assertEqual(again, value)

    def test_primitive_dataclass(self):
        self.assert_round_trip(PIDGains(1.25, -0.5, 3.0))

    def test_plant_report_with_complex_poles(self):
        report = normalize_plant(KNOWN)
        self.assertTrue(any(pole.imag != 0.0 for pole in report.poles))
        self.assert_round_trip(report)

    def test_stability_report(self):
        self.assert_round_trip(analyze_stability(KNOWN))

    def test_margin_result(self):
        self.assert_round_trip(bode_margins(KNOWN))

    def test_nyquist_result(self):
        self.assert_round_trip(nyquist_response(KNOWN))

    def test_root_locus_result(self):
        self.assert_round_trip(root_locus(KNOWN))

    def test_nested_dataclass(self):
        gains = PIDGains(2.0, 0.5, 0.1)
        block = InterconnectBlock(id="c", kind="pid", gains=gains)
        spec = InterconnectSpec(
            blocks=(block,),
            forward=("c",),
            feedback="unity",
            stop_time=5.0,
            time_step=0.01,
        )
        payload = to_ir(spec)
        self.assertEqual(payload["data"]["blocks"][0]["gains"]["kp"], 2.0)
        self.assert_round_trip(spec)

    def test_interconnect_result(self):
        spec = InterconnectSpec(
            blocks=(
                InterconnectBlock(id="g", kind="tf", num=(1.0,), den=(1.0, 1.0)),
            ),
            forward=("g",),
            feedback="unity",
            stop_time=2.0,
            time_step=0.01,
        )
        self.assert_round_trip(interconnect(spec))


class IrPrimitiveTests(unittest.TestCase):
    def test_non_finite_float_is_rejected(self):
        with self.assertRaises(IrError):
            to_ir({"value": float("nan")})
        with self.assertRaises(IrError):
            to_ir({"value": float("inf")})

    def test_non_finite_float_in_a_dataclass_field_is_rejected(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class LooseFloat:
            value: float

        with self.assertRaises(IrError):
            to_ir(LooseFloat(float("nan")))

    def test_binary_payload_is_rejected(self):
        with self.assertRaises(IrError):
            to_ir({"blob": b"\x00\x01"})

    def test_unsupported_type_is_rejected(self):
        with self.assertRaises(IrError):
            to_ir({"handle": object()})

    def test_non_finite_error_message_mentions_the_reason(self):
        with self.assertRaises(IrError) as caught:
            to_ir({"value": float("nan")})
        self.assertIn("non-finite", str(caught.exception))


class IrDecodingErrorTests(unittest.TestCase):
    def test_wrong_version_is_rejected(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["ir_version"] = "9.9"
        with self.assertRaises(IrError):
            from_ir(payload)

    def test_unknown_kind_is_rejected(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["kind"] = "NotAThing"
        with self.assertRaises(IrError):
            from_ir(payload)

    def test_missing_field_is_rejected(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        del payload["data"]["ki"]
        with self.assertRaises(IrError):
            from_ir(payload)

    def test_non_mapping_payload_is_rejected(self):
        with self.assertRaises(IrError):
            from_ir(["not", "a", "mapping"])

    def test_wrong_leaf_type_is_rejected(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["data"]["kp"] = "one"
        with self.assertRaises(IrError):
            from_ir(payload)

    def test_error_is_a_value_error(self):
        self.assertTrue(issubclass(IrError, ValueError))


class IrRegistryTests(unittest.TestCase):
    def test_registry_contains_the_engine_results(self):
        names = registry()
        for expected in (
            "PIDGains",
            "PlantReport",
            "StabilityReport",
            "InterconnectSpec",
            "StateSpaceModel",
        ):
            self.assertIn(expected, names)

    def test_register_adds_a_new_kind(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class CustomIrThing:
            label: str

        try:
            register(CustomIrThing)
            self.assertIn("CustomIrThing", registry())
            thing = CustomIrThing("hello")
            self.assertEqual(from_ir(to_ir(thing)), thing)
        finally:
            registry().pop("CustomIrThing", None)

    def test_register_rejects_a_non_dataclass(self):
        with self.assertRaises(IrError):
            register(dict)


class IrSchemaTests(unittest.TestCase):
    def test_schema_declares_the_envelope(self):
        schema = build_ir_schema()
        envelope = schema["$defs"]["IREnvelope"]
        self.assertEqual(envelope["required"], ["ir_version", "kind", "data"])
        self.assertEqual(envelope["properties"]["ir_version"]["const"], IR_VERSION)

    def test_schema_has_a_definition_per_registered_kind(self):
        schema = build_ir_schema()
        for name in registry():
            self.assertIn(name, schema["$defs"])

    def test_validate_accepts_a_real_payload(self):
        validate_ir(to_ir(PIDGains(1.0, 0.5, 0.25)))
        validate_ir(to_ir(normalize_plant(KNOWN)))

    def test_validate_rejects_a_bad_leaf_type(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["data"]["kp"] = "one"
        with self.assertRaises(IrError):
            validate_ir(payload)

    def test_validate_rejects_a_missing_field(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        del payload["data"]["ki"]
        with self.assertRaises(IrError):
            validate_ir(payload)

    def test_validate_rejects_a_bad_version(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["ir_version"] = "9.9"
        with self.assertRaises(IrError):
            validate_ir(payload)

    def test_validate_rejects_an_unknown_kind(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["kind"] = "NoSuchKind"
        with self.assertRaises(IrError):
            validate_ir(payload)

    def test_validate_rejects_an_extra_field(self):
        payload = to_ir(PIDGains(1.0, 0.5, 0.25))
        payload["data"]["unexpected"] = 1
        with self.assertRaises(IrError):
            validate_ir(payload)

    def test_schema_is_json_serializable(self):
        json.dumps(build_ir_schema())


class IrSequenceDecodingTests(unittest.TestCase):
    """Regression tests for the tuple-shape handling in the IR decoder.

    The engine's annotations use three distinct tuple shapes, and each needs
    its own decoding rule.
    """

    def test_fixed_length_tuple_keeps_its_arity(self):
        report = normalize_plant(KNOWN)
        restored = from_ir(to_ir(report))
        self.assertEqual(restored, report)

    def test_variadic_tuple_decodes_every_item(self):
        report = normalize_plant(KNOWN)
        payload = to_ir(report)
        self.assertIsInstance(payload["data"]["denominator"], list)
        self.assertTrue(all(isinstance(v, float) for v in payload["data"]["denominator"]))
        self.assertEqual(from_ir(payload), report)

    def test_nested_tuple_of_tuples_round_trips(self):
        report = normalize_plant(KNOWN)
        payload = to_ir(report)
        self.assertIsInstance(payload["data"]["A"], list)
        self.assertIsInstance(payload["data"]["A"][0], list)
        self.assertEqual(from_ir(payload), report)

    def test_a_fixed_length_tuple_with_the_wrong_arity_is_rejected(self):
        @dataclass(frozen=True)
        class FixedPair:
            pair: tuple[float, str]

        register(FixedPair)
        good = {
            "ir_version": IR_VERSION,
            "kind": "FixedPair",
            "data": {"pair": [1.5, "two"]},
        }
        self.assertEqual(from_ir(good), FixedPair((1.5, "two")))

        bad = {
            "ir_version": IR_VERSION,
            "kind": "FixedPair",
            "data": {"pair": [1.5, "two", 3.0]},
        }
        with self.assertRaises(IrError):
            from_ir(bad)

    def test_a_fixed_length_tuple_decodes_each_position_by_its_own_type(self):
        @dataclass(frozen=True)
        class MixedPair:
            pair: tuple[float, str]

        register(MixedPair)
        payload = {
            "ir_version": IR_VERSION,
            "kind": "MixedPair",
            "data": {"pair": [2.5, "text"]},
        }
        restored = from_ir(payload)
        self.assertIsInstance(restored.pair[0], float)
        self.assertIsInstance(restored.pair[1], str)

    def test_a_fixed_length_tuple_rejects_a_mistyped_position(self):
        @dataclass(frozen=True)
        class StrictPair:
            pair: tuple[float, str]

        register(StrictPair)
        payload = {
            "ir_version": IR_VERSION,
            "kind": "StrictPair",
            "data": {"pair": [2.5, 7]},
        }
        with self.assertRaises(IrError):
            from_ir(payload)


class IrFileTests(unittest.TestCase):
    def test_load_ir_reads_a_document_from_disk(self):
        gains = PIDGains(1.0, 0.5, 0.25)
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(dumps_ir(gains))
            self.assertEqual(load_ir(path), gains)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
