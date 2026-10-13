# Project Analysis: PyCircuits and ControlKit

This document is a side-by-side analysis of the two projects in this repository.
It was produced by a full traversal of both codebases before any merge or
refactoring work, and it is the factual basis for
[UNIFIED_ARCHITECTURE.md](UNIFIED_ARCHITECTURE.md) and
[PORTING_MAP.md](PORTING_MAP.md).

Neither project is a validated design tool. Both are educational simulators.

## 1. Origins and intent

| | PyCircuits | ControlKit |
|---|---|---|
| Location | repository root (`pycircuits_sim/`) | `ControlKit/` (nested, its own git repo) |
| Git history | 4 commits: "Engine & Solver Foundation" ×2 → Streamlit UI → schematic GUI | 2 commits: "First release version 1.0.0" → "docs: rename project to ControlKit" |
| Stated purpose | Educational **power-electronics and control-systems** simulator: buck converters, rectifier netlists, sampled PID loops, continuous/discrete state-space plants, transfer functions, interactive waveform analysis | SISO **control-systems workspace**: `python-control`/NumPy/SciPy behind FastAPI, Plotly.js dashboard for time response, stability, Bode, Nyquist, root locus, and PID |
| Internal name | PyCircuits Workbench | "ControlLens" (FastAPI `title`, localStorage key `controllens.plant`, frontend package `controllens-ui`) |
| Language stack | Pure Python (numpy, matplotlib, plotly, streamlit) | Python backend (fastapi, control, scipy, pydantic) + React/TypeScript/Vite frontend |

**PyCircuits** grew outward from a physics core: first the buck-converter
solver, then an MNA circuit solver, then a Streamlit UI and a schematic editor.
Its center of gravity is *circuits and time-domain simulation*.

**ControlKit** grew from control theory: a plant in, analysis and controller
design out, over HTTP. Its center of gravity is *linear-systems analysis and
controller design*.

## 2. PyCircuits architecture

Package `pycircuits_sim` (3,563 lines across 13 modules), packaged via
`pyproject.toml` (name `pycircuits-sim`, console script `pycircuits-sim`,
requires Python >= 3.10), tested with `unittest` (8 test files under `tests/`).

### 2.1 Simulation engines

| Module | Lines | Responsibility |
|---|---:|---|
| `buck.py` | 136 | Ideal buck power stage. `BuckConfig` (frozen dataclass, full validation in `__post_init__`), `BuckPlant` advances one fixed backward-Euler step at a time, PWM sampling at step start, diode prevents negative inductor current (DCM clamping). `simulate_buck` returns `SimulationResult(time, inductor_current, output_voltage, switch_on)` |
| `closed_loop.py` | 188 | Sampled PID regulating the buck. `PIDConfig` (duty limits), `ReferenceStep`, `ClosedLoopConfig` enforces `sample_time` = integer multiple of plant `time_step`. Derivative acts on measurement (no setpoint kick); conditional integral anti-windup at duty limits; duty held between controller updates |
| `mna.py` | 519 | Generic transient modified nodal analysis. Components: resistor, capacitor, inductor, DC/sine voltage and current sources, Shockley diode, controlled switch (`ron`/`roff`, `control_points` + `threshold`). Fixed-step backward Euler; damped Newton-Raphson per timestep for diodes (`newton_tolerance`, `newton_max_iterations`, `newton_damping`); `gmin` conductance to ground (default 1e-12 S); exponent clamp on the diode exponential. Ground aliases: `0`, `gnd`, `ground` |
| `linear_systems.py` | 681 | `StateSpaceModel` (continuous, MIMO) and `DiscreteStateSpaceModel` (with `sample_time`); `transfer_function_to_state_space` (proper SISO, descending powers, controllable canonical); `simulate_state_space` / `simulate_discrete_state_space` (open loop, MIMO, arbitrary input callables); `simulate_state_space_pid` / `simulate_discrete_state_space_pid` (sampled SISO PID, `D=0` required, derivative-on-measurement, conditional anti-windup, output saturation); `frequency_response` (per-input-output-channel complex response), `discrete_frequency_response`, `logarithmic_frequency_grid` |

### 2.2 Supporting layers

