"""Command-line interface for running a buck converter simulation."""

from __future__ import annotations

import argparse

from .buck import simulate_buck
from .closed_loop import simulate_closed_loop
from .io import (
    load_config,
    load_closed_loop_config,
    load_mna_config_file,
    load_sweep_config,
    read_waveforms_csv,
    write_csv,
    write_closed_loop_csv,
    write_metrics_csv,
    write_mna_csv,
    write_sweep_csv,
)
from .metrics import measure_sweep
from .mna import simulate_mna
from .plotting import plot_circuit, plot_closed_loop, plot_sweep, plot_waveforms
from .sweep import run_parameter_sweep


def main() -> None:
    parser = argparse.ArgumentParser(prog="pycircuits-sim")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run a buck converter simulation")
    run_parser.add_argument("config", help="path to a JSON simulation configuration")
    run_parser.add_argument("--output", default="waveforms.csv", help="output CSV path")
    plot_parser = subparsers.add_parser("plot", help="plot a waveform CSV")
    plot_parser.add_argument("input", help="path to a waveform CSV")
    plot_parser.add_argument("--output", default="waveforms.png", help="output image path")
    plot_parser.add_argument("--show", action="store_true", help="also open an interactive plot window")
    sweep_parser = subparsers.add_parser("sweep", help="run and plot a parameter sweep")
    sweep_parser.add_argument("config", help="path to a sweep JSON configuration")
    sweep_parser.add_argument("--csv-output", default="sweep.csv", help="long-form output CSV path")
    sweep_parser.add_argument("--plot-output", default="sweep.png", help="overlay plot image path")
    sweep_parser.add_argument("--metrics-output", default="sweep_metrics.csv", help="per-run metrics CSV path")
    sweep_parser.add_argument("--steady-state-fraction", type=float, default=0.1, help="final sample fraction used for steady-state metrics")
    sweep_parser.add_argument("--settling-band", type=float, default=0.02, help="relative settling band, for example 0.02 for 2 percent")
    sweep_parser.add_argument("--show", action="store_true", help="also open an interactive plot window")
    closed_parser = subparsers.add_parser("closed-loop", help="run a PID-controlled buck simulation")
    closed_parser.add_argument("config", help="path to a closed-loop JSON configuration")
    closed_parser.add_argument("--csv-output", default="closed_loop.csv", help="controller and plant trace CSV")
    closed_parser.add_argument("--plot-output", default="closed_loop.png", help="closed-loop plot image")
    closed_parser.add_argument("--show", action="store_true", help="also open an interactive plot window")
    mna_parser = subparsers.add_parser("mna", help="simulate a component netlist with transient MNA")
    mna_parser.add_argument("config", help="path to an MNA JSON netlist")
    mna_parser.add_argument("--csv-output", default="circuit.csv", help="node/component trace CSV")
    mna_parser.add_argument("--plot-output", default="circuit.png", help="node-voltage plot image")
    mna_parser.add_argument("--show", action="store_true", help="also open an interactive plot window")
    args = parser.parse_args()

    if args.command == "run":
        config = load_config(args.config)
        result = simulate_buck(config)
        write_csv(result, args.output)
        print(
            f"Wrote {len(result.time)} samples to {args.output}; "
            f"final output voltage: {result.output_voltage[-1]:.6g} V"
        )
    elif args.command == "plot":
        waveforms = read_waveforms_csv(args.input)
        plot_waveforms(waveforms, output_path=args.output, show=args.show)
        print(f"Plotted {len(waveforms.time)} samples to {args.output}")
    elif args.command == "sweep":
        base_config, parameter, values = load_sweep_config(args.config)
        runs = run_parameter_sweep(base_config, parameter, values)
        metrics = measure_sweep(
            runs,
            steady_state_fraction=args.steady_state_fraction,
            settling_band=args.settling_band,
        )
        write_sweep_csv(runs, args.csv_output)
        write_metrics_csv(metrics, args.metrics_output)
        plot_sweep(runs, output_path=args.plot_output, show=args.show)
        print(
            f"Wrote {len(runs)} runs ({len(runs[0].result.time)} samples each) "
            f"to {args.csv_output}, {args.metrics_output}, and {args.plot_output}"
        )
    elif args.command == "closed-loop":
        config = load_closed_loop_config(args.config)
        result = simulate_closed_loop(config)
        write_closed_loop_csv(result, args.csv_output)
        plot_closed_loop(result, output_path=args.plot_output, show=args.show)
        print(
            f"Wrote {len(result.time)} samples to {args.csv_output} and "
            f"{args.plot_output}; final output voltage: "
            f"{result.output_voltage[-1]:.6g} V"
        )
    elif args.command == "mna":
        config = load_mna_config_file(args.config)
        result = simulate_mna(config)
        write_mna_csv(result, args.csv_output)
        plot_circuit(result, output_path=args.plot_output, show=args.show)
        print(
            f"Simulated {len(config.components)} components for {result.time[-1]:g} s "
            f"({len(result.time)} samples); wrote {args.csv_output} and {args.plot_output}"
        )


if __name__ == "__main__":
    main()
