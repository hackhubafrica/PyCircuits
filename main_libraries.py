import numpy as np
import scipy.optimize as opt
import sympy as sp
import control

# Create a 2D array
arr = np.array([[1, 2, 3], [4, 5, 6]])
print(arr)

# Define a function to minimize
def objective(x):
    return x[0]**2 + x[1]**2
# Use the minimize function to find the minimum
result = opt.minimize(objective, [1, 1])
print(result)


# Define symbols
x, y = sp.symbols('x y')
# Define a polynomial
polynomial = x**2 + y**2
# Simplify the polynomial
simplified_polynomial = sp.simplify(polynomial)
print(simplified_polynomial)

# Define a transfer function
num = [1, 2]
den = [1, 3, 2]
sys = control.TransferFunction(num, den)

# Simulate the system
t, y = control.step(sys, T=10)
print(y)
