"""Controller-design layer ported from ControlKit, implemented in numpy.

Ziegler-Nichols tuning (ultimate gain + FOPDT reaction curve), pole
placement with PID/PD matching, and state-feedback design (Ackermann, LQR).
Heavy numerics use the optional ``pycircuits-sim[control]`` extra when
installed; everything works with numpy alone on teach-scale systems.
"""

from __future__ import annotations

from .state_feedback import (
    StateFeedbackResult,
    StepTrace,
    ackermann,
    lqr,
)
from .tuning import (
    FopdtFit,
    PIDGains,
    TuneResult,
    ackermann_gain,
    pid_transfer_function,
    tune_pole_placement,
    ziegler_nichols,
)

__all__ = [
    "FopdtFit",
    "PIDGains",
    "StateFeedbackResult",
    "StepTrace",
    "TuneResult",
    "ackermann",
    "ackermann_gain",
    "lqr",
    "pid_transfer_function",
    "tune_pole_placement",
    "ziegler_nichols",
]
