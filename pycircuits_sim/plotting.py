"""Waveform plotting helpers kept separate from the simulation engine."""

from __future__ import annotations

from pathlib import Path

from .closed_loop import ClosedLoopResult
from .io import WaveformData
from .mna import CircuitResult
from .sweep import SWEEPABLE_PARAMETERS, SweepRun


def plot_waveforms(
    waveforms: WaveformData,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Plot voltage, inductor current, and PWM state; optionally save/show it."""
    if output_path is None and not show:
        raise ValueError("provide output_path or set show=True")

    import matplotlib.pyplot as plt

    stop_time = waveforms.time[-1]
    if stop_time < 0.001:
        time_scale, time_unit = 1_000_000, "us"
    elif stop_time < 1:
        time_scale, time_unit = 1_000, "ms"
    else:
        time_scale, time_unit = 1, "s"
    scaled_time = [time * time_scale for time in waveforms.time]

    figure, axes = plt.subplots(
        3,
        1,
        sharex=True,
        figsize=(10, 7),
        gridspec_kw={"height_ratios": [2, 2, 0.8]},
        layout="constrained",
    )
    axes[0].plot(scaled_time, waveforms.output_voltage, color="#c54b35", linewidth=1.2)
    axes[0].set_ylabel("Output voltage (V)")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(scaled_time, waveforms.inductor_current, color="#167d83", linewidth=1.2)
    axes[1].set_ylabel("Inductor current (A)")
    axes[1].grid(True, alpha=0.25)

    axes[2].step(
        scaled_time,
        [int(state) for state in waveforms.switch_on],
        where="post",
        color="#383838",
        linewidth=1.0,
    )
    axes[2].set_ylabel("PWM")
    axes[2].set_yticks([0, 1])
    axes[2].set_yticklabels(["OFF", "ON"])
    axes[2].set_xlabel(f"Time ({time_unit})")
    axes[2].grid(True, axis="x", alpha=0.25)
    figure.suptitle("Buck converter waveforms")

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=160)
    if show:
        plt.show()

    return figure, axes


def plot_sweep(
    runs: list[SweepRun],
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Overlay output voltage and inductor current for a parameter sweep."""
    if output_path is None and not show:
        raise ValueError("provide output_path or set show=True")
    if not runs:
        raise ValueError("cannot plot an empty parameter sweep")

    parameter = runs[0].parameter
    if parameter not in SWEEPABLE_PARAMETERS:
        raise ValueError(f"unsupported sweep parameter {parameter!r}")
    reference_time = runs[0].result.time
    if any(
        run.parameter != parameter or run.result.time != reference_time
        for run in runs
    ):
        raise ValueError("sweep traces must share a parameter and time grid")

    import matplotlib.pyplot as plt

    stop_time = reference_time[-1]
    if stop_time < 0.001:
        time_scale, time_unit = 1_000_000, "us"
    elif stop_time < 1:
        time_scale, time_unit = 1_000, "ms"
    else:
        time_scale, time_unit = 1, "s"
    scaled_time = [time * time_scale for time in reference_time]

    figure, axes = plt.subplots(
        2,
        1,
        sharex=True,
        figsize=(10, 6),
        layout="constrained",
    )
    color_map = plt.get_cmap("tab10")
    for index, run in enumerate(runs):
        if parameter == "inductance":
            label = f"L = {run.value * 1_000_000:g} uH"
        elif parameter == "capacitance":
            label = f"C = {run.value * 1_000_000:g} uF"
        elif parameter == "load_resistance":
            label = f"R = {run.value:g} ohm"
        else:
            label = f"Duty = {run.value * 100:g}%"
        color = color_map(index % 10)
        axes[0].plot(
            scaled_time,
            run.result.output_voltage,
            color=color,
            linewidth=1.2,
            label=label,
        )
        axes[1].plot(
            scaled_time,
            run.result.inductor_current,
            color=color,
            linewidth=1.2,
            label=label,
        )

    axes[0].set_ylabel("Output voltage (V)")
    axes[1].set_ylabel("Inductor current (A)")
    axes[1].set_xlabel(f"Time ({time_unit})")
    for axis in axes:
        axis.grid(True, alpha=0.25)
        axis.legend()
    figure.suptitle(f"Buck converter sweep: {parameter.replace('_', ' ')}")

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=160)
    if show:
        plt.show()

    return figure, axes


def plot_closed_loop(
    result: ClosedLoopResult,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Plot reference/output, error, PID terms, and controller duty."""
    if output_path is None and not show:
        raise ValueError("provide output_path or set show=True")

    import matplotlib.pyplot as plt

    stop_time = result.time[-1]
    if stop_time < 0.001:
        time_scale, time_unit = 1_000_000, "us"
    elif stop_time < 1:
        time_scale, time_unit = 1_000, "ms"
    else:
        time_scale, time_unit = 1, "s"
    scaled_time = [time * time_scale for time in result.time]

    figure, axes = plt.subplots(
        4,
        1,
        sharex=True,
        figsize=(10, 9),
        gridspec_kw={"height_ratios": [2, 1, 1.5, 1]},
        layout="constrained",
    )
    axes[0].plot(
        scaled_time,
        result.reference_voltage,
        color="#383838",
        linestyle="--",
        linewidth=1.2,
        label="Reference",
    )
    axes[0].plot(
        scaled_time,
        result.output_voltage,
        color="#c54b35",
        linewidth=1.2,
        label="Output",
    )
    axes[0].set_ylabel("Voltage (V)")
    axes[0].legend(loc="best")

    axes[1].plot(scaled_time, result.error, color="#167d83", linewidth=1.1)
    axes[1].set_ylabel("Error (V)")

    axes[2].plot(scaled_time, result.proportional_term, label="P", linewidth=1.0)
    axes[2].plot(scaled_time, result.integral_term, label="I", linewidth=1.0)
    axes[2].plot(scaled_time, result.derivative_term, label="D", linewidth=1.0)
    axes[2].set_ylabel("PID terms")
    axes[2].legend(loc="best", ncols=3)

    axes[3].step(
        scaled_time,
        result.duty_cycle,
        where="post",
        color="#b07a16",
        linewidth=1.1,
    )
    axes[3].set_ylabel("Duty")
    axes[3].set_ylim(-0.03, 1.03)
    axes[3].set_xlabel(f"Time ({time_unit})")

    for axis in axes:
        axis.grid(True, alpha=0.25)
    figure.suptitle("Closed-loop buck converter")

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=160)
    if show:
        plt.show()

    return figure, axes


def plot_circuit(
    result: CircuitResult,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Plot all node voltages from a generic MNA circuit result."""
    if output_path is None and not show:
        raise ValueError("provide output_path or set show=True")
    if not result.node_voltages:
        raise ValueError("circuit result contains no node-voltage traces")

    import matplotlib.pyplot as plt

    stop_time = result.time[-1]
    if stop_time < 0.001:
        time_scale, time_unit = 1_000_000, "us"
    elif stop_time < 1:
        time_scale, time_unit = 1_000, "ms"
    else:
        time_scale, time_unit = 1, "s"
    scaled_time = [time * time_scale for time in result.time]

    figure, axis = plt.subplots(figsize=(10, 5), layout="constrained")
    for node, voltage in result.node_voltages.items():
        axis.plot(scaled_time, voltage, linewidth=1.2, label=f"V({node})")
    axis.set_xlabel(f"Time ({time_unit})")
    axis.set_ylabel("Node voltage (V)")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best")
    figure.suptitle("Transient MNA node voltages")

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=160)
    if show:
        plt.show()
    return figure, axis