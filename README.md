# PyCircuits

PyCircuits is an educational power-electronics and control-systems simulator.
It includes buck-converter simulations, rectifier netlists, sampled PID loops,
continuous and discrete state-space plants, transfer-function conversion, and
interactive waveform analysis. Models are simplified for learning and are not
validated for hardware design or safety decisions.

## Status & roadmap

PyCircuits is the base project of a planned merge with **ControlKit** (kept
under `ControlKit/` as a read-only reference archive). ControlKit's classical
control-analysis features — stability verdicts, Bode margins, Nyquist, root
locus, Ziegler–Nichols tuning, Ackermann/LQR state feedback, and block
interconnections — are being ported into `pycircuits_sim` as pure-numpy
engine modules under a **hybrid dependency policy**: everything works with
numpy alone, while `pip install "pycircuits-sim[control]"` adds
`python-control`/`scipy` fast paths for heavy numerics such as LQR.

**Progress:** Phase 1 (analysis layer: `pycircuits_sim/analysis/`), Phase 2
(design layer: `pycircuits_sim/design/`), and Phase 3 (block
interconnections: `pycircuits_sim/interconnect.py`) are implemented and
tested. Phase 4 (CLI/UI integration) remains. Read the full plan in
`docs/`:

- [`docs/PROJECT_ANALYSIS.md`](docs/PROJECT_ANALYSIS.md) — side-by-side analysis of both projects and the feature gap matrix
- [`docs/UNIFIED_ARCHITECTURE.md`](docs/UNIFIED_ARCHITECTURE.md) — target design, module layout, CLI/UI integration, phased roadmap
- [`docs/PORTING_MAP.md`](docs/PORTING_MAP.md) — file-by-file transfer plan and porting conventions

## Quick start

The project requires Python 3.10 or newer. `requirements.txt` is a fully pinned
snapshot of the current development virtual environment (Python 3.14.7), for
reproducing that setup. On another supported Python version, install the project
directly so pip can select compatible dependency builds:

```sh
python -m pip install -e .
```

Run setup commands from the project root.

Create and activate a virtual environment.

Linux or macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the pinned development environment and this project:

```sh
python -m pip install -r requirements.txt
python -m pip install -e .
```

# Start the browser workbench:

```sh
python -m streamlit run pycircuits_sim/ui.py
```

Streamlit prints the local URL; open **http://localhost:8501** in a browser if
it does not open automatically. Choose a circuit or plant from the sidebar,
adjust its controls, and select **Run simulation**. The workbench supports
open-loop and PID-controlled buck converters, half-wave and bridge rectifiers,
continuous or discrete linear control plants, and a first-pass schematic editor.
The editor lets you place supported two-terminal components, junctions, and
ground; connect them on the canvas; inspect values; validate the generated MNA
netlist; and run the existing solver. Results include interactive waveforms,
run measurements, and CSV downloads.

To run the headless buck example instead:

```sh
python -m pycircuits_sim.cli run examples/buck.json --output waveforms.csv
```

Plot its CSV later with:

```sh
python -m pycircuits_sim.cli plot waveforms.csv --output waveforms.png
```

Or run a diode rectifier netlist:

```sh
python -m pycircuits_sim.cli mna examples/half_wave_rectifier.json
```

The installed `pycircuits-sim` command is also available after `pip install -e .`.
For example, `pycircuits-sim mna examples/bridge_rectifier.json` runs the bridge.

## Interactive UI

The **Linear control plant** mode accepts continuous-time matrices, discrete-time
matrices, and proper continuous-time SISO numerator/denominator transfer
functions. Open-loop state-space models support multiple inputs and outputs;
the initial PID feedback implementation is SISO. Transfer-function coefficients
are entered in descending powers of `s` and converted to controllable-canonical
state space. Discrete plants use the sample period specified in the sidebar;
their Bode range is limited to frequencies below Nyquist. Matrix/coefficient
inputs use numeric Python-style lists. Simulation runs are explicit because
rectifier and fine-timestep runs can take a few seconds.

