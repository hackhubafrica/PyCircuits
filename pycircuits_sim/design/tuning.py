"""Controller tuning: Ziegler-Nichols and pole placement.

Pure numpy port of ControlKit's tuning engine. Two methods:

- ``ziegler_nichols``: classic ultimate-gain tuning from Bode phase
  crossover (Ku, Pu) with the open-loop reaction-curve fallback (FOPDT
  tangent fit) when no finite ultimate gain exists.
- ``tune_pole_placement``: state-feedback placement of desired closed-loop
  poles via the controllability-matrix inverse, with PID/PD coefficient
  matching when the plant is second order.

Educational tool: gains are starting points for simulation, not validated
controller designs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np

from ..analysis.margins import bode_margins
from ..analysis.plant import normalize_plant, require_continuous, require_siso
from ..linear_systems import StateSpaceModel, simulate_state_space
from ..ir import IrMixin


@dataclass(frozen=True)
class PIDGains(IrMixin):
    """Parallel-form PID coefficients (Kp + Ki/s + Kd*s)."""

    kp: float
    ki: float
    kd: float

    def __post_init__(self) -> None:
        for name, value in (("kp", self.kp), ("ki", self.ki), ("kd", self.kd)):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class FopdtFit(IrMixin):
    """First-order-plus-dead-time parameters K e^{-theta s} / (tau s + 1)."""

    gain: float
    time_constant_s: float
    dead_time_s: float


@dataclass(frozen=True)
class TuneResult(IrMixin):
    """Ziegler-Nichols tuning outcome.

    ``variant`` is "ultimate" (Ku/Pu from the phase crossover) or
    "reaction_curve" (FOPDT tangent fit). ``state_feedback_k`` is unused
    by ZN (None) and carries the placed K for pole placement. ``gains``
    is the recommended PID (or PD when Ki is zero by construction).
    """

    method: str
    variant: str | None
    gains: PIDGains
    p_gains: PIDGains | None
    pi_gains: PIDGains | None
    ku: float | None
    pu: float | None
    fopdt: FopdtFit | None
    state_feedback_k: tuple[tuple[float, ...], ...] | None
    message: str


def pid_transfer_function(
    kp: float, ki: float, kd: float, derivative_filter: float | None = None
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Numerator/denominator of a parallel PID, descending powers of s.

    Without a filter the controller is ``(kd s^2 + kp s + ki) / s``. With
    ``derivative_filter`` N the realization is
    ``((kp + kd N) s^2 + (kp N + ki) s + ki N) / (s (s + N))``.
    """
    for name, value in (("kp", kp), ("ki", ki), ("kd", kd)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if derivative_filter is None or derivative_filter <= 0:
        return (kd, kp, ki), (1.0, 0.0)
    if not math.isfinite(derivative_filter):
        raise ValueError("derivative_filter must be finite")
    n = float(derivative_filter)
    return (kp + kd * n, kp * n + ki, ki * n), (1.0, n, 0.0)


def _ultimate_variants(ku: float, pu: float) -> dict[str, PIDGains]:
    return {
        "P": PIDGains(0.5 * ku, 0.0, 0.0),
        "PI": PIDGains(0.45 * ku, 0.45 * ku / (pu / 1.2), 0.0),
        "PID": PIDGains(
            0.6 * ku, 0.6 * ku / (pu / 2.0), 0.6 * ku * (pu / 8.0)
        ),
    }


def _reaction_curve_variants(
    gain: float, tau: float, theta: float
) -> dict[str, PIDGains]:
    k_p = 1.2 * tau / (gain * theta)
    t_i = 2.0 * theta
    t_d = 0.5 * theta
    return {
        "P": PIDGains(tau / (gain * theta), 0.0, 0.0),
        "PI": PIDGains(
            0.9 * tau / (gain * theta),
            0.9 * tau / (gain * theta) / (theta / 0.3),
            0.0,
        ),
        "PID": PIDGains(k_p, k_p / t_i, k_p * t_d),
    }


def _reaction_curve_fit(model: StateSpaceModel) -> FopdtFit | None:
    """Fit FOPDT K e^{-theta s}/(tau s + 1) to the unit-step reaction curve.

    Uses the classic tangent construction at the steepest slope. Returns
    None when the plant is unstable or marginally stable, or when the
    response has no finite steady state (integrators, drift).
    """
    require_continuous(model, "reaction-curve fit")
    report = normalize_plant(model)
    eigenvalues = np.asarray(report.poles, dtype=complex)
    if eigenvalues.size == 0 or np.any(np.real(eigenvalues) >= -1e-9):
        return None
    slowest_time_constant = 1.0 / float(np.min(-np.real(eigenvalues)))
    stop_time = float(np.clip(10.0 * slowest_time_constant, 2.0, 1.0e4))
    time_step = stop_time / 1500.0
    try:
        result = simulate_state_space(
            model, time_step, stop_time, lambda _t: (1.0,)
        )
    except ValueError:
        return None
    times = np.asarray(result.time, dtype=float)
    values = np.asarray(result.outputs["y1"], dtype=float)
    if times.size < 50 or not np.isfinite(values).all():
        return None
    initial = float(values[0])
    tail = values[int(0.9 * times.size) :]
    steady = float(np.mean(tail))
    span = abs(steady - initial)
    if span < 1e-9 or float(np.ptp(tail)) > 0.02 * span:
        return None
    gradient = np.gradient(values, times)
    steepest = int(np.argmax(gradient))
    slope = float(gradient[steepest])
    if not math.isfinite(slope) or slope <= 0:
        return None
    value_at_steepest = float(values[steepest])
    time_at_steepest = float(times[steepest])
    dead_time = time_at_steepest - (value_at_steepest - initial) / slope
    time_constant = (time_at_steepest + (steady - value_at_steepest) / slope) - dead_time
    if dead_time <= 0 or time_constant <= 0:
        return None
    return FopdtFit(steady - initial, time_constant, dead_time)


def ziegler_nichols(model: StateSpaceModel) -> TuneResult:
    """Tune PID gains by the Ziegler-Nichols methods for a SISO plant.

    The ultimate-gain method applies when the open loop has a finite phase
    crossover (Ku = linear gain margin, Pu = 2*pi/w_pc). Otherwise the
    open-loop reaction-curve method fits an FOPDT model to the unit-step
    response. Raises ValueError when neither applies (unstable, marginal,
    or integrator plants): tune those by hand or with pole placement.
    """
    require_continuous(model, "ziegler_nichols")
    require_siso(model, "ziegler_nichols")

    margins = bode_margins(model)
    ku = margins.gain_margin
    wcg = margins.phase_crossover_rad_s
    if ku is not None and ku > 0 and wcg is not None and wcg > 0:
        pu = 2.0 * math.pi / wcg
        variants = _ultimate_variants(ku, pu)
        pid = variants["PID"]
        return TuneResult(
            method="ziegler_nichols",
            variant="ultimate",
            gains=pid,
            p_gains=variants["P"],
            pi_gains=variants["PI"],
            ku=ku,
            pu=pu,
            fopdt=None,
            state_feedback_k=None,
            message=(
                "Ziegler-Nichols (ultimate gain): Ku equals the linear gain "
                f"margin ({ku:.4g}), Pu = 2*pi/w_pc = {pu:.4g} s from the "
                "phase crossover; PID from the classic Ku/Pu table."
            ),
        )

    fit = _reaction_curve_fit(model)
    if fit is None:
        raise ValueError(
            "Ziegler-Nichols failed: (1) no finite phase-crossover, so the "
            "ultimate-gain method has no Ku/Pu; (2) the open-loop reaction "
            "curve is not usable either (the plant is unstable/marginal or "
            "its step response has no finite steady state, e.g. "
            "integrators). Tune such plants by hand or use pole placement."
        )
    variants = _reaction_curve_variants(fit.gain, fit.time_constant_s, fit.dead_time_s)
    pid = variants["PID"]
    return TuneResult(
        method="ziegler_nichols",
        variant="reaction_curve",
        gains=pid,
        p_gains=variants["P"],
        pi_gains=variants["PI"],
        ku=None,
        pu=None,
        fopdt=fit,
        state_feedback_k=None,
        message=(
            "Ziegler-Nichols open-loop (process reaction curve): FOPDT fit "
            f"K={fit.gain:.4g}, tau={fit.time_constant_s:.4g}s, "
            f"theta={fit.dead_time_s:.4g}s from the unit-step response; PID "
            "from Kp=1.2*tau/(K*theta), Ti=2*theta, Td=0.5*theta. "
            "(Ultimate-gain method unavailable: no finite phase-crossover.)"
        ),
    )


def _controllability_matrix(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    order = A.shape[0]
    blocks = [B]
    power = np.eye(A.shape[0])
    for _ in range(order - 1):
        power = power @ A
        blocks.append(power @ B)
    return np.hstack(blocks)


def _matrix_polynomial(A: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    """Evaluate the monic p(A) = A^n + c_{n-1} A^(n-1) + ... + c_0 I.

    ``coefficients`` is ordered from the A^(n-1) term down to the constant
    term (the descending-power order of ``np.poly`` without its leading 1),
    so the loop is Horner's method in A.
    """
    order = A.shape[0]
    result = np.eye(order)
    for coefficient in coefficients:
        result = result @ A + coefficient * np.eye(order)
    return result


def ackermann_gain(
    A: np.ndarray, B: np.ndarray, desired_poles: Sequence[complex]
) -> tuple[np.ndarray, int]:
    """State-feedback K via Ackermann's formula (SISO, numpy only).

    Returns (K column matrix, controllability_rank). Raises ValueError when
    the pole count does not match the order, the plant is not fully
    controllable, or the result would be complex (poles not conjugate
    symmetric).
    """
    order = A.shape[0]
    poles = np.asarray(desired_poles, dtype=complex)
    if poles.size != order:
        raise ValueError(
            f"provide exactly {order} desired poles for this plant (order {order})"
        )
    if B.ndim != 2 or B.shape[1] != 1:
        raise ValueError("ackermann placement supports SISO plants only")
    controllability = _controllability_matrix(A, B)
    rank = int(np.linalg.matrix_rank(controllability))
    if rank < order:
        raise ValueError(
            f"plant is not fully controllable (rank {rank} < order {order}); "
            "pole placement is not possible"
        )

    # Ackermann: K = e_n^T W^-1 p(A); the last row of W^-1 p(A).
    # desired[1:] = [a_{n-1}, ..., a_0] feeds Horner in descending order.
    desired = np.poly(poles)
    try:
        placed = np.linalg.solve(
            controllability, _matrix_polynomial(A, desired[1:])
        )
    except np.linalg.LinAlgError as error:
        raise ValueError(
            "controllability matrix is singular; cannot place poles"
        ) from error
    gain = placed[-1, :]
    if np.iscomplexobj(gain) and float(np.max(np.abs(np.imag(gain)))) > 1e-9:
        raise ValueError(
            "desired poles must be conjugate symmetric so K stays real"
        )
    # Row vector (1 x n) so matrix algebra reads A - B @ K.
    gain = np.real(gain).astype(float).reshape((1, order))
    return gain, rank


def tune_pole_placement(
    model: StateSpaceModel, desired_poles: Sequence[complex]
) -> TuneResult:
    """Place closed-loop poles with state feedback; map to PID when possible.

    Computes K with Ackermann's formula after a controllability check. For a
    second-order SISO plant with 2 (PD) or 3 (PID) desired poles, the gains
    of a parallel PID controller matching the characteristic polynomial are
    reported too; otherwise ``gains`` is zeroed and ``state_feedback_k``
    should be used directly.
    """
    require_continuous(model, "tune_pole_placement")
    require_siso(model, "tune_pole_placement")
    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    poles = np.asarray(desired_poles, dtype=complex)
    if poles.size == 0:
        raise ValueError("pole placement needs at least one desired pole")

    gain, rank = ackermann_gain(A, B, poles)

    pid_gains = _pid_from_second_order(model, poles)
    label = "PID" if poles.size == 3 else "PD"
    gain_matrix = tuple(tuple(float(v) for v in row) for row in gain)
    return TuneResult(
        method="pole_placement",
        variant=None,
        gains=pid_gains or PIDGains(0.0, 0.0, 0.0),
        p_gains=None,
        pi_gains=None,
        ku=None,
        pu=None,
        fopdt=None,
        state_feedback_k=gain_matrix,
        message=(
            "State-feedback K from Ackermann's formula. "
            + (
                f"{label} gains matched to a 2nd-order plant with "
                f"{poles.size} desired poles."
                if pid_gains
                else "Use K for state feedback; PID/PD mapping is only "
                "available for 2nd-order SISO plants with 2 (PD) or 3 (PID) "
                "desired poles."
            )
        ),
    )


def _pid_from_second_order(
    model: StateSpaceModel, poles: np.ndarray
) -> PIDGains | None:
    """Match PID (3 poles) or PD (2 poles) on G(s) = b / (s^2 + a1 s + a0)."""
    if poles.size not in (2, 3):
        return None
    report = normalize_plant(model)
    if report.numerator is None or len(report.denominator) != 3:
        return None
    numerator = np.asarray(report.numerator, dtype=float)
    denominator = np.asarray(report.denominator, dtype=float)
    if numerator.size != 1 or abs(denominator[0]) < 1e-15:
        return None
    a1 = float(denominator[1] / denominator[0])
    a0 = float(denominator[2] / denominator[0])
    b = float(numerator[0] / denominator[0])
    if abs(b) < 1e-12:
        return None
    desired = np.poly(poles)
    desired = np.real(desired / desired[0])
    if poles.size == 3:
        alpha, beta, gamma = float(desired[1]), float(desired[2]), float(desired[3])
        kd = (alpha - a1) / b
        kp = (beta - a0) / b
        ki = gamma / b
    else:
        alpha, beta = float(desired[1]), float(desired[2])
        kd = (alpha - a1) / b
        kp = (beta - a0) / b
        ki = 0.0
    try:
        return PIDGains(float(kp), float(ki), float(kd))
    except ValueError:
        return None


