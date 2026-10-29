"""Thin FastAPI wrapper reusing ControlKit's API contract.

The same endpoint paths, request schemas, and response field shapes as
ControlKit ({re, im} complex dicts, TimeSeries payloads, Bode/Nyquist/
root-locus arrays), but every computation runs on the pure-numpy
analysis/design/interconnect engines instead of python-control, so a
client written against ControlKit works unchanged.

Run with the API extra installed:

    pip install "pycircuits-sim[api]"
    uvicorn pycircuits_sim.api:app --reload --port 8000

Engine modeling errors (ValueError) map to HTTP 400 with the readable
message, mirroring ControlKit's ControlError handling. The boundary is
SISO-only, exactly like ControlKit's build_system. This module is never
imported by pycircuits_sim/__init__, so the core stays dependency-light.
"""

from __future__ import annotations

import functools
import math
from typing import Literal

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - only when the extra is missing
    raise ImportError(
        "pycircuits_sim.api requires the API extra; install it with: "
        'pip install "pycircuits-sim[api]"'
    ) from exc

import numpy as np

from .analysis import (
    analyze_stability,
    bode_margins,
    normalize_plant,
    nyquist_response,
    root_locus,
    step_metrics,
)
from .block_diagram import BlockDiagramDocument, BlockDiagramEdge, BlockDiagramNode
from .design import (
    PIDGains,
    ackermann,
    lqr,
    pid_transfer_function,
    tune_pole_placement,
    ziegler_nichols,
)
from .graph import interconnect_graph
from .interconnect import InterconnectBlock, InterconnectSpec, interconnect
from .linear_systems import (
    StateSpaceModel,
    simulate_state_space,
    transfer_function_to_state_space,
)

MAX_POINTS = 1800


# --- Request schemas (mirror ControlKit backend/app/schemas.py) -------------


class ComplexNumber(BaseModel):
    re: float
    im: float = 0.0


class PlantSpec(BaseModel):
    form: Literal["tf", "ss"] = "tf"
    num: list[float] | None = None
    den: list[float] | None = None
    A: list[list[float]] | None = None
    B: list[list[float]] | None = None
    C: list[list[float]] | None = None
    D: list[list[float]] | None = None


class SimRequest(BaseModel):
    plant: PlantSpec
    kind: Literal["step", "impulse", "custom"] = "step"
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)
    t: list[float] | None = None
    u: list[float] | None = None


class AnalyzeRequest(BaseModel):
    plant: PlantSpec
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)


class PidGains(BaseModel):
    Kp: float = 1.0
    Ki: float = 0.0
    Kd: float = 0.0
    N: float | None = None


class PidClosedLoopRequest(BaseModel):
    plant: PlantSpec
    gains: PidGains = PidGains()
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)


class PidTuneRequest(BaseModel):
    plant: PlantSpec
    method: Literal["zn", "pole_placement"] = "zn"
    desired_poles: list[ComplexNumber] | None = None


class AckermannRequest(BaseModel):
    plant: PlantSpec
    desired_poles: list[ComplexNumber] = Field(min_length=1)


class LqrRequest(BaseModel):
    plant: PlantSpec
    Q: list[float] = Field(min_length=1)
    R: float = Field(gt=0)


class BlockSpec(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    kind: Literal["tf", "ss", "pid", "gain"]
    num: list[float] | None = None
    den: list[float] | None = None
    A: list[list[float]] | None = None
    B: list[list[float]] | None = None
    C: list[list[float]] | None = None
    D: list[list[float]] | None = None
    gains: PidGains | None = None
    k: float | None = None


class InterconnectRequest(BaseModel):
    blocks: list[BlockSpec] = Field(min_length=1, max_length=6)
    forward: list[str] = Field(min_length=1, max_length=6)
    parallel: list[str] | None = Field(default=None, max_length=6)
    feedback: str | list[str] = "unity"
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)


