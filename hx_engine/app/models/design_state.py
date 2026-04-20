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
    Supports liquid, vapor, and two-phase states.
    """

    density_kg_m3: Optional[float] = None
    viscosity_Pa_s: Optional[float] = None
    cp_J_kgK: Optional[float] = None
    k_W_mK: Optional[float] = None
    Pr: Optional[float] = None

    # --- Phase state (populated by thermo adapter) ---
    phase: Optional[str] = None                # "liquid" | "vapor" | "two_phase"
    quality: Optional[float] = None            # vapor mass fraction 0.0–1.0 (None for single-phase)
    enthalpy_J_kg: Optional[float] = None      # specific enthalpy (J/kg)
    latent_heat_J_kg: Optional[float] = None   # h_fg at saturation (J/kg)
    T_sat_C: Optional[float] = None            # saturation temperature at operating pressure (°C)
    P_sat_Pa: Optional[float] = None           # saturation pressure at operating temperature (Pa)

    # --- Property provenance (populated by thermo adapter) ---
    property_source: Optional[str] = None      # e.g. "iapws", "coolprop", "thermo", "petroleum-named", "petroleum-generic", "specialty"
    property_confidence: Optional[float] = None  # 0.0–1.0; None = not assessed

    @field_validator("phase")
    @classmethod
    def _check_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"liquid", "vapor", "two_phase"}:
            raise ValueError(
                f"phase='{v}' not in {{liquid, vapor, two_phase}}"
            )
        return v

    @field_validator("quality")
    @classmethod
    def _check_quality(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError(
                f"quality={v} outside range [0.0, 1.0]"
            )
        return v

    @field_validator("density_kg_m3")
    @classmethod
    def _check_density(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.01 or v > 2000):
            raise ValueError(
                f"density_kg_m3={v} outside physical range [0.01, 2000]"
            )
        return v

    @field_validator("viscosity_Pa_s")
    @classmethod
    def _check_viscosity(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 1e-7 or v > 1.0):
            raise ValueError(
                f"viscosity_Pa_s={v} outside physical range [1e-7, 1.0]"
            )
        return v

    @field_validator("cp_J_kgK")
    @classmethod
    def _check_cp(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 100 or v > 100_000):
            raise ValueError(
                f"cp_J_kgK={v} outside physical range [100, 100000]"
            )
        return v

    @field_validator("k_W_mK")
    @classmethod
    def _check_k(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.005 or v > 100):
            raise ValueError(
                f"k_W_mK={v} outside physical range [0.005, 100]"
            )
        return v

    @field_validator("Pr")
    @classmethod
    def _check_Pr(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.001 or v > 10000):
            raise ValueError(
                f"Pr={v} outside physical range [0.001, 10000]"
            )
        return v


# ---------------------------------------------------------------------------
# IncrementResult — per-segment results for incremental calculation
# ---------------------------------------------------------------------------

class IncrementResult(BaseModel):
    """Results for a single segment of the incremental HX calculation.

    Used when the shell-side fluid undergoes phase change (condensation
    or evaporation). Each segment tracks local temperatures, quality,
    heat transfer coefficients, and the area required for that segment.
    """

    segment_index: int = 0
    T_hot_in_C: Optional[float] = None
    T_hot_out_C: Optional[float] = None
    T_cold_in_C: Optional[float] = None
    T_cold_out_C: Optional[float] = None
    quality_in: Optional[float] = None        # vapor fraction at segment inlet
    quality_out: Optional[float] = None       # vapor fraction at segment outlet
    phase: Optional[str] = None               # "liquid" | "vapor" | "two_phase"
    h_tube_W_m2K: Optional[float] = None
    h_shell_W_m2K: Optional[float] = None
    U_local_W_m2K: Optional[float] = None
    dQ_W: Optional[float] = None              # heat duty for this segment
    dA_m2: Optional[float] = None             # area required for this segment
    LMTD_local_K: Optional[float] = None


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
    n_shells: Optional[int] = None   # Number of shells (multi-shell arrangement)

    # --- Bell-Delaware specific (populated by Step 8 preconditions) ---
    tube_pitch_m: Optional[float] = None
    n_sealing_strip_pairs: Optional[int] = 0
    inlet_baffle_spacing_m: Optional[float] = None   # defaults to baffle_spacing_m
    outlet_baffle_spacing_m: Optional[float] = None   # defaults to baffle_spacing_m
    n_baffles: Optional[int] = None

    # --- Vibration-specific (Step 13) ---
    pitch_angle_deg: Optional[int] = None       # 30, 45, 60, or 90; derived from pitch_layout if None
    baffle_thickness_m: Optional[float] = None  # defaults to 0.00635 (1/4") if None

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

    @field_validator("n_shells")
    @classmethod
    def _check_n_shells(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 4):
            raise ValueError(
                f"n_shells={v} outside range [1, 4]"
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

    @field_validator("pitch_angle_deg")
    @classmethod
    def _check_pitch_angle(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in (30, 45, 60, 90):
            raise ValueError(
                f"pitch_angle_deg must be 30, 45, 60, or 90; got {v}"
            )
        return v

    @field_validator("baffle_thickness_m")
    @classmethod
    def _check_baffle_thickness(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.003 or v > 0.025):
            raise ValueError(
                f"baffle_thickness_m={v} outside range [0.003, 0.025]"
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

    def get_pitch_angle(self) -> int:
        """Return pitch angle in degrees.

        Uses ``pitch_angle_deg`` if set, otherwise derives from
        ``pitch_layout`` (triangular → 30, square → 90).
        """
        if self.pitch_angle_deg is not None:
            return self.pitch_angle_deg
        return 90 if self.pitch_layout == "square" else 30

    def get_baffle_thickness(self) -> float:
        """Return baffle thickness in metres. Defaults to 0.00635 (1/4 inch)."""
        return self.baffle_thickness_m if self.baffle_thickness_m is not None else 0.00635


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

    # --- flow input audit (P2-20) ---
    # When the request supplied a volumetric/mass flow object (hot_flow /
    # cold_flow), the resolver records the original value, unit, and the
    # density used for the conversion here. None when the caller passed
    # m_dot_*_kg_s directly. Step 3 re-confirms these densities at the
    # bulk-mean temperature and emits a WARN if drift exceeds
    # DENSITY_DRIFT_WARN_PCT.
    hot_flow_input: Optional[dict] = None
    cold_flow_input: Optional[dict] = None
    flow_density_drift: Optional[dict] = None  # {"hot": pct, "cold": pct}

    # --- fluid names ---
    hot_fluid_name: Optional[str] = None
    cold_fluid_name: Optional[str] = None

    # --- pressures (Pa) ---
    P_hot_Pa: Optional[float] = None
    P_cold_Pa: Optional[float] = None

    # --- fluid properties (populated by Step 3) ---
    hot_fluid_props: Optional[FluidProperties] = None
    cold_fluid_props: Optional[FluidProperties] = None

    # --- phase regime (populated by Step 3) ---
    # Declared phase regime for each stream
    hot_phase: Optional[str] = None    # "liquid" | "vapor" | "condensing" | "evaporating"
    cold_phase: Optional[str] = None   # "liquid" | "vapor" | "condensing" | "evaporating"
    # Number of increments for incremental (zone-based) calculation
    n_increments: Optional[int] = None
    # Per-segment results for incremental calculation
    increment_results: list[IncrementResult] = Field(default_factory=list)
    # P2-18 — per-side μ variation: {"hot": {"mu_ratio": ..., ...}, "cold": {...}}
    viscosity_variation: Optional[dict] = None

    # --- geometry (populated by Step 4+) ---
    geometry: Optional[GeometrySpec] = None

    # --- multi-shell arrangement (set by user response to Step 6 escalation) ---
    # "series"   — 2 shells in series, each handles full flow with full temperature program
    # "parallel" — 2 shells in parallel, each handles half the flow and half the duty
    # None       — single-shell design (default)
    multi_shell_arrangement: Optional[str] = None

    # --- mean temperatures (arithmetic mean of inlet/outlet, °C) ---
    T_mean_hot_C: Optional[float] = None
    T_mean_cold_C: Optional[float] = None

    # --- thermal results (populated by later steps) ---
    Q_W: Optional[float] = None
    LMTD_K: Optional[float] = None
    F_factor: Optional[float] = None
    U_W_m2K: Optional[float] = None
    A_m2: Optional[float] = None

    # --- area uncertainty band (FE-3, populated by Step 6 when tube-side ---
    # fluid source confidence < 0.80; None when confidence is sufficient) ---
    A_required_low_m2: Optional[float] = None
    A_required_high_m2: Optional[float] = None

    # --- tube-side heat transfer (populated by Step 7) ---
    h_tube_W_m2K: Optional[float] = None
    tube_velocity_m_s: Optional[float] = None
    Re_tube: Optional[float] = None
    Pr_tube: Optional[float] = None
    Nu_tube: Optional[float] = None
    flow_regime_tube: Optional[str] = None   # "laminar" | "transition_low_turbulent" | "turbulent"

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
    # P2-18 — cross-method agreement reliability: 1.0 (normal) or 0.85 (viscous service)
    cross_method_agreement_weight: Optional[float] = None

    # --- tube material properties (resolved by Step 9) ---
    tube_material: Optional[str] = None
    k_wall_W_mK: Optional[float] = None
    k_wall_source: Optional[str] = None
    k_wall_confidence: Optional[float] = None

    # --- pressure drops (populated by Step 10) ---
    dP_tube_Pa: Optional[float] = None
    dP_shell_Pa: Optional[float] = None
    dP_tube_friction_Pa: Optional[float] = None
    dP_tube_minor_Pa: Optional[float] = None
    dP_tube_nozzle_Pa: Optional[float] = None
    dP_shell_crossflow_Pa: Optional[float] = None
    dP_shell_window_Pa: Optional[float] = None
    dP_shell_end_Pa: Optional[float] = None
    dP_shell_nozzle_Pa: Optional[float] = None
    Fb_prime_dP: Optional[float] = None
    FL_prime_dP: Optional[float] = None
    nozzle_id_tube_m: Optional[float] = None
    nozzle_id_shell_m: Optional[float] = None
    rho_v2_tube_nozzle: Optional[float] = None
    rho_v2_shell_nozzle: Optional[float] = None
    n_nozzles_tube: int = 1
    n_nozzles_shell: int = 1
    nozzle_auto_corrected_tube: bool = False
    nozzle_auto_corrected_shell: bool = False
    dP_shell_simplified_delaware_Pa: Optional[float] = None
    dP_shell_kern_Pa: Optional[float] = None
    dP_shell_bell_vs_kern_pct: Optional[float] = None
    # P2-25 — shell-side wall viscosity (basis ∈ {"computed","approx_bulk"})
    mu_s_wall_Pa_s: Optional[float] = None
    mu_s_wall_basis: Optional[str] = None
    mu_s_wall_fail_reason: Optional[str] = None

    # --- area + overdesign (populated by Step 11) ---
    area_required_m2: Optional[float] = None       # Q / (U_dirty × F × LMTD)
    area_provided_m2: Optional[float] = None       # π × d_o × L × N_t
    overdesign_pct: Optional[float] = None          # (A_provided - A_required) / A_required × 100
    A_estimated_vs_required_pct: Optional[float] = None  # (A_m2 - area_required_m2) / area_required_m2 × 100
    service_classification: Optional[str] = None   # P2-23: clean_utility / phase_change / standard_process / fouling_service
    overdesign_band_low: Optional[float] = None    # P2-23: lower AI-trigger bound for this service (%)
    overdesign_band_high: Optional[float] = None   # P2-23: upper AI-trigger bound for this service (%)
    fouling_paradox_severity: Optional[str] = None  # P2-24: None / "warn" / "escalate"

    # --- convergence loop tracking (populated by Step 12) ---
    convergence_iteration: Optional[int] = None       # Which iteration converged (None if not run yet)
    convergence_converged: Optional[bool] = None       # True = converged, False = hit max iterations
    convergence_max_iterations: int = 20               # Configurable max
    convergence_trajectory: list[dict] = Field(default_factory=list)
    convergence_restart_count: int = 0                 # How many structural restarts so far

    # --- vibration check (populated by Step 13) ---
    vibration_safe: Optional[bool] = None
    vibration_details: Optional[dict] = None

    # --- mechanical design check (populated by Step 14) ---
    tube_thickness_ok: Optional[bool] = None
    shell_thickness_ok: Optional[bool] = None
    expansion_mm: Optional[float] = None
    mechanical_details: Optional[dict] = None
    shell_material: Optional[str] = None

    # --- cost estimate (populated by Step 15) ---
    cost_usd: Optional[float] = None
    cost_breakdown: Optional[dict] = None

    # --- pipeline state ---
    current_step: int = 0
    completed_steps: list[int] = Field(default_factory=list)
    pipeline_status: str = "pending"  # "pending" | "running" | "completed" | "error" | "cancelled" | "terminated"
    step_records: list[StepRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    waiting_for_user: bool = False
    in_convergence_loop: bool = False
    is_complete: bool = False

    # --- pipeline termination (set when user chooses to stop the design) ---
    # Populated when the user's escalation response signals that this design
    # path should be abandoned (e.g. "flag as impractical", "terminate").
    termination_reason: Optional[str] = None

    # --- AI cross-step observations (populated by base.py after each review) ---
    # Each entry is a short note from the AI engineer, forwarded to downstream
    # steps so the reviewer can reason across multiple steps.
    review_notes: list[str] = Field(default_factory=list)

    # --- Step 16: Final Validation ---
    confidence_score: Optional[float] = None
    confidence_breakdown: Optional[dict[str, float]] = None
    design_summary: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)

    # --- shell ID finalisation flag (FE-4) ---
    # False for floating-head types (AES/AEU) until Step 15 applies the
    # +50-75 mm clearance. True for fixed-tubesheet types (BEM, etc.) and
    # after Step 15 confirms the shell ID.
    shell_id_finalised: bool = False

    # P2-12 — Highly toxic service triggers double-tubesheet evaluation
    # in Step 14 (set by Step 4 allocator).
    requires_double_tubesheet_review: bool = False

    # --- design strengths / risks (FE-5, populated by Step 16) ---
    design_strengths: list[str] = Field(default_factory=list)
    design_risks: list[str] = Field(default_factory=list)

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

    # --- escalation history (per step) ---
    # Records what options the AI presented and what the user chose on each
    # escalation attempt. Injected into the AI prompt on re-escalation so the
    # AI generates different, more targeted options instead of repeating itself.
    # Format: { step_id: [{ "attempt": int, "options": [...], "user_chose": str }, ...] }
    escalation_history: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)

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