In **Schematic editor**, add components from the sidebar palette and drag them
to arrange the circuit. Draw wires from a component's right terminal to another
node's left terminal; add junctions to branch a net and add a ground reference.
Select a component in the properties panel to change its values. Open existing
MNA JSON netlists with the file picker and save circuits as JSON with editor
layout metadata plus standard MNA components/nodes. The editor currently covers
two-terminal MNA parts; multi-terminal semiconductor packages and the later
plant/controller block-diagram canvas are not included yet.

## CLI reference

Run an open-loop buck converter:

```sh
python -m pycircuits_sim.cli run examples/buck.json --output waveforms.csv
```

Run a sampled PID-controlled buck:

```sh
python -m pycircuits_sim.cli closed-loop examples/closed_loop_buck.json
```

Run component-circuit netlists and rectifiers:

```sh
python -m pycircuits_sim.cli mna examples/mna_switched_rc.json
python -m pycircuits_sim.cli mna examples/half_wave_rectifier.json
python -m pycircuits_sim.cli mna examples/bridge_rectifier.json
```

Sweep a supported buck parameter and create trace, metric, and plot files:

```sh
python -m pycircuits_sim.cli sweep examples/inductance_sweep_demo.json
```

The CSV contains time, inductor current, output voltage, and switch state. The
configuration file is ordinary JSON, so scripts and other tools can generate it.
Matplotlib is installed with the package and is used to render the trace plots.

To visualize an existing simulation:

```sh
python -m pycircuits_sim.cli plot waveforms.csv --output waveforms.png
```

The plot contains aligned panels for output voltage, inductor current, and PWM
state. Add `--show` to also open it in an interactive Matplotlib window.

## Parameter sweeps

Sweep one parameter at a time while keeping the rest of the base circuit fixed.
The initial supported parameters are inductance, capacitance, load resistance,
and duty cycle. The example sweeps inductance:

```sh
python -m pycircuits_sim.cli sweep examples/inductance_sweep_demo.json
```

This writes a long-form `sweep.csv`, a per-run `sweep_metrics.csv`, and a
`sweep.png` with overlaid output-voltage and inductor-current traces. Metrics
include peak overshoot relative to the estimated final voltage, settling time
within a 2% band, and peak-to-peak voltage/current ripple in the final 10% of
the samples. Adjust those analysis windows with `--steady-state-fraction` and
`--settling-band`; use `--csv-output`, `--metrics-output`, `--plot-output`, or
`--show` to customize the outputs.
An empty `settling_time_s` means the trace did not remain inside the band through
the end of the run. Overshoot is empty only when the estimated final voltage is
zero, where a percentage overshoot is undefined.

## Closed-loop buck control

Run a sampled PID controller against the buck power stage:

```sh
python -m pycircuits_sim.cli closed-loop examples/closed_loop_buck.json
```

This writes `closed_loop.csv` with reference, output, error, P/I/D terms, duty,
inductor current, and switch state, and `closed_loop.png` with aligned plots of
the reference/output, error, controller terms, and duty cycle. PID derivative
acts on measured output to avoid a setpoint derivative kick. Duty saturation
and conditional integral anti-windup are enabled. The controller sample time
must be an integer multiple of the plant timestep. The current controller is
educational and uses ideal switch models; it is not suitable for validating a
real converter or controller implementation.

## Linear control plants

Continuous-time LTI plants can be created directly with the public API:

```python
from pycircuits_sim import (
	LinearPIDConfig,
	StateSpaceModel,
	StepReference,
	simulate_state_space_pid,
	transfer_function_to_state_space,
)

plant = transfer_function_to_state_space([1.0], [1.0, 1.0])
result = simulate_state_space_pid(
	plant,
	LinearPIDConfig(kp=0.8, ki=2.0, kd=0.0, sample_time=0.01),
	StepReference(initial=0.0, final=1.0, step_time=0.1),
	time_step=0.001,
	stop_time=2.0,
)
```

