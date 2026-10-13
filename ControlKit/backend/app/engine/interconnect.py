from __future__ import annotations

import math

import control as ct

from app.engine.frequency import bode, nyquist
from app.engine.pid import pid_tf
from app.engine.plant import build_system, normalize_payload
from app.engine.root_locus import root_locus
from app.engine.stability import analyze_stability
from app.engine.time_domain import simulate
from app.engine.util import ControlError
from app.schemas import PlantSpec

MAX_ORDER = 20
MAX_BLOCKS = 6


def _block_system(b):
    if b.kind == "tf":
        if b.num is None or b.den is None:
            raise ControlError(f"Block '{b.id}': transfer-function block needs num and den.")
        return build_system(PlantSpec(form="tf", num=b.num, den=b.den))
    if b.kind == "ss":
        if b.A is None or b.B is None or b.C is None:
            raise ControlError(f"Block '{b.id}': state-space block needs A, B, and C.")
        return build_system(PlantSpec(form="ss", A=b.A, B=b.B, C=b.C, D=b.D))
    if b.kind == "pid":
        if b.gains is None:
            raise ControlError(f"Block '{b.id}': PID block needs gains (Kp, Ki, Kd).")
        g = b.gains
        return pid_tf(g.Kp, g.Ki, g.Kd, g.N)
    if b.kind == "gain":
        if b.k is None or not math.isfinite(b.k):
            raise ControlError(f"Block '{b.id}': gain block needs a finite k.")
        return ct.tf([float(b.k)], [1.0])
    raise ControlError(f"Block '{b.id}': unknown kind '{b.kind}'.")


def _chain(ids, systems, label: str):
    out = []
    for i in ids:
        if i not in systems:
            raise ControlError(f"Unknown block id '{i}' in {label}.")
        out.append(systems[i])
    if not out:
        raise ControlError(f"{label.capitalize()} needs at least one block.")
    return out


def compose(req) -> dict:
    if len(req.blocks) > MAX_BLOCKS:
        raise ControlError(f"At most {MAX_BLOCKS} blocks are supported.")
    systems: dict = {}
    for b in req.blocks:
        if b.id in systems:
            raise ControlError(f"Duplicate block id '{b.id}'.")
        systems[b.id] = _block_system(b)
    if not systems:
        raise ControlError("Define at least one block.")
    if not req.forward:
        raise ControlError("Forward path must contain at least one block.")

    comp = ct.series(*_chain(req.forward, systems, "forward path"))
    if req.parallel:
        comp = ct.parallel(comp, ct.series(*_chain(req.parallel, systems, "parallel path")))

    fb = req.feedback
    if isinstance(fb, str):
        if fb == "unity":
            comp = ct.feedback(comp, 1)
        elif fb == "none":
            pass
        else:
            raise ControlError("Feedback must be 'none', 'unity', or a list of block ids.")
    elif isinstance(fb, list):
        comp = ct.feedback(comp, ct.series(*_chain(fb, systems, "feedback path")))
    else:
        raise ControlError("Feedback must be 'none', 'unity', or a list of block ids.")

    n_in = int(getattr(comp, "ninputs", 1) or 1)
    n_out = int(getattr(comp, "noutputs", 1) or 1)
    if n_in != 1 or n_out != 1:
        raise ControlError("ControlLens analyzes SISO systems only; the composite must be SISO.")
    try:
        order = int(ct.ss(comp).nstates)
    except Exception as exc:
        raise ControlError(f"Could not realize the composite system: {exc}") from exc
    if order > MAX_ORDER:
        raise ControlError(
            f"Composite order {order} exceeds the limit of {MAX_ORDER}; simplify the interconnection."
        )

    norm = normalize_payload(comp)
    return {
        "composite": {"num": norm["num"], "den": norm["den"]},
        "structure": {
            "forward": list(req.forward),
            "parallel": list(req.parallel) if req.parallel else None,
            "feedback": fb,
        },
        "plant": norm,
        "stability": analyze_stability(comp),
        "step": simulate(comp, "step", t_final=req.t_final, n_points=req.n_points),
        "impulse": simulate(comp, "impulse", t_final=req.t_final, n_points=req.n_points),
        "bode": bode(comp),
        "nyquist": nyquist(comp),
        "root_locus": root_locus(comp),
    }