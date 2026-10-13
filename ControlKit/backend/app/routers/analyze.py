from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.engine.frequency import bode, nyquist
from app.engine.pid import closed_loop_payload, pole_placement, ziegler_nichols
from app.engine.plant import ControlError, build_system, normalize_payload
from app.engine.root_locus import root_locus
from app.engine.stability import analyze_stability
from app.engine.time_domain import simulate
from app.schemas import AnalyzeRequest, PidClosedLoopRequest, PidTuneRequest, PlantSpec, SimRequest

router = APIRouter(prefix="/api")


def _plant(spec: PlantSpec):
    try:
        return build_system(spec)
    except ControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plant/normalize")
def plant_normalize(spec: PlantSpec):
    sys = _plant(spec)
    return _run(normalize_payload, sys)


@router.post("/simulate")
def simulate_endpoint(req: SimRequest):
    sys = _plant(req.plant)
    return _run(
        simulate,
        sys,
        req.kind,
        t_final=req.t_final,
        n_points=req.n_points,
        t=req.t,
        u=req.u,
    )


@router.post("/stability")
def stability_endpoint(spec: PlantSpec):
    sys = _plant(spec)
    return _run(analyze_stability, sys)


@router.post("/bode")
def bode_endpoint(spec: PlantSpec):
    sys = _plant(spec)
    return _run(bode, sys)


@router.post("/nyquist")
def nyquist_endpoint(spec: PlantSpec):
    sys = _plant(spec)
    return _run(nyquist, sys)


@router.post("/root-locus")
def root_locus_endpoint(spec: PlantSpec):
    sys = _plant(spec)
    return _run(root_locus, sys)


@router.post("/analyze")
def analyze_all(req: AnalyzeRequest):
    sys = _plant(req.plant)
    return {
        "plant": _run(normalize_payload, sys),
        "stability": _run(analyze_stability, sys),
        "step": _run(simulate, sys, "step", t_final=req.t_final, n_points=req.n_points),
        "impulse": _run(simulate, sys, "impulse", t_final=req.t_final, n_points=req.n_points),
        "bode": _run(bode, sys),
        "nyquist": _run(nyquist, sys),
        "root_locus": _run(root_locus, sys),
    }


@router.post("/pid/closed-loop")
def pid_closed_loop(req: PidClosedLoopRequest):
    sys = _plant(req.plant)
    g = req.gains
    return _run(
        closed_loop_payload,
        sys,
        g.Kp,
        g.Ki,
        g.Kd,
        g.N,
        t_final=req.t_final,
        n_points=req.n_points,
    )


@router.post("/pid/tune")
def pid_tune(req: PidTuneRequest):
    sys = _plant(req.plant)
    if req.method == "zn":
        return _run(ziegler_nichols, sys)
    poles = [p.model_dump() for p in (req.desired_poles or [])]
    return _run(pole_placement, sys, poles)
