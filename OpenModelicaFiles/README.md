# OpenModelicaFiles

Physical modeling and hardware-in-the-loop (HIL) deployment layer for PyCircuits. This folder contains Modelica source files (`.mo`), OpenModelica compiler driver scripts, PlatformIO ESP32 firmware, and build artifacts.

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
| `PlantHILProject/` | PlatformIO ESP32 firmware project for HIL deployment |
| `plant_build/` | Generated C/headers/objects from OpenModelica compilation |
| `lin_build/` | Generated linearization artifacts |
| `venv/` | Isolated Python environment with OMPython |

## Quick start

### Prerequisites

- [OpenModelica](https://openmodelica.org/) installed with `omc` on PATH
- Python 3.10+
- `pip install OMPython` (included in `OpenModelicaFiles/venv/`)

### Compile a Modelica plant

```sh
cd OpenModelicaFiles
source venv/bin/activate
python compile-plant.py
```

This loads `plant.mo`, builds the `Plant` model with OpenModelica, moves generated C/headers into `plant_build/`, and copies `Plant.h`/`Plant.c` into `PlantHILProject/src/`.

### Linearize a model

```sh
python define_plant_model.py
```

This linearizes `MassSpringDamperPlant` and organizes artifacts into `lin_build/`.

### Simulate in Python (no OpenModelica needed)

```sh
python dynamic_model.py
```

Runs a closed-loop PID step response on a mass-spring-damper plant using SciPy and Matplotlib.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Multi-tier architecture: Modelica → Rumoca IR → C → shared memory → Python/Julia → PlatformIO
- [BUILD.md](BUILD.md) — Compile and linearize workflows, OMEdit GUI guide
- [HIL.md](HIL.md) — ESP32 hardware-in-the-loop deployment and PlatformIO setup
- [TELEMETRY.md](TELEMETRY.md) — Binary telemetry packet format + Python/Go serial parsers

## Related project

This folder is part of [PyCircuits](../README.md) — an educational power-electronics and control-systems simulator.
