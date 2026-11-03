from modelica_parser import parse_linearized_model
from scipy import signal
import numpy as np
import matplotlib.pyplot as plt

# --- 1. Load and Parse Matrices from File ---
mo_file_path = 'linearized_model.mo'
A, B, C, D = parse_linearized_model(mo_file_path)

# --- 2. Apply Safe Defaults ---
if A is not None:
    n_states = A.shape[0]
    if B is None: 
        B = np.zeros((n_states, 1))
        B[-1, 0] = 1.0
    if C is None: 
        C = np.zeros((1, n_states))
        C[0, 0] = 1.0
    if D is None: 
        D = np.zeros((1, 1))

print("--- Cleaned State-Space Dimensions ---")
print(f"A: {A.shape if A is not None else 'None'}")
print(f"B: {B.shape if B is not None else 'None'}")
print(f"C: {C.shape if C is not None else 'None'}")
print(f"D: {D.shape if D is not None else 'None'}\n")

# --- 3. Convert to Transfer Function & Print Cleanly ---
if A is not None:
    num, den = signal.ss2tf(A, B, C, D)
    num_siso = np.squeeze(num)

    print("--- Transfer Function Representation ---")
    print(f"Numerator coefficients:   {np.round(num_siso, 2)}")
    print(f"Denominator coefficients: {np.round(den, 2)}\n")

    # --- 4. Simulate State Trajectories via lsim (Linear Simulation) ---
    print("--- Running SciPy State Simulation ---")
    stop_time = 20.0
    num_points = 1000
    t_custom = np.linspace(0, stop_time, num_points)

    # Create a step input vector (1s for all time points)
    u_step = np.ones_like(t_custom)

    system = signal.StateSpace(A, B, C, D)

    # lsim returns: (time vector, output response array, state trajectories array)
    t, y_out, x_states = signal.lsim(system, U=u_step, T=t_custom)

    print(f"Simulation successful. Generated {len(t)} time steps. Final output position: {y_out[-1]:.4f}")

    # --- 5. Plotting All 4 States on a Single Axis ---
    plt.figure(figsize=(9, 6))

    state_labels = [
        'State 1: Mass Position (y)', 
        r'State 2: Mass Velocity ($\dot{y}$)', 
        'State 3: Controller Integrator ($e_i$)', 
        'State 4: Filtered Derivative State'
    ]
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    linestyles = ['-', '-', '--', '--']

    for i in range(4):
        plt.plot(t, x_states[:, i], label=state_labels[i], color=colors[i], linestyle=linestyles[i], linewidth=2)

    plt.title('All 4 Closed-Loop State Trajectories on a Single Axis')
    plt.xlabel('Time (seconds)')
    plt.ylabel('State Amplitude')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(loc='best')
    plt.tight_layout()
    plt.show()
else:
    print("[-] Error: A matrix could not be parsed.")
