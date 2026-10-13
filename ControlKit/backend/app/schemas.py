from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComplexNumber(BaseModel):
    re: float
    im: float = 0.0


class PlantSpec(BaseModel):
    form: Literal["tf", "ss"] = "tf"
    num: list[float] | None = None
    den: list[float] | None = None
    A: list[list[float]] | None = None
    B: list[list[float]] | None = None
    C: list[list[float]] | None = None
    D: list[list[float]] | None = None


class SimRequest(BaseModel):
    plant: PlantSpec
    kind: Literal["step", "impulse", "custom"] = "step"
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)
    t: list[float] | None = None
    u: list[float] | None = None


class AnalyzeRequest(BaseModel):
    plant: PlantSpec
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)


class PidGains(BaseModel):
    Kp: float = 1.0
    Ki: float = 0.0
    Kd: float = 0.0
    N: float | None = None


class PidClosedLoopRequest(BaseModel):
    plant: PlantSpec
    gains: PidGains = PidGains()
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)


class PidTuneRequest(BaseModel):
    plant: PlantSpec
    method: Literal["zn", "pole_placement"] = "zn"
    desired_poles: list[ComplexNumber] | None = None


class AckermannRequest(BaseModel):
    plant: PlantSpec
    desired_poles: list[ComplexNumber] = Field(min_length=1)


class LqrRequest(BaseModel):
    plant: PlantSpec
    Q: list[float] = Field(min_length=1)
    R: float = Field(gt=0)


class BlockSpec(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    kind: Literal["tf", "ss", "pid", "gain"]
    num: list[float] | None = None
    den: list[float] | None = None
    A: list[list[float]] | None = None
    B: list[list[float]] | None = None
    C: list[list[float]] | None = None
    D: list[list[float]] | None = None
    gains: PidGains | None = None
    k: float | None = None


class InterconnectRequest(BaseModel):
    blocks: list[BlockSpec] = Field(min_length=1, max_length=6)
    forward: list[str] = Field(min_length=1, max_length=6)
    parallel: list[str] | None = Field(default=None, max_length=6)
    feedback: str | list[str] = "unity"
    t_final: float = Field(default=10.0, gt=0)
    n_points: int = Field(default=500, ge=50, le=5000)
