from modelica_parser import parse_linearized_model
from scipy import signal
import numpy as np

# --- 1. Load and Clean Matrices ---
mo_file_path = 'linearized_model.mo'
A, B, C, D = parse_linearized_model(mo_file_path)

# Safe defaults if B, C, or D are missing from the text dump
if A is not None:
    n_states = A.shape[0]
    if B is None: B = np.zeros((n_states, 1))
    if C is None: C = np.zeros((1, n_states))
    if D is None: D = np.zeros((1, 1))

print("--- Cleaned State-Space Dimensions ---")
print(f"A: {A.shape if A is not None else 'None'}")
print(f"B: {B.shape if B is not None else 'None'}")
print(f"C: {C.shape if C is not None else 'None'}")
print(f"D: {D.shape if D is not None else 'None'}\n")

# --- 2. Convert to Transfer Function & Simulate ---
if A is not None:
    num, den = signal.ss2tf(A, B, C, D)
    num_siso = np.squeeze(num)

    print("--- Transfer Function Representation ---")
    print(f"Numerator coefficients:   {num_siso}")
    print(f"Denominator coefficients: {den}\n")

    print("--- Running SciPy Simulation ---")
    system = signal.StateSpace(A, B, C, D)
    t, y = signal.step(system)
    print(f"Simulation successful. Generated {len(t)} time steps. Final output: {y[-1]:.4f}")
else:
    print("[-] Error: A matrix could not be parsed.")
