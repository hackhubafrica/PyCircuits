# Architecture

Multi-tier architecture for the OpenModelica physical modeling layer.

## Overview

The suite replaces proprietary graphical block diagrams (Simulink) with Modelica's text-based `.mo` files as the foundational physical modeling and authoring frontend. Modelica defines physical systems, multi-domain components (electrical, mechanical, thermal), and governing differential-algebraic equations (DAEs).

## Layer stack

```text
Authoring Layer (.mo Modelica Files)
        │
        ▼
Rumoca Parser & Compiler Core
        │
        ▼
Flattened DAE IR
        │
        ▼
C Code Generation (via Jinja templates)
        │
        ▼
Compiled Native Shared Library (.so / .dll)
        │
        ▼
ZERO-COPY DATA BRIDGE (Apache Arrow / FFI)
        │
        ▼
Shared In-Memory Buffer Pool
        ├───────────────┬───────────────┐
        ▼               ▼               ▼
Python/Julia Layer   Event & Zero-Crossing   Hardware & Deployment
(NumPy, SciPy,       Synchronization Engine    Layer
DiffEq.jl)           (µs-accurate root-      (Microcontrollers,
reads shared         finding for           HIL loops & PWM
buffers instantly)   discrete switches)      PlatformIO/ESP32)
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

| Gap | Impact | Recommended fix |
|-----|--------|-----------------|
| Real-time determinism / OS scheduling jitter | Millisecond-scale latency spikes destabilize high-frequency control loops (e.g., 20 kHz inverter = 50 µs period) | Strict hardware boundary: MCU handles hard real-time (PWM, fast PID, ADC); host handles soft real-time (tuning, logging, visualization) |
| Steady-state initialization / homotopy solvers | Complex circuits fail to converge at $t=0$ due to algebraic loops and stiff systems | Automatic differentiation or analytical Jacobian generation in Rumoca |
| Unified event handling across language boundaries | Discrete state transitions drift during numerical integration | Standardized event-root finder and zero-crossing locator |
| Unified interactive workbench | Fragmented tool windows (Neovim, VS Code, Jupyter, PyQt/Streamlit) kill debugging productivity | Cohesive workspace protocol (LSP-like for scientific debugging) |

## Recommended next focus

Prioritize the core compilation and execution loop first: solidify how Rust-lowered IR targets either a pure Julia execution block or a standalone C/Python extension module. Once data flows seamlessly from authoring layer down to hardware telemetry via PlatformIO, the rest of the ecosystem snaps into place naturally.