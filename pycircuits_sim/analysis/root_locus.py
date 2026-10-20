"""Root locus for SISO continuous-time plants.

Pure numpy core: the closed-loop characteristic polynomial is
``den(s) + K * num(s)``; its roots are tracked on a gain grid and branches
are matched to the open-loop poles by nearest-neighbor continuation. When
the optional ``pycircuits-sim[control]`` extra is installed,
``ct.root_locus_map`` is preferred for its adaptive gain handling. This is
an educational tool, not a replacement for rigorous continuation software.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..linear_systems import StateSpaceModel
from ..optional import try_import_control
from .plant import (
    require_continuous,
    require_siso,
    siso_polynomials,
    normalize_plant,
)
from ..ir import IrMixin


@dataclass(frozen=True)
class RootLocusResult(IrMixin):
    """Locus branches over a gain grid.

    ``branches[i]`` is the continuation of open-loop pole ``i``; each entry
    is a complex root per gain in ``gains``.
    """

    gains: tuple[float, ...]
    branches: tuple[tuple[complex, ...], ...]
    open_loop_poles: tuple[complex, ...]
    open_loop_zeros: tuple[complex, ...]


def _control_loci(
    model: StateSpaceModel, gains: np.ndarray
) -> tuple[np.ndarray, np.ndarray] | None:
    control = try_import_control()
    if control is None or not hasattr(control, "root_locus_map"):
        return None
    report = normalize_plant(model)
    if report.numerator is None:
        return None
    try:
        locus = control.root_locus_map(
            control.tf(list(report.numerator), list(report.denominator)),
            gains=gains,
        )
        loci = np.asarray(locus.loci, dtype=complex)
        grid = np.asarray(getattr(locus, "gains", gains), dtype=float)
    except Exception:
        return None
    if loci.ndim == 1:
        loci = loci.reshape((-1, 1))
    if loci.shape[0] != grid.size and loci.shape[1] == grid.size:
        loci = loci.T
    return loci, grid


def root_locus(
    model: StateSpaceModel,
    gains: Sequence[float] | None = None,
    n_gains: int = 250,
) -> RootLocusResult:
    """Trace closed-loop poles over proportional gain for a SISO plant.

    ``gains`` defaults to ``[0, logspace(-3, 3)]``-style coverage of 250
    points. Branches are ordered to follow the open-loop poles, so
    ``branches[i][0] == open_loop_poles[i]`` at K = 0.
    """
    require_continuous(model, "root_locus")
    require_siso(model, "root_locus")

    if gains is None:
        count = max(20, min(int(n_gains), 1000))
        grid = np.concatenate(([0.0], np.logspace(-3.0, 3.0, count - 1)))
    else:
        grid = np.asarray(gains, dtype=float)
        if (
            grid.ndim != 1
            or grid.size < 2
            or not np.all(np.isfinite(grid))
            or np.any(grid < 0)
            or np.any(np.diff(grid) < 0)
        ):
            raise ValueError(
                "gains must be a nondecreasing sequence of nonnegative finite values"
            )

    report = normalize_plant(model)
    if report.numerator is None:
        raise ValueError("root_locus supports SISO plants only")
    denominator = np.asarray(report.denominator, dtype=float)
    numerator = np.asarray(report.numerator, dtype=float)

    control_loci = _control_loci(model, grid)
    if control_loci is not None:
        loci, actual_gains = control_loci
        # python-control already continues branches; permute so branch i
        # starts at sorted open-loop pole i.
        open_loop_poles = tuple(
            sorted(
                (complex(value) for value in loci[0]),
                key=lambda value: (value.real, value.imag),
            )
        )
        order = loci.shape[1]
        remaining = list(range(order))
        column_order: list[int] = []
        for target in open_loop_poles:
            nearest = min(
                remaining, key=lambda candidate: abs(loci[0, candidate] - target)
            )
            remaining.remove(nearest)
            column_order.append(nearest)
        ordered = np.empty_like(loci)
        for index in range(loci.shape[0]):
            ordered[index] = loci[index, column_order]
        branches = [
            tuple(complex(value) for value in ordered[:, branch])
            for branch in range(order)
        ]
    else:
        # np.roots returns an unordered set per gain, so track branches by
        # nearest-neighbor continuation from the previous gain's roots.
        actual_gains = grid
        order = denominator.size - 1
        padded_numerator = np.zeros(order + 1)
        offset = order + 1 - numerator.size
        padded_numerator[offset:] = numerator
        roots_per_gain = [
            np.roots(denominator + gain * padded_numerator) for gain in actual_gains
        ]
        initial = sorted(
            (complex(value) for value in roots_per_gain[0]),
            key=lambda value: (value.real, value.imag),
        )
        open_loop_poles = tuple(initial)
        branches_list: list[list[complex]] = [[root] for root in initial]
        previous = initial
        for gain_roots in roots_per_gain[1:]:
            candidates = [complex(value) for value in gain_roots]
            claimed = [False] * len(candidates)
            for branch, prior in zip(branches_list, previous):
                nearest = min(
                    (index for index in range(len(candidates)) if not claimed[index]),
                    key=lambda index: abs(candidates[index] - prior),
                )
                claimed[nearest] = True
                branch.append(candidates[nearest])
            previous = [branch[-1] for branch in branches_list]
        branches = [tuple(branch) for branch in branches_list]

    return RootLocusResult(
        gains=tuple(float(value) for value in actual_gains),
        branches=tuple(branches),
        open_loop_poles=open_loop_poles,
        open_loop_zeros=report.zeros,
    )

