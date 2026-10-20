# Unified Architecture: PyCircuits + ControlKit

This document defines the target design of the merged single project. It
follows the analysis in [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md); the
file-by-file transfer plan is in [PORTING_MAP.md](PORTING_MAP.md).

## 1. Goals and constraints

1. **One project, one language, one UI.** PyCircuits is the base: its
   packaging, CLI, engine style, test suite, and Streamlit workbench stay
   intact. ControlKit's React SPA and FastAPI service are not carried forward
   (an optional thin API wrapper is future work, phase 5).
2. **Hybrid dependency policy (decided).** Every new feature has a
   **pure-numpy core that is always available**. `python-control` and `scipy`
   become an optional extra — `pip install "pycircuits-sim[control]"` — that
   unlocks faster/robuster implementations behind guarded imports (LQR via
   `care`, `ct.place`, dense root-locus maps). Core modules must never import
   them at module top level, and a missing optional dependency must degrade
   gracefully: either fall back to the numpy path or raise a `ValueError`
   that names the extra to install.
3. **Conventions carried over from PyCircuits:**
   - `from __future__ import annotations` at the top of every module
   - frozen `@dataclass` configs and results with validation in
     `__post_init__`
   - readable `ValueError` messages (no `ControlError` in engine code; the
     readable-message tradition is preserved)
   - native Python types in results (lists/dicts of floats; `complex` in
     Python-facing outputs), numpy only for computation
   - `unittest` tests under `tests/`, run with
     `python -m unittest discover -s tests`
   - match the indentation of the file you are editing (`linear_systems.py`
     uses tabs; `buck.py`/`mna.py` use 4 spaces)
4. **ControlKit was kept untouched** under `ControlKit/` as a read-only
   reference archive during the port (its nested `.git` history preserved).
   Marked deprecated in its README; **deleted after phase 5 acceptance**
   (recoverable from commit `d908402`).

## 2. Target module layout

New subpackages are marked `+`; existing modules are unchanged:

```
pycircuits_sim/
    __init__.py            # extended public API (see section 6)
    buck.py                # unchanged
    closed_loop.py         # unchanged
    mna.py                 # unchanged
    linear_systems.py      # unchanged (reuse: models, frequency_response, sims)
    metrics.py             # unchanged (buck-sweep metrics stay here)
    sweep.py               # unchanged
    io.py                  # unchanged (+ loaders only if a new config appears)
    plotting.py            # extended: margin markers, nyquist, root-locus plots
    cli.py                 # extended: analyze, tune, sf, interconnect subcommands
    ui.py                  # extended: "Control analysis" mode + analysis tabs
    schematic.py           # unchanged
    schematic_ui.py        # unchanged
    analysis/              # + (Phase 1) ControlKit analysis layer, numpy core
        __init__.py
        plant.py           # normalize: poles/zeros/DC gain/TF<->SS report
        stability.py       # BIBO + Lyapunov verdicts with reasons
        metrics.py         # step-response metrics (rise/settle/overshoot/peak)
        margins.py         # gain/phase margins + crossovers from frequency data
        nyquist.py         # Nyquist real/imag trace
        root_locus.py      # numpy polynomial continuation; ct fast path
    design/                # + (Phase 2) controller design, numpy core
        __init__.py
        tuning.py          # Ziegler-Nichols (ultimate + FOPDT), pole placement
        state_feedback.py  # Ackermann (numpy); LQR (optional dependency)
    interconnect.py        # + (Phase 3) SISO series/parallel/feedback algebra
    optional.py            # + guarded optional-dependency helpers
tests/
    test_analysis.py       # + Phase 1
    test_design.py         # + Phase 2
    test_interconnect.py   # + Phase 3
docs/
    PROJECT_ANALYSIS.md    # this documentation set
    UNIFIED_ARCHITECTURE.md
    PORTING_MAP.md
ControlKit/                # (removed after phase 5; recoverable from d908402)
examples/
    ...existing JSON...
    analysis_plant.json    # + example plants for the analyze/tune CLI
```

### 2.1 Why subpackages instead of flat modules

The package already has 13 flat modules; adding 8 more would bury them.
`analysis/` (what a plant *does*) and `design/` (what to *build* for a plant)
mirror how ControlKit already split its engine, while `interconnect.py` stays
flat because it composes both.

## 3. Core data types (analysis/design layer)

All new configs/results are frozen dataclasses in PyCircuits style:

