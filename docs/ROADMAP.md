# PyCircuits — Roadmap & Extension Strategy

This document records the implemented five-phase roadmap and sketches the
extension strategy for scaling PyCircuits into a broad, open-source
"MATLAB/Simulink replacement" engineering stack.

---
## 1. Completed phases (this project)

| Phase | Content | Acceptance (unittest) |
|---|---|---|
| **1. Analysis layer** | `optional.py`, `analysis/` (`plant`, `stability`, `metrics`, `margins`, `nyquist`, `root_locus`); tests | poles of 1/(s^2+s+1) = -0.5 ± j·√3/2; step overshoot ≈ 16.3% for ζ=0.5; integrator not BIBO-stable; known-loop margins match; locus branches start at open-loop poles |
| **2. Design layer** | `design/` (`tuning`, `state_feedback`); tests | Ziegler–Nichols Ku/Pu table match; FOPDT fallback; Ackermann `eig(A-BK)` check; N̄ steady-state = 1; LQR smoke (skipped without `[control]` extra) |
| **3. Interconnect** | `interconnect.py`; tests | series/parallel/feedback identities; composite order limit; equals hand-computed rational function |
| **4. Interfaces + docs** | `cli.py` subcommands (`analyze`, `tune`, `sf`, `interconnect`), `ui.py` mode, `plotting.py` charts, README, examples | end-to-end CLI + UI mode + README; example JSONs |
| **5. Optional API** | `api.py` FastAPI wrapper reusing ControlKit's contract; tests | API smoke tests; final git cleanup |

> **Status:** all five phases are implemented and verified end-to-end
> (148 unittest cases collected; 2 skipped in this environment because the
> optional `python-control` and `scipy` dependencies are not installed). The
> `[control]` and `[api]` extras exist in `pyproject.toml`. The `ControlKit/`
> reference archive has been removed (it was recoverable from commit
> `d908402`); `docs/PORTING_MAP.md` retains the full porting provenance.

Each phase was independently shippable: engine + tests first, CLI second, UI
third. Acceptance = existing suite still green + new tests green
(`python -m unittest discover -s tests`) + demo commands run.
## 2. Where the project stands

PyCircuits is now a:

- **Core engine** — pure-numpy linear systems, MNA circuit solver, buck
  switching converter model, Bode/margin/Nyquist/root-locus/stability
  analysis, step metrics, Ziegler–Nichols + pole-placement controller
  design, block interconnections.
- **Interfaces** — CLIs (`pycircuits-sim`), a Streamlit workbench with an
  analysis/design UI, a FastAPI HTTP API (optional extra) reusing
  ControlKit's contract.
- **Docs** — `PROJECT_ANALYSIS.md`, `UNIFIED_ARCHITECTURE.md`,
  `PORTING_MAP.md`, `scientific.md`, `README.md`, and this file.

The largest architectural decision that reached its conclusion in Phase 5 is
the **hybrid dependency policy**: every feature has a pure-numpy core that is
always available, and `python-control` / `scipy` are an *optional extra*
(`"pycircuits-sim[control]"`) that unlocks faster/robust implementations
behind guarded imports. This design is what makes the extension path below
possible without hard-forking the core.
## 3. The grand vision: a MATLAB/Simulink replacement suite

MATLAB's value is not one program — it is the *ecosystem*: numeric computing,
model-based design (Simulink), domain toolboxes (Control System, Signal
Processing), and hardware-in-the-loop tooling. No single open-source binary
replaces that out of the box. The correct target is therefore not a clone but
a **modular, composable stack** whose pieces are individually open-source and
whose integration layer is **your PyCircuits project**.

The vision is summarised in the layer diagram below. PyCircuits occupies the
*pyramid base* (the always-available numeric and analysis core); the higher
layers are composable add-ons chosen by the user's workflow.

```
   Layer 4 — Hardware & Deployment   PlatformIO / MicroPython / RTOS / MQTT
                                     (embedded firmware loops, HIL test rigs)
   Layer 3 — Execution backends      Rust (real-time loops) | Python/CasADi/JAX (opt, ML)
   Layer 2 — Modeling frontends      Modelica (.mo) via Rumoca | Julia ModelingToolkit.jl
   Layer 1 — Numeric & analysis core PyCircuits (numpy; scipy optional)  <-- this project
```

Each upper layer is **optional and replaceable**. A user who only wants
classical control does not install Rust or Modelica tooling; a user doing
model-based design on large PDE systems can mount Julia+Rumoca on top of the
same `pycircuits_sim` result types. The decoupled Frontend-Compiler-Backend
architecture below is the mechanism that makes this mixing possible without
forking.
## 4. Proposed extension ladder

The ladder is best-effort in order of effort-vs-impact. A given system may
adopt any subset.

| Step | Effort | What it adds | Status / target scope |
|---|---|---|---|
| **0. Core** | already done | numpy engine + optional `[control]`/`[api]` extras, CLI, Streamlit workbench, test suite | shipped |
| **1. IR & serialization** | done | `pycircuits_sim/ir.py` derived JSON Schema and typed round trips | implemented |
| **2. Block-diagram frontend** | remaining | general graph interconnect and plant/controller diagram editor; current MNA schematic editor is separate | not implemented |
| **3. Hardware bridge** | partial | state-space ESP32 workflow, serial telemetry, explicit PlatformIO upload; automated HIL comparison remains | in progress |
| **4. Modelica front end** | partial | OMEdit authoring, OpenModelica linearize/export, and SISO state-space deployment; general Rumoca/DAE front end remains | in progress |
| **5. Execution backends** | future | Rust simulation kernels + CasADi/JAX code generation | remaining |
| **6. Julia integration** | future | ModelingToolkit.jl and DifferentialEquations.jl integration | remaining |
| **7. Signal processing/system ID** | partial | frequency response and control analysis exist; dedicated system identification remains optional | remaining |

