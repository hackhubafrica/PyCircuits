"""State-feedback design: Ackermann placement and LQR (SISO plants).

Pure numpy for Ackermann; LQR solves the continuous algebraic Riccati
equation (CARE) with scipy's ``solve_continuous_are`` when the optional
``pycircuits-sim[control]`` extra is installed, falling back to a numpy
Hamiltonian-eigensolver for small teach-scale systems. Both methods report
open- vs closed-loop unit-step comparisons using the N-bar reference
pre-gain. Educational tool.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np

from ..analysis.plant import require_continuous, require_siso
from ..linear_systems import StateSpaceModel, simulate_state_space
from ..optional import try_import_scipy
from .tuning import ackermann_gain


@dataclass(frozen=True)
class StepTrace:
    """Times and output samples of a unit-step simulation."""

    time_s: tuple[float, ...]
    output: tuple[float, ...]


@dataclass(frozen=True)
class StateFeedbackResult:
    """State-feedback design outcome with step comparisons.

    ``closed_loop_k`` is the row vector K (one tuple per state). ``nbar`` is
    the reference pre-gain making the closed-loop step reach unit steady
    state when it exists (None for plants with zero DC path).
    """

    method: str
    closed_loop_k: tuple[tuple[float, ...], ...]
    nbar: float | None
    order: int
    controllability_rank: int
    open_loop_poles: tuple[complex, ...]
    closed_loop_poles: tuple[complex, ...]
    desired_poles: tuple[complex, ...] | None
    open_step: StepTrace
    closed_step: StepTrace
    q: tuple[float, ...] | None
    r: float | None
    s: tuple[tuple[float, ...], ...] | None
    message: str


def _check_controllable(A: np.ndarray, B: np.ndarray) -> int:
    order = A.shape[0]
    blocks = [B]
    power = np.eye(order)
    for _ in range(order - 1):
        power = power @ A
        blocks.append(power @ B)
    rank = int(np.linalg.matrix_rank(np.hstack(blocks)))
    if rank < order:
        raise ValueError(
            f"plant is not fully controllable (rank {rank} < order {order}); "
            "state-feedback design is not possible"
        )
    return rank


def _closed_loop_step(
    A: np.ndarray,
    B: np.ndarray,
    C: np.ndarray,
    D: np.ndarray,
    gain: np.ndarray,
    nbar: float | None,
) -> tuple[StepTrace, StepTrace]:
    """Open- and closed-loop unit-step responses (closed loop uses nbar)."""
    # Time window from the slowest closed-loop time constant.
    closed_A = A - B @ gain
    real_parts = np.real(np.linalg.eigvals(closed_A))
    stable = -real_parts[real_parts < -1e-9]
    stop_time = (
        float(np.clip(8.0 / float(np.min(stable)), 2.0, 60.0))
        if stable.size
        else 12.0
    )
    time_step = stop_time / 500.0

    open_model = StateSpaceModel.from_matrices(A, B, C, D)
    open_result = simulate_state_space(
        open_model, time_step, stop_time, lambda _t: (1.0,)
    )
    scale = 1.0 if nbar is None else nbar
    closed_model = StateSpaceModel.from_matrices(
        closed_A, B * scale, C - D @ gain, D * scale
    )
    closed_result = simulate_state_space(
        closed_model, time_step, stop_time, lambda _t: (1.0,)
    )
    open_trace = StepTrace(
        tuple(float(v) for v in open_result.time),
        tuple(float(v) for v in open_result.outputs["y1"]),
    )
    closed_trace = StepTrace(
        tuple(float(v) for v in closed_result.time),
        tuple(float(v) for v in closed_result.outputs["y1"]),
    )
    return open_trace, closed_trace


def _nbar(
    A: np.ndarray, B: np.ndarray, C: np.ndarray, gain: np.ndarray
) -> float | None:
    """Reference pre-gain: nbar = -1 / (C (A - BK)^-1 B)."""
    closed_A = A - B @ gain
    try:
        denominator = float((C @ np.linalg.solve(closed_A, B)).item())
    except np.linalg.LinAlgError:
        return None
    if abs(denominator) <= 1e-12:
        return None
    return -1.0 / denominator


def _ss_data(model: StateSpaceModel) -> tuple[np.ndarray, ...]:
    require_continuous(model, "state-feedback design")
    require_siso(model, "state-feedback design")
    A = np.asarray(model.A, dtype=float)
    B = np.asarray(model.B, dtype=float)
    C = np.asarray(model.C, dtype=float)
    D = np.asarray(model.D, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1] or A.shape[0] == 0:
        raise ValueError("state-feedback design needs a square, non-empty A matrix")
    return A, B, C, D


def _payload(
    method: str,
    A: np.ndarray,
    B: np.ndarray,
    C: np.ndarray,
    D: np.ndarray,
    gain: np.ndarray,
    rank: int,
    message: str,
    desired: np.ndarray | None = None,
    q: np.ndarray | None = None,
    r: float | None = None,
    s: np.ndarray | None = None,
) -> StateFeedbackResult:
    closed_A = A - B @ gain
    nbar = _nbar(A, B, C, gain)
    open_step, closed_step = _closed_loop_step(A, B, C, D, gain, nbar)
    open_poles = tuple(
        sorted(
            (complex(v) for v in np.linalg.eigvals(A)),
            key=lambda z: (z.real, z.imag),
        )
    )
    closed_poles = tuple(
        sorted(
            (complex(v) for v in np.linalg.eigvals(closed_A)),
            key=lambda z: (z.real, z.imag),
        )
    )
    return StateFeedbackResult(
        method=method,
        closed_loop_k=tuple(tuple(float(v) for v in row) for row in gain),
        nbar=nbar,
        order=int(A.shape[0]),
        controllability_rank=rank,
        open_loop_poles=open_poles,
        closed_loop_poles=closed_poles,
        desired_poles=(
            tuple(complex(v) for v in desired) if desired is not None else None
        ),
        open_step=open_step,
        closed_step=closed_step,
        q=None if q is None else tuple(float(v) for v in q),
        r=r,
        s=None if s is None else tuple(tuple(float(v) for v in row) for row in s),
        message=message,
    )


def ackermann(
    model: StateSpaceModel, desired_poles: Sequence[complex]
) -> StateFeedbackResult:
    """Place all closed-loop poles with full state feedback (Ackermann).

    Computes K from the controllability-matrix inverse after checking the
    plant is controllable. The closed-loop step comparison uses the N-bar
    reference pre-gain. Educational tool; verify pole locations before use.
    """
    A, B, C, D = _ss_data(model)
    poles = np.asarray(desired_poles, dtype=complex)
    if poles.size == 0:
        raise ValueError("Ackermann needs at least one desired pole")
    gain, rank = ackermann_gain(A, B, poles)
    message = (
        f"Ackermann: K places {A.shape[0]} pole(s) via the "
        "controllability-matrix inverse; the closed-loop step uses the "
        "N-bar reference pre-gain."
    )
    return _payload("ackermann", A, B, C, D, gain, rank, message, desired=poles)


def _lqr_scipy(
    A: np.ndarray, B: np.ndarray, q: np.ndarray, r: float
) -> tuple[np.ndarray, np.ndarray] | None:
    """LQR via scipy's CARE solver; None when scipy is unavailable."""
    scipy_optional = try_import_scipy()
    if scipy_optional is None:
        return None
    try:
        from scipy import linalg as scipy_linalg  # noqa: PLC0415

        s_matrix = scipy_linalg.solve_continuous_are(
            A, B, q, np.array([[r]])
        )
    except Exception:
        return None
    gain = np.linalg.solve(np.array([[r]]), B.T @ s_matrix)
    return np.real(np.atleast_2d(gain)), np.real(np.atleast_2d(s_matrix))


