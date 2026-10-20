# Extension Ladder: from PyCircuits to a MATLAB/Simulink replacement

This document maps the modular "MATLAB replacement suite" architecture onto
PyCircuits' existing codebase. It is an opinionated design guide for 
iteratively extending the project without hard-forking the core.

---
## 1. The decoupled Frontend-Compiler-Backend architecture

The modern engineering stack is best understood as four layers with
explicit interfaces between them. PyCircuits is the **Layer 1** execution
core; the ladder below describes how to bolt on the other three.

| Layer | Responsibility | Open-source building blocks | PyCircuits role as bridge |
|---|---|---|---|
| **L1 – Data & analysis core** | Numerics, linear algebra, circuits simulation, control analysis | Python, numpy, scipy (optional) | `pycircuits_sim` is the always-available core; returns frozen dataclasses |
| **L2 – Modeling & authoring** | Text-based modeling, block diagrams, IDE experience | Modelica (.mo), Rumoca (parser+IR), OpenModelica, Julia ModelingToolkit | Consumes L1 results; a *proposed* `[modelica]` extra would load Rumoca |
| **L3 – Compile & execution** | IR lowering, codegen, simulation kernels | CasADi, JAX, Rust (no_std), C/C++, CoreIR | Template engine emits to any target; Rust kernel for real-time |
| **L4 – Hardware & deployment** | HIL, firmware, embedded deployment | PlatformIO, MicroPython, RTOS, MQTT, serial | Runs target code exported from L3; streams telemetry back to L1/L2 |

Key principle: **L1 results are the only language that crosses layer
boundaries**. A Modelica model (L2) calls `pycircuits_sim` (L1) via a
generated wrapper; a Rust kernel (L3) imports the same dataclasses;
a hardware runner (L4) streams device telemetry through the API (L3->L1).

## 2. Where Python fits today

Python is undisputed as the **glue + interactive research** layer:
- The entire L1 core is Python/numpy. SciPy is an optional `[control]` extra.
  Jupyter kernels, Streamlit workbenches, and the FastAPI layer all consume
  the core natively.
- SciPy provides signal processing, optimization, and special functions
  that complement PyCircuits' control-oriented numerics.
- Python's hardware ecosystem (pyserial, platformio-client, MQTT
  clients, USB-CDC drivers) is the reason L4 exists at all.

Python's weakness is raw solver speed for large systems (sparse DAES,
large-scale optimization). That is exactly why L3/Rust and L2/Julia
plugins exist.

## 3. Where Julia fits

Julia is the **interactive scripting + modelling + optimization** layer.

- **MATLAB scripting replacement**: Julia multiple dispatch and Julia
  syntax replace the `.m` prompt for interactive work and iterative
  exploration.
- **Symbolic-numeric modelling**: ModelingToolkit.jl lets users define
  DAEs with symbolic macros and compile them to native functions
  instantly, without leaving the language. This is an alternative to
  (or complement for) the Modelica/Rumoca front end.
- **The bridge**: Rumoca can generate code targets or bindings that load
  into Julia via CCall or shared libraries. A user can define a Modelica
  model, have Rumoca emit a Julia-callable library, and solve it with
  DifferentialEquations.jl — all from Julia, with Rust-compiled
  performance under the hood.

Julia beats Python where you need: raw solver speed, automatic
differentiation pipelines, and mathematical syntax clarity. Julia can
call Python libraries via PyCall.jl, so nothing is locked out of either
ecosystem; the choice is per-task.

## 4. Where Rust fits

Rust is the **hard infrastructure + compiler backend** layer.

- **Embedable simulation kernels**: Rust compiles to native machine
  code with no runtime, making it the right choice for ultra-low-latency
  real-time loops and HIL execution.
- **Code generation**: Rust templating engines can emit C, Rust, or
  WASM from the Solver IR, feeding the hardware deployment layer.
- **FFI**: A Rust library can expose PyCircuits results via a C ABI so
  Python, Julia (ccall), and C++ all consume the same objects without
  copying unnecessarily.

Rust does not replace Python's ecosystem; it makes the hot paths and the
compiler backend fast, safe, and portable.

## 5. Where Simulink/Xcos and Modelica fit

Simulink is the hardest MATLAB component to replace because of its
visual block-diagram modeling and code generation.

- **Rumoca route**: Parse `.mo` Modelica files with Rumoca built-in
  Language Server Protocol backend. The parsed AST -> IR -> DAE IR ->
  Solver IR pipeline mirrors what a Simulink block diagram compiles to.
  Write a Jinja-style template that maps the Solver IR to Python,
  Rust, C, or Julia syntax. This is Step B of the plan and is the
  most direct "block diagram -> code" path.
- **OpenModelica route**: OpenModelica provides a full Modelica
  compiler + simulation engine; it can act as a fallback when Rumoca
  toolchain is not installed. The `[modelica]` extra selects which.
- **Block diagram in Python**: PyCircuits already has SISO block algebra
  (series/parallel/feedback, `interconnect.py`). A visual block-diagram
  editor (React/JS or even a Streamlit UI with drag-and-drop) that
  emits the same JSON config format as `interconnect.py` would give a
  Simulink-like interface without leaving Python.

