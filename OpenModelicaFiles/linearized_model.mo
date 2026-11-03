model linearized_model "MassSpringDamperPlant"
  parameter Integer n = 4 "number of states";
  parameter Integer m = 0 "number of inputs";
  parameter Integer p = 0 "number of outputs";

  parameter Real x0[n] = {1.190526444343293, 4.788982993084345, -8.817802165223075, -1.631267287589839};
  parameter Real u0[m] = zeros(0);

  parameter Real A[n, n] =
	[-199.9999998301361, 0, 199.9999978320332, 0;
	0, 0, 1.999999978320333, 0;
	0, 0, 0, 1.000000000620696;
	1499.999998747752, -150.0000006665323, -1749.999980264181, -4.999999827519778];

  parameter Real B[n, m] = zeros(n, m);

  parameter Real C[p, n] = zeros(p, n);

  parameter Real D[p, m] = zeros(p, m);


  Real x[n](start=x0);
  input Real u[m];
  output Real y[p];

  Real 'x_PID.D.x' = x[1];
  Real 'x_PID.I.y' = x[2];
  Real 'x_damper.s_rel' = x[3];
  Real 'x_damper.v_rel' = x[4];
equation
  der(x) = A * x + B * u;
  y = C * x + D * u;
end linearized_model;
