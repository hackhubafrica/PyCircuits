from __future__ import annotations

import control as ct
import numpy as np

from app.engine.util import as_float_list, downsample, fnum


def _omega_grid(n: int = 400) -> np.ndarray:
    return np.logspace(-3, 3, int(np.clip(n, 80, 2000)))


def _eval_gjw(sys, omega: np.ndarray) -> np.ndarray:
    try:
        frd = ct.frequency_response(sys, omega)
        data = getattr(frd, "frdata", None)
        if data is not None:
            return np.squeeze(np.asarray(data, dtype=complex))
        mag = np.squeeze(np.asarray(frd.magnitude))
        phase = np.squeeze(np.asarray(frd.phase))
        return mag * np.exp(1j * phase)
    except Exception:
        mag, phase, _ = ct.bode(sys, omega, plot=False)
        mag = np.squeeze(np.asarray(mag))
        phase = np.squeeze(np.asarray(phase))
        return mag * np.exp(1j * phase)


def bode(sys, n_points: int = 400) -> dict:
    omega = _omega_grid(n_points)
    gjw = _eval_gjw(sys, omega)
    mag = np.abs(gjw)
    phase = np.unwrap(np.angle(gjw))
    mag_db = 20.0 * np.log10(np.maximum(mag, 1e-16))
    phase_deg = np.rad2deg(phase)

    gm = pm = wcg = wcp = None
    gm_db = None
    try:
        gm_raw, pm_raw, wcg_raw, wcp_raw = ct.margin(sys)
        gm = fnum(gm_raw)
        pm = fnum(pm_raw)
        wcg = fnum(wcg_raw)
        wcp = fnum(wcp_raw)
        if gm is not None and gm > 0:
            gm_db = fnum(20.0 * np.log10(gm))
    except Exception:
        pass

    omega_ds, mag_ds, phase_ds = downsample(omega, mag_db, phase_deg)
    return {
        "omega": as_float_list(omega_ds),
        "mag_db": as_float_list(mag_ds),
        "phase_deg": as_float_list(phase_ds),
        "gain_margin": gm,
        "gain_margin_db": gm_db,
        "phase_margin_deg": pm,
        "gain_crossover_omega": wcp,
        "phase_crossover_omega": wcg,
    }


def nyquist(sys, n_points: int = 400) -> dict:
    omega = _omega_grid(n_points)
    try:
        nyq = ct.nyquist_response(sys, omega)
        resp = np.squeeze(np.asarray(nyq.response, dtype=complex))
        w = np.squeeze(np.asarray(getattr(nyq, "omega", omega), dtype=float))
        if w.shape[0] != resp.shape[0]:
            w = omega[: resp.shape[0]]
            if w.shape[0] != resp.shape[0]:
                w = np.linspace(omega[0], omega[-1], resp.shape[0])
    except Exception:
        resp = _eval_gjw(sys, omega)
        w = omega

    real = np.real(resp)
    imag = np.imag(resp)
    w, real, imag = downsample(w, real, imag)
    return {
        "omega": as_float_list(w),
        "real": as_float_list(real),
        "imag": as_float_list(imag),
    }
