"""HTTP contract tests for pycircuits_sim.api (mirrors ControlKit's API tests).

Skipped entirely when the optional [api] extra (fastapi/httpx) is absent so
the core test suite stays dependency-light.
"""

import unittest

try:
    from fastapi.testclient import TestClient

    from pycircuits_sim.api import app

    HAVE_API = True
except ImportError:  # pragma: no cover - exercised without the extra
    HAVE_API = False

# ControlKit's teaching plants, in PlantSpec form.
KNOWN = {"form": "tf", "num": [1.0], "den": [1.0, 1.0, 1.0]}
THIRD = {"form": "tf", "num": [1.0], "den": [1.0, 6.0, 11.0, 6.0]}
PENDULUM = {"form": "tf", "num": [1.0], "den": [1.0, 0.0, -9.81]}
CONT3 = {
    "form": "ss",
    "A": [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-6.0, -11.0, -6.0]],
    "B": [[0.0], [0.0], [1.0]],
    "C": [[1.0, 0.0, 0.0]],
    "D": [[0.0]],
}
OSC = {
    "form": "ss",
    "A": [[0.0, 1.0], [-1.0, 0.0]],
    "B": [[0.0], [1.0]],
    "C": [[1.0, 0.0]],
    "D": [[0.0]],
}


@unittest.skipUnless(HAVE_API, "API extra (fastapi/httpx) not installed")
class ApiAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_normalize_second_order(self) -> None:
        response = self.client.post("/api/plant/normalize", json=KNOWN)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        poles = sorted(body["poles"], key=lambda p: p["re"])
        self.assertAlmostEqual(poles[0]["re"], -0.5, delta=1e-8)
        self.assertAlmostEqual(poles[1]["re"], -0.5, delta=1e-8)
        self.assertAlmostEqual(poles[0]["im"], -0.8660254, delta=1e-6)
        self.assertAlmostEqual(body["dc_gain"], 1.0, delta=1e-9)
        self.assertEqual(body["order"], 2)
        self.assertEqual((body["ninputs"], body["noutputs"]), (1, 1))

    def test_normalize_invalid_den_is_400(self) -> None:
        response = self.client.post(
            "/api/plant/normalize", json={"form": "tf", "num": [1], "den": [0, 0]}
        )
        self.assertEqual(response.status_code, 400)

    def test_stability_integrator_not_bibo(self) -> None:
        response = self.client.post(
            "/api/stability", json={"form": "tf", "num": [1.0], "den": [1.0, 0.0]}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["bibo_stable"])
        self.assertFalse(body["lyapunov_asymptotic"])
        self.assertIn("imaginary axis", body["bibo_reason"])

    def test_stability_unstable_pendulum(self) -> None:
        body = self.client.post("/api/stability", json=PENDULUM).json()
        self.assertFalse(body["bibo_stable"])
        self.assertIn("positive real part", body["bibo_reason"])

    def test_analyze_full_payload(self) -> None:
        response = self.client.post(
            "/api/analyze", json={"plant": KNOWN, "t_final": 12}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["stability"]["bibo_stable"])
        self.assertGreater(len(body["bode"]["omega"]), 10)
        self.assertGreater(len(body["nyquist"]["real"]), 10)
        self.assertGreaterEqual(len(body["root_locus"]["branches"]), 1)
        pm = body["bode"]["phase_margin_deg"]
        self.assertIsNotNone(pm)
        self.assertGreater(pm, 40)
        self.assertEqual(len(body["step"]["t"]), len(body["step"]["y"]))
        self.assertEqual(len(body["impulse"]["t"]), len(body["impulse"]["y"]))
        self.assertGreater(body["step"]["metrics"]["overshoot"], 10.0)

    def test_bode_and_nyquist_and_locus_endpoints(self) -> None:
        for path in ("/api/bode", "/api/nyquist", "/api/root-locus"):
            response = self.client.post(path, json=KNOWN)
            self.assertEqual(response.status_code, 200, path)
            self.assertGreater(len(response.json()), 1)

    def test_mimo_plant_rejected(self) -> None:
        mimo = {
            "form": "ss",
            "A": [[0.0, 1.0], [-1.0, -1.0]],
            "B": [[0.0, 0.0], [1.0, 0.5]],
            "C": [[1.0, 0.0]],
            "D": [[0.0, 0.0]],
        }
        response = self.client.post("/api/stability", json=mimo)
        self.assertEqual(response.status_code, 400)
        self.assertIn("SISO", response.json()["detail"])