`StateSpaceModel.from_matrices(A, B, C, D)` supports continuous-time MIMO
open-loop simulation through `simulate_state_space`. `transfer_function_to_state_space`
accepts proper continuous-time SISO polynomials with coefficients ordered from
highest to lowest power. Both use fixed-step backward Euler; the controller
sample time must be an integer multiple of the integration step. PID feedback
currently requires SISO and `D = 0`, avoiding an unresolved algebraic loop from
direct feedthrough. MIMO feedback and discrete transfer-function conversion are
not yet implemented. Discrete state-space plants use
`DiscreteStateSpaceModel.from_matrices(A_d, B_d, C_d, D_d, sample_time)` and
advance with $x[k+1] = A_d x[k] + B_d u[k]$. They support open-loop MIMO,
sampled SISO PID feedback, and discrete frequency response. Discrete Bode
frequencies must be below Nyquist (`1 / (2 * sample_time)`), and stability
requires every pole inside the unit circle. Discrete simulations stop at the
last complete plant sample. Continuous-time frequency response
is available through `frequency_response(model, frequencies_hz)` and
`logarithmic_frequency_grid(minimum_hz, maximum_hz)`. The workbench plots Bode
magnitude/phase per input-output channel and reports the eigenvalues of A as
the plant poles. For continuous-time models, all poles with negative real parts
indicate asymptotic stability. Example definitions are in
`examples/state_space_first_order.json` and
`examples/transfer_function_second_order.json`; a discrete model is in
`examples/discrete_first_order.json`.

## Generic transient MNA

The separate MNA engine accepts component netlists in JSON and solves node
voltages with fixed-step backward Euler integration:

```sh
python -m pycircuits_sim.cli mna examples/mna_switched_rc.json
```

Supported components are resistors, capacitors, inductors, DC or sine voltage
and current sources, Shockley-model diodes, and controlled switches approximated
by finite `ron`/`roff` resistances. Capacitor initial voltage and inductor
initial current can be supplied with `initial`. Switches use `control_points` as
`[time_s, control_value]` pairs; the control is linearly interpolated and
compared with `threshold`. Diodes accept `saturation_current`,
`ideality_factor`, and `thermal_voltage`. The solver uses damped Newton-Raphson
iterations at each transient timestep when a circuit contains diodes; tune
`newton_tolerance`, `newton_max_iterations`, and `newton_damping` if needed.
Output CSV contains all node voltages and component currents; the plot shows
node voltages.

The diode current uses the Shockley equation, with the exponential argument
limited to avoid floating-point overflow. This is a basic junction model; it
does not include reverse recovery, breakdown, junction capacitance, or series
resistance. `gmin` adds a configurable conductance from each non-ground node to
ground (default `1e-12` S) to help condition diode-off and floating networks.
Set `gmin` to zero to disable that numerical reference; truly floating circuits
may then produce a singular-system error.

Example rectifiers:

```sh
python -m pycircuits_sim.cli mna examples/half_wave_rectifier.json
python -m pycircuits_sim.cli mna examples/bridge_rectifier.json
```

This remains a teaching simulator, not a full SPICE replacement. It does not
currently implement MOSFET/BJT models, dependent sources, AC steady-state
analysis, adaptive timesteps, or schematic editing. Finite switch `roff` means
an off switch has small leakage, and high `ron`/`roff` ratios can worsen
conditioning. Circuits with floating modes can still be poorly conditioned,
especially if `gmin` is disabled; contradictory ideal sources produce a
singular-system diagnostic. Diode nonconvergence is reported with timestep,
residual, and junction voltages.

## Model boundaries

The solver uses fixed-step backward Euler integration. PWM state is sampled at
the beginning of each step. The diode prevents negative inductor current, but
switching transitions are only resolved to the configured timestep. This is a
teaching model, not a validated design or safety tool. It does not yet model
parasitics, semiconductor losses, reverse recovery, gate-drive behavior, or
control-loop dynamics.

Choose a timestep substantially smaller than the switching period to resolve
switching behavior. Decrease it further when you need more accurate switching
edges, at the cost of longer runs.

## Tests

```sh
python -m unittest discover -s tests
```