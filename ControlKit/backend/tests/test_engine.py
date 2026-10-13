from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.engine.plant import build_system
from app.engine.stability import analyze_stability
from app.engine.time_domain import simulate
from app.main import app
from app.schemas import PlantSpec


KNOWN = PlantSpec(form="tf", num=[1.0], den=[1.0, 1.0, 1.0])
client = TestClient(app)


def test_poles_of_second_order():
    sys = build_system(KNOWN)
    st = analyze_stability(sys)
    poles = sorted(st["poles"], key=lambda z: z["im"])
    assert len(poles) == 2
    assert poles[0]["re"] == pytest.approx(-0.5, abs=1e-8)
    assert poles[1]["re"] == pytest.approx(-0.5, abs=1e-8)
    assert poles[0]["im"] == pytest.approx(-math.sqrt(3) / 2, abs=1e-6)
    assert poles[1]["im"] == pytest.approx(math.sqrt(3) / 2, abs=1e-6)
    assert st["bibo_stable"] is True
    assert st["lyapunov_asymptotic"] is True


def test_step_overshoot_matches_zeta():
    sys = build_system(KNOWN)
    step = simulate(sys, "step", t_final=20.0, n_points=800)
    # wn=1, zeta=0.5 → overshoot ≈ 16.3%
    assert step["metrics"]["overshoot"] == pytest.approx(16.3, abs=1.5)


def test_integrator_not_bibo():
    sys = build_system(PlantSpec(form="tf", num=[1.0], den=[1.0, 0.0]))
    st = analyze_stability(sys)
    assert st["bibo_stable"] is False
    assert st["lyapunov_asymptotic"] is False


def test_analyze_endpoint():
    res = client.post("/api/analyze", json={"plant": KNOWN.model_dump(), "t_final": 12})
    assert res.status_code == 200
    body = res.json()
    assert body["stability"]["bibo_stable"] is True
    assert len(body["bode"]["omega"]) > 10
    assert len(body["nyquist"]["real"]) > 10
    assert len(body["root_locus"]["branches"]) >= 1
    pm = body["bode"]["phase_margin_deg"]
    assert pm is not None and pm > 40


def test_invalid_den_is_400():
    res = client.post("/api/plant/normalize", json={"form": "tf", "num": [1], "den": [0, 0]})
    assert res.status_code == 400


def test_pid_closed_loop():
    res = client.post(
        "/api/pid/closed-loop",
        json={"plant": KNOWN.model_dump(), "gains": {"Kp": 1.2, "Ki": 0.4, "Kd": 0.2}},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["closed_loop_step"]["y"]) > 10
    assert "phase_margin_deg" in body["loop_bode"]


def test_ss_roundtrip():
    spec = PlantSpec(
        form="ss",
        A=[[0.0, 1.0], [-1.0, -1.0]],
        B=[[0.0], [1.0]],
        C=[[1.0, 0.0]],
        D=[[0.0]],
    )
    res = client.post("/api/plant/normalize", json=spec.model_dump())
    assert res.status_code == 200
    poles = res.json()["poles"]
    reals = sorted(p["re"] for p in poles)
    assert reals[0] == pytest.approx(-0.5, abs=1e-5)


def test_simulate_custom_rejects_non_increasing():
    res = client.post(
        "/api/simulate",
        json={"plant": KNOWN.model_dump(), "kind": "custom", "t": [0.0, 2.0, 1.0], "u": [0.0, 1.0, 0.0]},
    )
    assert res.status_code == 400
    assert "strictly increasing" in res.json()["detail"]


def test_simulate_custom_nonuniform_t_is_resampled():
    """Default UI CSV (0,1,4,8): python-control needs a uniform grid → resample."""
    res = client.post(
        "/api/simulate",
        json={"plant": KNOWN.model_dump(), "kind": "custom", "t": [0.0, 1.0, 4.0, 8.0], "u": [0.0, 1.0, 1.0, 0.0]},
    )
    assert res.status_code == 200
    body = res.json()
    t = body["t"]
    assert len(t) >= 50
    dts = [round(t[i + 1] - t[i], 9) for i in range(len(t) - 1)]
    assert len(set(dts)) == 1  # uniform output grid
    assert len(body["y"]) == len(t)
    assert len(body["u"]) == len(t)


def test_zn_reaction_curve_fallback():
    """Default 2nd-order plant: no phase crossover → open-loop reaction-curve ZN."""
    res = client.post("/api/pid/tune", json={"plant": KNOWN.model_dump(), "method": "zn"})
    assert res.status_code == 200
    body = res.json()
    assert body["variant"] == "reaction_curve"
    assert body["fopdt"] is not None
    assert body["fopdt"]["theta"] > 0
    assert body["fopdt"]["tau"] > 0
    g = body["gains"]
    assert g["Kp"] > 0 and g["Ki"] > 0 and g["Kd"] > 0


