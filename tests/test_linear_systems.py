import unittest
from pathlib import Path

from pycircuits_sim.linear_systems import (
    LinearPIDConfig,
    StateSpaceModel,
    StepReference,
    simulate_state_space,
    simulate_state_space_pid,
    load_linear_plant,
    transfer_function_to_state_space,
)


class LinearPlantTests(unittest.TestCase):
    def test_first_order_transfer_function_backward_euler_step(self) -> None:
        model = transfer_function_to_state_space([1.0], [1.0, 1.0])
        result = simulate_state_space(
            model,
            time_step=1.0,
            stop_time=3.0,
            input_signal=lambda _time: [1.0],
        )

        self.assertAlmostEqual(result.outputs["y1"][1], 0.5)
        self.assertAlmostEqual(result.outputs["y1"][2], 0.75)
        self.assertAlmostEqual(result.outputs["y1"][3], 0.875)

    def test_second_order_transfer_function_conversion(self) -> None:
        model = transfer_function_to_state_space([4.0], [1.0, 2.0, 4.0])
        self.assertEqual(model.state_count, 2)
        self.assertEqual(model.input_count, 1)
        self.assertEqual(model.output_count, 1)
        self.assertEqual(model.A, ((-2.0, -4.0), (1.0, 0.0)))
        self.assertEqual(model.C, ((0.0, 4.0),))

    def test_mimo_state_space_simulation(self) -> None:
        model = StateSpaceModel.from_matrices(
            [[-1.0]],
            [[1.0, 2.0]],
            [[1.0], [2.0]],
            [[0.0, 0.0], [0.0, 0.0]],
        )
        result = simulate_state_space(
            model,
            time_step=0.1,
            stop_time=0.1,
            input_signal=lambda _time: [1.0, 0.0],
        )

        self.assertAlmostEqual(result.outputs["y2"][-1], 2 * result.outputs["y1"][-1])

    def test_improper_transfer_function_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "improper"):
            transfer_function_to_state_space([1.0, 1.0, 1.0], [1.0, 1.0])

    def test_matrix_shape_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "B row count"):
            StateSpaceModel.from_matrices(
                [[-1.0, 0.0], [0.0, -2.0]],
                [[1.0]],
                [[1.0, 0.0]],
                [[0.0]],
            )

    def test_sampled_pid_tracks_first_order_plant(self) -> None:
        model = transfer_function_to_state_space([1.0], [1.0, 1.0])
        result = simulate_state_space_pid(
            model,
            LinearPIDConfig(
                kp=0.8,
                ki=2.0,
                kd=0.0,
                sample_time=0.1,
                output_min=0.0,
                output_max=2.0,
            ),
            StepReference(initial=0.0, final=1.0, step_time=0.1),
            time_step=0.01,
            stop_time=2.0,
        )

        self.assertGreater(result.output[-1], 0.8)
        self.assertLess(result.output[-1], 1.2)
        self.assertTrue(all(0.0 <= value <= 2.0 for value in result.control))
        self.assertEqual(len(result.reference), len(result.time))

    def test_pid_rejects_mimo_model(self) -> None:
        model = StateSpaceModel.from_matrices(
            [[-1.0]], [[1.0, 1.0]], [[1.0]], [[0.0, 0.0]]
        )
        with self.assertRaisesRegex(ValueError, "SISO"):
            simulate_state_space_pid(
                model,
                LinearPIDConfig(1.0, 0.0, 0.0, 0.1),
                StepReference(0.0, 1.0, 0.1),
                time_step=0.01,
                stop_time=1.0,
            )

    def test_pid_rejects_direct_feedthrough(self) -> None:
        model = StateSpaceModel.from_matrices([[-1.0]], [[1.0]], [[1.0]], [[0.5]])
        with self.assertRaisesRegex(ValueError, "D=0"):
            simulate_state_space_pid(
                model,
                LinearPIDConfig(1.0, 0.0, 0.0, 0.1),
                StepReference(0.0, 1.0, 0.1),
                time_step=0.01,
                stop_time=1.0,
            )

    def test_example_json_models_load(self) -> None:
        examples_directory = Path(__file__).parents[1] / "examples"
        state_model, state_data = load_linear_plant(
            examples_directory / "state_space_first_order.json"
        )
        transfer_model, transfer_data = load_linear_plant(
            examples_directory / "transfer_function_second_order.json"
        )

        self.assertEqual(state_data["type"], "state_space")
        self.assertEqual(state_model.state_count, 1)
        self.assertEqual(transfer_data["type"], "transfer_function")
        self.assertEqual(transfer_model.state_count, 2)


if __name__ == "__main__":
    unittest.main()