## Known architecture gaps and planned stages

| Known gap | Stage that addresses it | Current/next work |
|---|---|---|
| Real-time determinism and OS scheduling jitter | **Stage 3: hardware bridge hardening** | Current ESP32 firmware uses a cooperative Arduino loop and is not a hard-real-time guarantee. Keep fast control/PWM on-device; move ticks to an ESP32 hardware timer or pinned high-priority task, remove serial I/O from the control deadline, and measure worst-case execution time and jitter before documenting supported frequencies. |
| Steady-state initialization and homotopy for stiff DAEs/algebraic loops | **Stage 4: general Modelica frontend/runtime** | Current linearization delegates operating-point solving to OpenModelica and now carries `x0`. Next, expose initialization failures and test nontrivial initial conditions; homotopy/DAE solving and Jacobian generation require a general solver backend and remain future work. |
| Unified event/root-finding across language runtimes | **Stages 4–5: shared solver/event runtime** | Define event surfaces, root tolerances, event priority, reinitialization, and communication-step semantics in the shared IR; add cross-backend switching-system conformance traces before enabling multi-runtime HIL. |
| Unified interactive workbench | **Stages 2 and 7: diagram editor + IDE** | Stage 2 adds general plant/controller diagrams; Stage 7 connects OMEdit/LSP authoring, simulation, telemetry, and notebooks into one workspace. |
## 5. Milestones

> **Scope note.** "MATLAB/Simulink replacement" is the long-term ceiling, not
> the next milestone. The near-term path deepens the existing power-electronics
> and control moat; the general-suite layers arrive only once their foundation
> (the shared IR, below) exists.

**Milestone A (done):** the shared IR. A single JSON Schema describing
plants, blocks, interconnections, and analyses, with `to_ir()`/`from_ir()` on
every frozen result dataclass, plus one canonical payload schema shared with
`api.py` so the wire format and the IR cannot drift. This is the layer that
makes every later extension a *plugin* rather than a *fork*.

Implemented in `pycircuits_sim/ir.py` (578 lines):

- `to_ir(value)` / `from_ir(payload)` with a self-describing envelope
  (`{"ir_version", "kind", "data"}`) that names the dataclass it carries.
- `IrMixin`, mixed into all 26 engine dataclasses, so every result exposes
  `.to_ir()` and `.from_ir(...)` with no change to field order or equality.
- `build_ir_schema()` derives the JSON Schema **from the same registry** that
  drives encoding and decoding, so the published schema and the runtime
  payload cannot drift apart.
- `validate_ir(payload)` validates against that schema (uses `jsonschema`
  when installed, falls back to a structural check so the core stays
  dependency-free).
- `register(kind)` lets an extension front end (a Modelica importer, a
  hardware bridge) make its own result types round-trip through the IR.
- Complex numbers encode as `{"re", "im"}`; NaN/inf are rejected with a
  readable error because JSON cannot represent them.

The IR is the firewall that keeps later stages additive: a Modelica front
end, a Julia bridge, or a hardware runner all consume the same wire format
instead of each inventing bespoke glue.

**Milestone B (remaining):** a general graph interconnect model. `interconnect.py`
currently models ordered forward/parallel/feedback chains only; a Simulink-
like canvas needs arbitrary topology. The existing chain spec must keep
producing identical results.

**Milestone C (in progress):** the hardware bridge. A serial command layer for
flashing/reading an Arduino or ESP32, a `HILClient` that streams telemetry,
and a `HILRunner` that executes a closed-loop test sequence against a
simulated plant — all using the same `PlantReport` conventions already in
PyCircuits. This is the differentiator a generic MATLAB clone will not have.

**Milestone D (partial):** extension payload packaging — a `pycircuits-sim[modelica]`
extra that only loads Rumoca/OpenModelica when installed, with a clean
`ValueError` + install hint when absent.

**Milestone E (remaining):** the decoupled IDE — an LSP-backed `.mo` authoring
experience in Neovim/VS Code, with a Jupyter kernel that exposes
PyCircuits results and an optional Julia kernel binding the same objects.

**Milestone F (far; remaining):** general CasADi/JAX -> C -> PlatformIO
deployment driven by a template engine over the Stage 1 IR. The first
state-space ESP32 workflow is a narrower path, not this general backend.

## 6. Guiding principles

1. **Always-available pure Python core.** No extension may hard-require a
   non-Python dependency; optional extras degrade gracefully with a readable
   `ValueError` telling the user the extra to install.
2. **One result vocabulary.** Analysis and design results are dataclasses;
   every extension (Web, CLI, Jupyter, hardware bridge, Julia) consumes the
   same objects rather than re-defining its own schema.
3. **Decouple front end from back end.** Authoring, compilation, execution,
   and deployment are separate layers with explicit interfaces; swapping a
   backend (Python -> Rust -> CasADi) does not change the front end.
4. **Tests pin conventions.** The existing unittest suite is the contract;
   new capabilities must adopt it rather than invent a parallel test suite.
5. **Open and auditable.** Text-based config/JSON model files, version
   control friendly, LLM-usable; no closed binaries.

---

*See also: [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md),
[UNIFIED_ARCHITECTURE.md](UNIFIED_ARCHITECTURE.md),
[PORTING_MAP.md](PORTING_MAP.md).*
