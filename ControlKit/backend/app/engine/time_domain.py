from __future__ import annotations

import control as ct
import numpy as np

from app.engine.util import ControlError, as_float_list, downsample, fnum


def _time_grid(t_final: float, n_points: int) -> np.ndarray:
    if t_final <= 0:
        raise ControlError("Simulation horizon t_final must be positive.")
    n = max(50, min(int(n_points), 5000))
    return np.linspace(0.0, float(t_final), n)


def _step_metrics(sys, t, y) -> dict:
    metrics = {
        "rise_time": None,
        "settling_time": None,
        "overshoot": None,
        "peak": None,
        "peak_time": None,
        "steady_state": fnum(y[-1]) if len(y) else None,
    }
    try:
        info = ct.step_info(sys, T=t)
        metrics.update(
            {
                "rise_time": fnum(info.get("RiseTime")),
                "settling_time": fnum(info.get("SettlingTime")),
                "overshoot": fnum(info.get("Overshoot")),
                "peak": fnum(info.get("Peak")),
                "peak_time": fnum(info.get("PeakTime")),
                "steady_state": fnum(info.get("SteadyStateValue")),
            }
        )
    except Exception:
        if len(y):
            peak_i = int(np.argmax(np.abs(y)))
            metrics["peak"] = fnum(y[peak_i])
            metrics["peak_time"] = fnum(t[peak_i])
    return metrics


def simulate_custom(sys, t, u, n_points: int = 500) -> dict:
    T = np.asarray(t, dtype=float).flatten()
    U = np.asarray(u, dtype=float).flatten()
    if T.size < 2 or T.size != U.size:
        raise ControlError("t and u must be the same length with at least two samples.")
    if not np.isfinite(T).all() or not np.isfinite(U).all():
        raise ControlError("t and u must contain finite values.")
    if np.any(np.diff(T) <= 0):
        raise ControlError("Time vector t must be strictly increasing.")
    # python-control (>= 0.10) requires an equally spaced T in forced_response.
    # Resample the user's piecewise-linear signal onto a uniform grid; this is
    # the identity when the input is already uniform with >= n_points samples.
    n = int(np.clip(max(T.size, int(n_points)), 50, 5000))
    t_grid = np.linspace(T[0], T[-1], n)
    u_grid = np.interp(t_grid, T, U)
    try:
        T_out, y = ct.forced_response(sys, T=t_grid, U=u_grid)
    except Exception as exc:
        raise ControlError(f"Forced response failed: {exc}") from exc
    y = np.squeeze(np.asarray(y, dtype=float))
    T_out, y, U_ds = downsample(T_out, y, u_grid)
    return {
        "kind": "custom",
        "t": as_float_list(T_out),
        "y": as_float_list(y),
        "u": as_float_list(U_ds),
        "metrics": {},
    }


def simulate(sys, kind: str, t_final: float = 10.0, n_points: int = 500, t=None, u=None) -> dict:
    kind = kind.lower()
    if kind == "custom":
        return simulate_custom(sys, t, u, n_points)

    T = _time_grid(t_final, n_points)
    try:
        if kind == "step":
            T_out, y = ct.step_response(sys, T=T)
        elif kind == "impulse":
            T_out, y = ct.impulse_response(sys, T=T)
        else:
            raise ControlError("Simulation kind must be step, impulse, or custom.")
    except Exception as exc:
        raise ControlError(f"{kind} response failed: {exc}") from exc

    y = np.squeeze(np.asarray(y, dtype=float))
    T_out = np.squeeze(np.asarray(T_out, dtype=float))
    T_ds, y_ds = downsample(T_out, y)
    return {
        "kind": kind,
        "t": as_float_list(T_ds),
        "y": as_float_list(y_ds),
        "u": None,
        "metrics": _step_metrics(sys, T_out, y) if kind == "step" else {},
    }