class GraphNodeSpec(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    kind: Literal["tf", "ss", "pid", "gain"]
    num: list[float] | None = None
    den: list[float] | None = None
    A: list[list[float]] | None = None
    B: list[list[float]] | None = None
    C: list[list[float]] | None = None
    D: list[list[float]] | None = None
    gains: PidGains | None = None
    derivative_filter: float | None = None
    k: float | None = None
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class GraphEdgeSpec(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=32)
    target: str = Field(min_length=1, max_length=32)
    gain: float = 1.0
    label: str = ""


class BlockDiagramRequest(BaseModel):
    nodes: list[GraphNodeSpec] = Field(min_length=1, max_length=12)
    edges: list[GraphEdgeSpec] = Field(default_factory=list, max_length=32)
    input_node: str = Field(min_length=1, max_length=32)
    output_node: str = Field(min_length=1, max_length=32)
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)


# --- Helpers ----------------------------------------------------------------


def handle_errors(function):
    """Map engine ValueErrors to HTTP 400 with the readable message."""

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return wrapper


def _build_model(spec: PlantSpec) -> StateSpaceModel:
    """Build a continuous SISO StateSpaceModel from a PlantSpec (SISO gate)."""
    if spec.form == "tf":
        if spec.num is None or spec.den is None:
            raise ValueError("transfer-function plants need numerator and denominator coefficients")
        model = transfer_function_to_state_space(spec.num, spec.den)
    else:
        if spec.A is None or spec.B is None or spec.C is None:
            raise ValueError("state-space plants need A, B, and C matrices")
        try:
            b_array = np.asarray(spec.B, dtype=float)
            c_array = np.asarray(spec.C, dtype=float)
        except (TypeError, ValueError) as error:
            raise ValueError("B and C must be rectangular numeric matrices") from error
        if b_array.ndim != 2 or c_array.ndim != 2:
            raise ValueError("B and C must be rectangular numeric matrices")
        default_d = [[0.0] * b_array.shape[1] for _ in range(c_array.shape[0])]
        model = StateSpaceModel.from_matrices(
            spec.A, spec.B, spec.C, spec.D if spec.D is not None else default_d
        )
    if model.input_count != 1 or model.output_count != 1:
        raise ValueError("this API analyzes SISO plants only (use the Python API for MIMO)")
    return model


def _cplx(value) -> dict:
    number = complex(value)
    return {"re": float(number.real), "im": float(number.imag)}


def _cplx_list(values) -> list[dict]:
    return [_cplx(value) for value in values]


def _floats(values) -> list[float]:
    return [float(value) for value in values]


def _downsample(*arrays):
    """Cap payload size at MAX_POINTS (ControlKit's transport limit)."""
    n = len(np.atleast_1d(arrays[0]))
    if n <= MAX_POINTS:
        return tuple(np.atleast_1d(array) for array in arrays)
    index = np.linspace(0, n - 1, MAX_POINTS).astype(int)
    return tuple(np.atleast_1d(array)[index] for array in arrays)


def _metrics_payload(metrics) -> dict:
    return {
        "rise_time": metrics.rise_time_s,
        "settling_time": metrics.settling_time_s,
        "overshoot": metrics.overshoot_percent,
        "peak": metrics.peak,
        "peak_time": metrics.peak_time_s,
        "steady_state": metrics.steady_state,
    }


def _series(kind: str, times, values, u=None, metrics: dict | None = None) -> dict:
    t, y = _downsample(np.asarray(times, dtype=float), np.asarray(values, dtype=float))
    u_payload = None
    if u is not None:
        (u_ds,) = _downsample(np.asarray(u, dtype=float))
        u_payload = [float(value) for value in u_ds]
    return {
        "kind": kind,
        "t": [float(value) for value in t],
        "y": [float(value) for value in y],
        "u": u_payload,
        "metrics": metrics if metrics is not None else {},
    }


def _time_step(t_final: float, n_points: int) -> float:
    return float(t_final) / max(int(n_points) - 1, 1)


def _step_series(model, t_final: float, n_points: int) -> dict:
    result = simulate_state_space(
        model, _time_step(t_final, n_points), float(t_final), lambda _t: (1.0,)
    )
    y = result.outputs["y1"]
    metrics = step_metrics(result.time, y)
    return _series("step", result.time, y, None, _metrics_payload(metrics))


