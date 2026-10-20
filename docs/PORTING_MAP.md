# Porting Map: ControlKit → PyCircuits

File-by-file transfer plan from `ControlKit/backend/app/` into
`pycircuits_sim/`. Companion documents:
[PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) (why),
[UNIFIED_ARCHITECTURE.md](UNIFIED_ARCHITECTURE.md) (target design).

Legend for the "Port mode" column:

- **DIRECT** — logic ports nearly as-is; only re-style (frozen dataclass
  payloads instead of dicts, `ValueError` instead of `ControlError`, PyCircuits
  indentation/docstring conventions).
- **REIMPLEMENT** — behavior ports but the implementation must be rewritten in
  pure numpy (ControlKit delegated it to `python-control`/scipy).
- **FAST PATH** — numpy reimplementation first, optional `python-control`
  fast path behind `optional.py`.
- **SKIP** — deliberately not ported.

## 1. Engine files

| ControlKit source | Destination in `pycircuits_sim` | Port mode | Notes |
|---|---|---|---|
| `engine/util.py` | `optional.py` (guarded imports) + small helpers inside each new module | DIRECT (selectively) | `ControlError` is **not** ported (use `ValueError`); `downsample`/`fnum` JSON shaping only needed for CLI JSON output — keep as private helpers where used; `cplx_list` becomes native `complex` tuples |
| `engine/plant.py` | `analysis/plant.py` | DIRECT | `build_system` validation logic (shape checks, finite checks, den leading-coefficient trim) maps onto PyCircuits' `StateSpaceModel.from_matrices` / `transfer_function_to_state_space` — reuse those instead of duplicating; `normalize_payload` becomes `normalize_plant(model)` returning `PlantReport` (num, den, A–D, poles, zeros, dc_gain, order) computed with numpy; SISO-only *margins/locus* checks move to the features that need them, not to plant building (PyCircuits supports MIMO) |
| `engine/stability.py` | `analysis/stability.py` | REIMPLEMENT (trivial) | Logic ports line-for-line; replace `ct.poles`/`ct.zeros` with eigenvalues of A and SISO polynomial roots (`np.roots(den)`, `np.roots(num padded)`); keep the BIBO reason strings and repeated-jω handling exactly |
| `engine/time_domain.py` | `analysis/metrics.py` + input helpers | REIMPLEMENT | `_step_metrics` → numpy rise/settling/overshoot/peak computed from existing `simulate_state_space` traces (final-value as steady state; rising-edge 10–90% rise time; last outside-band sample for settling — same definitions as `ct.step_info`); `simulate_custom` resampling logic ports as a helper for arbitrary t,u inputs; `step`/`impulse` use input callables (`lambda t: 1.0`, impulse approximated as a one-step unit impulse with documented scaling, or a `dt`-scaled pulse — decide in Phase 1 and pin with a test) |
| `engine/frequency.py` | `analysis/margins.py` + `analysis/nyquist.py` | REIMPLEMENT | Nyquist = real/imag of existing `frequency_response` output (change units: document rad/s grid). Margins: interpolate on the existing magnitude/phase grids — gain crossover via log-magnitude zero crossing, phase crossover via unwrapped phase crossing -180°, linear interpolation between samples, refine by densifying the grid locally; optional `ct.margin` fast path. Choose and document units: **rad/s + dB + degrees** for margins (ControlKit convention), keep `frequency_response`'s Hz API unchanged |
| `engine/root_locus.py` | `analysis/root_locus.py` | FAST PATH | Numpy core: closed-loop characteristic polynomial `den + K*num` (after normalizing den to monic), roots per K via `np.roots`, K grid `[0] + logspace(-3, 3, n)`, branch continuity matching (nearest-root assignment from the previous K); optional `ct.root_locus_map` fast path. Port branch downsampling (≤ 400 pts) |
| `engine/pid.py` | `design/tuning.py` | DIRECT + REIMPLEMENT (mixed) | `pid_tf` ports directly as `pid_transfer_function(Kp, Ki, Kd, N)` returning `(num, den)` (pure poly arithmetic — python-control not needed); `closed_loop_payload` rebuilt on `interconnect`/feedback algebra + existing sims; `ziegler_nichols` ultimate branch: DIRECT (uses new `bode_margins`); `_reaction_curve_fit` (FOPDT K/τ/θ): DIRECT pure numpy; P/PI/PID variant table: DIRECT; `pole_placement` + `_pid_from_second_order`: DIRECT once `place` exists (numpy Ackermann core) |
| `engine/state_feedback.py` | `design/state_feedback.py` | REIMPLEMENT + FAST PATH | `_ss_data`/`_check_controllable`: port (SISO checks, ctrb rank via SVD); `ackermann`: numpy Ackermann formula `K = [0 … 1] · W⁻¹ · α(A)` with `W = ctrb(A,B)`; conjugate-symmetric pole check ports directly; `_closed_loop_step` (N̄ pre-gain, time window from slowest poles, open vs closed step): DIRECT but uses PyCircuits sims; `lqr`: **scipy/python-control fast path; numpy `care` fallback decision deferred to Phase 2** (see roadmap risk note) |
| `engine/interconnect.py` | `interconnect.py` | REIMPLEMENT | Replace `ct.series/parallel/feedback` with SISO polynomial algebra (`numpy.polynomial` or `np.convolve`); block kinds `tf`/`ss`/`pid`/`gain`: ss blocks convert via existing TF-from-SS; keep limits (6 blocks, order ≤ 20) and the full-analysis payload; `_block_system` validation ports directly |
| `engine/diagram/*` | — | SKIP | Dead scaffolding (base class only, unwired); the "free-form block canvas" idea maps to PyCircuits' future UI work, not this port |

