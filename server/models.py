from pydantic import BaseModel, Field


class Vec3(BaseModel):
    x: float
    y: float
    z: float


class FixedSupportParam(BaseModel):
    position: Vec3
    normal: Vec3


class LoadVectorParam(BaseModel):
    position: Vec3
    direction: Vec3
    magnitude: float = 1.0


class OptimizationParams(BaseModel):
    fixed_supports: list[FixedSupportParam]
    load_vectors: list[LoadVectorParam]
    volume_fraction: float = Field(0.3, ge=0.05, le=0.95)
    nelx: int = Field(60, ge=4, le=200)
    nely: int = Field(20, ge=4, le=200)
    nelz: int = Field(10, ge=4, le=200)
    penal: float = Field(3.0, ge=1.0, le=5.0)
    rmin: float = Field(1.5, ge=1.0, le=5.0)
    max_iterations: int = Field(80, ge=1, le=2000)
    tolx: float = Field(0.01, ge=0.0001, le=0.1)


class ProgressUpdate(BaseModel):
    iteration: int
    max_iterations: int
    objective: float
    volume_fraction: float
    change: float
    elapsed_seconds: float