def _impulse_series(model, t_final: float, n_points: int) -> dict:
    # Unit impulse as the free response from x(0+) = B: y(t) = C e^{At} B,
    # exact for t > 0. The direct-feedthrough D*delta(t) spike cannot be
    # represented on a sample grid (educational limitation, like the CLI).
    initial = np.asarray(model.B, dtype=float)[:, 0]
    result = simulate_state_space(
        model,
        _time_step(t_final, n_points),
        float(t_final),
        lambda _t: (0.0,),
        initial_state=initial,
    )
    return _series("impulse", result.time, result.outputs["y1"], None, {})


def _custom_series(model, t, u, n_points: int) -> dict:
    times = np.asarray(t, dtype=float)
    values = np.asarray(u, dtype=float)
    if times.ndim != 1 or times.size != values.size or times.size < 2:
        raise ValueError("t and u must be the same length with at least two samples")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        raise ValueError("t and u must contain finite values")
    if np.any(np.diff(times) <= 0):
        raise ValueError("Time vector t must be strictly increasing")
    count = int(np.clip(max(times.size, int(n_points)), 50, 5000))
    span = float(times[-1] - times[0])

    def signal(
        _t: float,
        offset: float = float(times[0]),
        xs: np.ndarray = times,
        ys: np.ndarray = values,
    ) -> float:
        return float(np.interp(_t + offset, xs, ys))

    result = simulate_state_space(model, span / (count - 1), span, signal)
    shifted = [value + float(times[0]) for value in result.time]
    u_out = [float(np.interp(value, times, values)) for value in shifted]
    return _series("custom", shifted, result.outputs["y1"], u_out, {})


def _bode_payload(margins) -> dict:
    return {
        "omega": _floats(margins.frequencies_rad_s),
        "mag_db": _floats(margins.magnitude_db),
        "phase_deg": _floats(margins.phase_deg),
        "gain_margin": margins.gain_margin,
        "gain_margin_db": margins.gain_margin_db,
        "phase_margin_deg": margins.phase_margin_deg,
        "gain_crossover_omega": margins.gain_crossover_rad_s,
        "phase_crossover_omega": margins.phase_crossover_rad_s,
    }


def _nyquist_payload(result) -> dict:
    return {
        "omega": _floats(result.frequencies_rad_s),
        "real": _floats(result.real),
        "imag": _floats(result.imaginary),
    }


def _locus_payload(result) -> dict:
    gains = _floats(result.gains)
    return {
        "gains": gains,
        "branches": [
            {
                "re": _floats(root.real for root in branch),
                "im": _floats(root.imag for root in branch),
            }
            for branch in result.branches
        ],
        "open_loop_poles": _cplx_list(result.open_loop_poles),
        "open_loop_zeros": _cplx_list(result.open_loop_zeros),
        "gain_min": min(gains) if gains else None,
        "gain_max": max(gains) if gains else None,
    }


def _plant_payload(report) -> dict:
    return {
        "num": list(report.numerator) if report.numerator is not None else None,
        "den": list(report.denominator),
        "A": [list(row) for row in report.A],
        "B": [list(row) for row in report.B],
        "C": [list(row) for row in report.C],
        "D": [list(row) for row in report.D],
        "poles": _cplx_list(report.poles),
        "zeros": _cplx_list(report.zeros),
        "dc_gain": report.dc_gain,
        "order": report.order,
        "ninputs": report.input_count,
        "noutputs": report.output_count,
    }


def _stability_payload(stability) -> dict:
    return {
        "poles": _cplx_list(stability.poles),
        "zeros": _cplx_list(stability.zeros),
        "eigenvalues": _cplx_list(stability.eigenvalues),
        "bibo_stable": stability.bibo_stable,
        "bibo_reason": stability.bibo_reason,
        "lyapunov_asymptotic": stability.lyapunov_asymptotic,
        "lyapunov_reason": stability.lyapunov_reason,
        "max_real_pole": stability.max_real_pole,
        "max_real_eig": stability.max_real_eig,
    }


def _sf_series(step) -> dict:
    metrics = step_metrics(step.time_s, step.output)
    return _series("step", step.time_s, step.output, None, _metrics_payload(metrics))