## 2. API and schema files

| ControlKit source | Destination | Port mode | Notes |
|---|---|---|---|
| `app/schemas.py` | — (Phase 5 only) | SKIP (for now) | Pydantic request models exist only to serve HTTP; the CLI/UI construct dataclasses directly. Keep as reference when building the optional FastAPI wrapper |
| `app/routers/analyze.py` | `cli.py` + `ui.py` (Phase 4) | SKIP (contract only) | Each endpoint maps to a CLI subcommand/UI widget (see UNIFIED section 5). The router's error mapping (`ControlError` → 400) is the model for CLI error printing |
| `app/routers/design.py` | `cli.py` + `ui.py` (Phase 4) | SKIP (contract only) | Same as above for `/sf/*` and `/interconnect` |
| `app/main.py` | — | SKIP | CORS/app setup only needed in Phase 5 |

## 3. Frontend files

| ControlKit source | Destination | Port mode | Notes |
|---|---|---|---|
| `frontend/src/App.tsx` | `ui.py` "Control analysis" mode (behavioral reference) | SKIP (code) / REIMPLEMENT (UX) | Port the *UX inventory*: example plants (DC motor `4/s(s+12)`, inverted pendulum `1/(s²−9.81)`, 3rd-order), pole text parser (accepts `3`, `-1+2j`, comma/semicolon separated), matrix parser (`;`/newline rows), tab set (step/impulse/custom/bode/nyquist/rlocus/sf/interconnect), localStorage → not needed (Streamlit session state) |
| `frontend/src/types.ts` | dataclass definitions in `analysis/`/`design/` | REIMPLEMENT | Shapes map 1:1 onto the frozen dataclasses in UNIFIED section 3 |
| `frontend/src/api.ts` | — | SKIP | fetch wrappers have no Streamlit equivalent |
| `frontend/src/PlotlyChart.tsx` | existing `style_chart` + `st.plotly_chart` in `ui.py` | SKIP | PyCircuits already renders Plotly |
| `frontend/dist/`, `node_modules/`, Vite config | — | SKIP | Build artifacts; not carried forward |

## 4. Tests

`ControlKit/backend/tests/test_engine.py` (336 lines) is the acceptance-test
source. Translate to `unittest` under `tests/` per phase:

| ControlKit test (representative) | Destination | Phase |
|---|---|---|
| `test_poles_of_second_order` (poles -0.5 ± j√3/2, BIBO + Lyapunov true) | `tests/test_analysis.py::TestStability` | 1 |
| `test_integrator_not_bibo` (pole at origin → not BIBO, with reason) | `tests/test_analysis.py::TestStability` | 1 |
| `test_step_overshoot_matches_zeta` (≈16.3% for ζ=0.5) | `tests/test_analysis.py::TestMetrics` | 1 |
| rise/settling/peak assertions | `tests/test_analysis.py::TestMetrics` | 1 |
| gain/phase margin numeric assertions on known plants | `tests/test_analysis.py::TestMargins` | 1 |
| Nyquist real/imag sanity (DC value, encircle checks on simple plants) | `tests/test_analysis.py::TestNyquist` | 1 |
| root locus starts at open-loop poles (K→0), one branch per pole | `tests/test_analysis.py::TestRootLocus` | 1 |
| plant normalize round-trip (TF → SS → TF coefficients) | `tests/test_analysis.py::TestPlant` | 1 |
| ZN ultimate table values (Ku/Pu → P/PI/PID gains) | `tests/test_design.py::TestZieglerNichols` | 2 |
| FOPDT reaction-curve fit on a lag plant | `tests/test_design.py::TestZieglerNichols` | 2 |
| pole placement: `eig(A−BK)` equals desired poles; PID/PD mapping | `tests/test_design.py::TestPolePlacement` | 2 |
| Ackermann: K places poles; uncontrollable plant raises; N̄ gives unit steady state | `tests/test_design.py::TestAckermann` | 2 |
| LQR: smoke test + known 2×2 answer (skipUnless optional extra) | `tests/test_design.py::TestLqr` | 2 |
| interconnect: series/parallel/feedback identities, order limit, duplicate ids | `tests/test_interconnect.py` | 3 |
| API `TestClient` tests | — | SKIP (no API until Phase 5) |

## 5. Porting conventions checklist (per file)

Before merging any ported module, verify:

1. `from __future__ import annotations` present; module docstring explains
   the feature and its educational limits (match existing docstring tone).
2. Frozen `@dataclass` results; validation in `__post_init__` with readable
   `ValueError` messages — no `ControlError`, no bare `except Exception`
   swallowing (ControlKit's broad excepts are narrowed where reasonable).
3. No top-level `import control` / `import scipy` — use `optional.py`.
4. Native Python types in returned data (`float`, `complex`, `list`, `tuple`);
   numpy confined to computation.
5. Units documented in the docstring (Hz vs rad/s, linear vs dB, seconds).
6. New/changed public functions exported through `pycircuits_sim/__init__.py`.
7. Tests added under `tests/` and full suite green:
   `python -m unittest discover -s tests`.
8. Indentation/docstring style matches the file being edited; tabs in
   modules that use tabs (`linear_systems.py`), spaces in modules that use
   spaces (`buck.py`, `mna.py`).
9. ControlKit source left unmodified during the port (reference archive).
   The archive was deleted after phase 5 acceptance; its files remain
   recoverable from commit `d908402`.

