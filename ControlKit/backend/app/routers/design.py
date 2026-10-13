from __future__ import annotations

from fastapi import APIRouter

from app.engine.interconnect import compose
from app.engine.state_feedback import ackermann, lqr
from app.routers.analyze import _plant, _run
from app.schemas import AckermannRequest, InterconnectRequest, LqrRequest

router = APIRouter(prefix="/api")


@router.post("/sf/ackermann")
def sf_ackermann(req: AckermannRequest):
    sys = _plant(req.plant)
    return _run(ackermann, sys, [p.model_dump() for p in req.desired_poles])


@router.post("/sf/lqr")
def sf_lqr(req: LqrRequest):
    sys = _plant(req.plant)
    return _run(lqr, sys, req.Q, req.R)


@router.post("/interconnect")
def interconnect_endpoint(req: InterconnectRequest):
    return _run(compose, req)