def test_zn_ultimate_on_third_order():
    """1/((s+1)(s+2)(s+3)) has a finite phase crossover → classic ultimate-gain ZN."""
    third = PlantSpec(form="tf", num=[1.0], den=[1.0, 6.0, 11.0, 6.0])
    res = client.post("/api/pid/tune", json={"plant": third.model_dump(), "method": "zn"})
    assert res.status_code == 200
    body = res.json()
    assert body["variant"] == "ultimate"
    assert body["Ku"] is not None and body["Ku"] > 0
    assert body["Pu"] is not None and body["Pu"] > 0
    assert body["gains"]["Kp"] > 0


def test_pole_placement_two_poles_pd_mapping():
    """2 desired poles on an order-2 plant → PD gains, Ki == 0."""
    res = client.post(
        "/api/pid/tune",
        json={
            "plant": KNOWN.model_dump(),
            "method": "pole_placement",
            "desired_poles": [{"re": -2.0, "im": 1.0}, {"re": -2.0, "im": -1.0}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    # desired s²+4s+5 on plant s²+s+1 → Kd=(4−1)/1=3, Kp=(5−1)/1=4, Ki=0
    g = body["gains"]
    assert g["Ki"] == pytest.approx(0.0, abs=1e-9)
    assert g["Kp"] == pytest.approx(4.0, abs=1e-6)
    assert g["Kd"] == pytest.approx(3.0, abs=1e-6)
    assert body["K"] is not None


def test_zn_unusable_plant_is_readable_400():
    """Unstable pendulum: neither ultimate nor reaction curve applies → 400 with both reasons."""
    pend = PlantSpec(form="tf", num=[1.0], den=[1.0, 0.0, -9.81])
    res = client.post("/api/pid/tune", json={"plant": pend.model_dump(), "method": "zn"})
    assert res.status_code == 400
    detail = res.json()["detail"].lower()
    assert "phase-crossover" in detail and "reaction curve" in detail


# --- State feedback & LQR -----------------------------------------------------

CONT3 = PlantSpec(
    form="ss",
    A=[[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-6.0, -11.0, -6.0]],
    B=[[0.0], [0.0], [1.0]],
    C=[[1.0, 0.0, 0.0]],
    D=[[0.0]],
)
OSC = PlantSpec(form="ss", A=[[0.0, 1.0], [-1.0, 0.0]], B=[[0.0], [1.0]], C=[[1.0, 0.0]], D=[[0.0]])


def test_ackermann_places_poles():
    desired = [{"re": -2.0, "im": 0.0}, {"re": -3.0, "im": 1.0}, {"re": -3.0, "im": -1.0}]
    res = client.post("/api/sf/ackermann", json={"plant": CONT3.model_dump(), "desired_poles": desired})
    assert res.status_code == 200
    body = res.json()
    K = np.array(body["K"], dtype=float)
    A = np.array(CONT3.A, dtype=float)
    B = np.array(CONT3.B, dtype=float)
    eigs = np.sort_complex(np.linalg.eigvals(A - B @ K))
    want = np.sort_complex(np.array([-2.0 + 0j, -3.0 + 1j, -3.0 - 1j]))
    assert np.allclose(eigs, want, atol=1e-6)
    assert body["nbar"] is not None
    assert len(body["closed_step"]["y"]) > 10
    assert len(body["open_step"]["y"]) > 10


def test_ackermann_uncontrollable_400():
    spec = PlantSpec(form="ss", A=[[0.0, 0.0], [0.0, -1.0]], B=[[1.0], [0.0]], C=[[1.0, 1.0]], D=[[0.0]])
    res = client.post(
        "/api/sf/ackermann",
        json={"plant": spec.model_dump(), "desired_poles": [{"re": -1.0}, {"re": -2.0}]},
    )
    assert res.status_code == 400
    assert "controllable" in res.json()["detail"]


def test_ackermann_wrong_pole_count_400():
    res = client.post(
        "/api/sf/ackermann",
        json={"plant": CONT3.model_dump(), "desired_poles": [{"re": -1.0}, {"re": -2.0}]},
    )
    assert res.status_code == 400
    assert "exactly 3" in res.json()["detail"]


def test_lqr_stabilizes_oscillator():
    res = client.post("/api/sf/lqr", json={"plant": OSC.model_dump(), "Q": [1.0, 1.0], "R": 1.0})
    assert res.status_code == 200
    body = res.json()
    assert len(body["K"][0]) == 2
    assert all(p["re"] < 0 for p in body["closed_loop_poles"])
    assert body["S"] is not None and len(body["S"]) == 2
    assert body["method"] == "lqr"


def test_lqr_bigger_R_smaller_gain():
    def norm_K(R: float) -> float:
        res = client.post("/api/sf/lqr", json={"plant": OSC.model_dump(), "Q": [1.0, 1.0], "R": R})
        assert res.status_code == 200
        return float(np.linalg.norm(np.array(res.json()["K"], dtype=float)))

    assert norm_K(100.0) < norm_K(0.1)


def test_lqr_bad_inputs_400():
    res = client.post("/api/sf/lqr", json={"plant": OSC.model_dump(), "Q": [1.0, 1.0, 1.0], "R": 1.0})
    assert res.status_code == 400
    assert "Q must have 2" in res.json()["detail"]
    res = client.post("/api/sf/lqr", json={"plant": OSC.model_dump(), "Q": [0.0, 0.0], "R": 1.0})
    assert res.status_code == 400
    res = client.post("/api/sf/lqr", json={"plant": OSC.model_dump(), "Q": [1.0, -1.0], "R": 1.0})
    assert res.status_code == 400
    res = client.post("/api/sf/lqr", json={"plant": OSC.model_dump(), "Q": [1.0, 1.0], "R": 0.0})
    assert res.status_code in (400, 422)  # Field(gt=0) → 422


# --- Interconnect (block algebra) ---------------------------------------------


def test_interconnect_matches_pid_closed_loop():
    """series(PID, plant) + unity feedback must equal /api/pid/closed-loop exactly."""
    plant = {"form": "tf", "num": [4.0], "den": [1.0, 12.0, 0.0]}
    gains = {"Kp": 1.2, "Ki": 0.4, "Kd": 0.2}
    ref = client.post("/api/pid/closed-loop", json={"plant": plant, "gains": gains}).json()
    res = client.post(
        "/api/interconnect",
        json={
            "blocks": [
                {"id": "c", "kind": "pid", "gains": gains},
                {"id": "g", "kind": "tf", "num": [4.0], "den": [1.0, 12.0, 0.0]},
            ],
            "forward": ["c", "g"],
            "feedback": "unity",
        },
    )
    assert res.status_code == 200
    comp = res.json()["composite"]
    assert comp["den"] == pytest.approx(ref["closed_loop_den"], abs=1e-9)
    assert comp["num"] == pytest.approx(ref["closed_loop_num"], abs=1e-9)
    assert res.json()["structure"] == {"forward": ["c", "g"], "parallel": None, "feedback": "unity"}


def test_interconnect_parallel_algebra():
    """1/(s+1) ∥ 2/(s+2) = (3s+4)/(s²+3s+2), open loop."""
    res = client.post(
        "/api/interconnect",
        json={
            "blocks": [
                {"id": "a", "kind": "tf", "num": [1.0], "den": [1.0, 1.0]},
                {"id": "b", "kind": "tf", "num": [2.0], "den": [1.0, 2.0]},
            ],
            "forward": ["a"],
            "parallel": ["b"],
            "feedback": "none",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["composite"]["num"] == pytest.approx([3.0, 4.0], abs=1e-9)
    assert body["composite"]["den"] == pytest.approx([1.0, 3.0, 2.0], abs=1e-9)
    assert len(body["step"]["y"]) > 10 and "bode" in body and "root_locus" in body


def test_interconnect_gain_block_feedback():
    """feedback(100, 1) → 100/101 static composite."""
    res = client.post(
        "/api/interconnect",
        json={
            "blocks": [{"id": "k", "kind": "gain", "k": 100.0}],
            "forward": ["k"],
            "feedback": "unity",
        },
    )
    assert res.status_code == 200
    comp = res.json()["composite"]
    assert comp["num"] == pytest.approx([100.0], abs=1e-9)
    assert comp["den"] == pytest.approx([101.0], abs=1e-9)


def test_interconnect_unknown_block_400():
    res = client.post(
        "/api/interconnect",
        json={
            "blocks": [{"id": "a", "kind": "tf", "num": [1.0], "den": [1.0, 1.0]}],
            "forward": ["a", "nope"],
            "feedback": "none",
        },
    )
    assert res.status_code == 400
    assert "Unknown block id" in res.json()["detail"]


def test_interconnect_duplicate_id_400():
    res = client.post(
        "/api/interconnect",
        json={
            "blocks": [
                {"id": "a", "kind": "tf", "num": [1.0], "den": [1.0, 1.0]},
                {"id": "a", "kind": "gain", "k": 2.0},
            ],
            "forward": ["a"],
            "feedback": "none",
        },
    )
    assert res.status_code == 400
    assert "Duplicate block id" in res.json()["detail"]
