from __future__ import annotations

import control as ct
import numpy as np

from app.engine.frequency import bode
from app.engine.plant import to_ss, to_tf
from app.engine.time_domain import simulate
from app.engine.util import ControlError, fnum, matrix_to_lists, tf_coeffs


def pid_tf(Kp: float, Ki: float, Kd: float, N: float | None = None):
    if N is None or N <= 0:
        return ct.tf([Kd, Kp, Ki], [1.0, 0.0])
    num = [Kp + Kd * N, Kp * N + Ki, Ki * N]
    den = [1.0, N, 0.0]
    return ct.tf(num, den)


def closed_loop(plant, Kp: float, Ki: float, Kd: float, N: float | None = None):
    C = pid_tf(Kp, Ki, Kd, N)
    G = to_tf(plant)
    try:
        L = C * G
        T = ct.feedback(L, 1)
    except Exception as exc:
        raise ControlError(f"Could not form unity-feedback closed loop: {exc}") from exc
    return C, L, T


def closed_loop_payload(
    plant,
    Kp: float,
    Ki: float,
    Kd: float,
    N: float | None = None,
    t_final: float = 10.0,
    n_points: int = 500,
) -> dict:
    C, L, T = closed_loop(plant, Kp, Ki, Kd, N)
    c_num, c_den = tf_coeffs(C)
    t_num, t_den = tf_coeffs(T)
    plant_step = simulate(plant, "step", t_final=t_final, n_points=n_points)
    cl_step = simulate(T, "step", t_final=t_final, n_points=n_points)
    loop_bode = bode(L)
    cl_bode = bode(T)
    return {
        "gains": {"Kp": Kp, "Ki": Ki, "Kd": Kd, "N": N},
        "controller_num": c_num,
        "controller_den": c_den,
        "closed_loop_num": t_num,
        "closed_loop_den": t_den,
        "plant_step": plant_step,
        "closed_loop_step": cl_step,
        "loop_bode": loop_bode,
        "closed_loop_bode": cl_bode,
    }


def ziegler_nichols(plant) -> dict:
    info = bode(plant)
    gm = info.get("gain_margin")
    wcg = info.get("phase_crossover_omega")
    if gm is not None and np.isfinite(gm) and gm > 0 and wcg is not None and wcg > 0:
        Ku = float(gm)
        Pu = 2.0 * np.pi / float(wcg)
        variants = {
            "P": {"Kp": 0.5 * Ku, "Ki": 0.0, "Kd": 0.0},
            "PI": {"Kp": 0.45 * Ku, "Ki": 0.45 * Ku / (Pu / 1.2), "Kd": 0.0},
            "PID": {"Kp": 0.6 * Ku, "Ki": 0.6 * Ku / (Pu / 2.0), "Kd": 0.6 * Ku * (Pu / 8.0)},
        }
        pid = variants["PID"]
        return {
            "method": "zn",
            "variant": "ultimate",
            "fopdt": None,
            "Ku": fnum(Ku),
            "Pu": fnum(Pu),
            "phase_crossover_omega": fnum(wcg),
            "variants": variants,
            "gains": pid,
            "K": None,
            "message": (
                "Classic Ziegler–Nichols (ultimate gain): Ku = gain margin (linear), "
                "Pu = 2π/ωpc; PID from the standard Ku/Pu table."
            ),
        }

    fit = _reaction_curve_fit(plant)
    if fit is None:
        raise ControlError(
            "Ziegler–Nichols failed: (1) no finite phase-crossover, so the ultimate-gain "
            "method has no Ku/Pu; (2) the open-loop reaction curve is not usable either "
            "(the plant is unstable/marginal or its step response has no finite steady "
            "state, e.g. integrators). Tune such plants by hand or use pole placement."
        )
    K, tau, theta = fit
    k_p = 1.2 * tau / (K * theta)
    t_i = 2.0 * theta
    t_d = 0.5 * theta
    variants = {
        "P": {"Kp": tau / (K * theta), "Ki": 0.0, "Kd": 0.0},
        "PI": {"Kp": 0.9 * tau / (K * theta), "Ki": 0.9 * tau / (K * theta) / (theta / 0.3), "Kd": 0.0},
        "PID": {"Kp": k_p, "Ki": k_p / t_i, "Kd": k_p * t_d},
    }
    pid = variants["PID"]
    return {
        "method": "zn",
        "variant": "reaction_curve",
        "fopdt": {"K": fnum(K), "tau": fnum(tau), "theta": fnum(theta)},
        "Ku": None,
        "Pu": None,
        "phase_crossover_omega": None,
        "variants": variants,
        "gains": pid,
        "K": None,
        "message": (
            "Ziegler–Nichols open-loop (process reaction curve): FOPDT fit "
            f"K={K:.4g}, τ={tau:.4g}s, θ={theta:.4g}s from the unit step response; "
            "PID from Kp=1.2τ/(Kθ), Ti=2θ, Td=0.5θ. (Ultimate-gain method unavailable: "
            "no finite phase-crossover.)"
        ),
    }


