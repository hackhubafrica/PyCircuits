model Plant
  parameter Real tau = 0.05 "Time constant (seconds)";
  Real x(start=0.0) "Plant state variable";
  input Real u "Control input";
  output Real y "Plant output";
  Modelica.Electrical.Analog.Sources.StepVoltage stepVoltage(V = 5)  annotation(
    Placement(transformation(origin = {4, 16}, extent = {{-10, -10}, {10, 10}}, rotation = 0)));
  Modelica.Electrical.Analog.Basic.Resistor resistor1(R = 10)  annotation(
    Placement(transformation(origin = {-36, -10}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Electrical.Analog.Basic.Capacitor capacitor1(C = 0.01)  annotation(
    Placement(transformation(origin = {38, -8}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Electrical.Analog.Basic.Ground ground1 annotation(
    Placement(transformation(origin = {4, -38}, extent = {{-10, -10}, {10, 10}}, rotation = 0)));
equation
  der(x) = (u - x)/tau;
  y = x;
  connect(stepVoltage.n, capacitor1.p) annotation(
    Line(points = {{14, 16}, {26, 16}, {26, 2}, {38, 2}}, color = {0, 0, 255}));
  connect(stepVoltage.p, resistor1.p) annotation(
    Line(points = {{-6, 16}, {-36, 16}, {-36, 0}}, color = {0, 0, 255}));
  connect(resistor1.n, ground1.p) annotation(
    Line(points = {{-36, -20}, {4, -20}, {4, -28}}, color = {0, 0, 255}));
  connect(capacitor1.n, ground1.p) annotation(
    Line(points = {{38, -18}, {4, -18}, {4, -28}}, color = {0, 0, 255}));
  annotation(
    uses(Modelica(version = "4.1.0")));
end Plant;