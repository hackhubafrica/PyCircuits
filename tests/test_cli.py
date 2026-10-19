import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from pycircuits_sim.cli import _parse_complex_list, _parse_float_list
from pycircuits_sim.design import PIDGains, StateFeedbackResult
from pycircuits_sim.design.state_feedback import StepTrace
from pycircuits_sim.io import (
    load_interconnect_spec,
    write_state_feedback_csv,
)


class ParserTests(unittest.TestCase):
    def test_complex_list_accepts_j_and_i(self) -> None:
        values = _parse_complex_list("-2+1j, -3-1j, 4")
        self.assertEqual(values, [-2.0 + 1.0j, -3.0 - 1.0j, 4.0 + 0.0j])

    def test_complex_list_accepts_bare_j(self) -> None:
        self.assertEqual(_parse_complex_list("j, -j"), [1.0j, -1.0j])

    def test_complex_list_rejects_garbage(self) -> None:
        with self.assertRaisesRegex(ValueError, "could not parse"):
            _parse_complex_list("banana")

    def test_float_list_parses_and_rejects(self) -> None:
        self.assertEqual(_parse_float_list("1, 2.5, 3"), [1.0, 2.5, 3.0])
        with self.assertRaisesRegex(ValueError, "could not parse"):
            _parse_float_list("1, x")


class InterconnectSpecLoaderTests(unittest.TestCase):
    def test_example_file_loads_and_composes(self) -> None:
        from pycircuits_sim.interconnect import interconnect

        spec = load_interconnect_spec(
            PROJECT_ROOT / "examples" / "interconnect_pid_loop.json"
        )
        self.assertEqual(len(spec.blocks), 2)
        self.assertEqual(spec.forward, ("c", "g"))
        self.assertEqual(spec.feedback, "unity")
        controller = spec.blocks[0]
        self.assertEqual(controller.kind, "pid")
        self.assertEqual(controller.gains, PIDGains(kp=1.2, ki=0.4, kd=0.2))
        result = interconnect(spec)
        self.assertAlmostEqual(result.step.output[-1], 1.0, places=6)

    def test_missing_blocks_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"forward": ["a"]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "blocks"):
                load_interconnect_spec(path)


class StateFeedbackCsvTests(unittest.TestCase):
    def test_csv_writer_round_trips(self) -> None:
        result = StateFeedbackResult(
            method="ackermann",
            closed_loop_k=((1.0,),),
            nbar=1.0,
            order=1,
            controllability_rank=1,
            open_loop_poles=(-1.0 + 0j,),
            closed_loop_poles=(-2.0 + 0j,),
            desired_poles=(-2.0 + 0j,),
            open_step=StepTrace((0.0, 1.0), (0.0, 0.5)),
            closed_step=StepTrace((0.0, 1.0), (0.0, 0.9)),
            q=None,
            r=None,
            s=None,
            message="test",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sf.csv"
            write_state_feedback_csv(result, path)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(lines[0], "time_s,open_output,closed_output")
        self.assertEqual(lines[1], "0.0,0.0,0.0")
        self.assertEqual(lines[2], "1.0,0.5,0.9")


class CliEndToEndTests(unittest.TestCase):
    def _run(self, *arguments: str) -> subprocess.CompletedProcess:
        environment = dict(os.environ, MPLBACKEND="Agg")
        return subprocess.run(
            [sys.executable, "-m", "pycircuits_sim.cli", *arguments],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=environment,
        )

    def test_analyze_reports_stability(self) -> None:
        completed = self._run(
            "analyze", "examples/analysis_third_order.json", "--no-step"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("BIBO stable: True", completed.stdout)
        self.assertIn("Poles: -3, -2, -1", completed.stdout)

    def test_tune_ultimate_prints_ku(self) -> None:
        completed = self._run("tune", "examples/analysis_third_order.json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ziegler-Nichols ultimate", completed.stdout)
        self.assertIn("Ku=", completed.stdout)

    def test_error_is_one_clean_line(self) -> None:
        # A pure first-order plant has no phase crossover and zero dead
        # time, so ZN fails; the CLI must report it as one clean line.
        completed = self._run("tune", "examples/state_space_first_order.json")
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(completed.stderr.startswith("error: Ziegler-Nichols failed"))
        self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()
