from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Optional, Callable

from ..ir import IrMixin, to_ir, from_ir
from .telemetry import encode_input_command, parse_telemetry_line

__all__ = [
    "HILRunner",
    "HILReport",
    "serialize_plant_report",
    "deserialize_plant_report",
]


@dataclass(frozen=True)
class HILReport(IrMixin):
    """Telemetry report sent from hardware to the simulator."""

    timestamp_s: float
    values: tuple[float, ...]
    node_names: tuple[str, ...]


def serialize_plant_report(report) -> bytes:
    """Serialize a plant report (StateSpaceModel or PlantReport) to bytes."""
    return json.dumps(to_ir(report)).encode("utf-8")


def deserialize_plant_report(data: bytes):
    """Deserialize a plant report from bytes received from hardware."""
    return from_ir(json.loads(data.decode("utf-8")))


class HILRunner:
    """Receive ESP32 telemetry and send virtual-plant input commands."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        *,
        on_message: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_message = on_message
        self._serial: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._serial_lib = self._try_import_serial()

    @staticmethod
    def _try_import_serial():
        try:
            import serial as pyserial
            return pyserial
        except ImportError:
            return None

    def _ensure_serial(self) -> None:
        if self._serial_lib is None:
            raise RuntimeError(
                "Serial telemetry requires pyserial; install "
                "'pycircuits-sim[hardware]'."
            )
        if self._serial is None:
            self._serial = self._serial_lib.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1,
            )

    def _close_serial(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _report_error(self, message: str) -> None:
        if self.on_message is not None:
            self.on_message({"type": "error", "message": message})

    def start(self) -> None:
        """Start the background serial reader, raising on port-open errors."""
        if self._running:
            return
        self._ensure_serial()
        self._running = True

        def _reader() -> None:
            try:
                while self._running:
                    raw = self._serial.readline() if self._serial is not None else b""
                    if not raw:
                        continue
                    try:
                        message = parse_telemetry_line(raw)
                    except ValueError as error:
                        self._report_error(str(error))
                        continue
                    if self.on_message is not None:
                        self.on_message(message)
            except OSError as error:
                self._report_error(f"Serial telemetry failed: {error}")
            finally:
                self._running = False
                self._close_serial()

        self._thread = threading.Thread(target=_reader, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the serial reader and close the port."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._close_serial()

    def send_input(self, value: float) -> int:
        """Set the input of a device running in virtual-plant mode."""
        self._ensure_serial()
        if self._serial is None or not self._serial.is_open:
            raise RuntimeError("Serial port is not open.")
        return self._serial.write(encode_input_command(value))
import json
import time
import threading
from pathlib import Path
from typing import Any, Optional, Callable, Union

import numpy as np

from ..ir import to_ir, from_ir

__all__ = [
    "HILRunner",
    "HILReport",
    "serialize_plant_report",
    "deserialize_plant_report",
]

@dataclass(frozen=True)
class HILReport(IrMixin):
    """Telemetry report sent from hardware to the simulator."""
    """timestamp_s`` is the time of the measurement relative to the
    simulation start. ``values`` contains the measured signals."""
    timestamp_s: float
    values: tuple[float, ...]
    node_names: tuple[str, ...]

def serialize_plant_report(report) -> bytes:
    """Serialize a plant report (StateSpaceModel or PlantReport) to bytes."""
    """Used for transmission to hardware."""
    payload = to_ir(report)
    return json.dumps(payload).encode("utf-8")

def deserialize_plant_report(data: bytes):
    """Deserialize a plant report from bytes received from hardware."""
    payload = json.loads(data.decode("utf-8"))
    return from_ir(payload)

class HILRunner:
    """Hardware-in-the-Loop runner."""
    """Streams simulation outputs to a serial device and receives
    telemetry/control inputs in real time."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        *,
        simulation_loop: Optional[Callable[[], float]] = None,
        on_message: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """Initialize the HIL runner."""
        self.port = port
        self.baudrate = baudrate
        self.simulation_loop = simulation_loop
        self.on_message = on_message
        self._serial: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._sim_time = 0.0
        self._serial_lib = self._try_import_serial()

    @staticmethod
    def _try_import_serial():
        """Try to import the serial module."""
        try:
            import serial as pyserial
            return pyserial
        except ImportError:
            return None

    def _ensure_serial(self):
        """Lazy import and open the serial port."""
        if self._serial is None and self._serial_lib is not None:
            import serial as pyserial
            self._serial = pyserial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1
            )

    def _close_serial(self):
        """Close the serial port if open."""
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def start(self, simulation_loop: Optional[Callable[[], float]] = None) -> None:
        """Start the HIL runner thread."""
        if self._running:
            return
        self._running = True
        if simulation_loop is not None:
            self.simulation_loop = simulation_loop
        def _runner():
            try:
                self._ensure_serial()
                while self._running:
                    dt = self.simulation_loop() if self.simulation_loop else 0.01
                    self._sim_time += dt
                    msg = {"type": "measurement", "timestamp": self._sim_time, "values": [0.0]}
                    line = json.dumps(msg) + "\n"
                    if self._serial and self._serial.is_open:
                        self._serial.write(line.encode("utf-8"))
                    if self._serial and self._serial.in_waiting:
                        try:
                            raw = self._serial.readline().decode("utf-8").strip()
                            if raw:
                                msg = json.loads(raw)
                                if self.on_message:
                                    self.on_message(msg)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
            except Exception as e:
                if self.on_message:
                    self.on_message({"type": "error", "message": str(e)})
            finally:
                self._close_serial()
        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the HIL runner thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._close_serial()

    def send(self, message: dict) -> int:
        """Send a JSON message to the hardware."""
        line = json.dumps(message) + "\n"
        self._ensure_serial()
        if self._serial and self._serial.is_open:
            return self._serial.write(line.encode("utf-8"))
        return 0

    def send_step(self, step_index: int, total_steps: int) -> int:
        """Send a step progress message."""
        return self.send({"type": "step", "step_index": step_index, "total_steps": total_steps})