@unittest.skipUnless(HAVE_API, "API extra (fastapi/httpx) not installed")
class ApiSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_step_overshoot_matches_zeta(self) -> None:
        response = self.client.post(
            "/api/simulate",
            json={"plant": KNOWN, "kind": "step", "t_final": 20, "n_points": 800},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kind"], "step")
        # zeta=0.5 predicts ~16.3% overshoot.
        self.assertAlmostEqual(body["metrics"]["overshoot"], 16.3, delta=1.5)

    def test_custom_rejects_non_increasing(self) -> None:
        response = self.client.post(
            "/api/simulate",
            json={
                "plant": KNOWN,
                "kind": "custom",
                "t": [0.0, 2.0, 1.0],
                "u": [0.0, 1.0, 0.0],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("strictly increasing", response.json()["detail"])

    def test_custom_nonuniform_t_is_resampled(self) -> None:
        response = self.client.post(
            "/api/simulate",
            json={
                "plant": KNOWN,
                "kind": "custom",
                "t": [0.0, 1.0, 4.0, 8.0],
                "u": [0.0, 1.0, 1.0, 0.0],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        t = body["t"]
        self.assertGreaterEqual(len(t), 50)
        steps = [round(t[i + 1] - t[i], 9) for i in range(len(t) - 1)]
        self.assertEqual(len(set(steps)), 1)  # uniform output grid
        self.assertEqual(len(body["y"]), len(t))
        self.assertEqual(len(body["u"]), len(t))


@unittest.skipUnless(HAVE_API, "API extra (fastapi/httpx) not installed")
class ApiDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_pid_closed_loop_payload(self) -> None:
        response = self.client.post(
            "/api/pid/closed-loop",
            json={
                "plant": KNOWN,
                "gains": {"Kp": 1.2, "Ki": 0.4, "Kd": 0.2},
                # The slow closed-loop pole at -0.2 (tau=5 s) needs a long
                # horizon before the type-1 loop visually settles at 1.
                "t_final": 40,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreater(len(body["closed_loop_step"]["y"]), 10)
        self.assertIn("phase_margin_deg", body["loop_bode"])
        # C=(0.2s^2+1.2s+0.4)/s on 1/(s^2+s+1), unity feedback:
        # T = (0.2s^2+1.2s+0.4) / (s^3+1.2s^2+2.2s+0.4).
        for got, want in zip(body["closed_loop_num"], [0.2, 1.2, 0.4]):
            self.assertAlmostEqual(got, want, places=9)
        for got, want in zip(body["closed_loop_den"], [1.0, 1.2, 2.2, 0.4]):
            self.assertAlmostEqual(got, want, places=9)
        # Type-1 loop tracks its unit step reference.
        self.assertAlmostEqual(body["closed_loop_step"]["y"][-1], 1.0, delta=0.02)

    def test_zn_ultimate_on_third_order(self) -> None:
        response = self.client.post(
            "/api/pid/tune", json={"plant": THIRD, "method": "zn"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["variant"], "ultimate")
        self.assertIsNotNone(body["Ku"])
        self.assertGreater(body["Ku"], 0)
        self.assertGreater(body["Pu"], 0)
        self.assertGreater(body["gains"]["Kp"], 0)
        self.assertIn("PID", body["variants"])

    def test_zn_unusable_plant_is_readable_400(self) -> None:
        response = self.client.post(
            "/api/pid/tune", json={"plant": PENDULUM, "method": "zn"}
        )
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"].lower()
        self.assertIn("phase-crossover", detail)
        self.assertIn("reaction curve", detail)

    def test_pole_placement_pd_mapping(self) -> None:
        response = self.client.post(
            "/api/pid/tune",
            json={
                "plant": KNOWN,
                "method": "pole_placement",
                "desired_poles": [{"re": -2.0, "im": 1.0}, {"re": -2.0, "im": -1.0}],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # desired s^2+4s+5 on plant s^2+s+1: Kd=(4-1)=3, Kp=(5-1)=4, Ki=0.
        self.assertAlmostEqual(body["gains"]["Ki"], 0.0, delta=1e-9)
        self.assertAlmostEqual(body["gains"]["Kp"], 4.0, delta=1e-6)
        self.assertAlmostEqual(body["gains"]["Kd"], 3.0, delta=1e-6)
        self.assertIsNotNone(body["K"])

    def test_ackermann_places_poles(self) -> None:
        response = self.client.post(
            "/api/sf/ackermann",
            json={
                "plant": CONT3,
                "desired_poles": [
                    {"re": -2.0},
                    {"re": -3.0, "im": 1.0},
                    {"re": -3.0, "im": -1.0},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["K"], [[14.0, 11.0, 2.0]])
        self.assertIsNotNone(body["nbar"])
        self.assertEqual(body["controllability_rank"], 3)
        self.assertGreater(len(body["closed_step"]["y"]), 10)
        self.assertGreater(len(body["open_step"]["y"]), 10)
        real_parts = sorted(p["re"] for p in body["closed_loop_poles"])
        self.assertAlmostEqual(real_parts[0], -3.0, delta=1e-6)
        self.assertAlmostEqual(real_parts[2], -2.0, delta=1e-6)

    def test_ackermann_uncontrollable_400(self) -> None:
        response = self.client.post(
            "/api/sf/ackermann",
            json={
                "plant": {
                    "form": "ss",
                    "A": [[0.0, 0.0], [0.0, -1.0]],
                    "B": [[1.0], [0.0]],
                    "C": [[1.0, 1.0]],
                    "D": [[0.0]],
                },
                "desired_poles": [{"re": -1.0}, {"re": -2.0}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("controllable", response.json()["detail"])

    def test_lqr_stabilizes_oscillator(self) -> None:
        response = self.client.post(
            "/api/sf/lqr", json={"plant": OSC, "Q": [1.0, 1.0], "R": 1.0}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["method"], "lqr")
        self.assertEqual(len(body["K"][0]), 2)
        self.assertTrue(all(p["re"] < 0 for p in body["closed_loop_poles"]))
        self.assertEqual(len(body["S"]), 2)
        self.assertEqual(body["Q"], [1.0, 1.0])

    def test_lqr_bad_q_is_400(self) -> None:
        response = self.client.post(
            "/api/sf/lqr", json={"plant": OSC, "Q": [1.0, 1.0, 1.0], "R": 1.0}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Q must have 2", response.json()["detail"])


@unittest.skipUnless(HAVE_API, "API extra (fastapi/httpx) not installed")
class ApiInterconnectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_parallel_algebra(self) -> None:
        # 1/(s+1) + 2/(s+2) = (3s+4)/(s^2+3s+2), open loop.
        response = self.client.post(
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
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for got, want in zip(body["composite"]["num"], [3.0, 4.0]):
            self.assertAlmostEqual(got, want, places=9)
        for got, want in zip(body["composite"]["den"], [1.0, 3.0, 2.0]):
            self.assertAlmostEqual(got, want, places=9)
        self.assertEqual(
            body["structure"],
            {"forward": ["a"], "parallel": ["b"], "feedback": "none"},
        )
        self.assertGreater(len(body["step"]["y"]), 10)
        self.assertIn("bode", body)
        self.assertIn("root_locus", body)

    def test_gain_block_feedback(self) -> None:
        response = self.client.post(
            "/api/interconnect",
            json={
                "blocks": [{"id": "k", "kind": "gain", "k": 100.0}],
                "forward": ["k"],
                "feedback": "unity",
            },
        )
        self.assertEqual(response.status_code, 200)
        composite = response.json()["composite"]
        ratio = composite["num"][0] / composite["den"][0]
        self.assertAlmostEqual(ratio, 100.0 / 101.0, places=9)

    def test_unknown_block_400(self) -> None:
        response = self.client.post(
            "/api/interconnect",
            json={
                "blocks": [
                    {"id": "a", "kind": "tf", "num": [1.0], "den": [1.0, 1.0]}
                ],
                "forward": ["a", "nope"],
                "feedback": "none",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown block id", response.json()["detail"])

    def test_duplicate_block_400(self) -> None:
        response = self.client.post(
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
        self.assertEqual(response.status_code, 400)
        self.assertIn("duplicate block id", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()



