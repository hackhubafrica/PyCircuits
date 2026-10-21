"""SISO block-diagram interconnections: series, parallel, and feedback.

Pure numpy polynomial algebra, ported from ControlKit's interconnect
engine. Blocks of kind tf/ss/pid/gain are composed along an ordered
forward chain, an optional parallel chain, and an optional feedback path
("none", "unity", or a chain of block ids). Negative feedback is assumed.
The composite transfer function is normalized to a monic denominator and
analyzed with the Phase 1 analysis layer (stability, margins, Nyquist,
root locus, unit step). Educational tool: at most 6 blocks and composite
order at most 20, mirroring ControlKit's limits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .analysis.margins import MarginResult, bode_margins
from .analysis.nyquist import NyquistResult, nyquist_response
from .analysis.plant import PlantReport, normalize_plant
from .analysis.root_locus import RootLocusResult
from .analysis.root_locus import root_locus as compute_root_locus
from .analysis.stability import StabilityReport, analyze_stability
from .design.state_feedback import StepTrace
from .design.tuning import PIDGains, pid_transfer_function
from .linear_systems import (
    StateSpaceModel,
    simulate_state_space,
    transfer_function_to_state_space,
)
from .ir import IrMixin

MAX_BLOCKS = 6
MAX_ORDER = 20

BLOCK_KINDS = ("tf", "ss", "pid", "gain")


@dataclass(frozen=True)
class InterconnectBlock(IrMixin):
    """One block of an interconnection.

    ``kind`` selects which fields matter: "tf" uses ``num``/``den``
    (descending powers of s), "ss" uses ``A``/``B``/``C``/``D`` (SISO),
    "pid" uses ``gains`` (plus optional ``derivative_filter``), and "gain"
    uses ``k``.
    """

    id: str
    kind: str
    num: tuple[float, ...] | None = None
    den: tuple[float, ...] | None = None
    A: tuple[tuple[float, ...], ...] | None = None
    B: tuple[tuple[float, ...], ...] | None = None
    C: tuple[tuple[float, ...], ...] | None = None
    D: tuple[tuple[float, ...], ...] | None = None
    gains: PIDGains | None = None
    derivative_filter: float | None = None
    k: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("every block requires a nonempty id")
        if self.kind not in BLOCK_KINDS:
            raise ValueError(
                f"block '{self.id}': unknown kind {self.kind!r}; choose from "
                + ", ".join(BLOCK_KINDS)
            )


@dataclass(frozen=True)
class InterconnectSpec(IrMixin):
    """Block-algebra request: forward chain plus optional parallel/feedback.

    ``feedback`` is "none", "unity", or a tuple of block ids forming the
    feedback-path chain (negative feedback). ``stop_time``/``time_step``
    bound the embedded unit-step simulation; ``time_step`` defaults to
    ``stop_time / 500``.
    """

    blocks: tuple[InterconnectBlock, ...]
    forward: tuple[str, ...]
    parallel: tuple[str, ...] | None = None
    feedback: str | tuple[str, ...] = "unity"
    stop_time: float = 10.0
    time_step: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocks", tuple(self.blocks))
        object.__setattr__(self, "forward", tuple(self.forward))
        if self.parallel is not None:
            object.__setattr__(self, "parallel", tuple(self.parallel))
        if isinstance(self.feedback, list):
            object.__setattr__(self, "feedback", tuple(self.feedback))
        if not self.forward:
            raise ValueError("forward path must contain at least one block")
        for name, value in (("stop_time", self.stop_time), ("time_step", self.time_step)):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive number")
            if not float(value) > 0:
                raise ValueError(f"{name} must be a positive number")


@dataclass(frozen=True)
class InterconnectResult(IrMixin):
    """Composite transfer function plus the full Phase 1 analysis payload.

    ``composite_num``/``composite_den`` are normalized to a monic
    denominator (leading zeros trimmed); a static composite keeps den = (1,).
    """

    composite_num: tuple[float, ...]
    composite_den: tuple[float, ...]
    plant: PlantReport
    stability: StabilityReport
    margins: MarginResult
    nyquist: NyquistResult
    root_locus: RootLocusResult
    step: StepTrace


# A rational transfer function as descending-power coefficient arrays.
Rational = tuple[np.ndarray, np.ndarray]


def _polyadd(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    size = max(left.size, right.size)
    out = np.zeros(size, dtype=float)
    out[size - left.size :] += left
    out[size - right.size :] += right
    return out


def _series(left: Rational, right: Rational) -> Rational:
    return np.convolve(left[0], right[0]), np.convolve(left[1], right[1])


def _parallel(left: Rational, right: Rational) -> Rational:
    return (
        _polyadd(np.convolve(left[0], right[1]), np.convolve(right[0], left[1])),
        np.convolve(left[1], right[1]),
    )


def _feedback(forward: Rational, feedback_path: Rational) -> Rational:
    """Negative feedback: F / (1 + F*H)."""
    nf, df = forward
    nh, dh = feedback_path
    return np.convolve(nf, dh), _polyadd(np.convolve(df, dh), np.convolve(nf, nh))


def _normalize_rational(num: np.ndarray, den: np.ndarray) -> Rational:
    den = np.trim_zeros(den, "f")
    if den.size == 0 or not np.any(den):
        raise ValueError("composite denominator is identically zero")
    num = np.trim_zeros(num, "f")
    if num.size == 0:
        num = np.zeros(1)
    scale = float(den[0])
    return num / scale, den / scale


def _block_rational(block: InterconnectBlock) -> Rational:
    """Convert a validated block to normalized (num, den) coefficients."""
    if block.kind == "tf":
        if block.num is None or block.den is None:
            raise ValueError(
                f"block '{block.id}': transfer-function block needs num and den"
            )
        num = np.asarray(block.num, dtype=float)
        den = np.asarray(block.den, dtype=float)
        if num.ndim != 1 or den.ndim != 1 or num.size == 0 or den.size == 0:
            raise ValueError(
                f"block '{block.id}': num and den must be nonempty coefficient lists"
            )
        if not np.all(np.isfinite(num)) or not np.all(np.isfinite(den)):
            raise ValueError(
                f"block '{block.id}': polynomial coefficients must be finite"
            )
        den = np.trim_zeros(den, "f")
        if den.size == 0:
            raise ValueError(
                f"block '{block.id}': denominator cannot be identically zero"
            )
        return _normalize_rational(num, den)

    if block.kind == "ss":
        if block.A is None or block.B is None or block.C is None:
            raise ValueError(
                f"block '{block.id}': state-space block needs A, B, and C"
            )
        D = block.D if block.D is not None else ((0.0,),)
        try:
            model = StateSpaceModel.from_matrices(block.A, block.B, block.C, D)
        except ValueError as error:
            raise ValueError(f"block '{block.id}': {error}") from error
        if model.input_count != 1 or model.output_count != 1:
            raise ValueError(
                f"block '{block.id}': interconnections support SISO blocks only"
            )
        report = normalize_plant(model)
        if report.numerator is None:
            raise ValueError(
                f"block '{block.id}': could not extract a transfer function"
            )
        return (
            np.asarray(report.numerator, dtype=float),
            np.asarray(report.denominator, dtype=float),
        )

    if block.kind == "pid":
        if block.gains is None:
            raise ValueError(f"block '{block.id}': PID block needs gains")
        num, den = pid_transfer_function(
            block.gains.kp,
            block.gains.ki,
            block.gains.kd,
            derivative_filter=block.derivative_filter,
        )
        return np.asarray(num, dtype=float), np.asarray(den, dtype=float)

    # kind == "gain", validated in InterconnectBlock.__post_init__.
    if block.k is None or not np.isfinite(block.k):
        raise ValueError(f"block '{block.id}': gain block needs a finite k")
    return np.array([float(block.k)]), np.array([1.0])


def _rational_chain(
    ids: Sequence[str], systems: dict[str, Rational], label: str
) -> list[Rational]:
    chain: list[Rational] = []
    for block_id in ids:
        if block_id not in systems:
            raise ValueError(f"unknown block id '{block_id}' in {label}")
        chain.append(systems[block_id])
    if not chain:
        raise ValueError(f"{label} needs at least one block")
    return chain


def _fold_series(chain: list[Rational]) -> Rational:
    composite = chain[0]
    for block in chain[1:]:
        composite = _series(composite, block)
    return composite


def _composite_model(num: np.ndarray, den: np.ndarray) -> StateSpaceModel:
    """Realize the composite for the analysis layer.

    A static gain (order 0) has no natural state, so it is wrapped in a
    decoupled dummy state whose output equals the gain; every analysis
    quantity (DC gain, flat Bode, step) is still exact.
    """
    if num.size > den.size:
        raise ValueError(
            "composite transfer function is improper (numerator degree "
            "exceeds denominator degree)"
        )
    order = den.size - 1
    if order == 0:
        gain = float(num[0]) if num.size else 0.0
        return StateSpaceModel.from_matrices([[-1.0]], [[0.0]], [[0.0]], [[gain]])
    return transfer_function_to_state_space(
        [float(value) for value in num], [float(value) for value in den]
    )


def block_transfer_function(
    block: InterconnectBlock,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return the normalized transfer function of one block.

    The result is ``(numerator, denominator)`` with descending powers of
    ``s``, leading zeros trimmed, and a monic denominator. The chain engine
    and the general graph engine share this conversion so both agree on
    what a block means.

    Trimming matters: a PI controller has the padded numerator
    ``(0, kp, ki)`` over ``(1, 0)``, which is a proper first-order block
    even though the raw coefficient lists have different lengths.
    """
    num, den = _block_rational(block)
    normalized_num, normalized_den = _normalize_rational(num, den)
    return (
        tuple(float(value) for value in normalized_num),
        tuple(float(value) for value in normalized_den),
    )