| Module | Lines | Responsibility |
|---|---:|---|
| `sweep.py` | 53 | One-parameter sweeps of the buck config: `inductance`, `capacitance`, `load_resistance`, `duty_cycle`; requires at least 2 unique finite values |
| `metrics.py` | 102 | `measure_sweep`: steady-state window (final fraction of samples), peak overshoot %, settling time in a configurable band, peak-to-peak V/A ripple |
| `io.py` | 254 | JSON loaders (`load_config`, `load_sweep_config`, `load_closed_loop_config`, `load_mna_config_file`) and CSV writers for every result type |
| `plotting.py` | 272 | Matplotlib: aligned panels for waveforms, closed-loop traces, sweeps, MNA node voltages |
| `cli.py` | 106 | `argparse` subcommands: `run`, `plot`, `sweep`, `closed-loop`, `mna` |
| `schematic.py` | 203 | Canvas model to MNA netlist: union-find over terminal ports, ground requirement, short detection, node naming (`N1...`); `schematic_document` embeds `editor` layout metadata; `editor_from_document` auto-layouts plain MNA netlists |
| `schematic_ui.py` | 376 | Streamlit schematic editor (palette, drag, wire drawing, properties panel, validate/save) |
| `ui.py` | 606 | Streamlit workbench; sidebar mode selector with 6 modes: Closed-loop buck, Open-loop buck, Half-wave rectifier, Bridge rectifier, Linear control plant, Schematic editor. Plotly charts, CSV downloads, custom CSS theme |

### 2.3 Tests and examples

Tests: `tests/` contains `test_buck`, `test_closed_loop`,
`test_linear_systems`, `test_metrics`, `test_mna`, `test_plotting`,
`test_schematic`, `test_sweep` — all `unittest`, run with
`python -m unittest discover -s tests`.

Examples: `examples/` contains `buck.json`, `closed_loop_buck.json`,
`mna_switched_rc.json`, `half_wave_rectifier.json`, `bridge_rectifier.json`,
`inductance_sweep.json` / `inductance_sweep_demo.json`,
`state_space_first_order.json`, `transfer_function_second_order.json`,
`discrete_first_order.json`.

## 3. ControlKit architecture

Two-tier app: FastAPI backend (`ControlKit/backend`, app title **ControlLens**
v0.1.0) and React frontend (`ControlKit/frontend`, package `controllens-ui`).
Backend dependencies: `fastapi`, `uvicorn`, `control`, `numpy`, `scipy`,
`pydantic`, `pytest`, `httpx`. Tests: `backend/tests/test_engine.py`
(336 lines, `pytest`, includes FastAPI `TestClient` API tests).

### 3.1 Engine modules (`ControlKit/backend/app/engine/`)

| Module | Lines | Responsibility |
|---|---:|---|
| `plant.py` | 115 | `build_system(spec)` returns a `ct.StateSpace` or `ct.TransferFunction` from a `PlantSpec` (tf or ss form) with thorough validation; **SISO-only** check; `to_tf`/`to_ss` conversions; `dc_gain`; `normalize_payload` (num, den, A-D, poles, zeros, dc_gain, order) |
| `time_domain.py` | 100 | `simulate(sys, kind)` for `step`, `impulse`, `custom`; custom inputs resampled onto a uniform grid (python-control >= 0.10 requirement); step metrics via `ct.step_info` (rise time, settling time, overshoot %, peak, peak time, steady state) with a manual fallback; downsampling to at most 1800 points |
| `stability.py` | 67 | `analyze_stability`: BIBO verdict (all poles in the open left half-plane; explicit handling of RHP poles, repeated j-omega poles, integrators) **and** Lyapunov asymptotic stability (eigenvalues of A); both with human-readable reason strings; poles/zeros/eigenvalues as `{re, im}` dicts |
| `frequency.py` | 84 | `bode`: magnitude dB and unwrapped phase on a log grid (1e-3 to 1e3 rad/s) plus **gain margin, phase margin, gain/phase crossover frequencies** via `ct.margin`; `nyquist`: real/imag trace; both downsampled |
| `root_locus.py` | 61 | Locus branches vs gain: `ct.root_locus_map` with `ct.root_locus` fallback, gain grid `[0, logspace(-3, 3)]`, at most 400 points per branch |
| `pid.py` | 251 | `pid_tf(Kp, Ki, Kd, N)`: parallel PID with optional derivative filter `N`; `closed_loop_payload` (controller and closed-loop TFs, plant vs closed-loop step, loop vs closed-loop Bode); **`ziegler_nichols`**: ultimate-gain method (Ku = gain margin, Pu = 2*pi/wpc, P/PI/PID table variants) with **FOPDT reaction-curve fallback** (K, tau, theta fit from the unit-step response; Kp = 1.2*tau/(K*theta), Ti = 2*theta, Td = 0.5*theta); **`pole_placement`**: controllability check, `ct.place`, PID/PD coefficient matching for 2nd-order plants |
| `state_feedback.py` | 136 | `ackermann` (`ct.acker`, conjugate-symmetric pole check, controllability rank) and `lqr` (`ct.lqr`, diagonal Q, scalar R; returns K, S); both produce an open- vs closed-loop step comparison with **N-bar reference pre-gain** and a closed-loop pole report |
| `interconnect.py` | 109 | Block algebra: ordered forward chain (`ct.series`), optional parallel chain (`ct.parallel`), feedback as `none`/`unity`/block chain (`ct.feedback`, negative); block kinds `tf`/`ss`/`pid`/`gain`; at most 6 blocks, composite order at most 20; returns a full analysis payload plus the composite TF |
| `diagram/` | 122 | **Incomplete stub**: `model.py` (Pydantic `DiagramModel` with wires/ports) and `blocks.py` (base `Block` class only, `NotImplementedError` outputs). No solver, not referenced by the routers — dead scaffolding for a free-form block canvas |
| `util.py` | 58 | `ControlError` (readable errors), `fnum` (finite-or-None), `cplx`/`cplx_list`, `as_float_list`, `downsample` (at most 1800), `matrix_to_lists`, `tf_coeffs` |

