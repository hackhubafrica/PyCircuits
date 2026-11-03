model Plant
  parameter Real tau = 0.05 "Time constant (seconds)";
  Real x(start=0.0) "Plant state variable";
  input Real u "Control input";
  Modelica.Electrical.Analog.Sources.StepVoltage stepVoltage(V = 5)  annotation(
    Placement(transformation(origin = {-30, 164}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Electrical.Analog.Basic.Resistor resistor1(R = 10)  annotation(
    Placement(transformation(origin = {-70, 138}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Electrical.Analog.Basic.Capacitor capacitor1(C = 0.01)  annotation(
    Placement(transformation(origin = {4, 140}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Electrical.Analog.Basic.Ground ground1 annotation(
    Placement(transformation(origin = {-30, 110}, extent = {{-10, -10}, {10, 10}})));
equation
  der(x) = (u - x)/tau;
  connect(stepVoltage.n, capacitor1.p) annotation(
    Line(points = {{-20, 164}, {-8, 164}, {-8, 150}, {4, 150}}, color = {0, 0, 255}));
  connect(stepVoltage.p, resistor1.p) annotation(
    Line(points = {{-40, 164}, {-70, 164}, {-70, 148}}, color = {0, 0, 255}));
  connect(resistor1.n, ground1.p) annotation(
    Line(points = {{-70, 128}, {-30, 128}, {-30, 120}}, color = {0, 0, 255}));
  connect(capacitor1.n, ground1.p) annotation(
    Line(points = {{4, 130}, {-30, 130}, {-30, 120}}, color = {0, 0, 255}));
  annotation(
    uses(Modelica(version = "4.1.0")));
end Plant;