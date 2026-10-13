from __future__ import annotations

import control as ct
import numpy as np

from app.engine.plant import to_tf
from app.engine.util import as_float_list, cplx, downsample, fnum


def root_locus(sys, n_gains: int = 250) -> dict:
    tf_sys = to_tf(sys)
    kvect = np.concatenate(([0.0], np.logspace(-3, 3, max(20, n_gains - 1))))
    loci = None
    gains = kvect

    if hasattr(ct, "root_locus_map"):
        try:
            rmap = ct.root_locus_map(tf_sys, gains=kvect)
            loci = np.asarray(rmap.loci, dtype=complex)
            gains = np.asarray(getattr(rmap, "gains", kvect), dtype=float)
        except Exception:
            loci = None

    if loci is None:
        try:
            rlist, klist = ct.root_locus(tf_sys, kvect=kvect, plot=False)
            loci = np.asarray(rlist, dtype=complex)
            gains = np.asarray(klist, dtype=float)
        except TypeError:
            rlist, klist = ct.root_locus(tf_sys, kvect)
            loci = np.asarray(rlist, dtype=complex)
            gains = np.asarray(klist, dtype=float)

    # python-control uses (n_gains, n_poles) or (n_poles, n_gains)
    if loci.ndim == 1:
        loci = loci.reshape((-1, 1))
    if loci.shape[0] != gains.shape[0] and loci.shape[1] == gains.shape[0]:
        loci = loci.T

    n_g = min(loci.shape[0], gains.shape[0])
    loci = loci[:n_g, :]
    gains = gains[:n_g]
    idx = np.linspace(0, n_g - 1, min(n_g, 400)).astype(int)
    loci = loci[idx, :]
    gains = gains[idx]

    branches = []
    for p in range(loci.shape[1]):
        re = np.real(loci[:, p])
        im = np.imag(loci[:, p])
        re, im = downsample(re, im, max_n=400)
        branches.append({"re": as_float_list(re), "im": as_float_list(im)})

    poles0 = [cplx(z) for z in loci[0, :]] if loci.size else []
    return {
        "gains": as_float_list(gains),
        "branches": branches,
        "open_loop_poles": poles0,
        "gain_min": fnum(gains[0]) if gains.size else None,
        "gain_max": fnum(gains[-1]) if gains.size else None,
    }