```python
@dataclass(frozen=True)
class StabilityReport:
    poles: tuple[complex, ...]
    zeros: tuple[complex, ...]
    eigenvalues: tuple[complex, ...]
    bibo_stable: bool
    bibo_reason: str
    lyapunov_asymptotic: bool
    lyapunov_reason: str
    max_real_pole: float | None
    max_real_eig: float | None

@dataclass(frozen=True)
class StepMetrics:
    rise_time_s: float | None
    settling_time_s: float | None
    overshoot_percent: float | None
    peak: float | None
    peak_time_s: float | None
    steady_state: float | None

@dataclass(frozen=True)
class MarginResult:
    gain_margin: float | None          # linear
    gain_margin_db: float | None
    phase_margin_deg: float | None
    gain_crossover_rads: float | None
    phase_crossover_rads: float | None
    omega_rads: tuple[float, ...]      # grid used
    magnitude_db: tuple[float, ...]
    phase_deg: tuple[float, ...]

@dataclass(frozen=True)
class RootLocusResult:
    gains: tuple[float, ...]
    branches: tuple[tuple[complex, ...], ...]   # one tuple per branch
    open_loop_poles: tuple[complex, ...]
    open_loop_zeros: tuple[complex, ...]
```

`TuneResult` (method, Kp/Ki/Kd, Ku/Pu/FOPDT fit, state-feedback K, message),
`StateFeedbackResult` (K, nbar, open/closed poles, open/closed step traces,
message), and `InterconnectResult` (composite num/den, structure, embedded
`StabilityReport`/margin/step payloads) follow the same pattern.

