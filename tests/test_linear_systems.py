import unittest
from pathlib import Path
import math

from pycircuits_sim.linear_systems import (
    LinearPIDConfig,
    DiscreteStateSpaceModel,
    discrete_frequency_response,
    simulate_discrete_state_space,
    simulate_discrete_state_space_pid,
    logarithmic_frequency_grid,
    StateSpaceModel,
    StepReference,
    simulate_state_space,
    simulate_state_space_pid,
    frequency_response,
    load_linear_plant,
    transfer_function_to_state_space,
)


class LinearPlantTests(unittest.TestCase):
    def test_discrete_plant_follows_sample_recurrence(self) -> None:
        model = DiscreteStateSpaceModel.from_matrices(
            [[0.5]], [[1.0]], [[1.0]], [[0.0]], sample_time=0.1
        )
        result = simulate_discrete_state_space(
            model,
            stop_time=0.3,
            input_signal=lambda _time: [1.0],
        )

        self.assertEqual(result.time, [0.0, 0.1, 0.2, 0.30000000000000004])
        self.assertAlmostEqual(result.outputs["y1"][0], 0.0)
        self.assertAlmostEqual(result.outputs["y1"][1], 1.0)
        self.assertAlmostEqual(result.outputs["y1"][2], 1.5)
        self.assertAlmostEqual(result.outputs["y1"][3], 1.75)

    def test_discrete_frequency_response_and_pole_stability(self) -> None:
        model = DiscreteStateSpaceModel.from_matrices(
            [[0.5]], [[1.0]], [[1.0]], [[0.0]], sample_time=0.1
        )
        response = discrete_frequency_response(model, [0.0 + 0.1])

        self.assertEqual(response.poles, [complex(0.5, 0.0)])
        self.assertAlmostEqual(abs(response.response[0][0][0]), 1.0 / abs(complex(math.cos(2 * math.pi * 0.01) - 0.5, math.sin(2 * math.pi * 0.01))))
        with self.assertRaisesRegex(ValueError, "Nyquist"):
            discrete_frequency_response(model, [5.0])

    def test_discrete_sampled_pid_tracks_reference(self) -> None:
        model = DiscreteStateSpaceModel.from_matrices(
            [[0.8]], [[0.2]], [[1.0]], [[0.0]], sample_time=0.01
        )
        result = simulate_discrete_state_space_pid(
            model,
            LinearPIDConfig(1.5, 5.0, 0.0, 0.05, output_min=0.0, output_max=2.0),
            StepReference(0.0, 1.0, 0.1),
            stop_time=2.0,
        )

        self.assertGreater(result.output[-1], 0.8)
        self.assertLess(result.output[-1], 1.2)
        self.assertTrue(all(0 <= value <= 2.0 for value in result.control))
        with self.assertRaisesRegex(ValueError, "integer multiple"):
            simulate_discrete_state_space_pid(
                model,
                LinearPIDConfig(1.0, 0.0, 0.0, 0.025),
                StepReference(0.0, 1.0, 0.1),
                stop_time=1.0,
            )

    def test_first_order_bode_and_pole(self) -> None:
        model = transfer_function_to_state_space([10.0], [1.0, 10.0])
        corner_hz = 10.0 / (2.0 * 3.141592653589793)
        bode = frequency_response(model, [0.01, corner_hz, 1000.0])

        self.assertAlmostEqual(bode.magnitude_db[1][0][0], -3.0103, places=3)
        self.assertAlmostEqual(bode.phase_deg[1][0][0], -45.0, places=3)
        self.assertAlmostEqual(bode.magnitude_db[0][0][0], 0.0, places=2)
        self.assertEqual(bode.poles, [complex(-10.0, 0.0)])

    def test_second_order_resonance_response_and_complex_poles(self) -> None:
        model = transfer_function_to_state_space([25.0], [1.0, 4.0, 25.0])
        resonance_hz = 5.0 / (2.0 * 3.141592653589793)
        bode = frequency_response(model, [resonance_hz])

        self.assertAlmostEqual(bode.magnitude_db[0][0][0], 20.0 * math.log10(1.25), places=5)
        self.assertAlmostEqual(bode.phase_deg[0][0][0], -90.0, places=5)
        self.assertAlmostEqual(bode.poles[0].real, -2.0)
        self.assertAlmostEqual(abs(bode.poles[0].imag), 21.0 ** 0.5)
        self.assertAlmostEqual(bode.poles[1].real, -2.0)
        self.assertAlmostEqual(abs(bode.poles[1].imag), 21.0 ** 0.5)

    def test_mimo_frequency_response_has_output_input_channels(self) -> None:
        model = StateSpaceModel.from_matrices(
            [[-1.0]], [[1.0, 2.0]], [[1.0], [2.0]], [[0.0, 0.0], [0.0, 0.0]]
        )
        response = frequency_response(model, [1.0])

        self.assertEqual(len(response.response[0]), 2)
        self.assertEqual(len(response.response[0][0]), 2)
        self.assertAlmostEqual(
            abs(response.response[0][1][1]),
            4.0 * abs(response.response[0][0][0]),
        )

    def test_logarithmic_frequency_grid_and_validation(self) -> None:
        grid = logarithmic_frequency_grid(1.0, 100.0, points_per_decade=10)
        self.assertAlmostEqual(grid[0], 1.0)
        self.assertAlmostEqual(grid[-1], 100.0)
        self.assertTrue(all(left < right for left, right in zip(grid, grid[1:])))
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            frequency_response(
                transfer_function_to_state_space([1.0], [1.0, 1.0]), [0.0]
            )

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
        discrete_model, discrete_data = load_linear_plant(
            examples_directory / "discrete_first_order.json"
        )

        self.assertEqual(state_data["type"], "state_space")
        self.assertEqual(state_model.state_count, 1)
        self.assertEqual(transfer_data["type"], "transfer_function")
        self.assertEqual(transfer_model.state_count, 2)
        self.assertEqual(discrete_data["type"], "discrete_state_space")
        self.assertEqual(discrete_model.state_count, 1)
        self.assertEqual(discrete_model.sample_time, 0.01)


if __name__ == "__main__":
    unittest.main()