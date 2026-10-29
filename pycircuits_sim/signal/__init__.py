"""Signal processing and system identification.

Expands the analysis core beyond classical control: analog filter design
(Butterworth, Chebyshev Type I) and frequency-response fitting (system ID)
via the Sanathanan-Koerner iteration. Pure numpy core; scipy is an optional
fast path.
"""

from __future__ import annotations

from .filter_design import (
    FilterDesignResult,
    FilterSpec,
    design_filter,
)
from .system_id import (
    FrequencyResponseFit,
    FitSpec,
    fit_frequency_response,
)

__all__ = [
    "FilterDesignResult",
    "FilterSpec",
    "FrequencyResponseFit",
    "FitSpec",
    "design_filter",
    "fit_frequency_response",
]