## 6. Where hardware deployment fits

The [control] extra gives you the plant models; the [api] extra gives
you the network; hardware is the final leg.

- **PlatformIO + Python automation**: PlatformIO compiles firmware
  for Arduino/ESP32 (aka. the target microcontroller). A Python script
  (the `HILRunner`) streams a test sequence to the device via serial,
  collects telemetry (ADC readings, encoder counts, motor current), and
  compares against `pycircuits_sim` simulation predictions in real
  time. MQTT or WebSocket can relay telemetry to the Streamlit/Jupyter
  UI.
- **MicroPython**: For simpler deployments, MicroPython on the
  microcontroller embeds the model evaluation directly on-device,
  removing the serial round-trip entirely.
- **RTOS**: A real-time OS (FreeRTOS, Zephyr, or bare-metal) sits
  between PlatformIO and the firmware logic, providing deterministic
  scheduling for control loops.

## 7. Decision matrix for toolchain choice

| Decision | Choose A | Choose B | Evidence |
|---|---|---|---|
| **Modeling language** | Modelica + Rumoca | Julia ModelingToolkit.jl | Rumoca fits the "text + version control" principle; MTK fits "pure Julia" workflows |
| **Numeric backend** | numpy/scipy | JAX (via L3) | numpy is always-available; JAX adds GPU/autodiff for large batches |
| **Compilation target** | CasADi (Python) | Rust (native) | CasADi is Python-friendly; Rust is faster for real-time |
| **IDE** | VS Code + LSP | Neovim + LSP | Both can host the Rumoca LSP; VS Code offers the richest debugging UI |
| **Hardware runner** | PlatformIO + serial | MicroPython + MQTT | PlatformIO = full embedded toolchain; MicroPython = smaller/portable |
| **Web UI** | Streamlit (in-repo) | React + FastAPI | Streamlit is faster to ship; React is more flexible for complex UIs |

The safest default: keep L1 (numpy/scipy) as the always-on core; make L2-L4
optional extras that degrade gracefully; cross-layer communication uses
the frozen dataclasses from L1 across a `pycircuits_sim.api` HTTP layer.

## 8. Risk assessment

**Technology risk** (high): Modelica/Modelica tooling (Rumoca, OpenModelica)
is maturing but not yet as plug-and-play as `scipy.signal`. A user who
installs `[modelica]` and tries to simulate an unfamiliar `.mo` file may
hit parser quirks. Mitigation: treat Rumoca/OpenModelica as optional
extras that degrade to a clear `ValueError` + install hint, exactly as
`[control]` and `[api]` are handled.

**Performance risk** (medium): Rust and JAX paths can be much faster than
numpy for large-scale or real-time scenarios, but they add build complexity
and FFI boundaries. Mitigation: run acceptance tests on all three paths;
instrument per-path speed; document which path to choose for which workload.

**Maintenance risk** (medium): PyCircuits must not be tightly coupled to any
single L2/L3/L4 tool. Mitigation: L1-only `pycircuits_sim/__init__.py`
production, with separation via explicit `__init__.py` in each optional
extra; all optional modules are guarded-imports-with-ValueError pattern.

**Ecosystem risk** (low): Python/numpy/scipy are extremely stable; the
risk is in the optional toolchain, not the core.

## 9. Phased extension implementation

| Phase | Scope | Key deliverables | Estimated effort |
|---|---|---|---|
| **E1 – Hardware bridge** | add `hardware/` subpackage: `HILRunner`, serial CLI, PlatformIO/flashing automation | `tests/test_hardware.py`; `pycircuits-sim hardware flash`; `HILRunner` class | medium |
| **E2 – Extension payloads** | add `[modelica]`, `[rust]`, `[jax]` extras (guarded imports + ValueError + install hint) | `optional_payloads.py`; docs/examples per extra | low-moderate |
| **E3 – Jupyter/binder** | publish L1 results as a Jupyter kernel / interactive binder; expose `pycircuits_sim.*` across notebooks | `pycircuits_jupyter/` wrapper; example notebooks | low-moderate |
| **E4 – Rust runtime** | port hot-path simulation to Rust (simulation kernels) with a C ABI; optional `[rust]` extra | `rust_runtime/` crate; `pycircuits_sim/rust/` module | high |
| **E5 – Modelica front-end** | add `.mo` import via Rumoca; block-diagram UI that emits `interconnect.py`-compatible JSON | `modelica/` package; template engine; VS Code/Neovim LSP extension | high |
| **E6 – Deployment** | CasADi/JAX -> C -> PlatformIO wiring; example firmware + HIL test | `deploy/` cookbook; firmware examples; `HILRunner` end-to-end test | high |

---

*See also: [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md),
[UNIFIED_ARCHITECTURE.md](UNIFIED_ARCHITECTURE.md),
[PORTING_MAP.md](PORTING_MAP.md),
[ROADMAP.md](ROADMAP.md).*
