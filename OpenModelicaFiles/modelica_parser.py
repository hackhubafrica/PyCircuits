"""Parse state-space matrices and the initial state from Modelica source files."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

import numpy as np

__all__ = ["parse_linearized_initial_state", "parse_linearized_model"]

_MATRIX_NAMES = ("A", "B", "C", "D")
_NUMBER = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)


def _read_assignments(content: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for name in _MATRIX_NAMES:
        declaration = re.search(
            rf"^\s*(?:(?:parameter|constant)\s+)?Real\s+{name}"
            rf"\s*(?:\[[^\]]*\])?\s*=\s*",
            content,
            re.MULTILINE,
        )
        if declaration is None:
            declaration = re.search(
                rf"^\s*{name}\s*=\s*",
                content,
                re.MULTILINE,
            )
        if declaration is None:
            continue

        start = declaration.end()
        depth = 0
        for index in range(start, len(content)):
            char = content[index]
            if char in "[({":
                depth += 1
            elif char in "])}":
                depth -= 1
            elif char == ";" and depth == 0:
                assignments[name] = content[start:index].strip()
                break
    return assignments


def _read_assignment(content: str, name: str) -> str | None:
    declaration = re.search(
        rf"^\s*(?:(?:parameter|constant)\s+)?Real\s+{re.escape(name)}"
        rf"\s*(?:\[[^\]]*\])?\s*=\s*",
        content,
        re.MULTILINE,
    )
    if declaration is None:
        return None

    start = declaration.end()
    depth = 0
    for index in range(start, len(content)):
        char = content[index]
        if char in "[({":
            depth += 1
        elif char in "])}":
            depth -= 1
        elif char == ";" and depth == 0:
            return content[start:index].strip()
    return None


def _integer_parameters(content: str) -> dict[str, int]:
    return {
        name: int(value)
        for name, value in re.findall(
            r'\bparameter\s+Integer\s+(\w+)\s*=\s*(\d+)'
            r'(?:\s+"(?:[^"]|"")*")?\s*;',
            content,
        )
    }


def _declared_shapes(
    content: str,
    dimensions: dict[str, int],
) -> dict[str, tuple[int, int]]:
    shapes: dict[str, tuple[int, int]] = {}
    for name in _MATRIX_NAMES:
        match = re.search(
            rf"\bReal\s+{name}\s*\[([^\]]+)\]",
            content,
        )
        if match is None:
            continue
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) != 2:
            continue
        shape: list[int] = []
        for part in parts:
            if part.isdigit():
                shape.append(int(part))
            elif part in dimensions:
                shape.append(dimensions[part])
            else:
                break
        if len(shape) == 2:
            shapes[name] = (shape[0], shape[1])
    return shapes


def _parse_zeros(expression: str, dimensions: dict[str, int]) -> np.ndarray:
    match = re.fullmatch(r"zeros\s*\(([^()]*)\)", expression.strip())
    if match is None:
        raise ValueError(f"Unsupported matrix expression: {expression!r}")

    shape: list[int] = []
    for part in match.group(1).split(","):
        value = part.strip()
        if value.isdigit():
            shape.append(int(value))
        elif value in dimensions:
            shape.append(dimensions[value])
        else:
            raise ValueError(f"Cannot resolve matrix dimension {value!r}")
    if len(shape) not in (1, 2):
        raise ValueError("zeros() must specify one or two dimensions")
    return np.zeros(tuple(shape), dtype=float)


def parse_linearized_initial_state(
    file_path: str | Path,
    state_count: int,
) -> np.ndarray:
    """Read the linearizer's ``x0`` vector, defaulting to zero when absent."""
    content = Path(file_path).read_text(encoding="utf-8")
    expression = _read_assignment(content, "x0")
    if expression is None:
        return np.zeros(state_count, dtype=float)
    if expression.startswith("zeros"):
        vector = _parse_zeros(expression, _integer_parameters(content)).reshape(-1)
    else:
        normalized = expression.replace("{", "[").replace("}", "]")
        try:
            vector = np.asarray(ast.literal_eval(normalized), dtype=float).reshape(-1)
        except (OverflowError, SyntaxError, ValueError) as error:
            raise ValueError(
                f"Unsupported initial state vector: {expression!r}"
            ) from error
    if vector.shape != (state_count,):
        raise ValueError(
            f"x0 must contain {state_count} values; got {vector.size}."
        )
    if not np.all(np.isfinite(vector)):
        raise ValueError("x0 contains a non-finite value.")
    return vector


def _parse_literal(expression: str) -> np.ndarray:
    raw = expression.strip()
    if ";" in raw:
        if raw[0] not in "[{(" or raw[-1] not in "]})":
            raise ValueError(f"Malformed matrix literal: {expression!r}")
        body = raw[1:-1]
        rows = [row.strip() for row in body.split(";")]
        parsed_rows: list[list[float]] = []
        for row in rows:
            row = row.strip().strip("[]{}()")
            values = [value.strip() for value in row.split(",")]
            if not values or any(not _NUMBER.fullmatch(value) for value in values):
                raise ValueError(f"Malformed matrix row: {row!r}")
            parsed_rows.append([float(value) for value in values])
        if len({len(row) for row in parsed_rows}) != 1:
            raise ValueError("Matrix rows must all have the same number of columns")
        return np.asarray(parsed_rows, dtype=float)

    normalized = raw.replace("{", "[").replace("}", "]")
    try:
        literal = ast.literal_eval(normalized)
    except (OverflowError, SyntaxError, ValueError) as error:
        raise ValueError(f"Unsupported matrix literal: {expression!r}") from error
    return np.asarray(literal, dtype=float)


def _extract_matrix(
    name: str,
    assignments: dict[str, str],
    dimensions: dict[str, int],
    declared_shapes: dict[str, tuple[int, int]],
) -> Optional[np.ndarray]:
    expression = assignments.get(name)
    if expression is None:
        return None
    if expression.startswith("zeros"):
        matrix = _parse_zeros(expression, dimensions)
    else:
        matrix = _parse_literal(expression)

    declared_shape = declared_shapes.get(name)
    if matrix.ndim == 1 and declared_shape is not None:
        if matrix.size == declared_shape[0] * declared_shape[1]:
            matrix = matrix.reshape(declared_shape)
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"Matrix {name} contains a non-finite value")
    return matrix


def parse_linearized_model(
    file_path: str | Path,
) -> tuple[
    Optional[np.ndarray],
    Optional[np.ndarray],
    Optional[np.ndarray],
    Optional[np.ndarray],
]:
    """Extract state-space matrices ``(A, B, C, D)`` from a Modelica file.

    Supports numeric matrix literals written with Modelica ``[]`` or ``{}``
    delimiters, semicolon-separated rows, and ``zeros()`` expressions whose
    dimensions are numeric or declared integer parameters. Missing matrices
    are returned as ``None``.
    """
    content = Path(file_path).read_text(encoding="utf-8")
    assignments = _read_assignments(content)
    dimensions = _integer_parameters(content)
    declared_shapes = _declared_shapes(content, dimensions)

    matrices = tuple(
        _extract_matrix(name, assignments, dimensions, declared_shapes)
        for name in _MATRIX_NAMES
    )
    A, B, C, D = matrices

    if A is not None and A.ndim == 1:
        state_count = int(np.sqrt(A.size))
        if state_count * state_count == A.size:
            A = A.reshape((state_count, state_count))

    return A, B, C, D
