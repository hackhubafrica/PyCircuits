# from OMPython import OMCSessionLocal
# omc = OMCSessionLocal()
# omc.sendExpression('loadFile("mass_spring_damper_pid.mo")')

# # Linearize and get ABCD matrices or transfer function representation
# lin_res = omc.sendExpression('linearize(MassSpringDamperPID)')
# print("[+] Linearization result:", lin_res)


import os
import shutil
from OMPython import OMCSessionLocal

def linearize_and_organize(mo_file, model_name, build_dir="lin_build", pio_src_dir=None):
    omc = OMCSessionLocal()
    
    print(f"[*] Loading model file: {mo_file}")
    load_res = omc.sendExpression(f'loadFile("{mo_file}")')
    if not load_res:
        raise RuntimeError(f"Failed to load {mo_file}")

    print(f"[*] Executing linearization for target: {model_name}")
    lin_res = omc.sendExpression(f"linearize({model_name})")
    print(f"[+] Linearization result / output files: {lin_res}")

    # Create an explicit dedicated build folder for linearization artifacts
    os.makedirs(build_dir, exist_ok=True)
    print(f"[*] Organizing generated linearization artifacts into explicit folder: ./{build_dir}/")

    # Move generated C files, headers, matrices, .mat result files, and makefiles into the build folder
    for filename in os.listdir('.'):
        if (filename.startswith(model_name) or 
            filename.endswith('.makefile') or 
            filename.endswith('.json') or 
            filename.endswith('.mat') or 
            filename.endswith('.log')):
            
            src = filename
            dst = os.path.join(build_dir, filename)
            if os.path.isfile(src) and src != build_dir:
                if os.path.exists(dst):
                    os.remove(dst)  # Clear out old file version to prevent collision
                shutil.move(src, dst)
                print(f"    -> Moved: {filename}")

    # Automatically copy core linearization C/header files straight into PlatformIO src directory
    if pio_src_dir and os.path.exists(pio_src_dir):
        # OpenModelica linearization typically emits model files and linear system definitions
        target_files = [f"{model_name}.h", f"{model_name}.c", f"{model_name}_lin.h"]
        for core_file in target_files:
            src_path = os.path.join(build_dir, core_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(pio_src_dir, core_file)
                shutil.copy(src_path, dst_path)
                print(f"[+] Copied {core_file} directly to PlatformIO src: {pio_src_dir}")

if __name__ == "__main__":
    MO_FILE = "MassSpringDamperPlant.mo"
    MODEL_NAME = "MassSpringDamperPlant"
    BUILD_DIR = "lin_build"  # Explicit build directory name
    PIO_SRC_DIR = "PlantHILProject/src"
    
    linearize_and_organize(MO_FILE, MODEL_NAME, BUILD_DIR, PIO_SRC_DIR)