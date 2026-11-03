import re
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from scipy import signal

def parse_linearized_model(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    def extract_matrix(name, content):
        pattern = rf'(?:parameter\s+)?Real\s+{name}\s*(?:\[.*?\])?\s*=\s*({{\s*.*?}}|\[\s*.*?\s*\]);'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            pattern_alt = rf'{name}\s*=\s*(\[.*?\]|\{{.*?\}});'
            match = re.search(pattern_alt, content, re.DOTALL)
        
        if match:
            raw_str = match.group(1)
            cleaned = raw_str.replace('{', '[').replace('}', ']')
            cleaned = cleaned.replace(';', ',')
            try:
                return np.array(eval(cleaned))
            except Exception as e:
                print(f"[-] Error evaluating matrix {name}: {e}")
        return None

    A = extract_matrix('A', content)
    B = extract_matrix('B', content)
    C = extract_matrix('C', content)
    D = extract_matrix('D', content)

    # Reshape A if it's a flat 1D array (e.g., 16 elements -> 4x4 matrix)
    if A is not None and A.ndim == 1:
        n = int(np.sqrt(len(A)))
        if n * n == len(A):
            A = A.reshape((n, n))

    return A, B, C, D

# --- 1. Load and Clean Matrices ---
mo_file_path = '/home/th3blaacksh33p/Documents/PyCircuits/OpenModelicaFiles/linearized_model.mo'
A, B, C, D = parse_linearized_model(mo_file_path)




# Safe defaults if B, C, or D are missing from the text dump
if A is not None:
    n_states = A.shape[0]
    if B is None: B = np.zeros((n_states, 1))
    if C is None: C = np.zeros((1, n_states))
    if D is None: D = np.zeros((1, 1))

# Assuming A, B, C, D are already loaded and parsed from your script:
system = signal.StateSpace(A, B, C, D)

# Generate the step response time series
t, y = signal.step(system)

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



# # Plotting with Matplotlib
# plt.figure(figsize=(8, 5))
# plt.plot(t, y, label='Closed-Loop Position (y)', color='#1f77b4', linewidth=2)
# plt.title('Step Response of Closed-Loop Mass-Spring-Damper System')
# plt.xlabel('Time (seconds)')
# plt.ylabel('Position (m)')
# plt.grid(True, linestyle='--', alpha=0.6)
# plt.legend()
# plt.tight_layout()

# # Show the interactive plot window
# plt.show()


# --- 3. Convert to Transfer Function & Simulate with Custom Duration/Steps ---
if A is not None:
    num, den = signal.ss2tf(A, B, C, D)
    num_siso = np.squeeze(num)

    print("--- Transfer Function Representation ---")
    print(f"Numerator coefficients:   {num_siso}")
    print(f"Denominator coefficients: {den}\n")
    
    print("--- Running SciPy Simulation ---")
    
    # --- Customizing Duration and Time Steps ---
    stop_time = 10.0     # Total duration in seconds (adjust as needed)
    num_points = 500   # Number of evaluation points (higher = finer resolution)
    t_custom = np.linspace(0, stop_time, num_points)
    
    # Pass the custom time vector into signal.step()
    system = signal.StateSpace(A, B, C, D)
    t, y = signal.step(system, T=t_custom)
    
    print(f"Simulation successful. Generated {len(t)} time steps over {stop_time}s. Final output: {y[-1]:.4f}")

    # --- 4. Plotting with Matplotlib ---
    plt.figure(figsize=(8, 5))
    plt.plot(t, y, label='Closed-Loop Position (y)', color='#1f77b4', linewidth=2)
    plt.title(f'Step Response ({stop_time}s Duration, {num_points} Steps)')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Position (m)')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.show()
else:
    print("[-] Error: A matrix could not be parsed.")