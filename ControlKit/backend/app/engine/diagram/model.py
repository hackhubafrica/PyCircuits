from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PortRef(BaseModel):
    block: str = Field(min_length=1, max_length=32)
    port: int = Field(default=0, ge=0, le=16)


class Wire(BaseModel):
    source: PortRef  # output port the signal leaves from
    target: PortRef  # input port the signal arrives at


class BlockNode(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=32)
    params: dict[str, object] = Field(default_factory=dict)
    position: tuple[float, float] = (0.0, 0.0)


class DiagramModel(BaseModel):
    blocks: list[BlockNode] = Field(min_length=1, max_length=64)
    wires: list[Wire] = Field(default_factory=list, max_length=256)
    t_final: float = Field(default=10.0, gt=0, le=600)
    step_size: float = Field(default=0.001, gt=0, le=1.0)
    solver: Literal["rk4", "euler"] = "rk4"