### 3.2 API (`ControlKit/backend/app/`)

`schemas.py` (88 lines): `PlantSpec`, `SimRequest`, `AnalyzeRequest`,
`PidGains`, `PidClosedLoopRequest`, `PidTuneRequest`, `AckermannRequest`,
`LqrRequest`, `BlockSpec`, `InterconnectRequest`, `ComplexNumber`.

`routers/analyze.py` (114 lines): `POST /api/plant/normalize`,
`/api/simulate`, `/api/stability`, `/api/bode`, `/api/nyquist`,
`/api/root-locus`, `/api/analyze` (everything at once),
`/api/pid/closed-loop`, `/api/pid/tune`.
`routers/design.py` (26 lines): `POST /api/sf/ackermann`, `/api/sf/lqr`,
`/api/interconnect`.
`main.py`: CORS allow-all, `GET /health`.
Errors: `ControlError` maps to HTTP 400 with a readable `detail`.

### 3.3 Frontend (`ControlKit/frontend/src/`, 1,447 lines of TS/TSX)

`App.tsx` (1,184 lines): tabs `step | impulse | custom | bode | nyquist |
rlocus | sf | interconnect`; example plants (2nd-order, DC motor, inverted
pendulum, 3rd-order); matrix/pole/CSV parsers; localStorage persistence of the
working plant. `PlotlyChart.tsx` renders Plotly.js. `api.ts` holds typed fetch
wrappers. `types.ts` mirrors the API payloads. `vite.config.ts` proxies
`/api` to port 8000.

## 4. Feature gap matrix

### 4.1 Present in ControlKit, absent from PyCircuits

| # | Feature | ControlKit implementation |
|---|---|---|
| 1 | Formal stability analysis | `stability.py` — BIBO + Lyapunov verdicts with reasons |
| 2 | Bode gain/phase margins and crossovers | `frequency.py` via `ct.margin` (PyCircuits has magnitude/phase only) |
| 3 | Nyquist plot | `frequency.py` |
| 4 | Root locus | `root_locus.py` |
| 5 | PID auto-tuning | `pid.py` — Ziegler–Nichols (ultimate + FOPDT fallback), pole placement with PID/PD matching |
| 6 | State-feedback design | `state_feedback.py` — Ackermann, LQR, N-bar pre-gain, open/closed comparison |
| 7 | Block interconnection algebra | `interconnect.py` — series/parallel/feedback, at most 6 blocks |
| 8 | Impulse and custom-input responses | `time_domain.py` |
| 9 | Step-response metrics | `time_domain.py` — rise time, overshoot %, settling time, peak via `ct.step_info` |
| 10 | Plant normalization | `plant.py` — TF-to-SS, poles, zeros, DC gain, order in one payload |
| 11 | Headless HTTP API | FastAPI routers + Pydantic schemas with clean error mapping |
| 12 | Rich example plants | DC motor, inverted pendulum, and others in `App.tsx` |

### 4.2 Present in PyCircuits, absent from ControlKit

