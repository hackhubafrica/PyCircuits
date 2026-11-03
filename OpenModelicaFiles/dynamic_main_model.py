from modelica_parser import parse_linearized_model
from scipy import signal
import numpy as np
import matplotlib.pyplot as plt

# --- 1. Load and Parse Matrices from your File ---
mo_file_path = 'linearized_model.mo'
A, B, C, D = parse_linearized_model(mo_file_path)

# --- 2. Apply Safe Defaults & Ensure Valid Output Mapping ---
if A is not None:
    n_states = A.shape[0]

    if B is None: 
        B = np.zeros((n_states, 1))
        B[-1, 0] = 1.0 # Default input mapping fallback

    if C is None: 
        # Measure the first state (position y) by default
        C = np.zeros((1, n_states))
        C[0, 0] = 1.0

    if D is None: 
        D = np.zeros((1, 1))

print("--- Parsed State-Space Dimensions ---")
print(f"A: {A.shape if A is not None else 'None'}")
print(f"B: {B.shape if B is not None else 'None'}")
print(f"C: {C.shape if C is not None else 'None'}")
print(f"D: {D.shape if D is not None else 'None'}\n")

# --- 3. Convert to Transfer Function & Print ---
if A is not None:
    num, den = signal.ss2tf(A, B, C, D)
    num_siso = np.squeeze(num)

    print("--- Transfer Function Representation ---")
    print(f"Numerator coefficients:   {num_siso}")
    print(f"Denominator coefficients: {den}\n")

    # --- 4. Simulation with Custom Duration & Steps ---
    print("--- Running SciPy Simulation ---")
    stop_time = 20.0     # Adjust total duration here
    num_points = 500   # Adjust resolution here
    t_custom = np.linspace(0, stop_time, num_points)

    system = signal.StateSpace(A, B, C, D)
    t, y = signal.step(system, T=t_custom)

    print(f"Simulation successful. Generated {len(t)} time steps. Final output: {y[-1]:.4f}")

    # --- 5. Plotting with Matplotlib ---
    plt.figure(figsize=(8, 5))
    plt.plot(t, y, label='Closed-Loop Position (y from linearized_model.mo)', color='#1f77b4', linewidth=2)
    plt.title(f'Step Response ({stop_time}s Duration, {num_points} Steps)')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Position (m)')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.show()
else:
    print("[-] Error: A matrix could not be parsed from the file path.")