def analyze_composite(
    num: Sequence[float],
    den: Sequence[float],
    stop_time: float = 10.0,
    time_step: float | None = None,
) -> InterconnectResult:
    """Analyze a composite transfer function with the Phase 1 analysis layer.

    ``num``/``den`` are descending-power coefficient lists. The composite
    is normalized to a monic denominator and then analyzed for stability,
    margins, Nyquist, root locus, and unit-step response.
    """
    numerator = np.asarray(num, dtype=float)
    denominator = np.asarray(den, dtype=float)
    if numerator.ndim != 1 or denominator.ndim != 1:
        raise ValueError("composite coefficients must be 1-D arrays")
    if numerator.size == 0 or denominator.size == 0:
        raise ValueError("composite coefficients must be nonempty")
    if not np.all(np.isfinite(numerator)) or not np.all(np.isfinite(denominator)):
        raise ValueError("composite coefficients must all be finite")
    normalized_num, normalized_den = _normalize_rational(numerator, denominator)
    order = normalized_den.size - 1
    if order > MAX_ORDER:
        raise ValueError(
            f"composite order {order} exceeds the limit of {MAX_ORDER}; "
            "simplify the interconnection"
        )

    model = _composite_model(normalized_num, normalized_den)
    step = float(stop_time)
    resolved_step = float(time_step) if time_step is not None else step / 500.0
    step_result = simulate_state_space(
        model, resolved_step, step, lambda _t: (1.0,)
    )
    return InterconnectResult(
        composite_num=tuple(float(value) for value in normalized_num),
        composite_den=tuple(float(value) for value in normalized_den),
        plant=normalize_plant(model),
        stability=analyze_stability(model),
        margins=bode_margins(model),
        nyquist=nyquist_response(model),
        root_locus=compute_root_locus(model),
        step=StepTrace(
            tuple(float(value) for value in step_result.time),
            tuple(float(value) for value in step_result.outputs["y1"]),
        ),
    )


