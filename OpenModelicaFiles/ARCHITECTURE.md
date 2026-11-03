# Architecture

Multi-tier architecture for the OpenModelica physical modeling layer.

> **Implementation status:** this diagram describes the long-term target.
> Today, OMEdit is the graphical authoring tool and
> `modelica_workflow.py` deploys numeric, linearized SISO state-space models
> through PlatformIO. A Rumoca compiler, shared-memory/Arrow bridge,
> cross-runtime event engine, and general Modelica-to-firmware compiler are
> not implemented.

## Overview

The suite replaces proprietary graphical block diagrams (Simulink) with Modelica's text-based `.mo` files as the foundational physical modeling and authoring frontend. Modelica defines physical systems, multi-domain components (electrical, mechanical, thermal), and governing differential-algebraic equations (DAEs).

## Implemented Modelica-to-ESP32 path

```text
OMEdit graphical model (.mo)
        │
        ▼
OpenModelica linearize()
        │
        ▼
linearized .mo (A, B, C, D, x0)
        │
        ▼
Python validation + RK4 simulation
        │
        ▼
portable state-space C++ header
        │
        ▼
PlatformIO / ESP32 (virtual plant or configured ADC/PWM)
        │
        ▼
JSON-lines telemetry + host monitor
```

The implemented path is limited to 1–16 state, continuous-time, numeric SISO
linearizations. It carries the linearizer's initial state `x0` into both host
simulation and firmware. See [BUILD.md](BUILD.md) for the automated
`linearize` → validate → simulate/build workflow.

## Long-term target architecture

The following layers remain planned, not current implementation:

```text
Modelica/Julia frontends
        │
Rumoca / shared solver IR
        │
C / Rust / Julia execution backends
        │
FFI or shared-memory bridge
        │
cross-runtime hybrid event handling
        │
hardware deployment and telemetry
```

## Layer responsibilities

### 1. Authoring Layer (.mo Modelica Files)

Human- and LLM-friendly source. Modelica's text-based `.mo` files define physical systems without relying on a proprietary graphical format.

### 2. Rumoca Parser & Compiler Core

Parses Modelica text into a flattened Intermediate Representation (IR) before emitting target code. Extracts DAEs and lowers them for compilation.

### 3. Flattened DAE IR

A self-describing intermediate form of the differential-algebraic equations. This is the boundary where Jacobian generation and symbolic differentiation can be injected.

### 4. C Code Generation

Generates native C code from the flattened IR using Jinja templates. Output is a compiled shared library (`.so` / `.dll`).

### 5. Zero-Copy Data Bridge

A unified in-memory data layout standard (Apache Arrow or raw C-compatible memory buffers via FFI/shared libraries). Without zero-copy sharing between Rust, Julia, and Python, real-time HIL streaming will choke on IPC latency.

**Practical implementation:**
- Use the Apache Arrow C Data Interface, or
- Define contiguous memory structs in Rust (`#[repr(C)]`) exposed to Python via `ctypes` or `PyO3` as NumPy arrays (zero-copy)

### 6. Shared In-Memory Buffer Pool

Enables zero-copy streaming of massive arrays and matrices between language boundaries.

### 7. Python / Julia Numeric Layer

NumPy, SciPy, and DifferentialEquations.jl read shared buffers instantly for analysis, control design, and visualization.

### 8. Unified Event & Zero-Crossing Synchronization Engine

Microsecond-accurate root-finding for discrete switches. When a variable crosses zero (e.g., $v_{\text{switch}} = 0$), both the execution core and the controller pause at that exact timestamp, update discrete states, and resume integration synchronously.

**Practical implementation:** Use root-finding algorithms (e.g., Brent's method adapted for DAE discontinuities).

### 9. Hardware & Deployment Layer

Microcontrollers executing HIL loops and PWM switching, flashed via PlatformIO. The microcontroller handles hard real-time execution loops; the host handles soft real-time tasks (parameter tuning, logging, telemetry visualization).

## Known architectural gaps

| Gap | Impact | Planned stage and acceptance |
|-----|--------|------------------------------|
| Real-time determinism / OS scheduling jitter | The current Arduino `loop()` plus ADC, PWM, and telemetry is not a hard-real-time guarantee; jitter can break a 20 kHz / 50 µs deadline | **Stage 3: hardware bridge hardening.** Keep fast PWM/control on the MCU and host work soft real-time; later move the integration/control tick to an ESP32 hardware timer or pinned high-priority task, keep serial logging off the critical path, and measure worst-case execution time/jitter against an explicit deadline before claiming a rate. |
| Steady-state initialization / homotopy solvers | Nonlinear DAEs and algebraic loops may fail to initialize; the current model uses OpenModelica `linearize()` and carries its `x0`, but does not implement a homotopy solver | **Stage 4: general Modelica frontend/runtime.** First surface OpenModelica initialization diagnostics and preserve its operating point; then support initialization equations/homotopy or a proven backend solver. Analytical Jacobians/automatic differentiation are an optimization after correctness tests for representative stiff/algebraic models. |
| Unified event handling across language boundaries | Different solvers can locate zero crossings at different times and drift on hybrid systems | **Stages 4–5: shared solver/event runtime.** Define event surfaces, root tolerances, event priority, state reinitialization, and communication-step semantics in the IR; validate with cross-backend switching-system conformance traces before enabling multi-runtime HIL. |
| Unified interactive workbench | Separate OMEdit, Streamlit, terminal, and telemetry windows fragment the workflow | **Stage 2 and Stage 7.** Build a general plant/controller graph editor against the existing UI/core first; later add LSP/Jupyter integration and a shared run/telemetry workspace. |

## Recommended next focus

Immediate focus is automated OpenModelica linearization export and verification
of the supported ESP32 workflow. The next hardware stage is measured
determinism—not claiming hard real time from the current Arduino loop. General
DAE initialization and cross-runtime event synchronization belong to the
later Modelica/runtime stages, after a shared solver contract exists.