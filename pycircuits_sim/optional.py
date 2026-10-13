"""Guarded imports for the optional ``pycircuits-sim[control]`` extra.

The analysis and design layers are implemented with numpy alone. Installing
``python-control``/``scipy`` unlocks faster or more robust fast paths for a
few heavy numerics (margins, root locus, later LQR). Core modules must never
import those libraries at module top level; they go through this helper so a
missing extra degrades to the numpy path or raises a readable error.
"""

from __future__ import annotations

INSTALL_HINT = 'pip install "pycircuits-sim[control]"'


def try_import_control():
    """Return the python-control module, or None when it is not installed."""
    try:
        import control  # type: ignore[import-not-found]
    except ImportError:
        return None
    return control


def try_import_scipy():
    """Return the scipy module, or None when it is not installed."""
    try:
        import scipy  # type: ignore[import-not-found]
    except ImportError:
        return None
    return scipy


def require_control():
    """Return python-control or raise a readable error naming the extra."""
    control = try_import_control()
    if control is None:
        raise ValueError(
            "python-control is not installed; install the optional extra with: "
            + INSTALL_HINT
        )
    return control
