from modelica_parser import parse_linearized_model

# --- Execution ---
mo_file_path = 'linearized_model.mo'
A, B, C, D = parse_linearized_model(mo_file_path)

print("--- Extracted State-Space Matrices ---")
print(f"A matrix:\n{A}\n")
print(f"B matrix:\n{B}\n")
print(f"C matrix:\n{C}\n")
print(f"D matrix:\n{D}")
