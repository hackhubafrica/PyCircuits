import os
import shutil
from OMPython import OMCSessionLocal

def compile_and_organize(mo_file, model_name, build_dir="plant_build", pio_src_dir=None):
    omc = OMCSessionLocal()
    
    print(f"[*] Loading model file: {mo_file}")
    load_res = omc.sendExpression(f'loadFile("{mo_file}")')
    if not load_res:
        raise RuntimeError(f"Failed to load {mo_file}")

    print(f"[*] Building model target: {model_name}")
    build_res = omc.sendExpression(f"buildModel({model_name})")
    print(f"[+] Build output: {build_res}")

    # Create an explicit dedicated build folder
    os.makedirs(build_dir, exist_ok=True)
    print(f"[*] Organizing generated artifacts into explicit folder: ./{build_dir}/")

    # Move generated C files, headers, records, and makefiles into the build folder
    for filename in os.listdir('.'):
        if filename.startswith(model_name) or filename.endswith('.makefile') or filename.endswith('.json'):
            src = filename
            dst = os.path.join(build_dir, filename)
            if os.path.isfile(src) and src != build_dir:
                if os.path.exists(dst):
                    os.remove(dst)  # Clear out old file version to prevent collision
                shutil.move(src, dst)
                print(f"    -> Moved: {filename}")

    # Automatically copy core model files straight into PlatformIO src directory
    if pio_src_dir and os.path.exists(pio_src_dir):
        for core_file in [f"{model_name}.h", f"{model_name}.c"]:
            src_path = os.path.join(build_dir, core_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(pio_src_dir, core_file)
                shutil.copy(src_path, dst_path)
                print(f"[+] Copied {core_file} directly to PlatformIO src: {pio_src_dir}")

if __name__ == "__main__":
    MO_FILE = "plant.mo"
    MODEL_NAME = "Plant"
    BUILD_DIR = "plant_build"  # Explicit build directory name
    PIO_SRC_DIR = "PlantHILProject/src"
    
    compile_and_organize(MO_FILE, MODEL_NAME, BUILD_DIR, PIO_SRC_DIR)