def _lqr_numpy(
    A: np.ndarray, B: np.ndarray, q: np.ndarray, r: float
) -> tuple[np.ndarray, np.ndarray]:
    """Small-system LQR: stable invariant subspace of the Hamiltonian matrix.

    Solves A^T P + P A - P B R^-1 B^T P + Q = 0 by taking the eigenspace of
    H = [[A, -B R^-1 B^T], [-Q, -A^T]] spanned by eigenvalues with negative
    real part: P = U2 U1^-1. This is exact in exact arithmetic and reliable
    for teach-scale (<= ~6 states) controllable plants; ill-conditioned
    Hamiltonians raise a readable ValueError.
    """
    order = A.shape[0]
    r_inv_b = np.linalg.solve(np.array([[r]]), B.T)
    hamiltonian = np.block(
        [
            [A, -B @ r_inv_b],
            [-q, -A.T],
        ]
    )
    eigenvalues, eigenvectors = np.linalg.eig(hamiltonian)
    stable = np.real(eigenvalues) < -1e-10
    if int(np.count_nonzero(stable)) != order:
        raise ValueError(
            "numpy LQR needs exactly half of the Hamiltonian eigenvalues in "
            "the open left half-plane; the plant may be uncontrollable or "
            "the weighting degenerate. Install the optional extra "
            '(pip install "pycircuits-sim[control]") for a robust solver.'
        )
    subspace = eigenvectors[:, stable]
    upper = subspace[:order, :]
    lower = subspace[order:, :]
    try:
        s_matrix = np.real(lower @ np.linalg.inv(upper))
    except np.linalg.LinAlgError as error:
        raise ValueError(
            "numpy LQR eigenspace is singular; install the optional extra "
            '(pip install "pycircuits-sim[control]") for a robust solver.'
        ) from error
    s_matrix = 0.5 * (s_matrix + s_matrix.T)
    gain = np.linalg.solve(np.array([[r]]), B.T @ s_matrix)
    return np.atleast_2d(gain), s_matrix