def _sf_payload(result) -> dict:
    payload = {
        "method": result.method,
        "K": [list(row) for row in result.closed_loop_k],
        "nbar": result.nbar,
        "order": result.order,
        "controllability_rank": result.controllability_rank,
        "open_loop_poles": _cplx_list(result.open_loop_poles),
        "closed_loop_poles": _cplx_list(result.closed_loop_poles),
        "desired_poles": _cplx_list(result.desired_poles) if result.desired_poles else None,
        "open_step": _sf_series(result.open_step),
        "closed_step": _sf_series(result.closed_step),
        "message": result.message,
    }
    if result.method == "lqr":
        payload["Q"] = list(result.q) if result.q is not None else None
        payload["R"] = result.r
        payload["S"] = [list(row) for row in result.s] if result.s is not None else None
    return payload


def _poles(values: list[ComplexNumber] | None) -> list[complex]:
    if not values:
        raise ValueError("desired_poles must contain at least one pole")
    return [complex(p.re, p.im) for p in values]


def _plant_block(model, block_id: str) -> InterconnectBlock:
    report = normalize_plant(model)
    if report.numerator is None:
        raise ValueError("could not extract a transfer function from the plant")
    return InterconnectBlock(id=block_id, kind="tf", num=report.numerator, den=report.denominator)


# --- Application -------------------------------------------------------------

