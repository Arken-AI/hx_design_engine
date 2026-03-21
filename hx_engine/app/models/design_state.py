"""Central design state models for the HX design pipeline.

FluidProperties — physical-bound validated fluid properties
GeometrySpec   — CG3A-validated shell-and-tube geometry
DesignState    — the state bag passed between pipeline steps
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# FluidProperties
# ---------------------------------------------------------------------------

class FluidProperties(BaseModel):
    """Thermophysical properties for a single fluid stream.

    Every field has physical bounds enforced via Pydantic validators.
    """

    density_kg_m3: Optional[float] = None
    viscosity_Pa_s: Optional[float] = None
    cp_J_kgK: Optional[float] = None
    k_W_mK: Optional[float] = None
    Pr: Optional[float] = None

    @field_validator("density_kg_m3")
    @classmethod
    def _check_density(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 50 or v > 2000):
            raise ValueError(
                f"density_kg_m3={v} outside physical range [50, 2000]"
            )
        return v

    @field_validator("viscosity_Pa_s")
    @classmethod
    def _check_viscosity(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 1e-6 or v > 1.0):
            raise ValueError(
                f"viscosity_Pa_s={v} outside physical range [1e-6, 1.0]"
            )
        return v

    @field_validator("cp_J_kgK")
    @classmethod
    def _check_cp(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 500 or v > 10000):
            raise ValueError(
                f"cp_J_kgK={v} outside physical range [500, 10000]"
            )
        return v

    @field_validator("k_W_mK")
    @classmethod
    def _check_k(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.01 or v > 100):
            raise ValueError(
                f"k_W_mK={v} outside physical range [0.01, 100]"
            )
        return v

    @field_validator("Pr")
    @classmethod
    def _check_Pr(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.5 or v > 1000):
            raise ValueError(
                f"Pr={v} outside physical range [0.5, 1000]"
            )
        return v


# ---------------------------------------------------------------------------
# GeometrySpec
# ---------------------------------------------------------------------------

class GeometrySpec(BaseModel):
    """Shell-and-tube geometry with CG3A / TEMA validators."""

    baffle_spacing_m: Optional[float] = None
    pitch_ratio: Optional[float] = None
    shell_diameter_m: Optional[float] = None
    tube_od_m: Optional[float] = None
    tube_id_m: Optional[float] = None
    tube_length_m: Optional[float] = None
    baffle_cut: Optional[float] = None

    @field_validator("baffle_spacing_m")
    @classmethod
    def _check_baffle_spacing(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.05 or v > 2.0):
            raise ValueError(
                f"baffle_spacing_m={v} outside TEMA range [0.05, 2.0]"
            )
        return v

    @field_validator("pitch_ratio")
    @classmethod
    def _check_pitch_ratio(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 1.2 or v > 1.5):
            raise ValueError(
                f"pitch_ratio={v} outside TEMA range [1.2, 1.5]"
            )
        return v

    @field_validator("shell_diameter_m")
    @classmethod
    def _check_shell_diameter(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.05 or v > 3.0):
            raise ValueError(
                f"shell_diameter_m={v} outside range [0.05, 3.0]"
            )
        return v

    @field_validator("tube_od_m")
    @classmethod
    def _check_tube_od(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.005 or v > 0.10):
            raise ValueError(
                f"tube_od_m={v} outside range [0.005, 0.10]"
            )
        return v

    @field_validator("tube_id_m")
    @classmethod
    def _check_tube_id(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.003 or v > 0.095):
            raise ValueError(
                f"tube_id_m={v} outside range [0.003, 0.095]"
            )
        return v

    @field_validator("tube_length_m")
    @classmethod
    def _check_tube_length(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.5 or v > 10.0):
            raise ValueError(
                f"tube_length_m={v} outside range [0.5, 10.0]"
            )
        return v

    @field_validator("baffle_cut")
    @classmethod
    def _check_baffle_cut(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.15 or v > 0.45):
            raise ValueError(
                f"baffle_cut={v} outside TEMA range [0.15, 0.45]"
            )
        return v

    @model_validator(mode="after")
    def _check_tube_id_lt_od(self) -> "GeometrySpec":
        if (
            self.tube_id_m is not None
            and self.tube_od_m is not None
            and self.tube_id_m >= self.tube_od_m
        ):
            raise ValueError(
                f"tube_id_m ({self.tube_id_m}) must be less than "
                f"tube_od_m ({self.tube_od_m})"
            )
        return self


# ---------------------------------------------------------------------------
# DesignState — the central state bag
# ---------------------------------------------------------------------------

class DesignState(BaseModel):
    """Mutable state that flows through the HX design pipeline.

    Every step reads from and writes back to a DesignState instance.
    """

    # --- identity ---
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None

    # --- raw user input ---
    raw_request: str = ""

    # --- temperatures (°C) ---
    T_hot_in_C: Optional[float] = None
    T_hot_out_C: Optional[float] = None
    T_cold_in_C: Optional[float] = None
    T_cold_out_C: Optional[float] = None

    # --- flow rates (kg/s) ---
    m_dot_hot_kg_s: Optional[float] = None
    m_dot_cold_kg_s: Optional[float] = None

    # --- fluid names ---
    hot_fluid_name: Optional[str] = None
    cold_fluid_name: Optional[str] = None

    # --- pressures (Pa) ---
    P_hot_Pa: Optional[float] = None
    P_cold_Pa: Optional[float] = None

    # --- fluid properties (populated by Step 3) ---
    hot_fluid_props: Optional[FluidProperties] = None
    cold_fluid_props: Optional[FluidProperties] = None

    # --- geometry (populated by Step 4+) ---
    geometry: Optional[GeometrySpec] = None

    # --- thermal results (populated by later steps) ---
    Q_W: Optional[float] = None
    LMTD_K: Optional[float] = None
    U_W_m2K: Optional[float] = None
    A_m2: Optional[float] = None

    # --- pipeline state ---
    current_step: int = 0
    completed_steps: list[int] = Field(default_factory=list)
    step_records: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    in_convergence_loop: bool = False

    # --- optional preferences ---
    tema_class: Optional[str] = None
    tema_preference: Optional[str] = None