def lqr(
    model: StateSpaceModel, q_diag: Sequence[float], r: float
) -> StateFeedbackResult:
    """Linear-quadratic regulator for a SISO plant (diagonal Q, scalar R).

    Minimizes the integral of x^T Q x + u^T R u. Uses scipy's continuous
    algebraic Riccati solver when installed, otherwise a numpy Hamiltonian
    eigensolver intended for small teaching examples. The closed-loop step
    comparison uses the N-bar reference pre-gain.
    """
    A, B, C, D = _ss_data(model)
    order = A.shape[0]
    q = np.asarray(q_diag, dtype=float)
    if q.ndim != 1 or q.size != order:
        raise ValueError(f"Q must have {order} diagonal entries for this plant")
    if not np.all(np.isfinite(q)) or np.any(q < 0):
        raise ValueError("Q diagonal entries must be finite and >= 0")
    if not np.any(q > 0):
        raise ValueError("at least one Q entry must be positive")
    if not math.isfinite(r) or r <= 0:
        raise ValueError("R must be a finite positive scalar")

    rank = _check_controllable(A, B)
    q_matrix = np.diag(q)
    solved = _lqr_scipy(A, B, q_matrix, r)
    if solved is None:
        gain, s_matrix = _lqr_numpy(A, B, q_matrix, r)
        solver_note = "numpy Hamiltonian solver"
    else:
        gain, s_matrix = solved
        solver_note = "scipy CARE solver"
    message = (
        f"LQR ({solver_note}): K minimizes the integral of x^T Q x + u^T R u "
        f"with diag(Q)=[{', '.join(f'{v:g}' for v in q)}], R={r:g}; the "
        "closed-loop step uses the N-bar reference pre-gain."
    )
    return _payload(
        "lqr",
        A,
        B,
        C,
        D,
        gain,
        rank,
        message,
        q=q,
        r=float(r),
        s=s_matrix,
    )