app = FastAPI(
    title="PyCircuits Control API",
    version="0.1.0",
    description=(
        "ControlKit-compatible HTTP contract backed by the PyCircuits "
        "pure-numpy analysis, design, and interconnection engines."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/plant/normalize")
@handle_errors
def plant_normalize(spec: PlantSpec) -> dict:
    return _plant_payload(normalize_plant(_build_model(spec)))


@app.post("/api/simulate")
@handle_errors
def simulate_endpoint(req: SimRequest) -> dict:
    model = _build_model(req.plant)
    if req.kind == "custom":
        if req.t is None or req.u is None:
            raise ValueError("custom simulation needs t and u arrays")
        return _custom_series(model, req.t, req.u, req.n_points)
    if req.kind == "step":
        return _step_series(model, req.t_final, req.n_points)
    return _impulse_series(model, req.t_final, req.n_points)


@app.post("/api/stability")
@handle_errors
def stability_endpoint(spec: PlantSpec) -> dict:
    return _stability_payload(analyze_stability(_build_model(spec)))


@app.post("/api/bode")
@handle_errors
def bode_endpoint(spec: PlantSpec) -> dict:
    return _bode_payload(bode_margins(_build_model(spec)))


@app.post("/api/nyquist")
@handle_errors
def nyquist_endpoint(spec: PlantSpec) -> dict:
    return _nyquist_payload(nyquist_response(_build_model(spec)))


@app.post("/api/root-locus")
@handle_errors
def root_locus_endpoint(spec: PlantSpec) -> dict:
    return _locus_payload(root_locus(_build_model(spec)))


@app.post("/api/analyze")
@handle_errors
def analyze_endpoint(req: AnalyzeRequest) -> dict:
    model = _build_model(req.plant)
    return {
        "plant": _plant_payload(normalize_plant(model)),
        "stability": _stability_payload(analyze_stability(model)),
        "step": _step_series(model, req.t_final, req.n_points),
        "impulse": _impulse_series(model, req.t_final, req.n_points),
        "bode": _bode_payload(bode_margins(model)),
        "nyquist": _nyquist_payload(nyquist_response(model)),
        "root_locus": _locus_payload(root_locus(model)),
    }


@app.post("/api/pid/closed-loop")
@handle_errors
def pid_closed_loop(req: PidClosedLoopRequest) -> dict:
    model = _build_model(req.plant)
    gains = req.gains
    controller = InterconnectBlock(
        id="c",
        kind="pid",
        gains=PIDGains(kp=gains.Kp, ki=gains.Ki, kd=gains.Kd),
        derivative_filter=gains.N,
    )
    plant_block = _plant_block(model, "g")
    time_step = _time_step(req.t_final, req.n_points)
    stop_time = float(req.t_final)
    loop = interconnect(
        InterconnectSpec(
            blocks=(controller, plant_block),
            forward=("c", "g"),
            feedback="none",
            stop_time=stop_time,
            time_step=time_step,
        )
    )
    closed = interconnect(
        InterconnectSpec(
            blocks=(controller, plant_block),
            forward=("c", "g"),
            feedback="unity",
            stop_time=stop_time,
            time_step=time_step,
        )
    )
    controller_num, controller_den = pid_transfer_function(gains.Kp, gains.Ki, gains.Kd, gains.N)
    closed_metrics = step_metrics(closed.step.time_s, closed.step.output)
    return {
        "gains": gains.model_dump(),
        "controller_num": list(controller_num),
        "controller_den": list(controller_den),
        "closed_loop_num": list(closed.composite_num),
        "closed_loop_den": list(closed.composite_den),
        "plant_step": _step_series(model, req.t_final, req.n_points),
        "closed_loop_step": _series(
            "step",
            closed.step.time_s,
            closed.step.output,
            None,
            _metrics_payload(closed_metrics),
        ),
        "loop_bode": _bode_payload(loop.margins),
        "closed_loop_bode": _bode_payload(closed.margins),
    }


@app.post("/api/pid/tune")
@handle_errors
def pid_tune(req: PidTuneRequest) -> dict:
    model = _build_model(req.plant)
    if req.method == "zn":
        result = ziegler_nichols(model)
        variants = None
        if result.p_gains is not None and result.pi_gains is not None:
            variants = {
                "P": {"Kp": result.p_gains.kp, "Ki": result.p_gains.ki, "Kd": result.p_gains.kd},
                "PI": {
                    "Kp": result.pi_gains.kp,
                    "Ki": result.pi_gains.ki,
                    "Kd": result.pi_gains.kd,
                },
                "PID": {"Kp": result.gains.kp, "Ki": result.gains.ki, "Kd": result.gains.kd},
            }
        fit = result.fopdt
        return {
            "method": "zn",
            "variant": result.variant,
            "fopdt": (
                {"K": fit.gain, "tau": fit.time_constant_s, "theta": fit.dead_time_s}
                if fit is not None
                else None
            ),
            "Ku": result.ku,
            "Pu": result.pu,
            "phase_crossover_omega": (
                2.0 * math.pi / result.pu if result.variant == "ultimate" else None
            ),
            "variants": variants,
            "gains": {"Kp": result.gains.kp, "Ki": result.gains.ki, "Kd": result.gains.kd},
            "K": None,
            "message": result.message,
        }
    poles = _poles(req.desired_poles)
    placed = tune_pole_placement(model, poles)
    return {
        "method": "pole_placement",
        "variant": None,
        "fopdt": None,
        "Ku": None,
        "Pu": None,
        "phase_crossover_omega": None,
        "variants": None,
        "gains": {
            "Kp": placed.gains.kp,
            "Ki": placed.gains.ki,
            "Kd": placed.gains.kd,
        },
        "K": (
            [list(row) for row in placed.state_feedback_k]
            if placed.state_feedback_k is not None
            else None
        ),
        "placed_poles": _cplx_list(poles),
        "message": placed.message,
    }


@app.post("/api/sf/ackermann")
@handle_errors
def sf_ackermann(req: AckermannRequest) -> dict:
    return _sf_payload(ackermann(_build_model(req.plant), _poles(req.desired_poles)))


@app.post("/api/sf/lqr")
@handle_errors
def sf_lqr(req: LqrRequest) -> dict:
    return _sf_payload(lqr(_build_model(req.plant), req.Q, req.R))


@app.post("/api/interconnect")
@handle_errors
def interconnect_endpoint(req: InterconnectRequest) -> dict:
    def rows(matrix):
        return tuple(tuple(float(v) for v in row) for row in matrix) if matrix is not None else None

    blocks = []
    for block in req.blocks:
        gains = None
        if block.gains is not None:
            gains = PIDGains(kp=block.gains.Kp, ki=block.gains.Ki, kd=block.gains.Kd)
        blocks.append(
            InterconnectBlock(
                id=block.id,
                kind=block.kind,
                num=tuple(block.num) if block.num is not None else None,
                den=tuple(block.den) if block.den is not None else None,
                A=rows(block.A),
                B=rows(block.B),
                C=rows(block.C),
                D=rows(block.D),
                gains=gains,
                derivative_filter=block.gains.N if block.gains is not None else None,
                k=block.k,
            )
        )
    feedback = tuple(req.feedback) if isinstance(req.feedback, list) else req.feedback
    spec = InterconnectSpec(
        blocks=tuple(blocks),
        forward=tuple(req.forward),
        parallel=tuple(req.parallel) if req.parallel else None,
        feedback=feedback,
        stop_time=float(req.t_final),
        time_step=_time_step(req.t_final, req.n_points),
    )
    result = interconnect(spec)
    composite_model = StateSpaceModel.from_matrices(
        result.plant.A, result.plant.B, result.plant.C, result.plant.D
    )
    closed_metrics = step_metrics(result.step.time_s, result.step.output)
    return {
        "composite": {
            "num": list(result.composite_num),
            "den": list(result.composite_den),
        },
        "structure": {
            "forward": list(spec.forward),
            "parallel": list(spec.parallel) if spec.parallel else None,
            "feedback": spec.feedback if isinstance(spec.feedback, str) else list(spec.feedback),
        },
        "plant": _plant_payload(result.plant),
        "stability": _stability_payload(result.stability),
        "step": _series(
            "step",
            result.step.time_s,
            result.step.output,
            None,
            _metrics_payload(closed_metrics),
        ),
        "impulse": _impulse_series(composite_model, req.t_final, req.n_points),
        "bode": _bode_payload(result.margins),
        "nyquist": _nyquist_payload(result.nyquist),
        "root_locus": _locus_payload(result.root_locus),
    }


@app.post("/api/block-diagram")
@handle_errors
def block_diagram_endpoint(req: BlockDiagramRequest) -> dict:
    """Compose a block-diagram canvas into one closed-loop transfer function."""

    def rows(matrix):
        return tuple(tuple(float(v) for v in row) for row in matrix) if matrix is not None else None

    nodes = []
    for node in req.nodes:
        gains = None
        if node.gains is not None:
            gains = PIDGains(kp=node.gains.Kp, ki=node.gains.Ki, kd=node.gains.Kd)
        position = (float(node.position[0]), float(node.position[1]))
        nodes.append(
            BlockDiagramNode(
                id=node.id,
                block=InterconnectBlock(
                    id=node.id,
                    kind=node.kind,
                    num=tuple(node.num) if node.num is not None else None,
                    den=tuple(node.den) if node.den is not None else None,
                    A=rows(node.A),
                    B=rows(node.B),
                    C=rows(node.C),
                    D=rows(node.D),
                    gains=gains,
                    derivative_filter=node.derivative_filter,
                    k=node.k,
                ),
                position=position,
            )
        )
    edges = [
        BlockDiagramEdge(
            id=edge.id,
            source=edge.source,
            target=edge.target,
            gain=edge.gain,
            label=edge.label,
        )
        for edge in req.edges
    ]
    document = BlockDiagramDocument(
        nodes=tuple(nodes),
        edges=tuple(edges),
        input_node=req.input_node,
        output_node=req.output_node,
        stop_time=float(req.t_final),
        time_step=_time_step(req.t_final, req.n_points),
    )
    result = interconnect_graph(document.to_graph())
    composite_model = StateSpaceModel.from_matrices(
        result.plant.A, result.plant.B, result.plant.C, result.plant.D
    )
    closed_metrics = step_metrics(result.step.time_s, result.step.output)
    return {
        "composite": {
            "num": list(result.composite_num),
            "den": list(result.composite_den),
        },
        "structure": {
            "nodes": [node.id for node in document.nodes],
            "edges": [
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "gain": edge.gain,
                }
                for edge in document.edges
            ],
            "input_node": document.input_node,
            "output_node": document.output_node,
        },
        "plant": _plant_payload(result.plant),
        "stability": _stability_payload(result.stability),
        "step": _series(
            "step",
            result.step.time_s,
            result.step.output,
            None,
            _metrics_payload(closed_metrics),
        ),
        "impulse": _impulse_series(composite_model, req.t_final, req.n_points),
        "bode": _bode_payload(result.margins),
        "nyquist": _nyquist_payload(result.nyquist),
        "root_locus": _locus_payload(result.root_locus),
    }
