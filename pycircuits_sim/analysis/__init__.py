"""Classical control analysis ported from ControlKit, implemented in numpy.

Subpackage of ``pycircuits_sim`` with plant normalization, stability
verdicts, step-response metrics, Bode margins, Nyquist response, and root
locus. Everything here works with numpy alone; see ``pycircuits_sim.optional``
for the optional fast paths.
"""

from __future__ import annotations

from .margins import MarginResult, bode_margins
from .metrics import StepMetrics, step_metrics
from .nyquist import NyquistResult, nyquist_response
from .plant import PlantReport, normalize_plant
from .root_locus import RootLocusResult, root_locus
from .stability import StabilityReport, analyze_stability

__all__ = [
    "MarginResult",
    "NyquistResult",
    "PlantReport",
    "RootLocusResult",
    "StepMetrics",
    "StabilityReport",
    "analyze_stability",
    "bode_margins",
    "normalize_plant",
    "nyquist_response",
    "root_locus",
    "step_metrics",
]