def _reaction_curve_fit(plant) -> tuple[float, float, float] | None:
    """Fit FOPDT K·e^(−θs)/(τs+1) to the unit-step reaction curve (tangent method).

    Returns (K, tau, theta) or None when the response is not S-shaped (no finite
    steady state) or the tangent construction degenerates.
    """
    try:
        ss = to_ss(plant)
        eigs = np.linalg.eigvals(np.asarray(ss.A, dtype=complex))
    except Exception:
        return None
    if eigs.size == 0 or np.any(np.real(eigs) >= -1e-9):
        # Unstable or marginally stable (e.g. integrator) plants have no bounded
        # reaction curve for the classic ZN open-loop fit.
        return None
    tau_p = 1.0 / float(np.min(-np.real(eigs)))
    t_final = float(np.clip(10.0 * tau_p, 2.0, 1.0e4))
    try:
        sim = simulate(plant, "step", t_final=t_final, n_points=1500)
    except Exception:
        return None
    t = np.asarray(sim["t"], dtype=float)
    y_list = sim["y"]
    if t.size < 50 or any(v is None for v in y_list):
        return None
    y = np.asarray(y_list, dtype=float)
    if not np.isfinite(y).all():
        return None
    y0 = float(y[0])
    tail = y[int(0.9 * t.size) :]
    y_inf = float(np.mean(tail))
    span = abs(y_inf - y0)
    if span < 1e-9 or float(np.ptp(tail)) > 0.02 * span:
        # Flat response or still drifting: no usable steady state.
        return None
    grad = np.gradient(y, t)
    i_max = int(np.argmax(grad))
    m = float(grad[i_max])
    if not np.isfinite(m) or m <= 0:
        return None
    y_s, t_s = float(y[i_max]), float(t[i_max])
    theta = t_s - (y_s - y0) / m
    tau = (t_s + (y_inf - y_s) / m) - theta
    if theta <= 0 or tau <= 0:
        return None
    return float(y_inf - y0), float(tau), float(theta)


def pole_placement(plant, desired_poles: list) -> dict:
    if not desired_poles:
        raise ControlError("Pole placement needs at least one desired pole.")
    ss = to_ss(plant)
    A = np.asarray(ss.A, dtype=float)
    B = np.asarray(ss.B, dtype=float)
    n = A.shape[0]
    poles = np.array([complex(p["re"], p["im"]) for p in desired_poles], dtype=complex)
    if poles.size != n:
        raise ControlError(f"Provide exactly {n} desired closed-loop poles for this plant (order {n}).")
    try:
        ctrb = ct.ctrb(A, B)
        rank = int(np.linalg.matrix_rank(ctrb))
    except Exception:
        rank = 0
    if rank < n:
        raise ControlError("Plant is not fully controllable; pole placement is not possible.")
    try:
        K = ct.place(A, B, poles)
    except Exception as exc:
        raise ControlError(f"Pole placement failed: {exc}") from exc
    K = np.atleast_2d(np.asarray(K, dtype=float))

    pid_gains = _pid_from_second_order(plant, poles)
    map_label = "PID" if poles.size == 3 else "PD"
    return {
        "method": "pole_placement",
        "Ku": None,
        "Pu": None,
        "phase_crossover_omega": None,
        "variants": None,
        "gains": pid_gains or {"Kp": 0.0, "Ki": 0.0, "Kd": 0.0},
        "K": matrix_to_lists(K),
        "placed_poles": [{"re": fnum(p.real), "im": fnum(p.imag)} for p in poles],
        "message": (
            "State-feedback K from place(A, B, poles). "
            + (
                f"{map_label} gains matched to a 2nd-order plant with {poles.size} desired poles."
                if pid_gains
                else "Use K for state feedback; PID/PD mapping is only available for "
                "2nd-order SISO plants with 2 (PD) or 3 (PID) desired poles."
            )
        ),
    }


def _pid_from_second_order(plant, poles: np.ndarray) -> dict | None:
    """Match PID (3 desired poles) or PD (2 desired poles) on G(s) = b / (s^2 + a1 s + a0)."""
    if poles.size not in (2, 3):
        return None
    try:
        G = to_tf(plant)
        num, den = G.num[0][0], G.den[0][0]
        den = np.trim_zeros(np.asarray(den, dtype=float), "f")
        num = np.trim_zeros(np.asarray(num, dtype=float), "f")
        if den.size != 3 or num.size != 1:
            return None
        a1, a0 = float(den[1] / den[0]), float(den[2] / den[0])
        b = float(num[0] / den[0])
        if abs(b) < 1e-12:
            return None
        desired = np.poly(poles)  # monic in s
        desired = np.real(desired / desired[0])
        if poles.size == 3:
            # C = (Kd s^2 + Kp s + Ki)/s ; CL den = s^3 + (a1+b Kd)s^2 + (a0+b Kp)s + b Ki
            alpha, beta, gamma = float(desired[1]), float(desired[2]), float(desired[3])
            Kd = (alpha - a1) / b
            Kp = (beta - a0) / b
            Ki = gamma / b
        else:
            # C = Kd s + Kp ; CL den = s^2 + (a1+b Kd)s + (a0+b Kp)
            alpha, beta = float(desired[1]), float(desired[2])
            Kd = (alpha - a1) / b
            Kp = (beta - a0) / b
            Ki = 0.0
        return {"Kp": float(Kp), "Ki": float(Ki), "Kd": float(Kd)}
    except Exception:
        return None
