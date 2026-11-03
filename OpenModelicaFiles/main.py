from OMPython import OMCSessionLocal

# Initialize the local OpenModelica session backend via ZeroMQ
omc = OMCSessionLocal()

# Load and test your model (matching the capital 'P' in Plant)
omc.sendExpression("loadFile(\"plant.mo\")")
result = omc.sendExpression("buildModel(Plant)")

print("Build Output:", result)