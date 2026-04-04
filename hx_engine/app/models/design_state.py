"""Central design state models for the HX design pipeline.

FluidProperties — physical-bound validated fluid properties
GeometrySpec   — CG3A-validated shell-and-tube geometry
DesignState    — the state bag passed between pipeline steps
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Imported at runtime (not just TYPE_CHECKING) because DesignState stores
# StepRecord instances in step_records.
from hx_engine.app.models.step_result import StepRecord  # noqa: E402


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

    # --- Property provenance (populated by thermo adapter) ---
    property_source: Optional[str] = None      # e.g. "iapws", "coolprop", "thermo", "petroleum-named", "petroleum-generic", "specialty"
    property_confidence: Optional[float] = None  # 0.0–1.0; None = not assessed

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
    n_tubes: Optional[int] = None
    n_passes: Optional[int] = None
    pitch_layout: Optional[str] = None
    shell_passes: Optional[int] = None

    # --- Bell-Delaware specific (populated by Step 8 preconditions) ---
    tube_pitch_m: Optional[float] = None
    n_sealing_strip_pairs: Optional[int] = 0
    inlet_baffle_spacing_m: Optional[float] = None   # defaults to baffle_spacing_m
    outlet_baffle_spacing_m: Optional[float] = None   # defaults to baffle_spacing_m
    n_baffles: Optional[int] = None

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

    @field_validator("n_tubes")
    @classmethod
    def _check_n_tubes(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 10000):
            raise ValueError(
                f"n_tubes={v} outside range [1, 10000]"
            )
        return v

    @field_validator("n_passes")
    @classmethod
    def _check_n_passes(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in {1, 2, 4, 6, 8}:
            raise ValueError(
                f"n_passes={v} not in standard set {{1, 2, 4, 6, 8}}"
            )
        return v

    @field_validator("pitch_layout")
    @classmethod
    def _check_pitch_layout(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"triangular", "square"}:
            raise ValueError(
                f"pitch_layout='{v}' not in {{triangular, square}}"
            )
        return v

    @field_validator("shell_passes")
    @classmethod
    def _check_shell_passes(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in {1, 2}:
            raise ValueError(
                f"shell_passes={v} not in {{1, 2}}"
            )
        return v

    @field_validator("tube_pitch_m")
    @classmethod
    def _check_tube_pitch(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.01 or v > 0.10):
            raise ValueError(
                f"tube_pitch_m={v} outside range [0.01, 0.10]"
            )
        return v

    @field_validator("n_sealing_strip_pairs")
    @classmethod
    def _check_sealing_strips(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 0 or v > 20):
            raise ValueError(
                f"n_sealing_strip_pairs={v} outside range [0, 20]"
            )
        return v

    @field_validator("inlet_baffle_spacing_m")
    @classmethod
    def _check_inlet_baffle_spacing(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.05 or v > 2.0):
            raise ValueError(
                f"inlet_baffle_spacing_m={v} outside range [0.05, 2.0]"
            )
        return v

    @field_validator("outlet_baffle_spacing_m")
    @classmethod
    def _check_outlet_baffle_spacing(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.05 or v > 2.0):
            raise ValueError(
                f"outlet_baffle_spacing_m={v} outside range [0.05, 2.0]"
            )
        return v

    @field_validator("n_baffles")
    @classmethod
    def _check_n_baffles(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 100):
            raise ValueError(
                f"n_baffles={v} outside range [1, 100]"
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
    org_id: Optional[str] = None
    mode: str = "design"  # "design" | "rating"

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

    # --- mean temperatures (arithmetic mean of inlet/outlet, °C) ---
    T_mean_hot_C: Optional[float] = None
    T_mean_cold_C: Optional[float] = None

    # --- thermal results (populated by later steps) ---
    Q_W: Optional[float] = None
    LMTD_K: Optional[float] = None
    F_factor: Optional[float] = None
    U_W_m2K: Optional[float] = None
    A_m2: Optional[float] = None

    # --- tube-side heat transfer (populated by Step 7) ---
    h_tube_W_m2K: Optional[float] = None
    tube_velocity_m_s: Optional[float] = None
    Re_tube: Optional[float] = None
    Pr_tube: Optional[float] = None
    Nu_tube: Optional[float] = None
    flow_regime_tube: Optional[str] = None   # "laminar" | "transition" | "turbulent"

    # --- shell-side heat transfer (populated by Step 8) ---
    h_shell_W_m2K: Optional[float] = None
    Re_shell: Optional[float] = None
    shell_side_j_factors: Optional[dict] = None  # {"J_c": ..., "J_l": ..., ...}
    h_shell_ideal_W_m2K: Optional[float] = None
    h_shell_kern_W_m2K: Optional[float] = None   # Kern cross-check value

    # --- overall U + resistance breakdown (populated by Step 9) ---
    U_clean_W_m2K: Optional[float] = None
    U_dirty_W_m2K: Optional[float] = None
    U_overall_W_m2K: Optional[float] = None
    cleanliness_factor: Optional[float] = None
    resistance_breakdown: Optional[dict] = None
    controlling_resistance: Optional[str] = None
    U_kern_W_m2K: Optional[float] = None
    U_kern_deviation_pct: Optional[float] = None
    U_vs_estimated_deviation_pct: Optional[float] = None

    # --- tube material properties (resolved by Step 9) ---
    tube_material: Optional[str] = None
    k_wall_W_mK: Optional[float] = None
    k_wall_source: Optional[str] = None
    k_wall_confidence: Optional[float] = None

    # --- pipeline state ---
    current_step: int = 0
    completed_steps: list[int] = Field(default_factory=list)
    pipeline_status: str = "pending"  # "pending" | "running" | "completed" | "error" | "cancelled"
    step_records: list[StepRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    waiting_for_user: bool = False
    in_convergence_loop: bool = False
    is_complete: bool = False

    # --- AI cross-step observations (populated by base.py after each review) ---
    # Each entry is a short note from the AI engineer, forwarded to downstream
    # steps so the reviewer can reason across multiple steps.
    review_notes: list[str] = Field(default_factory=list)

    # --- confidence breakdown (populated by Step 16) ---
    confidence_breakdown: Optional[dict[str, float]] = None

    # --- fouling resistances (populated by Step 4; AI can correct these) ---
    # When set, Step 4 skips the lookup and uses these values directly,
    # breaking the correction loop caused by unresolvable fouling uncertainty.
    R_f_hot_m2KW: Optional[float] = None   # m²·K/W, hot-side fouling resistance
    R_f_cold_m2KW: Optional[float] = None  # m²·K/W, cold-side fouling resistance

    # --- TEMA type & allocation (populated by Step 4) ---
    tema_type: Optional[str] = None
    shell_side_fluid: Optional[str] = None

    # --- optional preferences ---
    tema_class: Optional[str] = None
    tema_preference: Optional[str] = None

    # --- correction loop overrides (cleared after each step completes) ---
    # Populated by run_with_review_loop() before re-executing a step so that
    # deterministic selection logic (e.g. TEMA type) respects the AI's correction
    # instead of re-running its own decision tree and overriding it.
    applied_corrections: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # State snapshot / restore helpers (used by correction loop in base.py)
    # ------------------------------------------------------------------

    def snapshot_fields(self, field_names: list[str]) -> dict[str, Any]:
        """Return {field: deep-copied value} for the listed fields.

        Deep copy is required because some fields are Pydantic sub-models
        (e.g. geometry: GeometrySpec). A shallow copy would store a reference
        to the same mutable object, making rollback ineffective.
        """
        return {f: copy.deepcopy(getattr(self, f, None)) for f in field_names}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Write snapshot values back to DesignState fields.

        Called when a correction causes a Layer 2 hard fail, so state is
        never left partially mutated.
        """
        for field_name, value in snapshot.items():
            if hasattr(self, field_name):
                setattr(self, field_name, value)
