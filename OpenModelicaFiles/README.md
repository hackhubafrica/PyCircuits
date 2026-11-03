# OpenModelicaFiles

Physical modeling and hardware-in-the-loop (HIL) deployment layer for PyCircuits.

This folder contains Modelica source files (`.mo`), OpenModelica analysis
scripts, a Python-to-ESP32 workflow, PlatformIO firmware, and generated build
artifacts.

## What's inside

| Path | Purpose |
|------|---------|
| `plant.mo` | First-order continuous plant model (RC-style low-pass) |
| `RCCircuit.mo` / `RCCircuit.mos` | Resistor-capacitor circuit model + OpenModelica script |
| `linearized_model.mo` | 4-state mass-spring-damper with PID (linearized state-space) |
| `compile-plant.py` | Compile Modelica plant → C, organize artifacts into `plant_build/`, sync to PlatformIO |
| `define_plant_model.py` | Linearize Modelica model → organize artifacts into `lin_build/` |
| `dynamic_model.py` | Closed-loop PID step-response simulation in Python (SciPy) |
| `dynamic_main_model.py` | Parse `linearized_model.mo` matrices, convert to TF, simulate |
| `extract_params.py` | Extract state-space matrices from `.mo`, simulate via `lsim` |
| `linearized_model.py` | Parse state-space matrices (A, B, C, D) from `.mo` |
| `linearized_model_simulate.py` | Parse + simulate state-space model with SciPy |
| `observe_plant_states.py` | Parse + plot all 4 closed-loop states on subplots |
| `TF.py` | Load model via OMPython, linearize, print ABCD matrices |
| `modelica_parser.py` | Shared parser: `parse_linearized_model()` used by all scripts above |
| `modelica_workflow.py` | Linearize, validate, simulate, and deploy supported SISO `.mo` models; monitor ESP32 telemetry |
| `esp32_demo.mo` | Deployable one-state state-space example |
| `PlantHILProject/` | PlatformIO ESP32 firmware project for HIL deployment |
| `ESP32HILProject/` | Older PlatformIO scaffold; not used by the current workflow |
| `plant_build/` | Generated C/headers/objects from OpenModelica compilation |
| `lin_build/` | Generated linearization artifacts |
| `venv/` | Isolated Python environment with OMPython |

## Getting started

### Prerequisites

1. **Python 3.10+** and the project installed in editable mode:
   `python -m pip install -e .`
2. **OpenModelica** (`omc`) for automatic model linearization and the legacy
   desktop compile/linearize scripts
3. **PlatformIO Core** (`pio`) for ESP32 build/upload
4. **pyserial** for telemetry monitoring:
```sh
python -m pip install -e ".[hardware]"
```

OMPython is only needed by the legacy scripts that use `OMCSessionLocal`.

### Graphically model and deploy an ESP32 plant

Use OMEdit for graphical Modelica authoring. See [BUILD.md](BUILD.md) for
model creation, linearization, and the MCU-supported state-space contract.
`esp32_demo.mo` demonstrates the required numeric `A`, `B`, `C`, and `D`
matrices. Validate and simulate it from the repository root:

```sh
python -m OpenModelicaFiles.modelica_workflow validate \
  --model OpenModelicaFiles/esp32_demo.mo

python -m OpenModelicaFiles.modelica_workflow simulate \
  --model OpenModelicaFiles/esp32_demo.mo --output outputs/plant.csv
```

Build firmware without uploading:

```sh
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo --mode virtual
```

For your OMEdit plant, first export its operating-point linearization:

```sh
python -m OpenModelicaFiles.modelica_workflow linearize \
  --model path/to/MyPlant.mo --model-class MyPlant \
  --output outputs/MyPlant_linearized.mo
```

Then use `outputs/MyPlant_linearized.mo` in the validate/simulate/deploy
commands above.

Upload only when explicitly requested and after selecting the correct port:

```sh
python -m OpenModelicaFiles.modelica_workflow deploy \
  --model OpenModelicaFiles/esp32_demo.mo --mode virtual \
  --upload --port /dev/ttyUSB0
python -m OpenModelicaFiles.modelica_workflow monitor --port /dev/ttyUSB0
```

For generic ADC/PWM real-I/O mode, use `--mode io --adc-pin N --pwm-pin N`.
Outputs remain disabled unless both pins are specified and configuration
validates. Confirm board voltage limits, signal conditioning, pin mapping, and
external hardware safety independently.

The workflow supports linearized, explicit state-space SISO models with 1–16
states, not arbitrary Modelica DAEs or generated OpenModelica simulation C.
That C may depend on the OpenModelica runtime and is not standalone ESP32
firmware.

### Legacy desktop compilation

