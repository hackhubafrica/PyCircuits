# Graphical Modelica to ESP32 workflow

Use OMEdit for graphical Modelica authoring. The Python workflow accepts a
linearized, continuous-time SISO state-space `.mo` model, generates a small
portable C++ model header, builds the PlatformIO firmware, and uploads only
when explicitly requested.

## 1. Create and check a plant in OMEdit

1. Open OMEdit and create or open a Modelica model. Use Diagram View to place
   and connect components from the Modelica Standard Library.
2. Expose one scalar continuous input `u` and one scalar output `y`. Add a
   reference/ground and complete all physical connections required by the
   component libraries.
3. Check the model, set its parameters, run a transient simulation, and save
   the `.mo` source.
4. For example, a mechanical plant can use Modelica > Mechanics >
   Translational components such as Mass, Spring, Damper, Force, and Fixed.
   Connect the flanges and a reference; use a signal source for excitation.
   An electrical plant needs its electrical Ground and appropriate sources
   and components. OMEdit shows the diagram and generated Modelica source for
   the same model.
5. For MCU deployment, expose one scalar input and output and linearize the
   model around the desired operating point. The workflow calls OpenModelica
   `linearize()`, finds its generated linearized `.mo`, checks that the result
   fits the SISO state-space profile, and writes the artifact to your chosen
   path. The output includes `A`, `B`, `C`, `D`, and (when emitted by OMC) `x0`.

For example, from the repository root:

```sh
python -m OpenModelicaFiles.modelica_workflow linearize \
  --model path/to/MyPlant.mo \
  --model-class MyPlant \
  --output outputs/MyPlant_linearized.mo \
  --start-time 0 --stop-time 1 --intervals 500
```

For a package model, pass the fully qualified class, such as
`--model-class MyPackage.MyPlant`. Then use the output with `validate`,
`simulate`, or `deploy`.

OpenModelica must be installed with `omc` available on PATH. The command keeps
compiler artifacts in a temporary directory, validates the extracted matrices
before copying the `.mo` output, and fails with diagnostics if OpenModelica
cannot linearize the class or if it emits a non-SISO result.

The workflow does not translate arbitrary Modelica component diagrams, DAEs,
events, or nonlinear equations into firmware. The supported export has 1–16
states, exactly one input and one output, and numeric finite matrix values.
The generated firmware uses the linearizer's `x0` initial state if present;
models without `x0` start at zero.
The current [linearized_model.mo](linearized_model.mo) has zero inputs and
outputs, so it remains an analysis example and is not deployable by this
profile. [esp32_demo.mo](esp32_demo.mo) is a small valid state-space example.

## 2. Install tools

- Python 3.10+ and the PyCircuits dependencies (`python -m pip install -e .`)
- OpenModelica (`omc`) for linearization and the optional `--omc-check`
- PlatformIO Core (`pio`) for firmware build and upload
- `pyserial` for host telemetry: `python -m pip install -e ".[hardware]"`

The workflow's model parser and header generation do not require OMPython.
OpenModelica and PlatformIO are external tools and are checked when their
actions are requested.

## 3. Validate and build (no upload)

Run from the repository root:

```sh
python -m OpenModelicaFiles.modelica_workflow validate \
  --model OpenModelicaFiles/esp32_demo.mo

python -m OpenModelicaFiles.modelica_workflow simulate \
  --model OpenModelicaFiles/esp32_demo.mo \
  --duration 1 --sample-period 0.001 \
  --output outputs/esp32_demo.csv

python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo \
  --mode virtual
```

`validate` checks the state-space dimensions and numeric values. `simulate`
runs a host-side RK4 simulation with a constant input, starting at `x0` when
present (otherwise zero), and writes time/input/output/state columns to CSV
(maximum one million samples).
Add `--omc-check` to run OpenModelica `checkModel()` as well. `deploy` writes
`plant_model.h` and `firmware_config.h` into
`OpenModelicaFiles/PlantHILProject/src/`, then builds with PlatformIO. It does
not flash the board unless `--upload` is present.

To generate headers without requiring PlatformIO:

```sh
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo \
  --mode virtual \
  --prepare-only
```

## 4. Explicitly upload to an ESP32

Virtual-plant mode evolves the model on the ESP32 and streams telemetry. It
does not touch GPIO outputs:

```sh
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo \
  --mode virtual \
  --upload \
  --port /dev/ttyUSB0
```

For configurable real I/O, provide an ADC1 input pin (GPIO 32–39) and a usable
PWM output pin (GPIO 0–33; flash, UART, and boot-strapping pins are rejected).
The input range maps the ADC reading to the model input; the model output is
clamped to the output range and mapped to an 8-bit PWM duty cycle:

```sh
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo \
  --mode io \
  --adc-pin 34 \
  --pwm-pin 25 \
  --input-min 0 --input-max 3.3 \
  --output-min 0 --output-max 3.3 \
  --upload \
  --port /dev/ttyUSB0
```

Use only a low-voltage, current-limited test setup appropriate for the selected
board and external circuit. Pin numbers, ranges, and external interface
protection must match the user's hardware. The generated default configuration
is virtual mode with GPIO output disabled. The workflow never uploads unless
`--upload` is supplied and a port is specified.

## 5. Read telemetry

Close any serial monitor that has the port open, then run:

```sh
python -m OpenModelicaFiles.modelica_workflow monitor --port /dev/ttyUSB0
```

Press Ctrl+C to stop. The optional hardware extra supplies `pyserial`. The
default model update period is 1 ms and telemetry is emitted every 100 ms;
both can be changed with `--sample-period` and `--telemetry-period`.

## Legacy OpenModelica scripts

`compile-plant.py` and `define_plant_model.py` call OpenModelica to build or
linearize desktop simulation artifacts. Those generated C files can depend on
the OpenModelica runtime and are not the standalone ESP32 firmware. Use
`modelica_workflow.py` for the supported ESP32 profile instead.