Design decision: **complex numbers stay `complex` in Python-facing results**
(unlike ControlKit's `{re, im}` dicts) because a Python API can carry them;
the CLI converts explicitly when printing or writing JSON.

## 4. Numerics strategy: numpy core, optional fast paths

`pycircuits_sim/optional.py` centralizes guarded imports:

```python
def try_import_control():   # -> module | None  ("python-control")
def try_import_scipy():     # -> module | None  (scipy.linalg for care)
def require_control() -> module:
    # raises ValueError naming: pip install "pycircuits-sim[control]"
```

`pyproject.toml` gains:

```toml
[project.optional-dependencies]
control = ["python-control>=0.10", "scipy>=1.11"]
```

Per-feature strategy:

| Feature | Pure-numpy core (always available) | Optional fast path |
|---|---|---|
| Stability verdicts | `np.linalg.eigvals(A)` for poles/eigenvalues; zeros from SISO poly roots — identical logic to ControlKit, zero python-control needed | none needed |
| Step metrics | manual rise/settle/overshoot from `simulate_state_space` traces (same math as `ct.step_info`) | `ct.step_info` when present, as cross-check |
| Bode + margins | extend existing `frequency_response`; margins by interpolation: gain crossover where `|G| = 0 dB`, phase margin there, phase crossover where `phase = -180°`, gain margin there (log-frequency interpolation, matching `ct.margin` conventions) | `ct.margin` when present |
| Nyquist | real/imag from existing `frequency_response` on a log grid (trivial) | none needed |
| Root locus | SISO: closed-loop char. poly `D(s) + K·N(s)`; roots per K via `np.roots` on a K grid (works because numerator/denominator are polynomials in s); branches sorted by continuity from previous K | `ct.root_locus_map` for adaptive grids when present |
| Ziegler–Nichols | ultimate method uses numpy margins; FOPDT fit ports directly (pure numpy regression on step response) | none needed |
| Pole placement (PID/PD map) | controllability rank via SVD; Ackermann formula `K = e_n' · W⁻¹ · p(A)` for SISO place | `ct.place` for MIMO/multi-pole robustness when present |
| State feedback: Ackermann | `np.poly(A - B·K)` coefficient match via controllability inverse (ControlKit's `ct.acker` is this same algorithm) | `ct.acker` when present |
| State feedback: LQR | numpy Hamiltonian/eigen-based `care` solve for small systems, **or** explicit `ValueError` naming the extra if the fallback is judged too fragile (decide during Phase 2 implementation; teach-scale systems are 2×2–4×4) | `scipy.linalg.solve_continuous_are` / `ct.lqr` |
| Interconnect | SISO polynomial algebra: series = `conv`, parallel = add over common denominator, feedback = `N/(D + N·H)`; normalize by leading coefficient | none needed |

Rules for every port:
- no top-level optional imports; use `optional.py`
- results identical in *shape* whether or not the fast path ran
- tests run without the optional extra installed (CI/tests use the numpy
  path); one smoke test per fast-path feature, skipped via
  `unittest.skipUnless(try_import_control(), ...)`.

## 5. Interface integration

### 5.1 CLI (`cli.py`) — new subcommands

| Command | Behavior |
|---|---|
| `pycircuits-sim analyze <plant.json>` | load plant (reuse `load_linear_plant` formats), print plant report (poles/zeros/DC gain), stability verdicts, step metrics; `--bode`, `--nyquist`, `--rlocus` flags write plots via `plotting.py` |
| `pycircuits-sim margins <plant.json>` | margin/crossover table (also implied by `analyze --bode`) |
| `pycircuits-sim tune <plant.json>` | `--method zn|pole-placement`, `--poles` for placement; prints gains + message; optional `--apply` writes a closed-loop step CSV |
| `pycircuits-sim sf <plant.json>` | `--method ackermann|lqr`, `--poles` / `--q --r`; prints K, nbar, closed-loop poles; optional CSV of open vs closed step |
| `pycircuits-sim interconnect <blocks.json>` | compose forward/parallel/feedback chains; full analysis printed + optional CSV/plots |

All follow the existing pattern: positional JSON path, `--csv-output` /
`--plot-output` / `--show` flags, one-line summary printed on success.

### 5.2 Streamlit UI (`ui.py`) — new mode

Add a 7th sidebar mode **"Control analysis"**:
- sidebar: plant entry (same examples/matrix editors as "Linear control
  plant"), analysis selector (Plant report / Stability / Bode+margins /
  Nyquist / Root locus / Step metrics / PID tuning / State feedback /
  Interconnect)
- main area: Plotly charts via existing `style_chart` helper; metric cards
  via `st.metric`; gains/poles tables
- reuse: the existing "Linear control plant" mode keeps its open-loop/PID
  tabs; the new mode adds what ControlKit had (analysis + design)

### 5.3 What is explicitly out of scope

- React/Vite frontend and FastAPI service (phase 5 optional wrapper only)
- `ControlKit/backend/app/engine/diagram/` stub — not ported
- Impulse/custom-input simulation: **in scope for Phase 1** as
  `simulate_state_space` already accepts arbitrary input callables; a small
  `step_input`/`impulse_input` helper + metrics covers ControlKit's `step`/
  `impulse` parity. Arbitrary t,u CSV input is a Phase 1 stretch.
- MIMO analysis beyond Bode: analysis stays **SISO-first** (margins, locus,
  tuning need SISO); MIMO plants continue to work for open-loop simulation
  and per-channel Bode exactly as today.

## 6. Public API additions (`pycircuits_sim/__init__.py`)

Phase exports follow the existing import-and-list pattern in `__init__.py`:

```python
# Phase 1 (analysis)
StabilityReport, StepMetrics, MarginResult, RootLocusResult,
normalize_plant, analyze_stability, step_metrics,
bode_margins, nyquist_response, root_locus,
# Phase 2 (design)
TuneResult, StateFeedbackResult,
ziegler_nichols, tune_pole_placement, ackermann, lqr,
# Phase 3
InterconnectSpec, InterconnectResult, interconnect,
```

Naming rule: keep the ControlKit verb names where they are already good
(`ziegler_nichols`, `ackermann`, `lqr`, `analyze_stability`), but prefix
ambiguous ones (`bode_margins` instead of `bode`, `root_locus` as a noun
function matching `frequency_response` style).

## 7. Phased roadmap

> **Status (all phases complete):** Phases 1–5 are implemented and tested
> (148 unittest cases collected; 2 skipped without the optional `python-control`
> and `scipy` dependencies). The `[control]` and `[api]` extras exist in
> `pyproject.toml`; the `ControlKit/` archive has been removed and is
> recoverable from commit `d908402`.

Each phase is independently shippable: engine + tests first, CLI second, UI
third. Acceptance = existing tests still pass + new tests green
(`python -m unittest discover -s tests`) + demo commands run.

| Phase | Content | Acceptance tests (drawn from ControlKit's `test_engine.py`) |
|---|---|---|
| **1. Analysis layer** | `optional.py`, `analysis/` (plant, stability, metrics, margins, nyquist, root_locus), tests | poles of 1/(s²+s+1) = -0.5 ± j·√3/2; step overshoot ≈ 16.3% for ζ=0.5; integrator not BIBO-stable; margins of a known loop match to tolerance; root-locus branches start at open-loop poles |
| **2. Design layer** | `design/` (tuning, state_feedback), tests | ZN ultimate gains from Ku/Pu table match; FOPDT fallback on a lag plant; Ackermann K places desired poles (check `eig(A-BK)`); N̄ steady-state = 1; LQR smoke test (skipped without extra) |
| **3. Interconnect** | `interconnect.py`, tests | series/parallel/feedback identities on toy blocks; composite order limit enforced; result equals hand-computed rational function |
| **4. Interfaces + docs** | `cli.py` subcommands, `ui.py` mode, `plotting.py` charts, README, examples | end-to-end: `analyze`, `tune`, `sf`, `interconnect` demo JSONs; UI mode renders; README updated |
| **5. Optional (deferred)** | FastAPI wrapper reusing the routers' contract; ControlKit removal after review | API smoke tests; final `git` cleanup |

Risk notes:
- **LQR without scipy** is the only feature that may hard-require the optional
  extra; decide in Phase 2 by prototyping the numpy `care` solve against a
  known example — if accuracy is poor, document `ValueError` + install hint.
- **Margin conventions** (linear vs dB, rad/s vs Hz) must be chosen once and
  documented in the docstrings; tests pin the convention.
- **Do not modify** existing engine behavior; new code consumes
  `linear_systems.py` results rather than changing them.