`compile-plant.py` and `define_plant_model.py` remain available for organizing
OpenModelica desktop compilation/linearization artifacts. They are separate
from the supported ESP32 workflow.

### Simulate in Python (no OpenModelica needed)

Run a closed-loop PID step response on the mass-spring-damper plant using SciPy and Matplotlib:

```sh
python dynamic_model.py
```

This loads the linearized state-space matrices from `linearized_model.mo` and plots the step response.

### Linearize a model

```sh
python -m OpenModelicaFiles.modelica_workflow linearize \
  --model path/to/MyPlant.mo \
  --model-class MyPlant \
  --output outputs/MyPlant_linearized.mo
```

This is the supported automated export. `define_plant_model.py` is a legacy
artifact organizer with a historical model filename; use the workflow above
for current OMEdit models.

## Architecture at a glance

```
Authoring Layer (.mo files)
        │
        ▼
OpenModelica linearize() → numeric A/B/C/D/x0
        │
        ▼
Python validation / RK4 simulation → portable C++ matrices
        │
        ▼
PlatformIO → ESP32 virtual-plant / configured ADC-PWM
        │
        ▼
JSON-lines telemetry → Python host
```

| Layer | What it does | Detail page |
|-------|-------------|-------------|
| Authoring | Graphical Modelica models in OMEdit | [BUILD.md](BUILD.md) |
| Linearization | OpenModelica `linearize()` exports numeric state space | [BUILD.md](BUILD.md) |
| Numeric | Validate/simulate supported SISO state space in Python | [BUILD.md](BUILD.md) |
| Hardware | Build and explicitly upload supported model firmware | [HIL.md](HIL.md) |
| Telemetry | JSON-lines state stream and virtual-input command | [TELEMETRY.md](TELEMETRY.md) |

## Common workflows

| Task | Command | Detail page |
|------|---------|-------------|
| Validate a deployable Modelica model | `python -m OpenModelicaFiles.modelica_workflow validate --model OpenModelicaFiles/esp32_demo.mo` | [BUILD.md](BUILD.md) |
| Linearize an OMEdit model | `python -m OpenModelicaFiles.modelica_workflow linearize --model path/to/Plant.mo --model-class Plant --output outputs/Plant_linearized.mo` | [BUILD.md](BUILD.md) |
| Simulate a model and save CSV | `python -m OpenModelicaFiles.modelica_workflow simulate --model OpenModelicaFiles/esp32_demo.mo` | [BUILD.md](BUILD.md) |
| Build ESP32 firmware without upload | `python -m OpenModelicaFiles.modelica_workflow deploy --model OpenModelicaFiles/esp32_demo.mo` | [BUILD.md](BUILD.md) |
| Flash firmware | Add `--upload --port /dev/ttyUSB0` to deploy command | [HIL.md](HIL.md) |
| Stream ESP32 telemetry | `python -m OpenModelicaFiles.modelica_workflow monitor --port /dev/ttyUSB0` | [TELEMETRY.md](TELEMETRY.md) |
| Compile desktop Modelica artifacts | `python OpenModelicaFiles/compile-plant.py` from its folder | [BUILD.md](BUILD.md) |
| Parse state-space matrices | `from modelica_parser import parse_linearized_model` | [modelica_parser.py](modelica_parser.py) |
| Simulate closed-loop PID | `python dynamic_model.py` | — |
| Model visually in OMEdit | Open `plant.mo` or create new model, run transient | [BUILD.md](BUILD.md) |

## Documentation

| Page | For |
|------|-----|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Full multi-tier architecture, layer responsibilities, known gaps |
| [BUILD.md](BUILD.md) | Compile/linearize workflows, OMEdit GUI guide, parameter modification, troubleshooting |
| [HIL.md](HIL.md) | ESP32 hardware-in-the-loop deployment, PlatformIO setup, real-time determinism |
| [TELEMETRY.md](TELEMETRY.md) | JSON-lines ESP32 telemetry and input-command protocol |

## For students & new contributors

1. **Pick a model to start with:** `plant.mo` is the simplest (first-order RC plant). `RCCircuit.mo` is a resistor-capacitor circuit. `linearized_model.mo` is a 4-state mass-spring-damper with PID.
2. **Use `modelica_workflow.py`** for the supported state-space → ESP32 path.
3. **Run a Python simulation script** to see state-space analysis without touching OpenModelica.
4. **When adding a new `.mo` model:** place it in `OpenModelicaFiles/`, add a compile script following `compile-plant.py`'s pattern, and update the table above.
5. **Generated build artifacts** (`plant_build/`, `lin_build/`) are gitignored — don't commit them.
6. **Simulation outputs** (`.csv`, `.png`) go in `outputs/` at the project root — also gitignored.

## Related project

This folder is part of [PyCircuits](../README.md) — an educational power-electronics and control-systems simulator.
