"""Step 08 — Shell-Side Heat Transfer Coefficient (Bell-Delaware / Shah).

Computes shell-side HTC using:
- Bell-Delaware method (Taborek, 1983) for single-phase (liquid or gas)
- Shah (1979) condensation correlation for condensing service

Includes wall-temperature iteration for viscosity correction and a
Kern cross-check for divergence validation (single-phase only).

ai_mode = FULL — AI is always called (most complex calculation in pipeline).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from hx_engine.app.adapters.thermo_adapter import (
    get_fluid_properties,
    get_saturation_props,
)
from hx_engine.app.correlations.bell_delaware import (
    kern_shell_side_htc,
    shell_side_htc,
)
from hx_engine.app.correlations.shah_condensation import (
    get_critical_pressure,
    shah_condensation_average_h,
    shah_condensation_h,
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

        # ── Phase-aware branch ─────────────────────────────────────────
        shell_phase = (
            getattr(state, "hot_phase", None) if shell_side == "hot"
            else getattr(state, "cold_phase", None)
        ) or "liquid"

        if shell_phase == "condensing":
            return await self._execute_condensing(
                state, shell_side, fluid_name, fluid_props,
                m_dot, T_shell_in, T_shell_out, T_tube_in, T_tube_out,
                pressure_Pa, g, tube_od_m, tube_id_m, tube_pitch_m,
                n_tubes, tube_length_m, warnings,
            )

        # ── Single-phase path (liquid or gas) ─────────────────────────

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
            wall_props = await get_fluid_properties(fluid_name, T_wall_est, pressure_Pa)
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
                wall_props_new = await get_fluid_properties(
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
                # Kern (1950) systematically underpredicts vs Bell-Delaware
                # by 40-60% for turbulent liquid flows — this is well-documented
                # (Serth 2007, Thulukkanam 2013). Only flag truly anomalous
                # divergence (>200%) or when both methods disagree on direction.
                if kern_divergence_pct > 200.0:
                    warnings.append(
                        f"Bell-Delaware / Kern divergence = {kern_divergence_pct:.1f}% "
                        f"(BD={h_bd:.1f}, Kern={h_kern:.1f}) — ESCALATE: "
                        f"extreme divergence suggests geometry or property error"
                    )
                elif kern_divergence_pct > 100.0:
                    warnings.append(
                        f"Bell-Delaware / Kern divergence = {kern_divergence_pct:.1f}% "
                        f"(BD={h_bd:.1f}, Kern={h_kern:.1f}) — "
                        f"within expected range for Kern vs BD (Kern underpredicts "
                        f"40-60% for turbulent flows)"
                    )
        except ValueError as exc:
            # Kern correlation raised for invalid Re range (laminar/transitional)
            warnings.append(
                f"Kern cross-check suppressed: {exc} "
                f"Bell-Delaware (h_shell={bd_result['h_o_W_m2K']:.1f} W/m²K) is the sole result."
            )
        except Exception as exc:
            warnings.append(f"Kern cross-check failed: {exc}")

        # 9. Persist derived geometry back to state so downstream steps
        #    (Step 10 pressure drops, Step 12 convergence, Step 13 vibration)
        #    can read tube_pitch_m and n_baffles from state.geometry.
        if g.tube_pitch_m is None:
            g.tube_pitch_m = tube_pitch_m
        if g.n_baffles is None:
            g.n_baffles = n_baffles

        # 10. Write thermal results to state
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
        if kern_divergence_pct is not None and kern_divergence_pct > 200.0:
            escalation_hints.append({
                "trigger": "kern_divergence",
                "recommendation": (
                    f"Bell-Delaware / Kern divergence is {kern_divergence_pct:.1f}% "
                    f"(extreme). Review shell-side geometry and fluid properties."
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

    # ------------------------------------------------------------------
    # Condensation path (Shah correlation)
    # ------------------------------------------------------------------

    async def _execute_condensing(
        self,
        state: "DesignState",
        shell_side: str,
        fluid_name: str,
        fluid_props,
        m_dot: float,
        T_shell_in: float,
        T_shell_out: float,
        T_tube_in: float,
        T_tube_out: float,
        pressure_Pa: float | None,
        g,
        tube_od_m: float,
        tube_id_m: float,
        tube_pitch_m: float,
        n_tubes: int,
        tube_length_m: float,
        warnings: list[str],
    ) -> StepResult:
        """Compute shell-side HTC for condensing service using Shah (1979).

        For shell-side condensation in a horizontal shell-and-tube HX, the
        condensation occurs on the outside of the tubes. The Shah correlation
        is applied using the tube OD as the characteristic diameter.
        """
        P_eff = pressure_Pa or 101_325.0

        # Get saturation properties
        try:
            sat = get_saturation_props(fluid_name, P_eff)
        except CalculationError as exc:
            raise CalculationError(
                8,
                f"Cannot obtain saturation properties for '{fluid_name}' "
                f"at P={P_eff} Pa for condensation calculation: {exc.message}",
                cause=exc,
            ) from exc

        # Get critical pressure
        P_crit = get_critical_pressure(fluid_name)
        if P_crit is None:
            # Fallback: try CoolProp
            try:
                import CoolProp.CoolProp as CP
                from hx_engine.app.adapters.thermo_adapter import _COOLPROP_MAP
                cp_name = _COOLPROP_MAP.get(fluid_name.strip().lower(), fluid_name)
                P_crit = CP.PropsSI("pcrit", cp_name)
            except Exception:
                # Use a generic estimate
                P_crit = P_eff / 0.05  # assume P_r ≈ 0.05
                warnings.append(
                    f"Critical pressure unknown for '{fluid_name}'; "
                    f"estimated P_crit={P_crit/1e6:.1f} MPa"
                )

        # Determine inlet/outlet quality
        # For condensation: inlet is vapor (x≈1.0), outlet is liquid (x≈0.0)
        T_sat = sat["T_sat_C"]
        x_in = 1.0
        x_out = 0.0

        # If inlet temp > T_sat, there's a desuperheating zone
        if T_shell_in > T_sat + 1.0:
            x_in = 1.0  # enters as superheated vapor, starts condensing at T_sat
            warnings.append(
                f"Shell-side fluid enters superheated at {T_shell_in:.1f}°C "
                f"(T_sat={T_sat:.1f}°C). Desuperheating zone exists."
            )

        # If outlet temp < T_sat, there's a subcooling zone
        if T_shell_out < T_sat - 1.0:
            x_out = 0.0
            warnings.append(
                f"Shell-side fluid exits subcooled at {T_shell_out:.1f}°C "
                f"(T_sat={T_sat:.1f}°C). Subcooling zone exists."
            )

        # Mass flux based on shell-side flow area
        # For shell-side condensation, use equivalent diameter
        # A_shell ≈ shell crossflow area approximation
        D_e = tube_od_m  # characteristic dimension for tube bundle
        A_shell_flow = math.pi / 4.0 * D_e ** 2 * n_tubes
        # Actually, mass flux for shell-side condensation on tube bundle
        # G = m_dot / (π × D_o × L × N_t) is not mass flux — that's area
        # G_shell = m_dot / A_crossflow
        # For shell-side, approximate crossflow area
        shell_id_m = g.shell_diameter_m
        baffle_spacing_m = g.baffle_spacing_m
        pitch_ratio = g.pitch_ratio

        # Crossflow area per Kern: A_s = D_s × l_B × (p - d_o) / p
        p_t = tube_pitch_m
        A_crossflow = shell_id_m * baffle_spacing_m * (p_t - tube_od_m) / p_t
        G_shell = m_dot / max(A_crossflow, 1e-6)

        # Shah condensation (using tube OD as characteristic diameter for
        # condensation on outside of tubes)
        shah_result = shah_condensation_average_h(
            G=G_shell,
            D_i=tube_od_m,  # OD is the condensation surface
            rho_l=sat["rho_f"],
            rho_g=sat["rho_g"],
            mu_l=sat["mu_f"],
            mu_g=sat["mu_g"],
            k_l=sat["k_f"],
            cp_l=sat["cp_f"],
            h_fg=sat["h_fg"],
            P_sat=P_eff,
            P_crit=P_crit,
            x_in=x_in,
            x_out=x_out,
        )

        h_shell = shah_result["h_avg"]
        warnings.extend(shah_result["warnings"])

        # ── Per-segment incremental results ───────────────────────
        # Divide condenser into n_increments segments by quality.
        # Each segment gets local h_shell, temperatures, LMTD, dQ.
        from hx_engine.app.models.design_state import IncrementResult

        n_inc = state.n_increments or 10
        dx = (x_in - x_out) / n_inc
        Q_total = state.Q_W or (m_dot * sat["h_fg"] * (x_in - x_out))
        dQ_per_seg = Q_total / n_inc
        h_tube = state.h_tube_W_m2K  # from Step 7 (single-phase tube side)

        # Cold side (tube) temperature range — counterflow arrangement
        T_cold_range = T_tube_out - T_tube_in
        increment_results: list[IncrementResult] = []

        for i in range(n_inc):
            x_seg_in = x_in - i * dx
            x_seg_out = x_in - (i + 1) * dx
            x_mid = (x_seg_in + x_seg_out) / 2.0

            # Local h_shell from Shah at midpoint quality
            local_shah = shah_condensation_h(
                x=x_mid, G=G_shell, D_i=tube_od_m,
                rho_l=sat["rho_f"], rho_g=sat["rho_g"],
                mu_l=sat["mu_f"], mu_g=sat["mu_g"],
                k_l=sat["k_f"], cp_l=sat["cp_f"],
                h_fg=sat["h_fg"], P_sat=P_eff, P_crit=P_crit,
            )
            h_shell_local = local_shah["h_cond"]

            # Hot side: constant at T_sat during condensation zone
            T_hot_seg = T_sat

            # Cold side: counterflow — segment 0 is at the hot-fluid inlet
            # (cold-fluid outlet), segment n-1 is at the hot-fluid outlet
            # (cold-fluid inlet). Cold temperature is linear with cumulative Q.
            frac_start = i / n_inc
            frac_end = (i + 1) / n_inc
            T_cold_seg_out = T_tube_out - frac_start * T_cold_range
            T_cold_seg_in = T_tube_out - frac_end * T_cold_range

            # Local LMTD for this segment
            dT1 = T_hot_seg - T_cold_seg_in   # larger ΔT (cold is colder)
            dT2 = T_hot_seg - T_cold_seg_out  # smaller ΔT (cold is hotter)

            if dT1 > 0 and dT2 > 0 and abs(dT1 - dT2) > 0.01:
                lmtd_local = (dT1 - dT2) / math.log(dT1 / dT2)
            elif dT1 > 0 and dT2 > 0:
                lmtd_local = (dT1 + dT2) / 2.0
            else:
                lmtd_local = max(abs(dT1), abs(dT2), 0.1)

            increment_results.append(IncrementResult(
                segment_index=i,
                T_hot_in_C=T_hot_seg,
                T_hot_out_C=T_hot_seg,
                T_cold_in_C=T_cold_seg_in,
                T_cold_out_C=T_cold_seg_out,
                quality_in=x_seg_in,
                quality_out=x_seg_out,
                phase="two_phase" if x_mid > 0.01 else "liquid",
                h_tube_W_m2K=h_tube,
                h_shell_W_m2K=h_shell_local,
                dQ_W=dQ_per_seg,
                LMTD_local_K=lmtd_local,
            ))

        state.increment_results = increment_results

        # Write to state
        state.h_shell_W_m2K = h_shell
        state.Re_shell = shah_result.get("Re_lo", G_shell * tube_od_m / sat["mu_f"])
        state.h_shell_ideal_W_m2K = h_shell  # No J-factor correction for condensation
        state.shell_side_j_factors = None
        state.h_shell_kern_W_m2K = None

        # Persist geometry
        if g.tube_pitch_m is None:
            g.tube_pitch_m = tube_pitch_m
        if g.n_baffles is None:
            inlet_bs = g.inlet_baffle_spacing_m or baffle_spacing_m
            outlet_bs = g.outlet_baffle_spacing_m or baffle_spacing_m
            g.n_baffles = max(1, int(
                (tube_length_m - inlet_bs - outlet_bs) / baffle_spacing_m
            ) + 1)

        outputs: dict = {
            "h_shell_W_m2K": h_shell,
            "h_shell_ideal_W_m2K": h_shell,
            "method": "shah_condensation",
            "x_in": x_in,
            "x_out": x_out,
            "T_sat_C": T_sat,
            "h_fg_J_kg": sat["h_fg"],
            "G_shell_kg_m2s": G_shell,
            "P_crit_Pa": P_crit,
            "Re_shell": state.Re_shell,
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )
