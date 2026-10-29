"""Command-line interface for the PyCircuits simulation and analysis engines."""

from __future__ import annotations

import argparse
import re
import sys

from .analysis import (
    analyze_stability,
    bode_margins,
    normalize_plant,
    nyquist_response,
    root_locus,
    step_metrics,
)
from .buck import simulate_buck
from .closed_loop import simulate_closed_loop
from .design import ackermann, lqr, tune_pole_placement, ziegler_nichols
from .graph import interconnect_graph
from .interconnect import interconnect
from .io import (
    load_block_diagram,
    load_closed_loop_config,
    load_config,
    load_interconnect_spec,
    load_mna_config_file,
    load_sweep_config,
    read_waveforms_csv,
    write_closed_loop_csv,
    write_csv,
    write_metrics_csv,
    write_mna_csv,
    write_state_feedback_csv,
    write_sweep_csv,
)
from .linear_systems import load_linear_plant, simulate_state_space
from .metrics import measure_sweep
from .mna import simulate_mna
from .plotting import (
    plot_bode_margins,
    plot_circuit,
    plot_closed_loop,
    plot_nyquist,
    plot_root_locus,
    plot_sweep,
    plot_waveforms,
)
from .sweep import run_parameter_sweep


def _parse_complex_list(text: str) -> list[complex]:
    """Parse 'a+bj, c+dj, ...' (comma separated, 'i' accepted for 'j')."""
    values: list[complex] = []
    for token in text.split(","):
        cleaned = token.strip().replace(" ", "").replace("i", "j")
        if not cleaned:
            continue
        if cleaned == "j":
            cleaned = "1j"
        cleaned = re.sub(r"(?<=[+-])j", "1j", cleaned)
        try:
            values.append(complex(cleaned))
        except ValueError as error:
            raise ValueError(f"could not parse value {token.strip()!r}") from error
    if not values:
        raise ValueError("expected at least one comma-separated value")
    return values


def _parse_float_list(text: str) -> list[float]:
    values: list[float] = []
    for token in text.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        try:
            values.append(float(cleaned))
        except ValueError as error:
            raise ValueError(f"could not parse number {cleaned!r}") from error
    if not values:
        raise ValueError("expected at least one comma-separated number")
    return values


def _format_row(row) -> str:
    return "[" + ", ".join(f"{float(value):.6g}" for value in row) + "]"


def _format_complex(values, digits: int = 4) -> str:
    def one(value: complex) -> str:
        if value.imag == 0:
            return f"{value.real:.{digits}g}"
        sign = "+" if value.imag >= 0 else "-"
        return f"{value.real:.{digits}g} {sign} {abs(value.imag):.{digits}g}j"

    return ", ".join(one(complex(value)) for value in values)


def _load_analysis_plant(path: str):
    """Load a continuous SISO plant JSON (state_space or transfer_function)."""
    model, _data = load_linear_plant(path)
    return model


def _command_analyze(args) -> None:
    model = _load_analysis_plant(args.config)
    report = normalize_plant(model)
    stability = analyze_stability(model)

    name = _format_complex(report.poles) if report.poles else "(none)"
    print(f"Plant order: {report.order}   DC gain: {report.dc_gain}")
    if report.numerator is not None:
        print(f"Transfer function: num={list(report.numerator)} den={list(report.denominator)}")
    print(f"Poles: {name}")
    if report.zeros:
        print(f"Zeros: {_format_complex(report.zeros)}")
    print(f"BIBO stable: {stability.bibo_stable} - {stability.bibo_reason}")
    print(f"Lyapunov asymptotic: {stability.lyapunov_asymptotic} - {stability.lyapunov_reason}")

    if model.input_count == 1 and model.output_count == 1 and not args.no_step:
        result = simulate_state_space(
            model, args.stop_time / 2000.0, args.stop_time, lambda _t: (1.0,)
        )
        metrics = step_metrics(result.time, result.outputs["y1"])
        print(
            "Step metrics: "
            f"rise={metrics.rise_time_s} s, settling={metrics.settling_time_s} s, "
            f"overshoot={metrics.overshoot_percent}%, peak={metrics.peak}"
        )

    if args.bode:
        plot_bode_margins(bode_margins(model), output_path=args.bode)
        print(f"Wrote Bode/margins plot to {args.bode}")
    if args.nyquist:
        plot_nyquist(nyquist_response(model), output_path=args.nyquist)
        print(f"Wrote Nyquist plot to {args.nyquist}")
    if args.rlocus:
        plot_root_locus(root_locus(model), output_path=args.rlocus)
        print(f"Wrote root-locus plot to {args.rlocus}")


def _command_tune(args) -> None:
    model = _load_analysis_plant(args.config)
    if args.method == "zn":
        result = ziegler_nichols(model)
        if result.ku is not None:
            print(f"Method: Ziegler-Nichols ultimate   Ku={result.ku:.6g}   Pu={result.pu:.6g} s")
        else:
            assert result.fopdt is not None
            fit = result.fopdt
            print(
                "Method: Ziegler-Nichols reaction curve   "
                f"K={fit.gain:.6g}, tau={fit.time_constant_s:.6g} s, "
                f"theta={fit.dead_time_s:.6g} s"
            )
        print(
            f"PID gains: Kp={result.gains.kp:.6g} Ki={result.gains.ki:.6g} Kd={result.gains.kd:.6g}"
        )
        if result.p_gains is not None:
            print(f"P gains:   Kp={result.p_gains.kp:.6g}")
        if result.pi_gains is not None:
            print(f"PI gains:  Kp={result.pi_gains.kp:.6g} Ki={result.pi_gains.ki:.6g}")
    else:
        poles = _parse_complex_list(args.poles)
        result = tune_pole_placement(model, poles)
        if result.state_feedback_k is not None:
            for index, row in enumerate(result.state_feedback_k):
                print(f"State-feedback row {index + 1}: {_format_row(row)}")
        print(
            f"PID gains: Kp={result.gains.kp:.6g} Ki={result.gains.ki:.6g} Kd={result.gains.kd:.6g}"
        )
    print(result.message)


def _command_sf(args) -> None:
    model = _load_analysis_plant(args.config)
    if args.method == "ackermann":
        poles = _parse_complex_list(args.poles)
        result = ackermann(model, poles)
    else:
        q = _parse_float_list(args.q)
        result = lqr(model, q, args.r)
    for index, row in enumerate(result.closed_loop_k):
        print(f"K row {index + 1}: {_format_row(row)}")
    print(f"N-bar: {result.nbar}")
    print(f"Controllability rank: {result.controllability_rank} (order {result.order})")
    print(f"Closed-loop poles: {_format_complex(result.closed_loop_poles)}")
    if args.csv_output:
        write_state_feedback_csv(result, args.csv_output)
        print(f"Wrote step comparison to {args.csv_output}")
    print(result.message)


def _command_interconnect(args) -> None:
    spec = load_interconnect_spec(args.config)
    result = interconnect(spec)
    print(f"Composite: num={list(result.composite_num)} den={list(result.composite_den)}")
    print(f"BIBO stable: {result.stability.bibo_stable} - {result.stability.bibo_reason}")
    if result.margins.phase_margin_deg is not None:
        print(f"Phase margin: {result.margins.phase_margin_deg:.2f} deg")
    if result.margins.gain_margin is not None:
        print(
            f"Gain margin: {result.margins.gain_margin:.4g} "
            f"({result.margins.gain_margin_db:.2f} dB)"
        )
    print(f"Step settles at: {result.step.output[-1]:.6g}")
    if args.bode:
        plot_bode_margins(result.margins, output_path=args.bode)
        print(f"Wrote Bode/margins plot to {args.bode}")
    if args.nyquist:
        plot_nyquist(result.nyquist, output_path=args.nyquist)
        print(f"Wrote Nyquist plot to {args.nyquist}")
    if args.rlocus:
        plot_root_locus(result.root_locus, output_path=args.rlocus)
        print(f"Wrote root-locus plot to {args.rlocus}")


