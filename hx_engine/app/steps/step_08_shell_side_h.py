"""Step 08 — Shell-Side Heat Transfer Coefficient (Bell-Delaware).

Computes shell-side HTC using the full Bell-Delaware method (Taborek, 1983)
with five correction factors (J_c, J_l, J_b, J_s, J_r). Includes a
wall-temperature iteration for viscosity correction and a Kern cross-check
for divergence validation.

ai_mode = FULL — AI is always called (most complex calculation in pipeline).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from hx_engine.app.adapters.thermo_adapter import get_fluid_properties
from hx_engine.app.correlations.bell_delaware import (
    kern_shell_side_htc,
    shell_side_htc,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.tema_tables import get_tema_clearances
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_08_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# Max wall temperature iterations
_MAX_WALL_TEMP_ITERATIONS = 3
_WALL_TEMP_CONVERGENCE_PCT = 1.0  # |Δh_o| < 1%


class Step08ShellSideH(BaseStep):
    """Step 8: Shell-side heat transfer coefficient (Bell-Delaware)."""

    step_id: int = 8
    step_name: str = "Shell-Side Heat Transfer Coefficient"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Return list of missing fields required from Steps 1–7."""
        missing: list[str] = []

        # Fluid allocation (Step 4)
        if state.shell_side_fluid is None:
            missing.append("shell_side_fluid")

        # Temperatures (Step 1/2)
        for field in ("T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C"):
            if getattr(state, field) is None:
                missing.append(field)

        # Fluid names (Step 1)
        if state.hot_fluid_name is None:
            missing.append("hot_fluid_name")
        if state.cold_fluid_name is None:
            missing.append("cold_fluid_name")

        # Flow rates (Step 1/2)
        if state.m_dot_hot_kg_s is None:
            missing.append("m_dot_hot_kg_s")
        if state.m_dot_cold_kg_s is None:
            missing.append("m_dot_cold_kg_s")

        # Geometry (Step 4/6)
        if state.geometry is None:
            missing.append("geometry")
        else:
            g = state.geometry
            if g.shell_diameter_m is None:
                missing.append("geometry.shell_diameter_m")
            if g.tube_od_m is None:
                missing.append("geometry.tube_od_m")
            if g.tube_id_m is None:
                missing.append("geometry.tube_id_m")
            if g.baffle_spacing_m is None:
                missing.append("geometry.baffle_spacing_m")
            if g.pitch_ratio is None:
                missing.append("geometry.pitch_ratio")
            if g.baffle_cut is None:
                missing.append("geometry.baffle_cut")
            if g.n_tubes is None:
                missing.append("geometry.n_tubes")
            if g.n_passes is None:
                missing.append("geometry.n_passes")
            if g.pitch_layout is None:
                missing.append("geometry.pitch_layout")
            if g.tube_length_m is None:
                missing.append("geometry.tube_length_m")

        # Fluid properties (Step 3)
        if state.hot_fluid_props is None:
            missing.append("hot_fluid_props")
        if state.cold_fluid_props is None:
            missing.append("cold_fluid_props")

        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute shell-side heat transfer coefficient."""

        # 1. Pre-condition checks
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                8,
                f"Step 8 requires the following from Steps 1-7: "
                f"{', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Identify shell-side fluid
        shell_side = state.shell_side_fluid  # "hot" or "cold"
        tube_side = "cold" if shell_side == "hot" else "hot"

        if shell_side == "hot":
            m_dot = state.m_dot_hot_kg_s
            fluid_props = state.hot_fluid_props
            fluid_name = state.hot_fluid_name
            T_shell_in = state.T_hot_in_C
            T_shell_out = state.T_hot_out_C
            T_tube_in = state.T_cold_in_C
            T_tube_out = state.T_cold_out_C
            pressure_Pa = state.P_hot_Pa
        else:
            m_dot = state.m_dot_cold_kg_s
            fluid_props = state.cold_fluid_props
            fluid_name = state.cold_fluid_name
            T_shell_in = state.T_cold_in_C
            T_shell_out = state.T_cold_out_C
            T_tube_in = state.T_hot_in_C
            T_tube_out = state.T_hot_out_C
            pressure_Pa = state.P_cold_Pa

        # 3. Mean temperatures
        T_mean_shell = (T_shell_in + T_shell_out) / 2.0
        T_mean_tube = (T_tube_in + T_tube_out) / 2.0

        # 4. Extract geometry
        g = state.geometry
        shell_id_m = g.shell_diameter_m
        tube_od_m = g.tube_od_m
        tube_id_m = g.tube_id_m
        n_tubes = g.n_tubes
        n_passes = g.n_passes
        tube_length_m = g.tube_length_m
        baffle_spacing_m = g.baffle_spacing_m
        pitch_ratio = g.pitch_ratio
        baffle_cut_pct = g.baffle_cut * 100.0  # GeometrySpec stores as fraction, BD needs %

        # Pitch layout → angle
        layout_angle_deg = 30 if g.pitch_layout == "triangular" else 90

        # Absolute tube pitch
        tube_pitch_m = g.tube_pitch_m
        if tube_pitch_m is None:
            tube_pitch_m = pitch_ratio * tube_od_m

        # Bell-Delaware optional fields with fallbacks
        inlet_baffle_spacing = g.inlet_baffle_spacing_m or baffle_spacing_m
        outlet_baffle_spacing = g.outlet_baffle_spacing_m or baffle_spacing_m
        n_sealing_strip_pairs = g.n_sealing_strip_pairs or 0

        # Number of baffles (compute if not provided)
        n_baffles = g.n_baffles
        if n_baffles is None:
            n_baffles = max(1, int(
                (tube_length_m - inlet_baffle_spacing - outlet_baffle_spacing)
                / baffle_spacing_m
            ) + 1)

        # 5. TEMA clearances
        clearances = get_tema_clearances(shell_id_m)
        delta_tb_m = clearances["delta_tb_m"]
        delta_sb_m = clearances["delta_sb_m"]
        # Bundle-to-shell diametral clearance (TEMA approximation)
        # For fixed tubesheet: ~10-12mm; for floating head: ~30-50mm
        # Use a standard approximation based on shell size
        delta_bundle_shell_m = 0.010 + 0.002 * (shell_id_m - 0.2)
        delta_bundle_shell_m = max(0.008, min(0.050, delta_bundle_shell_m))

        # 6. Fluid properties at bulk
        rho = fluid_props.density_kg_m3
        mu = fluid_props.viscosity_Pa_s
        Cp = fluid_props.cp_J_kgK
        k = fluid_props.k_W_mK
        Pr = fluid_props.Pr

        # 7. Wall temperature iteration
        T_wall_est = (T_mean_shell + T_mean_tube) / 2.0
        mu_wall = mu  # initial estimate

        try:
            wall_props = get_fluid_properties(fluid_name, T_wall_est, pressure_Pa)
            mu_wall = wall_props.viscosity_Pa_s
        except Exception:
            warnings.append(
                f"Could not retrieve wall properties at T_wall≈{T_wall_est:.1f}°C "
                f"for {fluid_name}; using bulk viscosity for wall correction"
            )

        # First Bell-Delaware computation
        bd_result = shell_side_htc(
            shell_id_m=shell_id_m,
            tube_od_m=tube_od_m,
            tube_pitch_m=tube_pitch_m,
            layout_angle_deg=layout_angle_deg,
            n_tubes=n_tubes,
            tube_passes=n_passes,
            baffle_cut_pct=baffle_cut_pct,
            baffle_spacing_central_m=baffle_spacing_m,
            baffle_spacing_inlet_m=inlet_baffle_spacing,
            baffle_spacing_outlet_m=outlet_baffle_spacing,
            n_baffles=n_baffles,
            n_sealing_strip_pairs=n_sealing_strip_pairs,
            delta_tb_m=delta_tb_m,
            delta_sb_m=delta_sb_m,
            delta_bundle_shell_m=delta_bundle_shell_m,
            density_kg_m3=rho,
            viscosity_Pa_s=mu,
            viscosity_wall_Pa_s=mu_wall,
            Cp_J_kgK=Cp,
            k_W_mK=k,
            Pr=Pr,
            mass_flow_kg_s=m_dot,
            pitch_ratio=pitch_ratio,
        )

        # Iterate on wall temperature (2-3 passes)
        h_o_prev = bd_result["h_o_W_m2K"]
        A_shell = math.pi * tube_od_m * tube_length_m * n_tubes
        Q = state.Q_W if state.Q_W else (m_dot * Cp * abs(T_shell_in - T_shell_out))

        for iteration in range(1, _MAX_WALL_TEMP_ITERATIONS):
            # Recompute T_wall from heat balance
            if A_shell > 0 and h_o_prev > 0:
                q_local = Q / A_shell
                if shell_side == "hot":
                    T_wall_new = T_mean_shell - q_local / h_o_prev
                else:
                    T_wall_new = T_mean_shell + q_local / h_o_prev
            else:
                break

            # Get new mu_wall
            try:
                wall_props_new = get_fluid_properties(
                    fluid_name, T_wall_new, pressure_Pa,
                )
                mu_wall_new = wall_props_new.viscosity_Pa_s
            except Exception:
                warnings.append(
                    f"Wall temp iteration {iteration}: could not get props "
                    f"at T_wall={T_wall_new:.1f}°C — stopping iteration"
                )
                break

            # Recompute h_o
            bd_result_new = shell_side_htc(
                shell_id_m=shell_id_m,
                tube_od_m=tube_od_m,
                tube_pitch_m=tube_pitch_m,
                layout_angle_deg=layout_angle_deg,
                n_tubes=n_tubes,
                tube_passes=n_passes,
                baffle_cut_pct=baffle_cut_pct,
                baffle_spacing_central_m=baffle_spacing_m,
                baffle_spacing_inlet_m=inlet_baffle_spacing,
                baffle_spacing_outlet_m=outlet_baffle_spacing,
                n_baffles=n_baffles,
                n_sealing_strip_pairs=n_sealing_strip_pairs,
                delta_tb_m=delta_tb_m,
                delta_sb_m=delta_sb_m,
                delta_bundle_shell_m=delta_bundle_shell_m,
                density_kg_m3=rho,
                viscosity_Pa_s=mu,
                viscosity_wall_Pa_s=mu_wall_new,
                Cp_J_kgK=Cp,
                k_W_mK=k,
                Pr=Pr,
                mass_flow_kg_s=m_dot,
                pitch_ratio=pitch_ratio,
            )

            h_o_new = bd_result_new["h_o_W_m2K"]

            # Check convergence
            if h_o_prev > 0:
                delta_pct = abs(h_o_new - h_o_prev) / h_o_prev * 100.0
                if delta_pct < _WALL_TEMP_CONVERGENCE_PCT:
                    bd_result = bd_result_new
                    mu_wall = mu_wall_new
                    T_wall_est = T_wall_new
                    logger.info(
                        "Wall temp converged at iteration %d (Δh=%.2f%%)",
                        iteration, delta_pct,
                    )
                    break

            bd_result = bd_result_new
            mu_wall = mu_wall_new
            T_wall_est = T_wall_new
            h_o_prev = h_o_new

        # Collect BD warnings
        warnings.extend(bd_result.get("warnings", []))

        # 8. Kern cross-check
        kern_result: dict | None = None
        kern_divergence_pct: float | None = None
        try:
            kern_result = kern_shell_side_htc(
                shell_id_m=shell_id_m,
                tube_od_m=tube_od_m,
                tube_pitch_m=tube_pitch_m,
                pitch_layout=g.pitch_layout,
                baffle_spacing_m=baffle_spacing_m,
                viscosity_Pa_s=mu,
                viscosity_wall_Pa_s=mu_wall,
                Cp_J_kgK=Cp,
                k_W_mK=k,
                mass_flow_kg_s=m_dot,
            )
            h_kern = kern_result["h_o_kern_W_m2K"]
            h_bd = bd_result["h_o_W_m2K"]
            if h_kern > 0:
                kern_divergence_pct = abs(h_bd - h_kern) / h_kern * 100.0
                if kern_divergence_pct > 50.0:
                    warnings.append(
                        f"Bell-Delaware / Kern divergence = {kern_divergence_pct:.1f}% "
                        f"(BD={h_bd:.1f}, Kern={h_kern:.1f}) — ESCALATE"
                    )
                elif kern_divergence_pct > 20.0:
                    warnings.append(
                        f"Bell-Delaware / Kern divergence = {kern_divergence_pct:.1f}% "
                        f"(BD={h_bd:.1f}, Kern={h_kern:.1f}) — review recommended"
                    )
        except Exception as exc:
            warnings.append(f"Kern cross-check failed: {exc}")

        # 9. Write to state
        state.h_shell_W_m2K = bd_result["h_o_W_m2K"]
        state.Re_shell = bd_result["Re_shell"]
        state.h_shell_ideal_W_m2K = bd_result["h_ideal_W_m2K"]
        state.shell_side_j_factors = {
            "J_c": bd_result["J_c"],
            "J_l": bd_result["J_l"],
            "J_b": bd_result["J_b"],
            "J_s": bd_result["J_s"],
            "J_r": bd_result["J_r"],
            "product": bd_result["J_product"],
        }
        state.h_shell_kern_W_m2K = (
            kern_result["h_o_kern_W_m2K"] if kern_result else None
        )

        # 10. Build outputs dict
        outputs: dict = {
            "h_shell_W_m2K": bd_result["h_o_W_m2K"],
            "h_shell_ideal_W_m2K": bd_result["h_ideal_W_m2K"],
            "Re_shell": bd_result["Re_shell"],
            "G_s_kg_m2s": bd_result["G_s_kg_m2s"],
            "j_i": bd_result["j_i"],
            "visc_correction": bd_result["visc_correction"],
            "J_c": bd_result["J_c"],
            "J_l": bd_result["J_l"],
            "J_b": bd_result["J_b"],
            "J_s": bd_result["J_s"],
            "J_r": bd_result["J_r"],
            "J_product": bd_result["J_product"],
            "T_wall_estimated_C": T_wall_est,
            "mu_wall_Pa_s": mu_wall,
            "n_baffles_used": n_baffles,
            "layout_angle_deg": layout_angle_deg,
            "method": "bell_delaware",
        }

        if kern_result:
            outputs["h_shell_kern_W_m2K"] = kern_result["h_o_kern_W_m2K"]
            outputs["Re_kern"] = kern_result["Re_kern"]
            outputs["kern_divergence_pct"] = kern_divergence_pct

        # 11. Escalation hints
        escalation_hints: list[dict] = []
        if kern_divergence_pct is not None and kern_divergence_pct > 20.0:
            escalation_hints.append({
                "trigger": "kern_divergence",
                "recommendation": (
                    f"Bell-Delaware / Kern divergence is {kern_divergence_pct:.1f}%. "
                    f"Review shell-side geometry and clearances."
                ),
            })
        if bd_result["J_product"] < 0.35:
            escalation_hints.append({
                "trigger": "low_j_product",
                "recommendation": (
                    f"J-factor product = {bd_result['J_product']:.3f} is low. "
                    f"Consider reducing baffle clearances or adding sealing strips."
                ),
            })
        if bd_result["h_o_W_m2K"] < 100:
            escalation_hints.append({
                "trigger": "low_h_shell",
                "recommendation": (
                    f"h_shell = {bd_result['h_o_W_m2K']:.1f} W/m²K is very low. "
                    f"Check fluid properties and geometry."
                ),
            })
        if escalation_hints:
            outputs["escalation_hints"] = escalation_hints

        # 12. Return StepResult
        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )
