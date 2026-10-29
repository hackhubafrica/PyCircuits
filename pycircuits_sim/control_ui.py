"""Interactive control-analysis workbench (analysis, tuning, state feedback).

Streams the Phase 1-3 engines into the Streamlit UI as a seventh sidebar
mode: plant report, stability, Bode margins, Nyquist, root locus, PID
tuning (Ziegler-Nichols or pole placement), state feedback (Ackermann or
LQR), and a PID-on-motor interconnection demo. Runs are explicit via the
Run button because fine-timestep simulations can take a few seconds.
"""

from __future__ import annotations

import ast

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pycircuits_sim.analysis import (
    analyze_stability,
    bode_margins,
    normalize_plant,
    nyquist_response,
    root_locus,
)
from pycircuits_sim.design import (
    ackermann,
    lqr,
    tune_pole_placement,
    ziegler_nichols,
)
from pycircuits_sim.interconnect import (
    InterconnectBlock,
    InterconnectSpec,
    interconnect,
)
from pycircuits_sim.linear_systems import (
    StateSpaceModel,
    transfer_function_to_state_space,
)

EXAMPLE_PLANTS = {
    "Second-order 1/(s^2+s+1)": {
        "format": "tf",
        "numerator": "[1.0]",
        "denominator": "[1.0, 1.0, 1.0]",
    },
    "DC motor 4/(s(s+12))": {
        "format": "tf",
        "numerator": "[4.0]",
        "denominator": "[1.0, 12.0, 0.0]",
    },
    "Inverted pendulum 1/(s^2-9.81)": {
        "format": "tf",
        "numerator": "[1.0]",
        "denominator": "[1.0, 0.0, -9.81]",
    },
    "Third-order 1/((s+1)(s+2)(s+3))": {
        "format": "tf",
        "numerator": "[1.0]",
        "denominator": "[1.0, 6.0, 11.0, 6.0]",
    },
    "Third-order controllable canonical": {
        "format": "ss",
        "A": "[[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-6.0, -11.0, -6.0]]",
        "B": "[[0.0], [0.0], [1.0]]",
        "C": "[[1.0, 0.0, 0.0]]",
        "D": "[[0.0]]",
    },
    "Oscillator A=[[0,1],[-1,0]]": {
        "format": "ss",
        "A": "[[0.0, 1.0], [-1.0, 0.0]]",
        "B": "[[0.0], [1.0]]",
        "C": "[[1.0, 0.0]]",
        "D": "[[0.0]]",
    },
}

ANALYSES = [
    "Plant report",
    "Stability",
    "Bode & margins",
    "Nyquist",
    "Root locus",
    "PID tuning",
    "State feedback",
    "Interconnect (PID on motor)",
]


def _style_chart(figure: go.Figure) -> go.Figure:
    figure.update_layout(
        template="plotly_white",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font={"family": "Space Grotesk, sans-serif", "color": "#172525"},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
    )
    figure.update_xaxes(gridcolor="#e3e9e3", zerolinecolor="#b9c7c0")
    figure.update_yaxes(gridcolor="#e3e9e3", zerolinecolor="#b9c7c0")
    return figure


def _format_complex(values) -> str:
    def one(value: complex) -> str:
        if abs(value.imag) < 1e-12:
            return f"{value.real:.4g}"
        sign = "+" if value.imag >= 0 else "-"
        return f"{value.real:.4g} {sign} {abs(value.imag):.4g}j"

    return ", ".join(one(complex(value)) for value in values) or "(none)"


def _build_model(
    example: str,
    use_example: bool,
    num_text: str,
    den_text: str,
    a_text: str,
    b_text: str,
    c_text: str,
    d_text: str,
    is_ss: bool,
):
    if use_example:
        data = EXAMPLE_PLANTS[example]
        is_ss = data["format"] == "ss"
        if is_ss:
            return StateSpaceModel.from_matrices(
                ast.literal_eval(data["A"]),
                ast.literal_eval(data["B"]),
                ast.literal_eval(data["C"]),
                ast.literal_eval(data["D"]),
            )
        return transfer_function_to_state_space(
            ast.literal_eval(data["numerator"]),
            ast.literal_eval(data["denominator"]),
        )
    if is_ss:
        return StateSpaceModel.from_matrices(
            ast.literal_eval(a_text),
            ast.literal_eval(b_text),
            ast.literal_eval(c_text),
            ast.literal_eval(d_text),
        )
    return transfer_function_to_state_space(ast.literal_eval(num_text), ast.literal_eval(den_text))


def _parse_poles(text: str) -> list[complex]:
    poles: list[complex] = []
    for token in text.split(","):
        cleaned = token.strip().replace(" ", "").replace("i", "j")
        if not cleaned:
            continue
        poles.append(complex(cleaned))
    if not poles:
        raise ValueError("enter at least one pole, e.g. '-2+1j, -2-1j'")
    return poles


def _bode_figure(margins) -> go.Figure:
    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4], vertical_spacing=0.06
    )
    figure.add_trace(
        go.Scatter(
            x=margins.frequencies_rad_s,
            y=margins.magnitude_db,
            name="Magnitude",
            line={"width": 1.5, "color": "#167d83"},
        ),
        row=1,
        col=1,
    )
    figure.add_hline(y=0.0, line_dash="dash", line_color="#383838", line_width=1, row=1, col=1)
    if margins.gain_crossover_rad_s is not None:
        figure.add_vline(
            x=margins.gain_crossover_rad_s, line_dash="dot", line_color="#b07a16", row=1, col=1
        )
    figure.add_trace(
        go.Scatter(
            x=margins.frequencies_rad_s,
            y=margins.phase_deg,
            name="Phase",
            line={"width": 1.5, "color": "#c54b35"},
        ),
        row=2,
        col=1,
    )
    figure.add_hline(y=-180.0, line_dash="dash", line_color="#383838", line_width=1, row=2, col=1)
    if margins.phase_crossover_rad_s is not None:
        figure.add_vline(
            x=margins.phase_crossover_rad_s, line_dash="dot", line_color="#b07a16", row=2, col=1
        )
    figure.update_xaxes(title_text="Frequency (rad/s)", type="log", row=2, col=1)
    figure.update_yaxes(title_text="Magnitude (dB)", row=1, col=1)
    figure.update_yaxes(title_text="Phase (deg)", row=2, col=1)
    figure.update_layout(height=560, hovermode="x unified", legend={"orientation": "h", "y": 1.08})
    return figure


def _nyquist_figure(nyq) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=nyq.real,
            y=nyq.imaginary,
            mode="lines",
            name="G(jw)",
            line={"width": 1.5, "color": "#167d83"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[-1.0],
            y=[0.0],
            mode="markers",
            name="-1 point",
            marker={"size": 10, "color": "#c54b35", "symbol": "x"},
        )
    )
    figure.update_xaxes(title_text="Re G(jw)", scaleanchor="x", scaleratio=1)
    figure.update_yaxes(title_text="Im G(jw)")
    figure.update_layout(height=520, legend={"orientation": "h", "y": 1.08})
    return figure


def _locus_figure(locus) -> go.Figure:
    figure = go.Figure()
    colors = ["#167d83", "#c54b35", "#b07a16", "#5a4fa0", "#383835", "#7a2f8a"]
    for index, branch in enumerate(locus.branches):
        figure.add_trace(
            go.Scatter(
                x=[root.real for root in branch],
                y=[root.imag for root in branch],
                mode="lines",
                name=f"Branch {index + 1}",
                line={"width": 1.2, "color": colors[index % len(colors)]},
            )
        )
    figure.add_trace(
        go.Scatter(
            x=[pole.real for pole in locus.open_loop_poles],
            y=[pole.imag for pole in locus.open_loop_poles],
            mode="markers",
            name="Open-loop poles",
            marker={"size": 10, "symbol": "x", "color": "#383838"},
        )
    )
    if locus.open_loop_zeros:
        figure.add_trace(
            go.Scatter(
                x=[zero.real for zero in locus.open_loop_zeros],
                y=[zero.imag for zero in locus.open_loop_zeros],
                mode="markers",
                name="Open-loop zeros",
                marker={"size": 9, "symbol": "circle-open", "color": "#383838"},
            )
        )
    figure.update_xaxes(title_text="Real part", zeroline=True)
    figure.update_yaxes(title_text="Imaginary part", zeroline=True, scaleanchor="x", scaleratio=1)
    figure.update_layout(height=520, legend={"orientation": "h", "y": 1.08})
    return figure


def _render_analysis(model) -> None:
    """Render the currently selected analysis for an already-built model."""
    analysis = st.session_state["control_analysis"]
    if analysis == "Plant report":
        report = normalize_plant(model)
        left, right = st.columns(2)
        with left:
            st.metric("Order", report.order)
            st.metric("DC gain", "n/a" if report.dc_gain is None else f"{report.dc_gain:.6g}")
        with right:
            st.metric("Inputs / outputs", f"{report.input_count} / {report.output_count}")
            st.metric("Finite zeros", len(report.zeros))
        if report.numerator is not None:
            st.markdown(
                f"**Transfer function**: num = `{list(report.numerator)}` "
                f"den = `{list(report.denominator)}`"
            )
        st.markdown(f"**Poles**: {_format_complex(report.poles)}")
        if report.zeros:
            st.markdown(f"**Zeros**: {_format_complex(report.zeros)}")
    elif analysis == "Stability":
        stability = analyze_stability(model)
        left, right = st.columns(2)
        with left:
            st.metric("BIBO stable", "yes" if stability.bibo_stable else "no")
            st.caption(stability.bibo_reason)
        with right:
            st.metric("Lyapunov asymptotic", "yes" if stability.lyapunov_asymptotic else "no")
            st.caption(stability.lyapunov_reason)
        st.markdown(f"**Poles**: {_format_complex(stability.poles)}")
        if stability.max_real_pole is not None:
            st.metric("Max real pole part", f"{stability.max_real_pole:.6g}")
    elif analysis == "Bode & margins":
        margins = bode_margins(model)
        columns = st.columns(4)
        columns[0].metric(
            "Phase margin",
            "n/a" if margins.phase_margin_deg is None else f"{margins.phase_margin_deg:.2f} deg",
        )
        columns[1].metric(
            "Gain margin",
            "n/a" if margins.gain_margin is None else f"{margins.gain_margin:.4g}",
        )
        columns[2].metric(
            "Gain crossover",
            "n/a"
            if margins.gain_crossover_rad_s is None
            else f"{margins.gain_crossover_rad_s:.4g} rad/s",
        )
        columns[3].metric(
            "Phase crossover",
            "n/a"
            if margins.phase_crossover_rad_s is None
            else f"{margins.phase_crossover_rad_s:.4g} rad/s",
        )
        st.plotly_chart(_style_chart(_bode_figure(margins)), use_container_width=True, theme=None)
    elif analysis == "Nyquist":
        st.plotly_chart(
            _style_chart(_nyquist_figure(nyquist_response(model))),
            use_container_width=True,
            theme=None,
        )
    elif analysis == "Root locus":
        st.plotly_chart(
            _style_chart(_locus_figure(root_locus(model))),
            use_container_width=True,
            theme=None,
        )
    elif analysis == "PID tuning":
        _render_pid_tuning(model)
    elif analysis == "State feedback":
        _render_state_feedback(model)
    elif analysis == "Interconnect (PID on motor)":
        _render_interconnect()


def _render_pid_tuning(model) -> None:
    method = st.session_state["control_tune_method"]
    if method == "Ziegler-Nichols":
        result = ziegler_nichols(model)
    else:
        result = tune_pole_placement(model, _parse_poles(st.session_state["control_tune_poles"]))
    columns = st.columns(3)
    columns[0].metric("Kp", f"{result.gains.kp:.6g}")
    columns[1].metric("Ki", f"{result.gains.ki:.6g}")
    columns[2].metric("Kd", f"{result.gains.kd:.6g}")
    if result.ku is not None:
        st.info(f"Ku = {result.ku:.6g}, Pu = {result.pu:.6g} s")
    if result.fopdt is not None:
        fit = result.fopdt
        st.info(
            f"FOPDT fit: K = {fit.gain:.4g}, tau = {fit.time_constant_s:.4g} s, "
            f"theta = {fit.dead_time_s:.4g} s"
        )
    if result.state_feedback_k is not None:
        st.code("K = " + str([list(row) for row in result.state_feedback_k]))
    st.caption(result.message)


def _render_state_feedback(model) -> None:
    method = st.session_state["control_sf_method"]
    if method == "Ackermann":
        result = ackermann(model, _parse_poles(st.session_state["control_sf_poles"]))
    else:
        q = [float(value) for value in st.session_state["control_sf_q"].split(",") if value.strip()]
        result = lqr(model, q, float(st.session_state["control_sf_r"]))
    st.code("K = " + str([list(row) for row in result.closed_loop_k]))
    columns = st.columns(2)
    columns[0].metric("N-bar", "n/a" if result.nbar is None else f"{result.nbar:.6g}")
    columns[1].metric("Controllability rank", f"{result.controllability_rank} / {result.order}")
    st.markdown(f"**Closed-loop poles**: {_format_complex(result.closed_loop_poles)}")
    figure = go.Figure()
    scale = 1000.0 if result.closed_step.time_s[-1] < 1.0 else 1.0
    unit = "ms" if scale == 1000.0 else "s"
    figure.add_trace(
        go.Scatter(
            x=[t * scale for t in result.open_step.time_s],
            y=result.open_step.output,
            name="Open loop",
            line={"width": 1.4, "color": "#383838"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[t * scale for t in result.closed_step.time_s],
            y=result.closed_step.output,
            name="Closed loop (N-bar)",
            line={"width": 1.5, "color": "#167d83"},
        )
    )
    figure.update_xaxes(title_text=f"Time ({unit})")
    figure.update_yaxes(title_text="Step response")
    figure.update_layout(height=420, hovermode="x unified", legend={"orientation": "h", "y": 1.08})
    st.plotly_chart(_style_chart(figure), use_container_width=True, theme=None)
    st.caption(result.message)


def _render_interconnect() -> None:
    from pycircuits_sim.design import PIDGains

    result = interconnect(
        InterconnectSpec(
            blocks=(
                InterconnectBlock(
                    id="c",
                    kind="pid",
                    gains=PIDGains(
                        kp=st.session_state["control_ic_kp"],
                        ki=st.session_state["control_ic_ki"],
                        kd=st.session_state["control_ic_kd"],
                    ),
                ),
                InterconnectBlock(id="g", kind="tf", num=(4.0,), den=(1.0, 12.0, 0.0)),
            ),
            forward=("c", "g"),
            feedback="unity",
            stop_time=100.0,
        )
    )
    st.markdown(
        f"**Composite**: num = `{list(result.composite_num)}` den = `{list(result.composite_den)}`"
    )
    columns = st.columns(3)
    columns[0].metric("BIBO stable", "yes" if result.stability.bibo_stable else "no")
    columns[1].metric(
        "Phase margin",
        "n/a"
        if result.margins.phase_margin_deg is None
        else f"{result.margins.phase_margin_deg:.2f} deg",
    )
    columns[2].metric("Step settles at", f"{result.step.output[-1]:.4g}")
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=list(result.step.time_s),
            y=list(result.step.output),
            name="Closed-loop step",
            line={"width": 1.5, "color": "#167d83"},
        )
    )
    figure.update_xaxes(title_text="Time (s)")
    figure.update_yaxes(title_text="Output")
    figure.update_layout(height=420, hovermode="x unified")
    st.plotly_chart(_style_chart(figure), use_container_width=True, theme=None)


def render_control_analysis() -> None:
    """Sidebar-driven entry point called from ui.py for the seventh mode."""
    st.sidebar.subheader("Plant")
    use_example = st.sidebar.checkbox("Use example plant", value=True)
    example = st.sidebar.selectbox("Example", list(EXAMPLE_PLANTS)) if use_example else ""
    is_ss = EXAMPLE_PLANTS[example]["format"] == "ss" if use_example else False
    if use_example:
        data = EXAMPLE_PLANTS[example]
        num_text = data.get("numerator", "[1.0]")
        den_text = data.get("denominator", "[1.0, 1.0]")
        a_text = data.get("A", "[[0.0]]")
        b_text = data.get("B", "[[1.0]]")
        c_text = data.get("C", "[[1.0]]")
        d_text = data.get("D", "[[0.0]]")
    else:
        is_ss = st.sidebar.checkbox("State-space instead of transfer function", value=False)
        num_text = st.sidebar.text_input("Numerator, descending powers of s", "[1.0]")
        den_text = st.sidebar.text_input("Denominator, descending powers of s", "[1.0, 1.0, 1.0]")
        a_text = st.sidebar.text_area("A", "[[0.0, 1.0], [-1.0, -1.0]]", height=70)
        b_text = st.sidebar.text_area("B", "[[0.0], [1.0]]", height=60)
        c_text = st.sidebar.text_area("C", "[[1.0, 0.0]]", height=60)
        d_text = st.sidebar.text_area("D", "[[0.0]]", height=50)

    st.sidebar.subheader("Analysis")
    analysis = st.sidebar.radio("Tool", ANALYSES)
    if analysis == "PID tuning":
        tune_method = st.sidebar.radio("Method", ["Ziegler-Nichols", "Pole placement"])
        tune_poles = st.sidebar.text_input("Desired poles (placement)", "-2+1j, -2-1j")
    else:
        tune_method, tune_poles = "Ziegler-Nichols", ""
    if analysis == "State feedback":
        sf_method = st.sidebar.radio("Method", ["Ackermann", "LQR"])
        sf_poles = st.sidebar.text_input("Desired poles (Ackermann)", "-2, -3+1j, -3-1j")
        sf_q = st.sidebar.text_input("Q diagonal (LQR)", "1,1")
        sf_r = st.sidebar.number_input("R (LQR)", value=1.0, step=0.1)
    else:
        sf_method, sf_poles, sf_q, sf_r = "Ackermann", "", "1,1", 1.0
    if analysis == "Interconnect (PID on motor)":
        ic_kp = st.sidebar.number_input("Kp", value=1.2, step=0.1)
        ic_ki = st.sidebar.number_input("Ki", value=0.4, step=0.1)
        ic_kd = st.sidebar.number_input("Kd", value=0.2, step=0.05)
    else:
        ic_kp, ic_ki, ic_kd = 0.0, 0.0, 0.0
    run = st.sidebar.button("Run analysis", type="primary", use_container_width=True)

    st.markdown(
        "<div class='workbench-kicker'>PyCircuits / Control lab</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='workbench-title'>Control analysis</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='workbench-subtitle'>Stability, classical margins, tuning, "
        "and state feedback for continuous SISO plants.</div>",
        unsafe_allow_html=True,
    )

    if run:
        st.session_state["control_analysis"] = analysis
        st.session_state["control_tune_method"] = tune_method
        st.session_state["control_tune_poles"] = tune_poles
        st.session_state["control_sf_method"] = sf_method
        st.session_state["control_sf_poles"] = sf_poles
        st.session_state["control_sf_q"] = sf_q
        st.session_state["control_sf_r"] = sf_r
        st.session_state["control_ic_kp"] = ic_kp
        st.session_state["control_ic_ki"] = ic_ki
        st.session_state["control_ic_kd"] = ic_kd
        try:
            model = _build_model(
                example,
                use_example,
                num_text,
                den_text,
                a_text,
                b_text,
                c_text,
                d_text,
                is_ss,
            )
            st.session_state["control_model"] = model
        except (ValueError, SyntaxError) as error:
            st.error(f"Could not build the plant: {error}")

    if "control_analysis" in st.session_state and "control_model" in st.session_state:
        try:
            _render_analysis(st.session_state["control_model"])
        except ValueError as error:
            st.error(str(error))
