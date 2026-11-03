"""Shared Modelica model parser for PyCircuits OpenModelicaFiles.

Provides parse_linearized_model() to extract state-space matrices (A, B, C, D)
from OpenModelica linearized .mo files, eliminating duplication across scripts.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np


def parse_linearized_model(file_path: str) -> tuple[Optional[np.ndarray], ...]:
    """Parse state-space matrices (A, B, C, D) from a linearized Modelica .mo file.

    Parameters
    ----------
    file_path : str
        Path to the linearized Modelica .mo file (e.g. linearized_model.mo).

    Returns
    -------
    tuple of Optional[np.ndarray]
        (A, B, C, D) matrices. Any matrix not found in the file is None.
    """
    with open(file_path, "r") as f:
        content = f.read()

    def extract_matrix(name: str, content: str) -> Optional[np.ndarray]:
        pattern = (
            rf"(?:parameter\s+)?Real\s+{name}\s*(?:\\[.*?\\])?\s*="
            rf"\s*({{\s*.*?}}|\\[\\s*.*?\\s*\\]);"
        )
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            pattern_alt = rf"{name}\s*=\s*(\\[.*?\\]|\\{{.*?\\}});"
            match = re.search(pattern_alt, content, re.DOTALL)

        if match:
            raw_str = match.group(1)
            cleaned = raw_str.replace("{", "[").replace("}", "]")
            cleaned = cleaned.replace(";", ",")
            try:
                return np.array(eval(cleaned))
            except Exception as e:
                print(f"[-] Error evaluating matrix {name}: {e}")
        return None

    A = extract_matrix("A", content)
    B = extract_matrix("B", content)
    C = extract_matrix("C", content)
    D = extract_matrix("D", content)

    # Reshape A if it's a flat 1D array (e.g., 16 elements -> 4x4 matrix)
    if A is not None and A.ndim == 1:
        n = int(np.sqrt(len(A)))
        if n * n == len(A):
            A = A.reshape((n, n))

    return A, B, C, D