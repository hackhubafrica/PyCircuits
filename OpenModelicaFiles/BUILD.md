# Build Guide

Compile and linearize Modelica models, organize build artifacts, and deploy to PlatformIO.

## Compile a Modelica plant (`compile-plant.py`)

`compile-plant.py` loads a `.mo` file via OpenModelica, builds the model, moves generated C/headers into `plant_build/`, and syncs core files to the PlatformIO `src/` directory.

```python
from compile_plant import compile_and_organize

compile_and_organize(
    mo_file="plant.mo",
    model_name="Plant",
    build_dir="plant_build",
    pio_src_dir="PlantHILProject/src"
)
```

Run from the `OpenModelicaFiles/` directory:

```sh
python compile-plant.py
```

### What it does

1. Loads `plant.mo` via `OMCSessionLocal`
2. Builds the `Plant` model with `buildModel(Plant)`
3. Creates `plant_build/` if it doesn't exist
4. Moves generated `Plant*.c`, `Plant*.h`, makefiles, and JSON records into `plant_build/`
5. Copies `Plant.h` and `Plant.c` into `PlantHILProject/src/` for PlatformIO

## Linearize a model (`define_plant_model.py`)

`define_plant_model.py` linearizes a Modelica model and organizes artifacts into `lin_build/`.

```sh
python define_plant_model.py
```

### What it does

1. Loads `MassSpringDamperPlant.mo` via `OMCSessionLocal`
2. Runs `linearize(MassSpringDamperPlant)`
3. Creates `lin_build/` if it doesn't exist
4. Moves generated linearization artifacts (C files, headers, matrices, `.mat`, `.json`, `.log`, makefiles) into `lin_build/`
5. Copies core linearization C/header files into `PlantHILProject/src/`

## OMEdit GUI workflow

To model the Mass-Spring-Damper system graphically in OMEdit:

1. **Create a new model**: File > New > Model, name it `MassSpringDamperPlant`, Diagram View
2. **Drag components** from the Modelica Standard Library:
   - Force Input: `Modelica > Mechanics > Translational > Sources > Force`
   - Mass: `Modelica > Mechanics > Translational > Components > Mass`
   - Spring: `Modelica > Mechanics > Translational > Components > Spring`
   - Damper: `Modelica > Mechanics > Translational > Components > Damper`
   - Fixed Reference Ground: `Modelica > Mechanics > Translational > Components > Fixed`
   - Real Input Signal: `Modelica > Blocks > Sources > Step`
3. **Connect translational flanges**: forceSource → mass → spring/damper → fixed ground
4. **Run transient simulation** in OMEdit to verify response
5. **Re-run** `python compile-plant.py` and your Python analysis script to verify SciPy step response matches OMEdit

## Modifying parameters

### Method A: Via OMEdit GUI (recommended for visual verification)

1. Double-click a component (e.g., step height or mass) in OMEdit and change the value
2. Run a transient simulation to see the new response curve
3. Re-run `python compile-plant.py` and your Python script
4. Verify Matplotlib plot matches OMEdit simulation window

### Method B: Programmatically in Python

Override parameters directly in your NumPy script before running `signal.step()`:

```python
B_modified = B * 2.0  # Scale step input force magnitude
system_custom = signal.StateSpace(A, B_modified, C, D)
t, y = signal.step(system_custom)
```

Customize simulation duration and time steps:

```python
stop_time = 5.0
num_points = 1000
t_custom = np.linspace(0, stop_time, num_points)
system = signal.StateSpace(A, B, C, D)
t, y = signal.step(system, T=t_custom)
```

## Build artifacts

| Directory | Contents |
|-----------|----------|
| `plant_build/` | Generated C/headers/objects from `buildModel(Plant)` |
| `lin_build/` | Generated linearization artifacts (C, headers, matrices, `.mat`, `.json`, `.log`) |
| `PlantHILProject/src/` | Synced `Plant.h` / `Plant.c` for ESP32 firmware |

## Troubleshooting

**`TypeError: 'module' object is not callable`**

`OMCSession` is a module/class inside `OMPython`, not a directly callable function. Use `OMCSessionLocal`:

```python
from OMPython import OMCSessionLocal
omc = OMCSessionLocal()
omc.sendExpression('loadFile("RCCircuit.mo")')
result = omc.sendExpression("buildModel(RCCircuit)")
```

**System is structurally singular**

Mixing standard components from the Modelica Standard Library without a Ground component or proper connections causes this. Every electrical circuit needs a ground reference; every mechanical system needs a fixed reference.

**LoadFile: file does not exist**

Ensure the `.mo` file is in the working directory or provide an absolute path. OpenModelica resolves relative paths from the current working directory, not the script location.