def interconnect(spec: InterconnectSpec) -> InterconnectResult:
    """Compose blocks and analyze the resulting SISO closed loop.

    The forward chain is multiplied in order; an optional parallel chain is
    summed with it; feedback is then applied (negative). At most
    ``MAX_BLOCKS`` blocks and composite order ``MAX_ORDER`` are supported,
    matching ControlKit. Raises ValueError with a readable message on any
    modeling error.
    """
    if len(spec.blocks) > MAX_BLOCKS:
        raise ValueError(f"at most {MAX_BLOCKS} blocks are supported")
    systems: dict[str, Rational] = {}
    for block in spec.blocks:
        if block.id in systems:
            raise ValueError(f"duplicate block id '{block.id}'")
        systems[block.id] = _block_rational(block)

    composite = _fold_series(
        _rational_chain(spec.forward, systems, "forward path")
    )
    if spec.parallel:
        parallel = _fold_series(
            _rational_chain(spec.parallel, systems, "parallel path")
        )
        composite = _parallel(composite, parallel)

    feedback = spec.feedback
    if isinstance(feedback, str):
        if feedback == "unity":
            composite = _feedback(composite, (np.array([1.0]), np.array([1.0])))
        elif feedback == "none":
            pass
        else:
            raise ValueError(
                "feedback must be 'none', 'unity', or a tuple of block ids"
            )
    elif isinstance(feedback, (tuple, list)):
        path = _rational_chain(feedback, systems, "feedback path")
        composite = _feedback(composite, _fold_series(path))
    else:
        raise ValueError(
            "feedback must be 'none', 'unity', or a tuple of block ids"
        )

    num, den = _normalize_rational(*composite)
    return analyze_composite(
        num,
        den,
        stop_time=float(spec.stop_time),
        time_step=(
            float(spec.time_step) if spec.time_step is not None else None
        ),
    )


