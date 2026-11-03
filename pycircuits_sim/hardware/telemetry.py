"""Validation and JSON-lines framing for ESP32 telemetry and input commands."""

from __future__ import annotations

import json
import math
from typing import Any


def parse_telemetry_line(line: bytes | str) -> dict[str, Any]:
    """Decode and validate one firmware line, raising ValueError on bad data."""
    try:
        text = line.decode("utf-8") if isinstance(line, bytes) else line
        message = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid telemetry JSON line: {error}") from error
    if not isinstance(message, dict):
        raise ValueError("Telemetry line must contain a JSON object.")

    message_type = message.get("type")
    if message_type == "error":
        if not isinstance(message.get("message"), str):
            raise ValueError("Firmware error message is missing its text.")
        return message
    if message_type != "telemetry":
        raise ValueError(f"Unexpected firmware message type: {message_type!r}.")

    timestamp = message.get("timestamp_us")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
        raise ValueError("Telemetry timestamp_us must be a non-negative integer.")
    for field in ("input", "output"):
        value = message.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Telemetry {field} must be numeric.")
        if not math.isfinite(value):
            raise ValueError(f"Telemetry {field} must be finite.")
    mode = message.get("mode")
    if mode not in {"virtual", "io"}:
        raise ValueError("Telemetry mode must be 'virtual' or 'io'.")
    states = message.get("states")
    if not isinstance(states, list) or not states:
        raise ValueError("Telemetry states must be a non-empty numeric list.")
    for value in states:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Telemetry states must contain only finite numbers.")
    return message


def encode_input_command(value: float) -> bytes:
    """Encode the supported host-to-device virtual-input command."""
    if not math.isfinite(value):
        raise ValueError("Input command value must be finite.")
    return (json.dumps({"type": "set_input", "value": value}) + "\n").encode("utf-8")
