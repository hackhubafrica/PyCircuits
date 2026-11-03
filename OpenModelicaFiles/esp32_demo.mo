model ESP32DemoPlant
  parameter Integer n = 1;
  parameter Integer m = 1;
  parameter Integer p = 1;

  parameter Real A[n, n] = [-20.0];
  parameter Real B[n, m] = [20.0];
  parameter Real C[p, n] = [1.0];
  parameter Real D[p, m] = [0.0];

  Real x[n](start = {0.0});
  input Real u[m];
  output Real y[p];
equation
  der(x) = A * x + B * u;
  y = C * x + D * u;
end ESP32DemoPlant;
