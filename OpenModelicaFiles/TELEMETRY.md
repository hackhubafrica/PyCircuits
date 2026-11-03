# ESP32 telemetry and command protocol

The PlatformIO firmware and Python host use UTF-8 JSON Lines at 115200 baud.
Each message is one JSON object followed by `\n`. This replaces the old
unimplemented binary/Go examples so that the firmware and host have one
consistent format.

## Device telemetry

```json
{"type":"telemetry","timestamp_us":1234,"input":0.5,"output":0.25,"mode":"virtual","states":[0.25]}
```

Fields:

| Field | Type | Meaning |
|---|---|---|
| `type` | string | `telemetry` |
| `timestamp_us` | integer | ESP32 `micros()` timestamp (wraps approximately every 71 minutes) |
| `input` | number | Model input used for this sample |
| `output` | number | Model output |
| `mode` | string | `virtual` or `io` |
| `states` | array of numbers | Current state vector |

Firmware errors use `{"type":"error","message":"..."}` and do not masquerade
as telemetry.

## Host command

Virtual mode accepts the following JSON-line command:

```json
{"type":"set_input","value":1.25}
```

The firmware ignores host input commands in real-I/O mode. The Python helper
validates finite values and sends the newline-delimited message:

```python
from pycircuits_sim.hardware import HILRunner

runner = HILRunner("/dev/ttyUSB0", on_message=print)
runner.start()
runner.send_input(1.25)  # virtual mode only
runner.stop()
```

Install the optional serial dependency with
`python -m pip install -e ".[hardware]"`. Or monitor using
`python -m OpenModelicaFiles.modelica_workflow monitor --port /dev/ttyUSB0`.
The helper validates message types and finite numeric fields and reports
malformed lines through `on_message` as an error object.

## Timing and limitations

The model step defaults to 1 ms; telemetry defaults to 100 ms. JSON is easy to
inspect but has more bandwidth and formatting cost than a packed binary
protocol. It is intended for educational low-rate telemetry, not high-rate
sampling guarantees or hard-real-time control. Firmware timing is subject to
Arduino/FreeRTOS scheduling. See [HIL.md](HIL.md) before connecting external
hardware.
