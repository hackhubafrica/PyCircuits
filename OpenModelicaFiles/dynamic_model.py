import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

# --- 1. Define Physical Plant Parameters ---
m = 1.0   # Mass (kg)
c = 100.0 # Spring stiffness (N/m)
d = 5.0  # Damping coefficient (Ns/m)

# --- 2. Define Adjustable PID Gains ---
# You can tweak these values right here in Python!
Kp = 150.0
Ki = 5.0
Kd = 0.05

# --- 3. Construct Closed-Loop State-Space Representation ---
# State vector x = [position (y), velocity (v), integral of error (ei)]^T
# A-matrix for PID-controlled mass-spring-damper system:
# Note: Closed-loop combines plant dynamics with controller error feedback.
A = np.array([
    [0.0,              1.0,         0.0],
    [-(c + Kp)/m,     -(d + Kd)/m,  Ki/m],
    [-1.0,             0.0,         0.0]
])

# Input matrix B (Command reference input scaling)
B = np.array([[0.0], [Kp/m], [1.0]])

# Output matrix C (We want to observe position y, which is state 0)
C = np.array([[1.0, 0.0, 0.0]])

# Feedthrough matrix D
D = np.array([[0.0]])

# --- 4. Simulate Custom Step Response ---
system = signal.StateSpace(A, B, C, D)
print(system)
print("--- Cleaned State-Space Dimensions ---")
print(f"A: {A.shape if A is not None else 'None'}")
print(f"B: {B.shape if B is not None else 'None'}")
print(f"C: {C.shape if C is not None else 'None'}")
print(f"D: {D.shape if D is not None else 'None'}\n")

stop_time = 10.0
num_points = 500
t_custom = np.linspace(0, stop_time, num_points)

t, y = signal.step(system, T=t_custom)

print(f"Simulation successful. Final output value: {y[-1]:.4f}")

# --- 5. Plotting the Response ---
plt.figure(figsize=(8, 5))
plt.plot(t, y, label=f'Closed-Loop Position (Kp={Kp}, Ki={Ki}, Kd={Kd})', color='#1f77b4', linewidth=2)
plt.title('Tunable Closed-Loop Step Response in Python')
plt.xlabel('Time (seconds)')
plt.ylabel('Position (m)')
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend()
plt.tight_layout()
plt.show()