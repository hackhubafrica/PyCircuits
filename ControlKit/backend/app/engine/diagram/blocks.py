from __future__ import annotations

from typing import Any

import control as ct
import numpy as np

from app.engine.pid import pid_tf
from app.engine.plant import build_system
from app.engine.util import ControlError
from app.schemas import PlantSpec


def _err(bid: str, kind: str, msg: str) -> ControlError:
    return ControlError(f"Block '{bid}' ({kind}): {msg}.")


def _scalar(params: dict, bid: str, kind: str, name: str, default: float | None = None) -> float:
    if name in params:
        raw = params[name]
    elif default is not None:
        raw = default
    else:
        raise _err(bid, kind, f"missing parameter '{name}'")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise _err(bid, kind, f"parameter '{name}' must be a number")
    try:
        v = float(raw)
    except (TypeError, ValueError) as exc:
        raise _err(bid, kind, f"parameter '{name}' must be a number") from exc
    if not np.isfinite(v):
        raise _err(bid, kind, f"parameter '{name}' must be finite")
    return v


def _float_list(params: dict, bid: str, kind: str, name: str, default=None) -> list[float]:
    raw = params.get(name, default)
    if raw is None:
        raise _err(bid, kind, f"missing parameter '{name}'")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise _err(bid, kind, f"parameter '{name}' must be a list of numbers")
    out: list[float] = []
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise _err(bid, kind, f"parameter '{name}' must contain only numbers")
        fv = float(v)
        if not np.isfinite(fv):
            raise _err(bid, kind, f"parameter '{name}' must be finite")
        out.append(fv)
    return out


def _matrix(params: dict, bid: str, kind: str, name: str, default=None) -> np.ndarray:
    raw = params.get(name, default)
    if raw is None:
        raise _err(bid, kind, f"missing parameter '{name}'")
    try:
        arr = np.asarray(raw, dtype=float)
    except (TypeError, ValueError) as exc:
        raise _err(bid, kind, f"parameter '{name}' must be a numeric matrix") from exc
    if arr.ndim == 1:
        arr = arr.reshape(1, -1) if name in ("C", "D") else arr.reshape(-1, 1)
    if arr.ndim != 2 or not np.isfinite(arr).all():
        raise _err(bid, kind, f"parameter '{name}' must be a finite numeric matrix")
    return arr


class Block:
    """Base block: scalar SISO signal, optional continuous state."""

    kind = "block"
    n_inputs = 0
    n_outputs = 1
    feedthrough = False
    n_states = 0

    def __init__(self, block_id: str, params: dict[str, Any]):
        self.id = block_id
        self.params = dict(params or {})
        self._setup()

    def _setup(self) -> None:
        pass

    def initial_state(self) -> np.ndarray:
        return np.zeros(self.n_states)

    def output(self, t: float, u: list[float], x: np.ndarray) -> list[float]:
        raise NotImplementedError

    def deriv(self, t: float, u: list[float], x: np.ndarray) -> np.ndarray:
        return np.zeros(self.n_states)