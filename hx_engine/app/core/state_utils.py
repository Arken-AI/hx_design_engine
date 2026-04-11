"""State utilities — shared helpers for DesignState manipulation.

Extracted from PipelineRunner so Step 12 (convergence loop) can reuse
the output-mapping logic without coupling to the pipeline orchestrator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState
    from hx_engine.app.models.step_result import StepResult


# Scalar field mapping: result.outputs key → DesignState attribute name.
_OUTPUT_FIELD_MAP: dict[str, str] = {
    "Q_W": "Q_W",
    "LMTD_K": "LMTD_K",
    "F_factor": "F_factor",
    "U_W_m2K": "U_W_m2K",
    "A_m2": "A_m2",
    "T_hot_in_C": "T_hot_in_C",
    "T_hot_out_C": "T_hot_out_C",
    "T_cold_in_C": "T_cold_in_C",
    "T_cold_out_C": "T_cold_out_C",
    "m_dot_hot_kg_s": "m_dot_hot_kg_s",
    "m_dot_cold_kg_s": "m_dot_cold_kg_s",
    "hot_fluid_name": "hot_fluid_name",
    "cold_fluid_name": "cold_fluid_name",
    "P_hot_Pa": "P_hot_Pa",
    "P_cold_Pa": "P_cold_Pa",
    "tema_type": "tema_type",
    "tema_class": "tema_class",
    "tema_preference": "tema_preference",
    "shell_side_fluid": "shell_side_fluid",
    "R_f_hot_m2KW": "R_f_hot_m2KW",
    "R_f_cold_m2KW": "R_f_cold_m2KW",
    "multi_shell_arrangement": "multi_shell_arrangement",
    "shell_id_finalised": "shell_id_finalised",
    "A_required_low_m2": "A_required_low_m2",
    "A_required_high_m2": "A_required_high_m2",
    "h_tube_W_m2K": "h_tube_W_m2K",
    "tube_velocity_m_s": "tube_velocity_m_s",
    "Re_tube": "Re_tube",
    "Pr_tube": "Pr_tube",
    "Nu_tube": "Nu_tube",
    "flow_regime_tube": "flow_regime_tube",
    "T_mean_hot_C": "T_mean_hot_C",
    "T_mean_cold_C": "T_mean_cold_C",
    # Step 8 shell-side HTC
    "h_shell_W_m2K": "h_shell_W_m2K",
    "Re_shell": "Re_shell",
    "shell_side_j_factors": "shell_side_j_factors",
    "h_shell_ideal_W_m2K": "h_shell_ideal_W_m2K",
    "h_shell_kern_W_m2K": "h_shell_kern_W_m2K",
    # Step 9 overall U
    "U_clean_W_m2K": "U_clean_W_m2K",
    "U_dirty_W_m2K": "U_dirty_W_m2K",
    "U_overall_W_m2K": "U_overall_W_m2K",
    "cleanliness_factor": "cleanliness_factor",
    "resistance_breakdown": "resistance_breakdown",
    "controlling_resistance": "controlling_resistance",
    "tube_material": "tube_material",
    "k_wall_W_mK": "k_wall_W_mK",
    "k_wall_source": "k_wall_source",
    "k_wall_confidence": "k_wall_confidence",
    "U_kern_W_m2K": "U_kern_W_m2K",
    "U_kern_deviation_pct": "U_kern_deviation_pct",
    "U_vs_estimated_deviation_pct": "U_vs_estimated_deviation_pct",
    # Step 10 pressure drops
    "dP_tube_Pa": "dP_tube_Pa",
    "dP_shell_Pa": "dP_shell_Pa",
    "dP_tube_friction_Pa": "dP_tube_friction_Pa",
    "dP_tube_minor_Pa": "dP_tube_minor_Pa",
    "dP_tube_nozzle_Pa": "dP_tube_nozzle_Pa",
    "dP_shell_crossflow_Pa": "dP_shell_crossflow_Pa",
    "dP_shell_window_Pa": "dP_shell_window_Pa",
    "dP_shell_end_Pa": "dP_shell_end_Pa",
    "dP_shell_nozzle_Pa": "dP_shell_nozzle_Pa",
    "Fb_prime_dP": "Fb_prime_dP",
    "FL_prime_dP": "FL_prime_dP",
    "nozzle_id_tube_m": "nozzle_id_tube_m",
    "nozzle_id_shell_m": "nozzle_id_shell_m",
    "rho_v2_tube_nozzle": "rho_v2_tube_nozzle",
    "rho_v2_shell_nozzle": "rho_v2_shell_nozzle",
    "dP_shell_simplified_delaware_Pa": "dP_shell_simplified_delaware_Pa",
    "dP_shell_kern_Pa": "dP_shell_kern_Pa",
    "dP_shell_bell_vs_kern_pct": "dP_shell_bell_vs_kern_pct",
    # Step 11 area + overdesign
    "area_required_m2": "area_required_m2",
    "area_provided_m2": "area_provided_m2",
    "overdesign_pct": "overdesign_pct",
    "A_estimated_vs_required_pct": "A_estimated_vs_required_pct",
    # Step 12 convergence tracking
    "convergence_iteration": "convergence_iteration",
    "convergence_converged": "convergence_converged",
    "convergence_restart_count": "convergence_restart_count",
    # Step 13 vibration check
    "vibration_safe": "vibration_safe",
    "vibration_details": "vibration_details",
    # Step 16 final validation
    "confidence_score": "confidence_score",
    "confidence_breakdown": "confidence_breakdown",
    "design_summary": "design_summary",
    "assumptions": "assumptions",
    "design_strengths": "design_strengths",
    "design_risks": "design_risks",
}


def apply_outputs(state: "DesignState", result: "StepResult") -> None:
    """Apply step ``result.outputs`` to ``DesignState`` fields.

    Handles scalar fields via ``_OUTPUT_FIELD_MAP``, plus nested
    FluidProperties and GeometrySpec objects.
    """
    for out_key, state_field in _OUTPUT_FIELD_MAP.items():
        if out_key in result.outputs:
            setattr(state, state_field, result.outputs[out_key])

    # FluidProperties (nested)
    if "hot_fluid_props" in result.outputs:
        from hx_engine.app.models.design_state import FluidProperties
        val = result.outputs["hot_fluid_props"]
        if isinstance(val, dict):
            state.hot_fluid_props = FluidProperties(**val)
        elif isinstance(val, FluidProperties):
            state.hot_fluid_props = val

    if "cold_fluid_props" in result.outputs:
        from hx_engine.app.models.design_state import FluidProperties
        val = result.outputs["cold_fluid_props"]
        if isinstance(val, dict):
            state.cold_fluid_props = FluidProperties(**val)
        elif isinstance(val, FluidProperties):
            state.cold_fluid_props = val

    # Geometry (nested)
    if "geometry" in result.outputs:
        from hx_engine.app.models.design_state import GeometrySpec
        val = result.outputs["geometry"]
        if isinstance(val, dict):
            state.geometry = GeometrySpec(**val)
        elif isinstance(val, GeometrySpec):
            state.geometry = val
