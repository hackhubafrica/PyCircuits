from __future__ import annotations

import control as ct
import numpy as np

from app.engine.plant import to_ss
from app.engine.time_domain import simulate
from app.engine.util import ControlError, cplx_list, fnum, matrix_to_lists


def _ss_data(plant):
    ss = to_ss(plant)
    A = np.asarray(ss.A, dtype=float)
    B = np.asarray(ss.B, dtype=float)
    C = np.asarray(ss.C, dtype=float)
    D = np.asarray(ss.D, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1] or A.shape[0] == 0:
        raise ControlError("State-feedback design needs a square, non-empty A matrix.")
    if B.shape[1] != 1 or C.shape[0] != 1 or D.shape != (1, 1):
        raise ControlError("State-feedback design requires a SISO plant.")
    return ss, A, B, C, D


def _check_controllable(A, B) -> int:
    try:
        rank = int(np.linalg.matrix_rank(ct.ctrb(A, B)))
    except Exception:
        rank = 0
    if rank < A.shape[0]:
        raise ControlError(
            f"Plant is not fully controllable (rank {rank} < order {A.shape[0]}); "
            "state-feedback design is not possible."
        )
    return rank


def _closed_loop_step(ss, A, B, C, D, K):
    """Open- and closed-loop step responses; closed loop uses the Nbar pre-gain."""
    Acl = A - B @ K
    nbar = None
    try:
        denom = float(np.squeeze(C @ np.linalg.solve(Acl, B)))
        if abs(denom) > 1e-12:
            nbar = -1.0 / denom
    except Exception:
        nbar = None
    gain = 1.0 if nbar is None else float(nbar)
    cl_sys = ct.ss(Acl, B * gain, C - D @ K, D * gain)

    re = np.real(np.linalg.eigvals(Acl))
    neg = -re[re < -1e-9]
    # 8 slowest closed-loop time constants, clamped to a sane window.
    t_final = float(np.clip(8.0 / float(np.min(neg)), 2.0, 60.0)) if neg.size else 12.0
    open_sim = simulate(ss, "step", t_final=t_final, n_points=500)
    cl_sim = simulate(cl_sys, "step", t_final=t_final, n_points=500)
    return open_sim, cl_sim, fnum(nbar)


def _payload(method, ss, A, B, C, D, K, rank, message, desired=None, extra=None):
    Acl = A - B @ K
    open_sim, cl_sim, nbar = _closed_loop_step(ss, A, B, C, D, K)
    out = {
        "method": method,
        "K": matrix_to_lists(K),
        "nbar": nbar,
        "order": int(A.shape[0]),
        "controllability_rank": rank,
        "open_loop_poles": cplx_list(np.linalg.eigvals(A)),
        "closed_loop_poles": cplx_list(np.linalg.eigvals(Acl)),
        "desired_poles": cplx_list(desired) if desired is not None else None,
        "open_step": open_sim,
        "closed_step": cl_sim,
        "message": message,
    }
    if extra:
        out.update(extra)
    return out


def ackermann(plant, desired_poles: list[dict]) -> dict:
    if not desired_poles:
        raise ControlError("Ackermann needs at least one desired pole.")
    ss, A, B, C, D = _ss_data(plant)
    n = A.shape[0]
    poles = np.array([complex(p["re"], p["im"]) for p in desired_poles], dtype=complex)
    if poles.size != n:
        raise ControlError(f"Provide exactly {n} desired poles for this plant (order {n}).")
    rank = _check_controllable(A, B)
    try:
        K_raw = np.atleast_2d(ct.acker(A, B, poles))
    except Exception as exc:
        raise ControlError(f"Ackermann failed: {exc}") from exc
    if np.iscomplexobj(K_raw) and float(np.max(np.abs(np.asarray(K_raw).imag))) > 1e-9:
        raise ControlError("Desired poles must be conjugate-symmetric so K stays real.")
    K = np.real(np.asarray(K_raw)).astype(float)
    msg = (
        f"Ackermann: K places {n} pole(s) via the controllability-matrix inverse (ct.acker); "
        "the closed-loop step uses the N̄ reference pre-gain."
    )
    return _payload("ackermann", ss, A, B, C, D, K, rank, msg, desired=poles)


def lqr(plant, Q_diag: list[float], R: float) -> dict:
    ss, A, B, C, D = _ss_data(plant)
    n = A.shape[0]
    if len(Q_diag) != n:
        raise ControlError(f"Q must have {n} diagonal entries for this plant (order {n}).")
    q = np.asarray(Q_diag, dtype=float)
    if not np.isfinite(q).all() or np.any(q < 0):
        raise ControlError("Q diagonal entries must be finite and >= 0.")
    if not np.any(q > 0):
        raise ControlError("At least one Q entry must be positive.")
    if not np.isfinite(R) or R <= 0:
        raise ControlError("R must be a finite positive scalar.")
    rank = _check_controllable(A, B)
    try:
        K, S, _E = ct.lqr(A, B, np.diag(q), np.array([[float(R)]]))
    except Exception as exc:
        raise ControlError(f"LQR failed: {exc}") from exc
    K = np.real(np.atleast_2d(np.asarray(K))).astype(float)
    S = np.real(np.atleast_2d(np.asarray(S)))
    msg = (
        f"LQR: K minimizes ∫(xᵀQx + uᵀRu) dt with diag(Q)=[{', '.join(f'{v:g}' for v in q)}], "
        f"R={R:g}; the closed-loop step uses the N̄ reference pre-gain."
    )
    return _payload(
        "lqr",
        ss,
        A,
        B,
        C,
        D,
        K,
        rank,
        msg,
        extra={"Q": [float(v) for v in q], "R": float(R), "S": matrix_to_lists(S)},
    )