"""Shared intermediate representation (IR) for PyCircuits results.

Milestone A of the extension ladder: one JSON-compatible schema describing
plants, blocks, interconnections, and analyses, with a lossless
``to_ir()``/``from_ir()`` round trip on every frozen result dataclass.

Design goals
------------
* **One vocabulary.** Every layer (CLI, HTTP API, workbench UI, future
  hardware bridge or Modelica front end) speaks this IR instead of
  inventing a second schema.
* **No drift.** The JSON Schema is *derived* from the same dataclass
  registry that drives encoding, so the published schema and the runtime
  payload can never disagree.
* **Pure Python core.** Only the standard library is required. The
  optional ``jsonschema`` package is used by :func:`validate_ir` when it
  happens to be installed; the schema itself is plain data.

Wire shape
----------
Every IR document is a JSON object::

    {
      "ir_version": "1.0",
      "kind": "PlantReport",
      "data": { ...kind-specific fields... }
    }

Nested dataclasses are encoded inline as their own field mappings; the
decoder recovers their types from the parent dataclass's annotations, so
the nested payload stays self-describing without nesting envelopes.
Complex numbers use ``{"re": ..., "im": ...}``.

Example
-------
>>> from pycircuits_sim.analysis import normalize_plant
>>> from pycircuits_sim.linear_systems import StateSpaceModel
>>> model = StateSpaceModel.from_matrices([[-1.0]], [[1.0]], [[1.0]], [[0.0]])
>>> payload = normalize_plant(model).to_ir()
>>> payload["kind"]
'PlantReport'
>>> payload["data"]["dc_gain"]
1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
import enum
import json
import math
import types
import typing
from typing import Any, Union, get_args, get_origin

__all__ = [
    "IR_VERSION",
    "IrError",
    "build_ir_schema",
    "dumps_ir",
    "from_ir",
    "load_ir",
    "register",
    "registry",
    "to_ir",
    "validate_ir",
]

IR_VERSION = "1.0"


class IrError(ValueError):
    """Raised when an IR payload is malformed or cannot be decoded."""


class IrMixin:
    """Adds the IR wire format to a result dataclass.

    Engine dataclasses inherit this so every result exposes the same two
    entry points::

        report.to_ir()             # -> {"ir_version": ..., "kind": ..., "data": ...}
        PlantReport.from_ir(payload)

    The mixin holds no fields, so it never changes a dataclass's field
    order or its ``__eq__``/``__hash__`` behaviour.
    """

    def to_ir(self) -> dict[str, Any]:
        """Encode this result as an IR document."""
        return to_ir(self)

    @classmethod
    def from_ir(cls, payload: Mapping[str, Any]) -> Any:
        """Decode an IR document back into an instance of this class."""
        decoded = from_ir(payload)
        if not isinstance(decoded, cls):
            raise IrError(
                f"the IR document holds a {type(decoded).__name__}, "
                f"not a {cls.__name__}"
            )
        return decoded


# --- Primitive codecs --------------------------------------------------------


def _encode_float(value: float) -> float:
    """Encode a float, rejecting NaN/inf which JSON cannot represent."""
    if not math.isfinite(value):
        raise IrError(
            "the IR cannot encode non-finite floats; "
            "NaN and infinity have no JSON representation"
        )
    return value


def _encode_primitive(value: Any) -> Any:
    """Encode a leaf value into a JSON-compatible form."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _encode_float(value)
    if isinstance(value, complex):
        return {"re": value.real, "im": value.imag}
    if isinstance(value, enum.Enum):
        return _encode_primitive(value.value)
    if isinstance(value, (bytes, bytearray)):
        raise IrError("the IR cannot encode binary payloads")
    # numpy scalars and arrays without importing numpy at module level.
    item = getattr(value, "item", None)
    if item is not None and getattr(value, "shape", None) == ():
        return _encode_primitive(item())
    tolist = getattr(value, "tolist", None)
    if tolist is not None and getattr(value, "shape", None) is not None:
        return _encode_primitive(tolist())
    raise IrError(f"cannot encode value of type {type(value).__name__} into the IR")


# --- Type-hint resolution -----------------------------------------------------


def _resolve_hints(cls: type) -> dict[str, Any]:
    """Resolve the annotations of a dataclass to runtime types.

    The engine modules use ``from __future__ import annotations``, so the
    raw field types are strings. ``get_type_hints`` evaluates them against
    the defining module's globals, which are complete by the time any IR
    call happens.
    """
    try:
        return typing.get_type_hints(cls)
    except Exception as error:  # pragma: no cover - defensive
        raise IrError(f"cannot resolve type hints for {cls.__name__}: {error}") from error


