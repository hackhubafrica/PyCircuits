from OMPython import OMCSessionLocal
omc = OMCSessionLocal()
omc.sendExpression('loadFile("MassSpringDamperPlant.mo")')

# Linearize and get ABCD matrices or transfer function representation
lin_res = omc.sendExpression('linearize(MassSpringDamperPlant)')
print("[+] Linearization result:", lin_res)