# PyCircuits Simulation Backend

A small, headless power-electronics simulator intended as a learning foundation.
The initial model is a buck converter with an ideal PWM-controlled switch, an
ideal freewheel diode, an inductor, an output capacitor, and a resistive load.

## Run

Requires Python 3.10 or newer. From the project directory:

```sh
python -m pycircuits_sim.cli run examples/buck.json --output waveforms.csv
```

After installing the project with `python -m pip install -e .`, the equivalent
command is:

```sh
pycircuits-sim run examples/buck.json --output waveforms.csv
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
python -m pycircuits_sim.cli sweep examples/inductance_sweep.json
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

## Generic transient MNA

The separate MNA engine accepts component netlists in JSON and solves node
voltages with fixed-step backward Euler integration:

```sh
python -m pycircuits_sim.cli mna examples/mna_switched_rc.json
```

Supported components are resistors, capacitors, inductors, DC or sine voltage
and current sources, and ideal controlled switches approximated by finite
`ron`/`roff` resistances. Capacitor initial voltage and inductor initial current
can be supplied with `initial`. Switches use `control_points` as `[time_s,
control_value]` pairs; the control is linearly interpolated and compared with
`threshold`. Output CSV contains all node voltages and component currents; the
plot shows node voltages.

This is a linear transient MNA core with PWL resistive switches, not yet a full
SPICE replacement. It does not currently implement diodes, nonlinear device
models, dependent sources, AC steady-state analysis, adaptive timesteps,
Newton-Raphson iteration, or a schematic editor. Finite `roff` means an off
switch has small leakage, and high `ron`/`roff` ratios can worsen numerical
conditioning. A circuit with floating nodes or contradictory ideal sources
will fail with a singular-system diagnostic.

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