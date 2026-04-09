"""Step 13 — Flow-Induced Vibration Check (TEMA Section 6).

Safety-critical post-convergence check. Evaluates 4 vibration mechanisms
across 3 span locations (inlet, central, outlet). Determines whether the
converged geometry can operate safely without tube damage from:

  1. Fluidelastic instability (V-10) — velocity ratio < 0.5
  2. Vortex shedding (V-11.2) — amplitude ≤ 2% of tube OD
  3. Turbulent buffeting (V-11.3) — amplitude ≤ 2% of tube OD
  4. Acoustic resonance (V-12) — gas service only

ai_mode = FULL — always reviewed (safety-critical), but skipped
inside convergence loop.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hx_engine.app.correlations.tema_vibration import check_all_spans
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.material_properties import (
    get_density,
    get_elastic_modulus,
    get_poisson,
)
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_13_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# Default tube material when state.tube_material is not set
_DEFAULT_MATERIAL = "carbon_steel"


class Step13VibrationCheck(BaseStep):
    """Step 13: Flow-Induced Vibration Check."""

    step_id: int = 13
    step_name: str = "Vibration Check"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    # ------------------------------------------------------------------
    # AI call decision
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        if state.in_convergence_loop:
            return False
        return True  # FULL mode — always call AI (safety-critical)

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []

        # Must have converged geometry
        if state.convergence_converged is None:
            missing.append("convergence_converged (Step 12)")

        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            g = state.geometry
            for attr in (
                "tube_od_m", "tube_id_m", "tube_pitch_m",
                "shell_diameter_m", "baffle_spacing_m",
                "baffle_cut", "n_baffles", "pitch_ratio",
            ):
                if getattr(g, attr, None) is None:
                    missing.append(f"geometry.{attr}")

        if state.shell_side_fluid is None:
            missing.append("shell_side_fluid (Step 4)")

        # Fluid properties
        if state.hot_fluid_props is None:
            missing.append("hot_fluid_props (Step 3)")
        if state.cold_fluid_props is None:
            missing.append("cold_fluid_props (Step 3)")

        # Flow rates
        if state.m_dot_hot_kg_s is None:
            missing.append("m_dot_hot_kg_s (Step 1)")
        if state.m_dot_cold_kg_s is None:
            missing.append("m_dot_cold_kg_s (Step 1)")

        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Run TEMA Section 6 vibration analysis."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                13,
                f"Step 13 requires: {', '.join(missing)}",
            )

        g = state.geometry
        warnings: list[str] = []

        # 2. Resolve material properties
        mat_key = state.tube_material or _DEFAULT_MATERIAL
        try:
            # Use tube-side mean temperature for E(T) lookup
            T_tube_C = state.T_mean_cold_C or state.T_mean_hot_C or 100.0
            E_Pa = get_elastic_modulus(mat_key, T_tube_C)
            rho_metal = get_density(mat_key)
        except KeyError:
            # Fall back to carbon steel defaults
            warnings.append(
                f"Unknown tube material '{mat_key}' — using carbon steel defaults"
            )
            mat_key = _DEFAULT_MATERIAL
            T_tube_C = state.T_mean_cold_C or state.T_mean_hot_C or 100.0
            E_Pa = get_elastic_modulus(mat_key, T_tube_C)
            rho_metal = get_density(mat_key)

        # 3. Resolve shell-side fluid properties
        shell_props = (
            state.hot_fluid_props
            if state.shell_side_fluid == "hot"
            else state.cold_fluid_props
        )
        tube_props = (
            state.cold_fluid_props
            if state.shell_side_fluid == "hot"
            else state.hot_fluid_props
        )
        shell_flow = (
            state.m_dot_hot_kg_s
            if state.shell_side_fluid == "hot"
            else state.m_dot_cold_kg_s
        )

        # 4. Determine pitch angle
        pitch_angle = g.get_pitch_angle()

        # 5. Determine baffle thickness
        baffle_thickness = g.get_baffle_thickness()

        # 6. OTL — use state value or estimate
        otl_m = getattr(g, "otl_m", None)
        if otl_m is None:
            # Estimate OTL from shell ID and TEMA clearances
            from hx_engine.app.data.tema_tables import get_tema_clearances
            clearances = get_tema_clearances(g.shell_diameter_m)
            delta_sb = clearances.get("delta_sb_m", 0.003)
            otl_m = g.shell_diameter_m - 2 * delta_sb

        # 7. Determine if gas service (simple heuristic: density < 50 kg/m³)
        is_gas = shell_props.density_kg_m3 < 50.0

        # 8. Run the full vibration analysis
        result = check_all_spans(
            tube_od_m=g.tube_od_m,
            tube_id_m=g.tube_id_m,
            tube_pitch_m=g.tube_pitch_m,
            shell_id_m=g.shell_diameter_m,
            baffle_spacing_m=g.baffle_spacing_m,
            inlet_baffle_spacing_m=getattr(g, "inlet_baffle_spacing_m", None),
            outlet_baffle_spacing_m=getattr(g, "outlet_baffle_spacing_m", None),
            baffle_cut=g.baffle_cut,
            baffle_thickness_m=baffle_thickness,
            n_baffles=g.n_baffles,
            pitch_angle_deg=pitch_angle,
            pitch_ratio=g.pitch_ratio,
            n_sealing_strip_pairs=getattr(g, "n_sealing_strip_pairs", 0),
            otl_m=otl_m,
            E_Pa=E_Pa,
            rho_metal_kg_m3=rho_metal,
            rho_shell_kg_m3=shell_props.density_kg_m3,
            mu_shell_Pa_s=shell_props.viscosity_Pa_s,
            rho_tube_fluid_kg_m3=tube_props.density_kg_m3,
            shell_flow_kg_s=shell_flow,
            is_gas=is_gas,
            P_shell_Pa=getattr(state, "P_shell_Pa", None),
            gamma=getattr(state, "gamma_shell", None),
        )

        # 9. Generate warnings
        if not result["all_safe"]:
            warnings.append(
                f"VIBRATION UNSAFE — controlling mechanism: "
                f"{result['controlling_mechanism']}, "
                f"worst velocity ratio = {result['worst_velocity_ratio']:.3f} "
                f"(limit 0.5)"
            )
        else:
            margin = result["velocity_margin_pct"]
            if margin < 20:
                warnings.append(
                    f"Vibration margin is tight: velocity ratio margin = {margin:.1f}%"
                )

        # 10. Write to state
        state.vibration_safe = result["all_safe"]
        state.vibration_details = {
            "controlling_mechanism": result["controlling_mechanism"],
            "critical_span": result["critical_span"],
            "worst_velocity_ratio": result["worst_velocity_ratio"],
            "worst_amplitude_ratio": result["worst_amplitude_ratio"],
            "velocity_margin_pct": result["velocity_margin_pct"],
            "amplitude_margin_pct": result["amplitude_margin_pct"],
            "tube_material": mat_key,
            "E_Pa": E_Pa,
            "spans": result["spans"],
            "tube_properties": result["tube_properties"],
            "crossflow_velocity": result["crossflow_velocity"],
            "acoustic_resonance": result["acoustic_resonance"],
        }

        # 11. Build outputs
        outputs = {
            "vibration_safe": result["all_safe"],
            "vibration_details": state.vibration_details,
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )
