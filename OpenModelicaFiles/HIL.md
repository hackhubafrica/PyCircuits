# Hardware-in-the-Loop and ESP32 deployment

The supported first deployment profile is a linearized continuous-time SISO
state-space plant (`der(x)=A*x+B*u`, `y=C*x+D*u`) with 1–16 states. The
ESP32 evaluates this plant using fixed-step RK4. Python generates the
standalone matrix header and configuration; PlatformIO builds and, only on
explicit request, uploads it. OpenModelica-generated simulation C is not
copied into the firmware because it can depend on the OpenModelica runtime.

## Modes

- **Virtual plant (default):** ESP32 evolves the model using a serial-settable
  constant input. No GPIO is driven. Set the input with a JSON-line command:
  `{"type":"set_input","value":1.25}`.
- **Real I/O:** an ADC1 pin is mapped to the model input range and a PWM output
  pin is driven from the clamped model output range. Configuration requires
  an ADC1 pin (GPIO 32–39), a usable PWM pin, and numeric ranges;
  flash/UART/boot-strapping pins are rejected. Unconfigured firmware keeps the
  PWM output disabled. PWM output is generic and is not an actuator safety
  system.

Do not connect an ESP32 pin directly to voltage/current levels beyond its
board's specifications. Select a board-appropriate ADC interface and
conditioning, external protection, a current-limited test circuit, and a
hardware-safe output stage. Confirm all pin assignments against the exact
board. No particular sensor, driver, or power stage is assumed.

## Build, flash, monitor

Follow [BUILD.md](BUILD.md) from the repository root. In short:

```sh
python -m OpenModelicaFiles.modelica_workflow validate \
  --model OpenModelicaFiles/esp32_demo.mo
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo --mode virtual
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo --mode virtual \
  --upload --port /dev/ttyUSB0
python -m OpenModelicaFiles.modelica_workflow monitor --port /dev/ttyUSB0
```

The default update interval is 1 ms; telemetry is sent every 100 ms so serial
printing does not run on every integration step. Configure the serial monitor
to 115200 baud. Close any other program using the device's serial port.

## Timing and model limits

- The ESP32 firmware is not a hard-real-time safety controller. Loop timing
  includes Arduino/FreeRTOS scheduling, ADC/PWM calls, and serial activity.
- Choose a sample interval appropriate for model stiffness and the expected
  real-time rate. RK4 can become numerically unstable when the step is too
  large; the current utility checks the specified interval but does not
  calculate an automatic stable step.
- ESP32 floating-point arithmetic uses `float`; very large or poorly scaled
  state-space coefficients may be inaccurate or exceed MCU range.
- Firmware starts from the linearizer's `x0` vector when present; a model
  without `x0` starts at zero.
- Nonlinear equations, implicit DAEs, discrete events, arbitrary Modelica
  components, and models with multiple inputs/outputs are not currently
  deployable through this workflow.

## Hardware smoke test

1. Build without upload first; inspect the generated headers and confirm the
   selected model/mode/pin map.
2. Flash only the intended ESP32 and open the telemetry monitor.
3. In virtual mode, check that the state converges as expected, then send a
   small input command from a serial terminal.
4. In real-I/O mode, first test with a safe low-voltage signal and a
   disconnected/current-limited load. Confirm ADC scaling and verify PWM
   clamping before connecting an actuator.
5. Record the board, pin map, ranges, sample period, and test result with the
   experiment.