def _command_block_diagram(args) -> None:
    """Compose a block-diagram canvas and report the closed-loop analysis."""
    document = load_block_diagram(args.config)
    result = interconnect_graph(document.to_graph())
    print(
        f"Blocks: {len(document.nodes)} | Connections: {len(document.edges)} | "
        f"reference -> {document.input_node} | tap -> {document.output_node}"
    )
    print(f"Composite: num={list(result.composite_num)} den={list(result.composite_den)}")
    print(f"BIBO stable: {result.stability.bibo_stable} - {result.stability.bibo_reason}")
    if result.margins.phase_margin_deg is not None:
        print(f"Phase margin: {result.margins.phase_margin_deg:.2f} deg")
    if result.margins.gain_margin is not None:
        print(
            f"Gain margin: {result.margins.gain_margin:.4g} "
            f"({result.margins.gain_margin_db:.2f} dB)"
        )
    print(f"Step settles at: {result.step.output[-1]:.6g}")
    if args.bode:
        plot_bode_margins(result.margins, output_path=args.bode)
        print(f"Wrote Bode/margins plot to {args.bode}")
    if args.nyquist:
        plot_nyquist(result.nyquist, output_path=args.nyquist)
        print(f"Wrote Nyquist plot to {args.nyquist}")
    if args.rlocus:
        plot_root_locus(result.root_locus, output_path=args.rlocus)
        print(f"Wrote root-locus plot to {args.rlocus}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="pycircuits-sim")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run a buck converter simulation")
    run_parser.add_argument("config", help="path to a JSON simulation configuration")
    run_parser.add_argument("--output", default="waveforms.csv", help="output CSV path")
    plot_parser = subparsers.add_parser("plot", help="plot a waveform CSV")
    plot_parser.add_argument("input", help="path to a waveform CSV")
    plot_parser.add_argument("--output", default="waveforms.png", help="output image path")
    plot_parser.add_argument(
        "--show", action="store_true", help="also open an interactive plot window"
    )
    sweep_parser = subparsers.add_parser("sweep", help="run and plot a parameter sweep")
    sweep_parser.add_argument("config", help="path to a sweep JSON configuration")
    sweep_parser.add_argument("--csv-output", default="sweep.csv", help="long-form output CSV path")
    sweep_parser.add_argument("--plot-output", default="sweep.png", help="overlay plot image path")
    sweep_parser.add_argument(
        "--metrics-output", default="sweep_metrics.csv", help="per-run metrics CSV path"
    )
    sweep_parser.add_argument(
        "--steady-state-fraction",
        type=float,
        default=0.1,
        help="final sample fraction used for steady-state metrics",
    )
    sweep_parser.add_argument(
        "--settling-band",
        type=float,
        default=0.02,
        help="relative settling band, for example 0.02 for 2 percent",
    )
    sweep_parser.add_argument(
        "--show", action="store_true", help="also open an interactive plot window"
    )
    closed_parser = subparsers.add_parser(
        "closed-loop", help="run a PID-controlled buck simulation"
    )
    closed_parser.add_argument("config", help="path to a closed-loop JSON configuration")
    closed_parser.add_argument(
        "--csv-output", default="closed_loop.csv", help="controller and plant trace CSV"
    )
    closed_parser.add_argument(
        "--plot-output", default="closed_loop.png", help="closed-loop plot image"
    )
    closed_parser.add_argument(
        "--show", action="store_true", help="also open an interactive plot window"
    )
    mna_parser = subparsers.add_parser(
        "mna", help="simulate a component netlist with transient MNA"
    )
    mna_parser.add_argument("config", help="path to an MNA JSON netlist")
    mna_parser.add_argument("--csv-output", default="circuit.csv", help="node/component trace CSV")
    mna_parser.add_argument("--plot-output", default="circuit.png", help="node-voltage plot image")
    mna_parser.add_argument(
        "--show", action="store_true", help="also open an interactive plot window"
    )
    analyze_parser = subparsers.add_parser(
        "analyze", help="analyze a continuous SISO plant (report, stability, metrics)"
    )
    analyze_parser.add_argument("config", help="path to a plant JSON file")
    analyze_parser.add_argument(
        "--stop-time", type=float, default=10.0, help="horizon for step metrics"
    )
    analyze_parser.add_argument("--no-step", action="store_true", help="skip step-response metrics")
    analyze_parser.add_argument("--bode", metavar="PNG", help="write a Bode/margins plot")
    analyze_parser.add_argument("--nyquist", metavar="PNG", help="write a Nyquist plot")
    analyze_parser.add_argument("--rlocus", metavar="PNG", help="write a root-locus plot")
    tune_parser = subparsers.add_parser(
        "tune", help="tune PID gains (Ziegler-Nichols or pole placement)"
    )
    tune_parser.add_argument("config", help="path to a plant JSON file")
    tune_parser.add_argument(
        "--method", choices=["zn", "pole-placement"], default="zn", help="tuning method"
    )
    tune_parser.add_argument(
        "--poles", default="", help="desired poles for pole placement, e.g. '-2+1j, -2-1j'"
    )
    sf_parser = subparsers.add_parser("sf", help="design full state feedback (Ackermann or LQR)")
    sf_parser.add_argument("config", help="path to a plant JSON file")
    sf_parser.add_argument(
        "--method", choices=["ackermann", "lqr"], default="ackermann", help="design method"
    )
    sf_parser.add_argument(
        "--poles", default="", help="desired poles for Ackermann, e.g. '-2, -3+1j, -3-1j'"
    )
    sf_parser.add_argument("--q", default="1", help="diagonal Q entries for LQR, e.g. '1,1'")
    sf_parser.add_argument("--r", type=float, default=1.0, help="control weight R for LQR")
    sf_parser.add_argument("--csv-output", default=None, help="open/closed step comparison CSV")
    interconnect_parser = subparsers.add_parser(
        "interconnect", help="compose blocks and analyze the resulting closed loop"
    )
    interconnect_parser.add_argument("config", help="path to an interconnect JSON file")
    interconnect_parser.add_argument("--bode", metavar="PNG", help="write a Bode/margins plot")
    interconnect_parser.add_argument("--nyquist", metavar="PNG", help="write a Nyquist plot")
    interconnect_parser.add_argument("--rlocus", metavar="PNG", help="write a root-locus plot")
    block_parser = subparsers.add_parser(
        "block-diagram",
        help="compose a block-diagram canvas and analyze the resulting closed loop",
    )
    block_parser.add_argument("config", help="path to a block-diagram JSON file")
    block_parser.add_argument("--bode", metavar="PNG", help="write a Bode/margins plot")
    block_parser.add_argument("--nyquist", metavar="PNG", help="write a Nyquist plot")
    block_parser.add_argument("--rlocus", metavar="PNG", help="write a root-locus plot")
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
    elif args.command == "analyze":
        _run_with_errors(_command_analyze, args)
    elif args.command == "tune":
        if args.method == "pole-placement" and not args.poles:
            parser.error("tune --method pole-placement requires --poles")
        _run_with_errors(_command_tune, args)
    elif args.command == "sf":
        if args.method == "ackermann" and not args.poles:
            parser.error("sf --method ackermann requires --poles")
        _run_with_errors(_command_sf, args)
    elif args.command == "interconnect":
        _run_with_errors(_command_interconnect, args)
    elif args.command == "block-diagram":
        _run_with_errors(_command_block_diagram, args)


def _run_with_errors(command, args) -> None:
    """Run a command, mapping ValueErrors to a clean one-line message."""
    try:
        command(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
