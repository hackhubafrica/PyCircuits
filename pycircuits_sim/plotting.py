"""Waveform plotting helpers kept separate from the simulation engine."""

from __future__ import annotations

from pathlib import Path

from .analysis.margins import MarginResult
from .analysis.nyquist import NyquistResult
from .analysis.root_locus import RootLocusResult
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
    if any(run.parameter != parameter or run.result.time != reference_time for run in runs):
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


def _analysis_output(figure, output_path: str | Path | None, show: bool, title: str):
    import matplotlib.pyplot as plt

    if output_path is None and not show:
        raise ValueError("provide output_path or set show=True")
    figure.suptitle(title)
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=160)
    if show:
        plt.show()
    return figure


def plot_bode_margins(
    margins: MarginResult,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Plot Bode magnitude/phase with gain/phase margin annotations."""
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 1, sharex=True, figsize=(10, 6), layout="constrained")
    frequency = margins.frequencies_rad_s
    axes[0].semilogx(frequency, margins.magnitude_db, color="#167d83", linewidth=1.2)
    axes[0].axhline(0.0, color="#383838", linewidth=0.8, linestyle="--")
    axes[0].set_ylabel("Magnitude (dB)")
    if margins.gain_crossover_rad_s is not None:
        axes[0].axvline(margins.gain_crossover_rad_s, color="#b07a16", linewidth=0.9, linestyle=":")
    axes[1].semilogx(frequency, margins.phase_deg, color="#c54b35", linewidth=1.2)
    axes[1].axhline(-180.0, color="#383838", linewidth=0.8, linestyle="--")
    axes[1].set_ylabel("Phase (degrees)")
    axes[1].set_xlabel("Frequency (rad/s)")
    if margins.phase_crossover_rad_s is not None:
        axes[1].axvline(
            margins.phase_crossover_rad_s, color="#b07a16", linewidth=0.9, linestyle=":"
        )
    for axis in axes:
        axis.grid(True, which="both", alpha=0.25)
    legend = []
    if margins.phase_margin_deg is not None:
        legend.append(f"PM = {margins.phase_margin_deg:.1f} deg")
    if margins.gain_margin is not None:
        legend.append(f"GM = {margins.gain_margin:.3g} ({margins.gain_margin_db:.1f} dB)")
    if legend:
        axes[0].legend([", ".join(legend)], loc="best")
    return _analysis_output(figure, output_path, show, "Bode magnitude/phase with margins")


def plot_nyquist(
    result: NyquistResult,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Plot the Nyquist diagram (imaginary vs real axis)."""
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(6, 6), layout="constrained")
    axis.plot(result.real, result.imaginary, color="#167d83", linewidth=1.2)
    axis.plot([-1.0], [0.0], marker="x", color="#c54b35", markersize=9)
    axis.axhline(0.0, color="#383838", linewidth=0.6)
    axis.axvline(0.0, color="#383838", linewidth=0.6)
    axis.set_xlabel("Re G(jw)")
    axis.set_ylabel("Im G(jw)")
    axis.set_aspect("equal", adjustable="datalim")
    axis.grid(True, alpha=0.25)
    return _analysis_output(figure, output_path, show, "Nyquist plot")


def plot_root_locus(
    result: RootLocusResult,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Plot root-locus branches with open-loop pole/zero markers."""
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(8, 6), layout="constrained")
    colors = ["#167d83", "#c54b35", "#b07a16", "#5a4fa0", "#383835", "#7a2f8a"]
    for index, branch in enumerate(result.branches):
        real = [root.real for root in branch]
        imag = [root.imag for root in branch]
        axis.plot(
            real,
            imag,
            color=colors[index % len(colors)],
            linewidth=1.0,
            label=f"Branch {index + 1}",
        )
    pole_real = [pole.real for pole in result.open_loop_poles]
    pole_imag = [pole.imag for pole in result.open_loop_poles]
    axis.plot(
        pole_real,
        pole_imag,
        marker="x",
        color="#383838",
        linestyle="none",
        markersize=9,
        label="Open-loop poles",
    )
    if result.open_loop_zeros:
        zero_real = [zero.real for zero in result.open_loop_zeros]
        zero_imag = [zero.imag for zero in result.open_loop_zeros]
        axis.plot(
            zero_real,
            zero_imag,
            marker="o",
            color="#383838",
            linestyle="none",
            markersize=7,
            label="Open-loop zeros",
        )
    axis.axhline(0.0, color="#888888", linewidth=0.6)
    axis.axvline(0.0, color="#888888", linewidth=0.6)
    axis.set_xlabel("Real part")
    axis.set_ylabel("Imaginary part")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best", fontsize=8)
    return _analysis_output(figure, output_path, show, "Root locus")
