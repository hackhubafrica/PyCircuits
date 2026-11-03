"""Optional payloads: modelica, rust, jax extensions.

Provides guarded imports for optional extras. Core modules must never import
those libraries at module top level; they go through this helper so a missing
extra degrades gracefully with a readable error.
"""

from __future__ import annotations

INSTALL_HINT = 'pip install "pycircuits-sim[modelica,arrow]"'


def try_import_modelica():
    """Return the rumoca module, or None when it is not installed."""
    try:
        import rumoca  # type: ignore[import-not-found]
    except ImportError:
        return None
    return rumoca


def require_modelica():
    """Return rumoca or raise a readable error naming the extra."""
    rum = try_import_modelica()
    if rum is None:
        raise ValueError(
            "modelica is not installed; install the optional extra with: " + INSTALL_HINT
        )
    return rum


def try_import_arrow():
    """Return the pyarrow module, or None when it is not installed."""
    try:
        import pyarrow  # type: ignore[import-not-found]
    except ImportError:
        return None
    return pyarrow


def require_arrow():
    """Return pyarrow or raise a readable error naming the extra."""
    pa = try_import_arrow()
    if pa is None:
        raise ValueError(
            "arrow is not installed; install the optional extra with: " + INSTALL_HINT
        )
    return pa
