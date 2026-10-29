"""Interactive browser workbench for the PyCircuits teaching simulator."""

from __future__ import annotations

import ast
import csv
import math
from dataclasses import replace
from io import StringIO

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pycircuits_sim.block_diagram_ui import render_block_diagram_editor
from pycircuits_sim.buck import BuckConfig, simulate_buck
from pycircuits_sim.closed_loop import (
    ClosedLoopConfig,
    PIDConfig,
    ReferenceStep,
    simulate_closed_loop,
)
from pycircuits_sim.control_ui import render_control_analysis
from pycircuits_sim.linear_systems import (
    DiscreteStateSpaceModel,
    LinearPIDConfig,
    StateSpaceModel,
    StepReference,
    discrete_frequency_response,
    frequency_response,
    logarithmic_frequency_grid,
    simulate_discrete_state_space,
    simulate_discrete_state_space_pid,
    simulate_state_space,
    simulate_state_space_pid,
    transfer_function_to_state_space,
)
from pycircuits_sim.mna import MNAConfig, simulate_mna
from pycircuits_sim.schematic_ui import render_schematic_editor

st.set_page_config(
    page_title="PyCircuits Workbench",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root {
        --ink: #172525; --muted: #657675; --paper: #f2f5ef;
        --line: #d7dfd7; --signal: #bc4c35; --teal: #117b75;
    }
    html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stSidebar"] { background: #e4ebe4; border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] label p { color: var(--ink) !important; }
    .workbench-kicker {
        font: 500 12px 'DM Mono', monospace; color: var(--teal); text-transform: uppercase;
    }
    .workbench-title { font-size: 34px; line-height: 1.1; font-weight: 700; margin: 4px 0 8px; }
    .workbench-subtitle { color: var(--muted); margin: 0 0 24px; }
    [data-testid="stMetric"] {
        background: #fff; border: 1px solid var(--line); border-radius: 4px; padding: 14px 16px;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--ink) !important; }
    .stButton > button { border-radius: 4px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def unit_time(stop_time: float) -> tuple[float, str]:
    if stop_time < 0.001:
        return 1e6, "us"
    if stop_time < 1:
        return 1e3, "ms"
    return 1.0, "s"


def csv_download(columns: dict[str, list[float] | list[bool]]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    names = list(columns)
    writer.writerow(names)
    writer.writerows(zip(*(columns[name] for name in names), strict=True))
    return output.getvalue()


def _final_window_ripple(trace: list[float]) -> float:
    """Return the peak-to-peak ripple over the final 10% of ``trace``."""
    window = trace[-max(2, len(trace) // 10) :]
    return max(window) - min(window)


def style_chart(figure: go.Figure) -> go.Figure:
    figure.update_layout(
        template="plotly_white",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font={"family": "Space Grotesk, sans-serif", "color": "#172525"},
    )
    figure.update_xaxes(gridcolor="#e3e9e3", zerolinecolor="#b9c7c0")
    figure.update_yaxes(gridcolor="#e3e9e3", zerolinecolor="#b9c7c0")
    return figure


st.sidebar.markdown("<div class='workbench-kicker'>Simulation setup</div>", unsafe_allow_html=True)
circuit = st.sidebar.selectbox(
    "Circuit",
    [
        "Closed-loop buck",
        "Open-loop buck",
        "Half-wave rectifier",
        "Bridge rectifier",
        "Linear control plant",
        "Control analysis",
        "Block diagram",
        "Schematic editor",
    ],
)
st.sidebar.caption("Adjust component and solver values, then run the simulation.")

st.markdown(
    "<div class='workbench-kicker'>PyCircuits / Interactive lab</div>", unsafe_allow_html=True
)
st.markdown(
    "<div class='workbench-title'>Power Electronics Workbench</div>", unsafe_allow_html=True
)
st.markdown(
    "<div class='workbench-subtitle'>Change a parameter, rerun the model, and "
    "inspect the resulting waveforms.</div>",
    unsafe_allow_html=True,
)

if circuit == "Schematic editor":
    render_schematic_editor()

elif circuit == "Block diagram":
    render_block_diagram_editor()

elif circuit == "Control analysis":
    render_control_analysis()

elif circuit == "Linear control plant":
    left, right = st.columns([0.72, 0.28], gap="large")
    with st.sidebar:
        st.subheader("Plant representation")
        representation = st.radio(
            "Model format",
            ["State-space matrices", "Discrete state-space", "Transfer function"],
            horizontal=False,
        )
        linear_mode = st.radio(
            "Analysis",
            ["Open-loop response", "PID feedback", "Frequency response"],
            horizontal=False,
        )
        if representation in {"State-space matrices", "Discrete state-space"}:
            examples = (
                ["First-order low-pass", "Second-order oscillator"]
                if representation == "State-space matrices"
                else ["Discrete first-order lag", "Discrete second-order plant"]
            )
            example = st.selectbox("Load example", examples)
            if example == "First-order low-pass":
                A_text, B_text, C_text, D_text = "[[-10.0]]", "[[10.0]]", "[[1.0]]", "[[0.0]]"
            elif example == "Discrete first-order lag":
                A_text, B_text, C_text, D_text = (
                    "[[0.904837418]]",
                    "[[0.095162582]]",
                    "[[1.0]]",
                    "[[0.0]]",
                )
            elif example == "Discrete second-order plant":
                A_text, B_text, C_text, D_text = (
                    "[[0.98, 0.01], [-0.25, 0.94]]",
                    "[[0.0], [0.25]]",
                    "[[1.0, 0.0]]",
                    "[[0.0]]",
                )
            else:
                A_text, B_text, C_text, D_text = (
                    "[[0.0, 1.0], [-25.0, -4.0]]",
                    "[[0.0], [25.0]]",
                    "[[1.0, 0.0]]",
                    "[[0.0]]",
                )
            with st.expander("Edit A, B, C, D matrices", expanded=True):
                A_text = st.text_area("A", A_text, height=70)
                B_text = st.text_area("B", B_text, height=70)
                C_text = st.text_area("C", C_text, height=70)
                D_text = st.text_area("D", D_text, height=70)
        else:
            example = st.selectbox("Load example", ["First-order lag", "Second-order plant"])
            if example == "First-order lag":
                numerator_text, denominator_text = "[1]", "[1, 1]"
            else:
                numerator_text, denominator_text = "[25]", "[1, 4, 25]"
            numerator_text = st.text_input(
                "Numerator coefficients, descending powers of s", numerator_text
            )
            denominator_text = st.text_input(
                "Denominator coefficients, descending powers of s", denominator_text
            )

        if representation == "Discrete state-space":
            discrete_sample_time = (
                st.select_slider("Plant sample time (ms)", [1, 2, 5, 10, 20, 50], value=10) * 1e-3
            )
        else:
            discrete_sample_time = None

        if linear_mode == "Frequency response":
            st.subheader("Frequency range")
            nyquist = (
                0.5 / discrete_sample_time if representation == "Discrete state-space" else None
            )
            maximum_decade_limit = max(
                -2, min(7, math.floor(math.log10(nyquist)) if nyquist else 7)
            )
            minimum_upper = min(3, maximum_decade_limit - 1)
            minimum_decade = st.slider(
                "Minimum frequency (decade, Hz)", -4, minimum_upper, min(-2, minimum_upper)
            )
            maximum_decade = st.slider(
                "Maximum frequency (decade, Hz)",
                minimum_decade + 1,
                maximum_decade_limit,
                max(minimum_decade + 1, min(4, maximum_decade_limit)),
            )
            points_per_decade = st.select_slider(
                "Points per decade", [10, 20, 30, 50, 100], value=30
            )
        else:
            st.subheader("Reference and time")
            if linear_mode == "PID feedback":
                reference_initial = st.number_input("Initial reference", value=0.0, step=0.1)
                reference_final = st.number_input("Final reference", value=1.0, step=0.1)
            else:
                input_initial_text = st.text_input("Initial input vector", "[0.0]")
                input_final_text = st.text_input("Final input vector", "[1.0]")
            stop = st.slider("Duration (s)", 0.1, 20.0, 2.0, 0.1)
            if representation == "Discrete state-space":
                time_step = discrete_sample_time
                if linear_mode == "PID feedback":
                    controller_ratio = st.select_slider(
                        "Controller interval (plant samples)", [1, 2, 5, 10], value=1
                    )
                    sample_time = discrete_sample_time * controller_ratio
                else:
                    sample_time = discrete_sample_time
            else:
                sample_time = (
                    st.select_slider("Controller sample time (ms)", [1, 2, 5, 10, 20, 50], value=10)
                    * 1e-3
                )
                integration_ratio = st.select_slider(
                    "Integration steps per controller interval", [2, 5, 10, 20], value=10
                )
                time_step = sample_time / integration_ratio
            reference_step_time = st.slider(
                "Reference step time (s)", 0.0, float(stop), min(0.1, float(stop)), 0.01
            )
            if linear_mode == "PID feedback":
                st.subheader("PID controller")
                kp = st.slider("Kp", 0.0, 20.0, 1.0, 0.05)
                ki = st.slider("Ki", 0.0, 50.0, 4.0, 0.1)
                kd = st.slider("Kd", 0.0, 2.0, 0.0, 0.005)
                output_min = st.number_input("Control minimum", value=0.0, step=0.1)
                output_max = st.number_input("Control maximum", value=3.0, step=0.1)
        run = st.button("Run simulation", type="primary", use_container_width=True)

    current_settings = (
        representation,
        linear_mode,
        example,
        A_text
        if representation in {"State-space matrices", "Discrete state-space"}
        else numerator_text,
        B_text
        if representation in {"State-space matrices", "Discrete state-space"}
        else denominator_text,
        C_text if representation in {"State-space matrices", "Discrete state-space"} else "",
        D_text if representation in {"State-space matrices", "Discrete state-space"} else "",
        (reference_initial, reference_final)
        if linear_mode == "PID feedback"
        else (
            (input_initial_text, input_final_text)
            if linear_mode == "Open-loop response"
            else (minimum_decade, maximum_decade, points_per_decade)
        ),
        stop if linear_mode != "Frequency response" else None,
        sample_time if linear_mode != "Frequency response" else None,
        time_step if linear_mode != "Frequency response" else None,
        discrete_sample_time if representation == "Discrete state-space" else None,
        reference_step_time if linear_mode != "Frequency response" else None,
        kp if linear_mode == "PID feedback" else 0.0,
        ki if linear_mode == "PID feedback" else 0.0,
        kd if linear_mode == "PID feedback" else 0.0,
        output_min if linear_mode == "PID feedback" else 0.0,
        output_max if linear_mode == "PID feedback" else 1.0,
    )
    with right:
        st.markdown("#### Run summary")
        if (
            run
            or "linear_result" not in st.session_state
            or st.session_state.get("linear_settings") != current_settings
        ):
            try:
                if representation in {"State-space matrices", "Discrete state-space"}:
                    model_type = (
                        DiscreteStateSpaceModel
                        if representation == "Discrete state-space"
                        else StateSpaceModel
                    )
                    matrices = (
                        ast.literal_eval(A_text),
                        ast.literal_eval(B_text),
                        ast.literal_eval(C_text),
                        ast.literal_eval(D_text),
                    )
                    model = model_type.from_matrices(
                        *matrices,
                        **(
                            {"sample_time": discrete_sample_time}
                            if representation == "Discrete state-space"
                            else {}
                        ),
                    )
                else:
                    model = transfer_function_to_state_space(
                        ast.literal_eval(numerator_text),
                        ast.literal_eval(denominator_text),
                    )
                st.session_state["linear_model"] = model
                if linear_mode == "Frequency response":
                    max_frequency = 10.0**maximum_decade
                    if representation == "Discrete state-space":
                        max_frequency = min(max_frequency, (0.5 / discrete_sample_time) * 0.99)
                    frequencies = logarithmic_frequency_grid(
                        10.0**minimum_decade,
                        max_frequency,
                        points_per_decade,
                    )
                    result = (
                        discrete_frequency_response(model, frequencies)
                        if representation == "Discrete state-space"
                        else frequency_response(model, frequencies)
                    )
                    st.session_state["linear_frequency_result"] = result
                elif linear_mode == "PID feedback":
                    pid_config = LinearPIDConfig(kp, ki, kd, sample_time, output_min, output_max)
                    reference_config = StepReference(
                        reference_initial, reference_final, reference_step_time
                    )
                    if representation == "Discrete state-space":
                        result = simulate_discrete_state_space_pid(
                            model, pid_config, reference_config, stop_time=stop
                        )
                    else:
                        result = simulate_state_space_pid(
                            model, pid_config, reference_config, time_step=time_step, stop_time=stop
                        )
                else:
                    input_initial = ast.literal_eval(input_initial_text)
                    input_final = ast.literal_eval(input_final_text)
                    if (
                        len(input_initial) != model.input_count
                        or len(input_final) != model.input_count
                    ):
                        raise ValueError(
                            f"input vectors must each contain {model.input_count} values"
                        )

                    def input_signal(time: float) -> list[float]:
                        values = input_initial if time < reference_step_time else input_final
                        return [float(value) for value in values]

                    if representation == "Discrete state-space":
                        result = simulate_discrete_state_space(
                            model, stop_time=stop, input_signal=input_signal
                        )
                    else:
                        result = simulate_state_space(
                            model, time_step=time_step, stop_time=stop, input_signal=input_signal
                        )
                if linear_mode != "Frequency response":
                    st.session_state["linear_result"] = result
                st.session_state["linear_settings"] = current_settings
            except Exception as error:
                st.error(f"Plant or simulation error: {error}")

        model = st.session_state.get("linear_model")
        result = st.session_state.get("linear_result")
        frequency_result = st.session_state.get("linear_frequency_result")
        if (
            linear_mode == "Frequency response"
            and frequency_result is not None
            and st.session_state.get("linear_settings") == current_settings
        ):
            st.metric("System order", str(model.state_count))
            discrete = representation == "Discrete state-space"
            stable = (
                all(abs(pole) < 1.0 for pole in frequency_result.poles)
                if discrete
                else all(pole.real < 0 for pole in frequency_result.poles)
            )
            stability_label = "Discrete-time stability" if discrete else "Continuous-time stability"
            stability_value = "Stable" if stable else "Unstable / marginal"
            st.metric(stability_label, stability_value)
            pole_lines = [
                f"p{index + 1} = {pole.real:.5g}{pole.imag:+.5g}j"
                for index, pole in enumerate(frequency_result.poles)
            ]
            st.code("\n".join(pole_lines) if pole_lines else "No poles")
            bode_columns: dict[str, list[float]] = {"frequency_hz": frequency_result.frequencies_hz}
            for output_index in range(model.output_count):
                for input_index in range(model.input_count):
                    bode_columns[f"magnitude_y{output_index + 1}_u{input_index + 1}_db"] = [
                        item[output_index][input_index] for item in frequency_result.magnitude_db
                    ]
                    bode_columns[f"phase_y{output_index + 1}_u{input_index + 1}_deg"] = [
                        item[output_index][input_index] for item in frequency_result.phase_deg
                    ]
            st.download_button(
                "Download Bode data CSV",
                csv_download(bode_columns),
                file_name="bode_response.csv",
                mime="text/csv",
                use_container_width=True,
            )
        elif result is not None and st.session_state.get("linear_settings") == current_settings:
            if linear_mode == "PID feedback":
                st.metric(
                    "Final output", f"{result.output[-1]:.4g}", f"target {result.reference[-1]:.4g}"
                )
                st.metric("Peak output", f"{max(result.output):.4g}")
                st.metric("Final error", f"{result.error[-1]:.4g}")
                st.metric("Peak control", f"{max(result.control):.4g}")
                download_columns = {
                    "time_s": result.time,
                    "reference": result.reference,
                    "output": result.output,
                    "error": result.error,
                    "control": result.control,
                    "P": result.proportional_term,
                    "I": result.integral_term,
                    "D": result.derivative_term,
                    **result.states,
                }
            else:
                for output_name, trace in result.outputs.items():
                    st.metric(f"Final {output_name}", f"{trace[-1]:.4g}")
                download_columns = {
                    "time_s": result.time,
                    **result.inputs,
                    **result.outputs,
                    **result.states,
                }
            st.download_button(
                "Download plant response CSV",
                csv_download(download_columns),
                file_name="linear_plant_response.csv",
                mime="text/csv",
                use_container_width=True,
            )

    model = st.session_state.get("linear_model")
    result = st.session_state.get("linear_result")
    frequency_result = st.session_state.get("linear_frequency_result")
    if (
        linear_mode == "Frequency response"
        and frequency_result is not None
        and st.session_state.get("linear_settings") == current_settings
    ):
        figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09)
        frequency_values = frequency_result.frequencies_hz
        colors = ["#bc4c35", "#117b75", "#b07a16", "#485caa", "#873d63", "#4a7970"]
        for output_index in range(model.output_count):
            for input_index in range(model.input_count):
                label = f"Y{output_index + 1}/U{input_index + 1}"
                color = colors[(output_index * model.input_count + input_index) % len(colors)]
                magnitude = [
                    item[output_index][input_index] for item in frequency_result.magnitude_db
                ]
                phase = [item[output_index][input_index] for item in frequency_result.phase_deg]
                figure.add_trace(
                    go.Scatter(x=frequency_values, y=magnitude, name=label, line={"color": color}),
                    row=1,
                    col=1,
                )
                figure.add_trace(
                    go.Scatter(
                        x=frequency_values,
                        y=phase,
                        name=label,
                        line={"color": color},
                        showlegend=False,
                    ),
                    row=2,
                    col=1,
                )
        figure.update_xaxes(type="log", title_text="Frequency (Hz)", row=2, col=1)
        figure.update_xaxes(type="log", row=1, col=1)
        figure.update_yaxes(title_text="Magnitude (dB)", row=1, col=1)
        figure.update_yaxes(title_text="Phase (degrees)", row=2, col=1)
        figure.update_layout(
            height=700, hovermode="x unified", margin={"l": 10, "r": 10, "t": 30, "b": 10}
        )
        left.plotly_chart(style_chart(figure), use_container_width=True, theme=None)
    elif result is not None and st.session_state.get("linear_settings") == current_settings:
        scale, time_label = unit_time(result.time[-1])
        times = [value * scale for value in result.time]
        if linear_mode == "PID feedback":
            figure = make_subplots(
                rows=3,
                cols=1,
                shared_xaxes=True,
                row_heights=[0.5, 0.22, 0.28],
                vertical_spacing=0.07,
            )
            figure.add_trace(
                go.Scatter(
                    x=times,
                    y=result.reference,
                    name="Reference",
                    line={"dash": "dash", "color": "#354543"},
                ),
                row=1,
                col=1,
            )
            figure.add_trace(
                go.Scatter(
                    x=times,
                    y=result.output,
                    name="Plant output",
                    line={"color": "#bc4c35", "width": 2},
                ),
                row=1,
                col=1,
            )
            figure.add_trace(
                go.Scatter(x=times, y=result.error, name="Error", line={"color": "#117b75"}),
                row=2,
                col=1,
            )
            figure.add_trace(
                go.Scatter(
                    x=times,
                    y=result.control,
                    name="Controller output",
                    line={"color": "#b07a16", "shape": "hv"},
                ),
                row=3,
                col=1,
            )
            figure.update_yaxes(title_text="Reference / output", row=1, col=1)
            figure.update_yaxes(title_text="Error", row=2, col=1)
            figure.update_yaxes(title_text="Control", row=3, col=1)
            figure.update_xaxes(title_text=f"Time ({time_label})", row=3, col=1)
            figure.update_layout(
                height=700, hovermode="x unified", margin={"l": 10, "r": 10, "t": 30, "b": 10}
            )
        else:
            figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08)
            for name, trace in result.outputs.items():
                figure.add_trace(go.Scatter(x=times, y=trace, name=f"Output {name}"), row=1, col=1)
            for name, trace in result.inputs.items():
                figure.add_trace(
                    go.Scatter(x=times, y=trace, name=f"Input {name}", line={"dash": "dot"}),
                    row=2,
                    col=1,
                )
            figure.update_yaxes(title_text="Plant outputs", row=1, col=1)
            figure.update_yaxes(title_text="Plant inputs", row=2, col=1)
            figure.update_xaxes(title_text=f"Time ({time_label})", row=2, col=1)
            figure.update_layout(
                height=650, hovermode="x unified", margin={"l": 10, "r": 10, "t": 30, "b": 10}
            )
        left.plotly_chart(style_chart(figure), use_container_width=True, theme=None)

elif circuit in {"Open-loop buck", "Closed-loop buck"}:
    left, right = st.columns([0.72, 0.28], gap="large")
    with st.sidebar:
        st.subheader("Power stage")
        vin = st.slider("Input voltage (V)", 3.0, 48.0, 12.0, 0.5)
        inductance = st.slider("Inductance (mH)", 0.05, 10.0, 1.0, 0.05) * 1e-3
        capacitance = st.slider("Capacitance (uF)", 1.0, 5000.0, 100.0, 1.0) * 1e-6
        load = st.slider("Load resistance (ohm)", 0.5, 200.0, 10.0, 0.5)
        frequency = st.slider("Switching frequency (kHz)", 1.0, 100.0, 10.0, 0.5) * 1000
        st.subheader("Simulation")
        stop = st.slider("Duration (ms)", 1.0, 100.0, 20.0, 1.0) * 1e-3
        step_ratio = st.select_slider("Steps per switching period", [10, 20, 40, 80, 100], value=40)
        step = min(1.0 / frequency / step_ratio, stop / 100)
        closed = circuit == "Closed-loop buck"
        if closed:
            st.subheader("PID controller")
            reference = st.slider(
                "Voltage reference (V)", 0.5, min(vin * 0.9, 40.0), min(5.0, vin * 0.5), 0.1
            )
            kp = st.slider("Kp", 0.0, 1.0, 0.12, 0.005)
            ki = st.slider("Ki (1/s)", 0.0, 200.0, 50.0, 1.0)
            kd = st.slider("Kd (s)", 0.0, 0.001, 0.00005, 0.000005, format="%.6f")
            sample_ratio = st.select_slider(
                "Controller interval (switching periods)", [1, 2, 5, 10], value=1
            )
            controller_dt = 1.0 / frequency * sample_ratio
            step = min(step, controller_dt / 10)
            step = round(step / 1e-9) * 1e-9
            duty = 0.5
        else:
            duty = st.slider("Duty cycle", 0.0, 0.95, 0.5, 0.01)
        run = st.button("Run simulation", type="primary", use_container_width=True)

    with right:
        st.markdown("#### Run summary")
        if (
            run
            or "buck_result" not in st.session_state
            or st.session_state.get("buck_mode") != circuit
        ):
            try:
                if closed:
                    controller_dt = max(controller_dt, step)
                    config = ClosedLoopConfig(
                        plant=BuckConfig(
                            vin, 0.3, frequency, inductance, capacitance, load, step, stop
                        ),
                        controller=PIDConfig(kp, ki, kd, controller_dt, 0.0, 0.95),
                        reference=ReferenceStep(0.0, reference, min(stop * 0.1, controller_dt)),
                    )
                    result = simulate_closed_loop(config)
                    st.session_state["buck_result"] = result
                    st.session_state["buck_mode"] = circuit
                else:
                    config = BuckConfig(
                        vin, duty, frequency, inductance, capacitance, load, step, stop
                    )
                    result = simulate_buck(config)
                    scale, label = unit_time(stop)
                    figure = make_subplots(
                        rows=3,
                        cols=1,
                        shared_xaxes=True,
                        row_heights=[0.45, 0.4, 0.15],
                        vertical_spacing=0.08,
                    )
                    figure.add_trace(
                        go.Scatter(
                            x=[t * scale for t in result.time],
                            y=result.output_voltage,
                            name="Output voltage",
                            line={"color": "#bc4c35", "width": 2},
                        ),
                        row=1,
                        col=1,
                    )
                    figure.add_trace(
                        go.Scatter(
                            x=[t * scale for t in result.time],
                            y=result.inductor_current,
                            name="Inductor current",
                            line={"color": "#117b75", "width": 1.5},
                        ),
                        row=2,
                        col=1,
                    )
                    figure.add_trace(
                        go.Scatter(
                            x=[t * scale for t in result.time],
                            y=[int(v) for v in result.switch_on],
                            name="PWM state",
                            line={"color": "#333f3d", "shape": "hv"},
                        ),
                        row=3,
                        col=1,
                    )
                    figure.update_yaxes(title_text="Vout (V)", row=1, col=1)
                    figure.update_yaxes(title_text="IL (A)", row=2, col=1)
                    figure.update_yaxes(title_text="PWM", tickvals=[0, 1], row=3, col=1)
                    figure.update_xaxes(title_text=f"Time ({label})", row=3, col=1)
                    figure.update_layout(
                        height=650,
                        margin={"l": 10, "r": 10, "t": 30, "b": 10},
                        legend={"orientation": "h", "y": 1.04},
                        hovermode="x unified",
                    )
                    st.session_state["buck_figure"] = figure
                    st.session_state["buck_result"] = result
                    st.session_state["buck_stats"] = (
                        result.output_voltage,
                        result.inductor_current,
                    )
                    st.session_state["buck_mode"] = circuit
                st.session_state["buck_settings"] = (
                    vin,
                    inductance,
                    capacitance,
                    load,
                    frequency,
                    step,
                    stop,
                )
            except Exception as error:
                st.error(f"Simulation failed: {error}")

        if st.session_state.get("buck_mode") == circuit:
            if closed and "buck_result" in st.session_state:
                result = st.session_state["buck_result"]
                values = result.output_voltage
                currents = result.inductor_current
                ref_value = result.reference_voltage[-1]
                st.metric("Final output", f"{values[-1]:.3f} V", f"target {ref_value:.2f} V")
                st.metric("Peak overshoot", f"{max(values):.3f} V")
                st.metric("Peak inductor current", f"{max(currents):.3f} A")
                st.metric("Final error", f"{result.error[-1]:.4f} V")
                st.download_button(
                    "Download waveform CSV",
                    csv_download(
                        {
                            "time_s": result.time,
                            "reference_voltage_v": result.reference_voltage,
                            "output_voltage_v": result.output_voltage,
                            "error_v": result.error,
                            "proportional_term": result.proportional_term,
                            "integral_term": result.integral_term,
                            "derivative_term": result.derivative_term,
                            "duty_cycle": result.duty_cycle,
                            "inductor_current_a": result.inductor_current,
                            "switch_on": result.switch_on,
                        }
                    ),
                    file_name="closed_loop.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            elif not closed and "buck_stats" in st.session_state:
                voltage_trace, current_trace = st.session_state["buck_stats"]
                st.metric("Final output", f"{voltage_trace[-1]:.3f} V")
                st.metric("Peak voltage", f"{max(voltage_trace):.3f} V")
                st.metric("Peak inductor current", f"{max(current_trace):.3f} A")
                st.metric(
                    "Voltage ripple, final 10%",
                    f"{_final_window_ripple(voltage_trace):.4f} V",
                )
                result = st.session_state["buck_result"]
                st.download_button(
                    "Download waveform CSV",
                    csv_download(
                        {
                            "time_s": result.time,
                            "output_voltage_v": result.output_voltage,
                            "inductor_current_a": result.inductor_current,
                            "switch_on": result.switch_on,
                        }
                    ),
                    file_name="buck_waveforms.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    if circuit == "Closed-loop buck" and "buck_result" in st.session_state:
        result = st.session_state["buck_result"]
        scale, time_label = unit_time(result.time[-1])
        figure = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.38, 0.18, 0.27, 0.17],
            vertical_spacing=0.06,
        )
        time_values = [value * scale for value in result.time]
        figure.add_trace(
            go.Scatter(
                x=time_values,
                y=result.reference_voltage,
                name="Reference",
                line={"dash": "dash", "color": "#354543"},
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=time_values,
                y=result.output_voltage,
                name="Output",
                line={"color": "#bc4c35", "width": 2},
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(x=time_values, y=result.error, name="Error", line={"color": "#117b75"}),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(x=time_values, y=result.proportional_term, name="P"), row=3, col=1
        )
        figure.add_trace(go.Scatter(x=time_values, y=result.integral_term, name="I"), row=3, col=1)
        figure.add_trace(
            go.Scatter(x=time_values, y=result.derivative_term, name="D"), row=3, col=1
        )
        figure.add_trace(
            go.Scatter(
                x=time_values,
                y=result.duty_cycle,
                name="Duty",
                line_shape="hv",
                line={"color": "#b07a16"},
            ),
            row=4,
            col=1,
        )
        figure.update_yaxes(title_text="Voltage (V)", row=1, col=1)
        figure.update_yaxes(title_text="Error (V)", row=2, col=1)
        figure.update_yaxes(title_text="PID", row=3, col=1)
        figure.update_yaxes(title_text="Duty", range=[-0.03, 1.03], row=4, col=1)
        figure.update_xaxes(title_text=f"Time ({time_label})", row=4, col=1)
        figure.update_layout(
            height=750, hovermode="x unified", margin={"l": 10, "r": 10, "t": 30, "b": 10}
        )
        left.plotly_chart(style_chart(figure), use_container_width=True, theme=None)
    elif circuit == "Open-loop buck" and "buck_figure" in st.session_state:
        left.plotly_chart(
            style_chart(st.session_state["buck_figure"]), use_container_width=True, theme=None
        )

else:
    left, right = st.columns([0.72, 0.28], gap="large")
    circuit_kind = "half" if circuit == "Half-wave rectifier" else "bridge"
    base_config = st.session_state.get(f"{circuit_kind}_base")
    if base_config is None:
        config_path = (
            "examples/half_wave_rectifier.json"
            if circuit_kind == "half"
            else "examples/bridge_rectifier.json"
        )
        from pycircuits_sim.io import load_mna_config_file

        base_config = load_mna_config_file(config_path)
        st.session_state[f"{circuit_kind}_base"] = base_config

    with st.sidebar:
        st.subheader("AC source")
        amplitude = st.slider("Peak amplitude (V)", 2.0, 48.0, 12.0, 0.5)
        frequency = st.slider("Frequency (Hz)", 10.0, 400.0, 50.0, 1.0)
        st.subheader("Output stage")
        load = st.slider("Load resistance (ohm)", 10.0, 1000.0, 100.0, 10.0)
        capacitance = st.slider("Smoothing capacitor (uF)", 10.0, 5000.0, 1000.0, 10.0) * 1e-6
        st.subheader("Numerics")
        cycles = st.slider("Simulated AC cycles", 1, 10, 3)
        samples_per_cycle = st.select_slider("Steps per AC cycle", [100, 200, 400, 800], value=200)
        stop = cycles / frequency
        step = 1.0 / frequency / samples_per_cycle
        run = st.button("Run simulation", type="primary", use_container_width=True)
    with right:
        st.markdown("#### Run summary")
        if (
            run
            or "rectifier_result" not in st.session_state
            or st.session_state.get("rectifier_mode") != circuit
        ):
            source_node = "ac" if circuit_kind == "half" else "ac_a"
            components = []
            for component in base_config.components:
                if component.kind == "voltage_source" and component.name == "VAC":
                    components.append(replace(component, amplitude=amplitude, frequency=frequency))
                elif component.name == "RLOAD":
                    components.append(replace(component, value=load))
                elif component.name == "CFILTER":
                    components.append(replace(component, value=capacitance))
                else:
                    components.append(component)
            config = MNAConfig(
                time_step=step,
                stop_time=stop,
                components=tuple(components),
                max_steps=base_config.max_steps,
                newton_tolerance=base_config.newton_tolerance,
                newton_max_iterations=base_config.newton_max_iterations,
                newton_damping=base_config.newton_damping,
                gmin=base_config.gmin,
            )
            try:
                st.session_state["rectifier_result"] = simulate_mna(config)
                st.session_state["rectifier_mode"] = circuit
                st.session_state["rectifier_circuit_kind"] = circuit_kind
            except Exception as error:
                st.error(f"Simulation failed: {error}")

        if st.session_state.get("rectifier_mode") == circuit:
            result = st.session_state["rectifier_result"]
            if circuit_kind == "half":
                output = result.node_voltages["out"]
            else:
                output = [
                    positive - negative
                    for positive, negative in zip(
                        result.node_voltages["dc_pos"],
                        result.node_voltages["dc_neg"],
                        strict=True,
                    )
                ]
            st.metric("Peak DC output", f"{max(output):.3f} V")
            st.metric("Final DC output", f"{output[-1]:.3f} V")
            window = output[-max(2, len(output) // 10) :]
            st.metric("Ripple, final 10%", f"{max(window) - min(window):.3f} V p-p")
            st.metric(
                "Peak source current",
                f"{max(abs(value) for value in result.component_currents['VAC']):.3f} A",
            )
            columns: dict[str, list[float] | list[bool]] = {"time_s": result.time}
            columns.update(
                {f"node_voltage_{name}_v": values for name, values in result.node_voltages.items()}
            )
            columns.update(
                {
                    f"component_current_{name}_a": values
                    for name, values in result.component_currents.items()
                }
            )
            columns.update(
                {f"switch_{name}_on": values for name, values in result.switch_states.items()}
            )
            st.download_button(
                "Download waveform CSV",
                csv_download(columns),
                file_name=f"{circuit_kind}_rectifier.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if st.session_state.get("rectifier_mode") == circuit:
        result = st.session_state["rectifier_result"]
        scale, time_label = unit_time(result.time[-1])
        times = [time * scale for time in result.time]
        figure = make_subplots(
            rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.08
        )
        if circuit_kind == "half":
            voltage_traces = [
                ("AC input", result.node_voltages["ac"]),
                ("Rectified output", result.node_voltages["out"]),
            ]
            current_traces = [("Diode current", result.component_currents["D1"])]
        else:
            voltage_traces = [
                ("AC input", result.node_voltages["ac_a"]),
                ("Positive rail", result.node_voltages["dc_pos"]),
                ("Negative rail", result.node_voltages["dc_neg"]),
                (
                    "DC output (rail difference)",
                    [
                        p - n
                        for p, n in zip(
                            result.node_voltages["dc_pos"],
                            result.node_voltages["dc_neg"],
                            strict=True,
                        )
                    ],
                ),
            ]
            current_traces = [
                (name, result.component_currents[name]) for name in ("D1", "D2", "D3", "D4")
            ]
        for name, trace in voltage_traces:
            figure.add_trace(
                go.Scatter(x=times, y=trace, name=name, line={"width": 1.5}), row=1, col=1
            )
        for name, trace in current_traces:
            figure.add_trace(
                go.Scatter(x=times, y=trace, name=name, line={"width": 1.0}), row=2, col=1
            )
        figure.update_yaxes(title_text="Voltage (V)", row=1, col=1)
        figure.update_yaxes(title_text="Current (A)", row=2, col=1)
        figure.update_xaxes(title_text=f"Time ({time_label})", row=2, col=1)
        figure.update_layout(
            height=650,
            hovermode="x unified",
            legend={"orientation": "h", "y": 1.08},
            margin={"l": 10, "r": 10, "t": 40, "b": 10},
        )
        left.plotly_chart(style_chart(figure), use_container_width=True, theme=None)

st.caption(
    "Educational fixed-step models. Results depend on timestep and idealized "
    "component assumptions; do not use for hardware safety or design sign-off."
)