def _union_members(hint: Any) -> tuple[Any, ...] | None:
    """Return the members of a union hint, or None if it is not a union."""
    origin = get_origin(hint)
    if origin is Union or origin is types.UnionType:
        return get_args(hint)
    return None


def _is_dataclass_hint(hint: Any) -> bool:
    return isinstance(hint, type) and is_dataclass(hint)


# --- Encoding ----------------------------------------------------------------


def _encode_value(value: Any) -> Any:
    """Encode any supported value into a JSON-compatible form."""
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        return _encode_float(value)
    if isinstance(value, complex):
        return {"re": value.real, "im": value.imag}
    if isinstance(value, enum.Enum):
        return _encode_primitive(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        # Nested dataclasses are encoded inline (their fields only). The
        # surrounding envelope already carries the kind, and the decoder
        # recovers the nested type from the dataclass field annotation.
        return {
            field.name: _encode_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _encode_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_encode_value(item) for item in sorted(value, key=repr)]
    return _encode_primitive(value)


def _encode_dataclass(instance: Any) -> dict[str, Any]:
    """Encode a dataclass instance into the self-describing envelope."""
    data: dict[str, Any] = {}
    for field in fields(instance):
        data[field.name] = _encode_value(getattr(instance, field.name))
    return {
        "ir_version": IR_VERSION,
        "kind": type(instance).__name__,
        "data": data,
    }


def to_ir(value: Any) -> dict[str, Any]:
    """Encode a result dataclass (or any supported value) into an IR document.

    >>> from pycircuits_sim.design import PIDGains
    >>> to_ir(PIDGains(1.0, 0.5, 0.0))["data"]["kp"]
    1.0
    """
    if is_dataclass(value) and not isinstance(value, type):
        return _encode_dataclass(value)
    return {"ir_version": IR_VERSION, "kind": "Value", "data": _encode_value(value)}


# --- Registry -----------------------------------------------------------------


def _collect_registry() -> dict[str, type]:
    """Build the name -> dataclass registry of every IR-encodable type.

    Imported lazily so that ``pycircuits_sim.ir`` never creates an import
    cycle with the engine modules it describes.
    """
    from importlib import import_module

    module_names = (
        "pycircuits_sim.analysis",
        "pycircuits_sim.buck",
        "pycircuits_sim.closed_loop",
        "pycircuits_sim.design",
        "pycircuits_sim.interconnect",
        "pycircuits_sim.linear_systems",
        "pycircuits_sim.metrics",
        "pycircuits_sim.mna",
        "pycircuits_sim.sweep",
    )
    registry: dict[str, type] = {}
    for module_name in module_names:
        module = import_module(module_name)
        for name, candidate in vars(module).items():
            if name.startswith("_"):
                continue
            if isinstance(candidate, type) and is_dataclass(candidate):
                registry.setdefault(candidate.__name__, candidate)
    return registry


_REGISTRY: dict[str, type] | None = None


def registry() -> dict[str, type]:
    """Return the mapping of IR ``kind`` names to their dataclass types."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _collect_registry()
    return _REGISTRY


def register(kind: type) -> type:
    """Register an extra dataclass so it can be decoded by name.

    Extension front ends (a Modelica importer, a hardware bridge) can call
    this to make their own result types round-trip through the IR.
    """
    if not is_dataclass(kind):
        raise IrError("only dataclasses can be registered in the IR registry")
    registry()[kind.__name__] = kind
    return kind


# --- Decoding ----------------------------------------------------------------


def _decode_primitive(value: Any, hint: Any) -> Any:
    """Coerce a decoded JSON leaf into the type the dataclass expects."""
    if hint is complex:
        if isinstance(value, Mapping) and "re" in value and "im" in value:
            return complex(float(value["re"]), float(value["im"]))
        raise IrError(f"cannot decode {value!r} as a complex number")
    if hint is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise IrError(f"cannot decode {value!r} as a float")
        return float(value)
    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise IrError(f"cannot decode {value!r} as an int")
        return value
    if hint is bool:
        if not isinstance(value, bool):
            raise IrError(f"cannot decode {value!r} as a bool")
        return value
    if hint is str:
        if not isinstance(value, str):
            raise IrError(f"cannot decode {value!r} as a string")
        return value
    return value


def _decode_sequence(
    value: list[Any],
    args: tuple[Any, ...],
    origin: Any,
) -> list[Any]:
    """Decode a JSON array against a sequence type hint.

    Three shapes occur in the engine's annotations and each needs different
    handling:

    * ``tuple[float, ...]`` -- variadic: every item is a ``float``.
    * ``tuple[float, str]`` -- fixed length: each position has its own type.
    * ``tuple[tuple[float, ...], ...]`` -- nested: the outer tuple is
      variadic, the inner one is too.

    ``tuple[()]/Ellipsis`` is the empty-tuple marker and decodes to ``[]``.
    """
    if not args:
        # Bare ``tuple`` / ``list``: no element type is known.
        return list(value)

    if len(args) == 2 and args[1] is Ellipsis:
        # ``tuple[float, ...]`` -- one item type for every position.
        item_hint = args[0]
        return [_decode_value(item, item_hint) for item in value]

    # A fixed-length tuple: the number of arguments is the exact arity.
    if origin is tuple and len(args) != len(value):
        raise IrError(
            f"expected a tuple of {len(args)} items, got {len(value)}"
        )
    decoded: list[Any] = []
    for index, item in enumerate(value):
        if index < len(args):
            item_hint = args[index]
        elif args and args[-1] is Ellipsis:
            item_hint = args[-2]
        else:
            item_hint = Any
        decoded.append(_decode_value(item, item_hint))
    return decoded


def _decode_value(value: Any, hint: Any) -> Any:
    """Decode a JSON value into the type described by ``hint``."""
    if hint is Any or hint is None:
        return value

    members = _union_members(hint)
    if members is not None:
        if value is None and type(None) in members:
            return None
        for member in members:
            if member is type(None):
                continue
            try:
                return _decode_value(value, member)
            except (IrError, TypeError, ValueError):
                continue
        raise IrError(f"cannot decode {value!r} as any member of {hint}")

    origin = get_origin(hint)
    if origin in (list, tuple, set, frozenset):
        if not isinstance(value, list):
            raise IrError(f"cannot decode {value!r} as a sequence")
        args = get_args(hint)
        decoded = _decode_sequence(value, args, origin)
        if origin is tuple:
            return tuple(decoded)
        if origin is set:
            return set(decoded)
        if origin is frozenset:
            return frozenset(decoded)
        return decoded

    if origin in (dict, Mapping):
        if not isinstance(value, Mapping):
            raise IrError(f"cannot decode {value!r} as a mapping")
        args = get_args(hint)
        value_hint = args[1] if len(args) == 2 else Any
        return {
            str(key): _decode_value(item, value_hint) for key, item in value.items()
        }

    if _is_dataclass_hint(hint):
        if not isinstance(value, Mapping):
            raise IrError(f"cannot decode {value!r} as {hint.__name__}")
        return _decode_dataclass(hint, value)

    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return hint(value)

    return _decode_primitive(value, hint)


def _decode_dataclass(cls: type, payload: Mapping[str, Any]) -> Any:
    """Rebuild a dataclass instance from its encoded ``data`` mapping."""
    if not isinstance(payload, Mapping):
        raise IrError(f"cannot decode {payload!r} as {cls.__name__}")
    hints = _resolve_hints(cls)
    kwargs: dict[str, Any] = {}
    for field in fields(cls):
        if field.name not in payload:
            has_default = (
                field.default is not MISSING
                or field.default_factory is not MISSING  # type: ignore[misc]
            )
            if has_default:
                continue
            raise IrError(
                f"payload for {cls.__name__} is missing required field {field.name!r}"
            )
        kwargs[field.name] = _decode_value(
            payload[field.name], hints.get(field.name, Any)
        )
    return cls(**kwargs)


def from_ir(payload: Mapping[str, Any]) -> Any:
    """Decode an IR document produced by :func:`to_ir`.

    >>> from pycircuits_sim.design import PIDGains
    >>> from_ir(to_ir(PIDGains(1.0, 0.5, 0.0))) == PIDGains(1.0, 0.5, 0.0)
    True
    """
    if not isinstance(payload, Mapping):
        raise IrError("an IR document must be a JSON object")
    version = payload.get("ir_version")
    if version != IR_VERSION:
        raise IrError(
            f"unsupported IR version {version!r}; this build reads {IR_VERSION!r}"
        )
    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise IrError("an IR document must carry a string 'kind'")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise IrError("an IR document must carry an object 'data'")
    if kind == "Value":
        return data
    target = registry().get(kind)
    if target is None:
        raise IrError(f"unknown IR kind {kind!r}")
    return _decode_dataclass(target, data)


def load_ir(path: str) -> Any:
    """Read an IR document from a JSON file and decode it."""
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return from_ir(payload)


# --- JSON Schema generation ---------------------------------------------------

_COMPLEX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "A complex number.",
    "properties": {
        "re": {"type": "number"},
        "im": {"type": "number"},
    },
    "required": ["re", "im"],
    "additionalProperties": False,
}


def _schema_for_hint(hint: Any) -> dict[str, Any]:
    """Return the JSON Schema fragment describing a type hint."""
    if hint is Any or hint is None:
        return {}
    if hint is complex:
        return dict(_COMPLEX_SCHEMA)
    if hint is float:
        return {"type": "number"}
    if hint is int:
        return {"type": "integer"}
    if hint is bool:
        return {"type": "boolean"}
    if hint is str:
        return {"type": "string"}

    members = _union_members(hint)
    if members is not None:
        schemas = [
            {"type": "null"} if member is type(None) else _schema_for_hint(member)
            for member in members
        ]
        return {"anyOf": schemas}

    origin = get_origin(hint)
    if origin in (list, tuple, set, frozenset):
        args = get_args(hint)
        if origin is tuple and args and args[-1] is not Ellipsis and len(args) > 1:
            # A fixed-length tuple: describe each position separately.
            return {
                "type": "array",
                "prefixItems": [_schema_for_hint(arg) for arg in args],
                "minItems": len(args),
                "maxItems": len(args),
                "items": False,
            }
        item_schema = _schema_for_hint(args[0]) if args else {}
        schema: dict[str, Any] = {"type": "array"}
        if item_schema:
            schema["items"] = item_schema
        return schema
    if origin in (dict, Mapping):
        args = get_args(hint)
        value_schema = _schema_for_hint(args[1]) if len(args) == 2 else {}
        schema = {"type": "object"}
        if value_schema:
            schema["additionalProperties"] = value_schema
        return schema
    if _is_dataclass_hint(hint):
        return {"$ref": f"#/$defs/{hint.__name__}"}
    if isinstance(hint, type) and issubclass(hint, enum.Enum):
        return {"enum": [member.value for member in hint]}
    return {}


def _schema_for_dataclass(cls: type) -> dict[str, Any]:
    """Return the JSON Schema describing one dataclass."""
    hints = _resolve_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in fields(cls):
        properties[field.name] = _schema_for_hint(hints.get(field.name, Any))
        if field.default is MISSING and field.default_factory is MISSING:  # type: ignore[misc]
            required.append(field.name)
    schema: dict[str, Any] = {
        "type": "object",
        "description": (cls.__doc__ or cls.__name__).strip().split("\n")[0],
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def build_ir_schema() -> dict[str, Any]:
    """Build the JSON Schema describing every IR document.

    The schema is *derived* from the same dataclass registry that drives
    encoding and decoding, so the published schema and the runtime
    payload cannot drift apart.

    >>> schema = build_ir_schema()
    >>> schema["$defs"]["IREnvelope"]["properties"]["ir_version"]["const"]
    '1.0'
    """
    defs = {
        name: _schema_for_dataclass(cls) for name, cls in sorted(registry().items())
    }
    # The envelope itself, plus one conditional per kind so that "data" is
    # validated against the definition matching the declared "kind".
    conditionals = [
        {
            "if": {"properties": {"kind": {"const": name}}, "required": ["kind"]},
            "then": {"properties": {"data": {"$ref": f"#/$defs/{name}"}}},
        }
        for name in sorted(defs)
    ]
    defs["IREnvelope"] = {
        "type": "object",
        "description": "The self-describing IR envelope.",
        "properties": {
            "ir_version": {
                "type": "string",
                "const": IR_VERSION,
                "description": "The IR contract version this document uses.",
            },
            "kind": {
                "type": "string",
                "enum": sorted(set(defs) | {"Value"}),
                "description": "The dataclass name the 'data' object encodes.",
            },
            "data": {
                "description": (
                    "The encoded payload for 'kind'. Object-shaped for every "
                    "registered dataclass kind; 'Value' may carry any JSON "
                    "value."
                ),
            },
        },
        "required": ["ir_version", "kind", "data"],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pycircuits.dev/schemas/ir-1.0.json",
        "title": "PyCircuits IR document",
        "description": (
            "Self-describing envelope wrapping any PyCircuits result "
            "dataclass. Nested dataclasses use the same field encoding."
        ),
        "$ref": "#/$defs/IREnvelope",
        "allOf": conditionals,
        "$defs": defs,
    }


def validate_ir(payload: Mapping[str, Any]) -> None:
    """Validate an IR document against :func:`build_ir_schema`.

    Uses the optional ``jsonschema`` package when it is installed. Without
    it, only the envelope is checked, so the core stays dependency-free.
    """
    schema = build_ir_schema()
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        from_ir(payload)  # structural check only
        return
    try:
        jsonschema.validate(dict(payload), schema)
    except jsonschema.ValidationError as error:
        raise IrError(f"IR payload failed schema validation: {error.message}") from error


def dumps_ir(value: Any, *, indent: int | None = 2) -> str:
    """Serialize a value to an IR JSON string."""
    return json.dumps(to_ir(value), indent=indent, allow_nan=False)