| # | Feature | PyCircuits implementation |
|---|---|---|
| 1 | Power-electronics plant | `buck.py` — PWM switching, ideal diode, DCM clamping |
| 2 | Sampled PID on a switching stage | `closed_loop.py` — duty saturation, conditional anti-windup |
| 3 | Generic nonlinear circuit solver | `mna.py` — Newton-Raphson diodes, controlled switches, sources |
| 4 | Visual schematic editor | `schematic.py` + `schematic_ui.py` → validated netlist |
| 5 | Discrete-time plants and discrete PID | `linear_systems.py` |
| 6 | MIMO open-loop simulation | `linear_systems.py` (ControlKit is SISO-only by design) |
| 7 | Parameter sweeps and ripple metrics | `sweep.py`, `metrics.py` |
| 8 | CLI | `cli.py` — 5 subcommands |
| 9 | CSV/matplotlib export pipeline | `io.py`, `plotting.py` |
| 10 | Packaging and `unittest` suite | `pyproject.toml`, 8 test modules |
| 11 | Single-language UI | Streamlit (`ui.py`) with themed CSS |
| 12 | Dependency-light engine | numpy only for all solvers — no scipy/python-control |

### 4.3 Overlap (implemented twice, differently)

| Capability | PyCircuits | ControlKit |
|---|---|---|
| Continuous SS/TF plants | `linear_systems.py`, hand-rolled controllable-canonical TF-to-SS | `plant.py` via `python-control` |
| Step response | backward Euler `simulate_state_space` | `ct.step_response` |
| PID feedback | sampled discrete implementation on a fixed step | continuous-time PID transfer function in unity feedback |
| Bode magnitude/phase | `frequency_response` (Hz, per channel) | `ct.frequency_response` (rad/s) plus margins |
| Plotting | Plotly in the Streamlit UI + matplotlib for the CLI | Plotly.js in the React SPA |

Key modeling difference: the PyCircuits PID is a **sampled-data controller**
(held output, integer sample/step ratio, saturation, anti-windup) that models
what firmware does; the ControlKit PID is a **continuous transfer function**
(`(Kd*s^2 + Kp*s + Ki)/s` with an optional derivative filter) used for
classical loop analysis. They answer different questions, and both are worth
keeping after the merge.

## 5. Engineering comparison

| Dimension | PyCircuits | ControlKit |
|---|---|---|
| Numerics | pure numpy, fixed-step backward Euler, damped Newton | `python-control` + scipy (adaptive solvers, `ct.margin`, `ct.lqr`, `ct.acker`, `ct.place`) |
| Dependencies | matplotlib, numpy, plotly, streamlit, streamlit-flow-component | fastapi, uvicorn, control, scipy, pydantic (+ React/Vite/TypeScript toolchain) |
| Data model | frozen dataclasses, validation in `__post_init__` | Pydantic models (request layer) + dict payloads (engine layer) |
| Errors | `ValueError` with readable messages | `ControlError` mapped to HTTP 400 with readable detail |
| Interfaces | CLI + Streamlit UI | REST API + React SPA |
| Tests | `unittest`, 8 modules, numerical assertions | `pytest`, 336 lines including API tests |
| MIMO | yes (open loop) | rejected at `build_system` |
| Discrete time | yes | no |
| Payload shaping | native Python types end to end | floats-or-`None` JSON-safe lists (`fnum`, `downsample` to 1800 points) |

## 6. Strengths and weaknesses

**PyCircuits strengths:** cohesive engineering (packaging, CLI, tests, UI,
examples); validated frozen configs; simulators that model real
implementation concerns (sampling, saturation, anti-windup, DCM); the
netlist/schematic pipeline; a dependency-light engine.

**PyCircuits weaknesses:** no classical-analysis tooling (margins, Nyquist,
root locus, stability verdicts); no controller tuning methods; no plant
normalization report; Bode output lacks margin/crossover markers; the UI has
no analysis tabs.

**ControlKit strengths:** a complete classical control toolbox; a well-factored
engine/service split; strong input validation; readable error messages; API
tests; compact readable engine code.

**ControlKit weaknesses:** SISO-only; no discrete time; no circuit/power
domain; requires a Node toolchain and a running server for the UI; hard
dependency on scipy/python-control; `diagram/` is dead scaffolding; a nested
git repo isolating it from the main history; a dict-payload style inconsistent
with the rest of PyCircuits' typed results.

## 7. Conclusion

The projects are complementary rather than competitive: PyCircuits owns
*time-domain circuit and plant simulation* while ControlKit owns *linear
control analysis and design*. The merge strategy (detail in
[UNIFIED_ARCHITECTURE.md](UNIFIED_ARCHITECTURE.md)) is to keep PyCircuits as
the single project and port ControlKit's analysis and design capabilities into
it as new engine modules — under a **hybrid dependency policy**: a pure-numpy
core that is always available, with optional `python-control`/`scipy` fast
paths for heavy numerics (LQR, dense root locus) when those libraries are
installed.




