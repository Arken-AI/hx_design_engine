"""Step 10 — Pressure Drops (Tube-Side + Shell-Side).

Computes tube-side ΔP (Churchill friction + minor + nozzle losses) and
shell-side ΔP (Bell's method with F'_b, F'_L corrections) plus two
independent cross-checks (Kern, Simplified Delaware).

ai_mode = CONDITIONAL — AI called only when ΔP margin < 15% of hard
limit or cross-check divergence > 30%. Skipped in convergence loop.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from hx_engine.app.adapters.thermo_adapter import get_fluid_properties
from hx_engine.app.correlations.bell_delaware import (
    kern_shell_side_dP,
    shell_side_dP,
)
from hx_engine.app.correlations.churchill_friction import churchill_friction_factor
from hx_engine.app.correlations.simplified_delaware_dp import (
    simplified_delaware_shell_dP,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.nozzle_table import (
    get_default_nozzle_diameter_m,
    get_next_larger_nozzle_diameter_m,
    nozzle_dP_Pa,
    nozzle_rho_v_squared,
)
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_10_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# Hard limits (Pa)
_DP_TUBE_LIMIT_PA = 70_000.0   # 0.7 bar
_DP_SHELL_LIMIT_PA = 140_000.0  # 1.4 bar
_RHO_V2_LIMIT = 2230.0          # TEMA erosion limit kg/m·s²

# P2-25: bulk-viscosity threshold above which a missing wall μ is worth a WARN.
# Below this we silently fall back to bulk because the Sieder-Tate correction
# (μ_b/μ_w)^0.14 stays within ±2% of unity for water-like fluids regardless.
_MU_VISCOUS_THRESHOLD_PA_S = 0.01  # 10 cP


class Step10PressureDrops(BaseStep):
    """Step 10: Tube-side and shell-side pressure drops."""

    step_id: int = 10
    step_name: str = "Pressure Drops"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # AI call decision
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        if state.in_convergence_loop:
            return False
        return self._conditional_ai_trigger(state)

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Trigger AI when ΔP margin is tight or cross-checks diverge."""
        # Check after execute populates state
        if state.dP_tube_Pa is not None and state.dP_tube_Pa > 0.85 * _DP_TUBE_LIMIT_PA:
            return True
        if state.dP_shell_Pa is not None and state.dP_shell_Pa > 0.85 * _DP_SHELL_LIMIT_PA:
            return True
        if state.rho_v2_tube_nozzle is not None and state.rho_v2_tube_nozzle > 0.85 * _RHO_V2_LIMIT:
            return True
        if state.rho_v2_shell_nozzle is not None and state.rho_v2_shell_nozzle > 0.85 * _RHO_V2_LIMIT:
            return True
        if state.dP_shell_bell_vs_kern_pct is not None and state.dP_shell_bell_vs_kern_pct > 30:
            return True
        return False

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []

        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            g = state.geometry
            for attr in (
                "shell_diameter_m", "tube_od_m", "tube_id_m",
                "tube_length_m", "n_tubes", "tube_pitch_m",
                "pitch_ratio", "n_passes", "baffle_spacing_m",
                "baffle_cut", "n_baffles",
            ):
                if getattr(g, attr, None) is None:
                    missing.append(f"geometry.{attr}")

        if state.tube_velocity_m_s is None:
            missing.append("tube_velocity_m_s (Step 7)")
        if state.Re_tube is None:
            missing.append("Re_tube (Step 7)")
        if state.Re_shell is None:
            missing.append("Re_shell (Step 8)")
        if state.shell_side_fluid is None:
            missing.append("shell_side_fluid (Step 4)")
        if state.hot_fluid_props is None:
            missing.append("hot_fluid_props (Step 3)")
        if state.cold_fluid_props is None:
            missing.append("cold_fluid_props (Step 3)")
        if state.m_dot_hot_kg_s is None:
            missing.append("m_dot_hot_kg_s (Step 1)")
        if state.m_dot_cold_kg_s is None:
            missing.append("m_dot_cold_kg_s (Step 1)")

        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Pure calculation of tube-side and shell-side ΔP."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                10,
                f"Step 10 requires: {', '.join(missing)}",
            )

        warnings: list[str] = []
        g = state.geometry

        # ── 2. Resolve fluid sides ────────────────────────────────
        if state.shell_side_fluid == "hot":
            shell_props = state.hot_fluid_props
            tube_props = state.cold_fluid_props
            m_dot_shell = state.m_dot_hot_kg_s
            m_dot_tube = state.m_dot_cold_kg_s
        else:
            shell_props = state.cold_fluid_props
            tube_props = state.hot_fluid_props
            m_dot_shell = state.m_dot_cold_kg_s
            m_dot_tube = state.m_dot_hot_kg_s

        # Tube-side properties
        rho_t = tube_props.density_kg_m3
        mu_t = tube_props.viscosity_Pa_s
        Re_tube = state.Re_tube
        v_tube = state.tube_velocity_m_s

        # Shell-side properties
        rho_s = shell_props.density_kg_m3
        mu_s = shell_props.viscosity_Pa_s

        # Geometry
        d_i = g.tube_id_m
        d_o = g.tube_od_m
        L = g.tube_length_m
        n_tubes = g.n_tubes
        n_passes = g.n_passes
        n_baffles = g.n_baffles

        # ── 3. TUBE-SIDE PRESSURE DROP ────────────────────────────

        # 3a. Friction factor (Churchill — all regimes)
        f_darcy = churchill_friction_factor(Re_tube)

        # 3b. Friction loss
        # G_tube = m_dot_tube / (N_tubes/n_passes × A_tube)
        A_tube = math.pi / 4.0 * d_i ** 2
        tubes_per_pass = n_tubes / n_passes
        G_tube = m_dot_tube / (tubes_per_pass * A_tube)

        # ΔP_f = f × n_passes × L × G² / (2 × ρ × d_i)
        dP_tube_friction = f_darcy * n_passes * L * G_tube ** 2 / (2.0 * rho_t * d_i)

        # 3c. Minor losses (Serth Table 5.1)
        if Re_tube <= 500:
            alpha_r = 3.25 * n_passes - 1.5
        else:
            alpha_r = 2.0 * n_passes - 1.5
        alpha_r = max(alpha_r, 0.5)  # floor

        dP_tube_minor = alpha_r * rho_t * v_tube ** 2 / 2.0

        # 3d. Nozzle losses (tube-side)
        nozzle_id_tube = get_default_nozzle_diameter_m(g.shell_diameter_m)
        n_nozzles_tube = 1
        nozzle_auto_corrected_tube = False
        original_nozzle_id_tube = nozzle_id_tube

        # Inlet + outlet nozzle combined: K ≈ 1.0 each → 2 × nozzle_dP
        dP_tube_nozzle = 2.0 * nozzle_dP_Pa(m_dot_tube, rho_t, nozzle_id_tube, n_nozzles_tube)
        rho_v2_tube = nozzle_rho_v_squared(m_dot_tube, rho_t, nozzle_id_tube, n_nozzles_tube)

        # Auto-correct: upsize nozzle if ρv² exceeds TEMA limit
        if rho_v2_tube > _RHO_V2_LIMIT:
            # Strategy 1: try next larger Schedule 40 nozzle sizes
            candidate = nozzle_id_tube
            while rho_v2_tube > _RHO_V2_LIMIT:
                bigger = get_next_larger_nozzle_diameter_m(candidate)
                if bigger is None:
                    break  # exhausted single-nozzle sizes
                candidate = bigger
                rho_v2_tube = nozzle_rho_v_squared(m_dot_tube, rho_t, candidate, 1)

            if rho_v2_tube <= _RHO_V2_LIMIT:
                nozzle_id_tube = candidate
                nozzle_auto_corrected_tube = True
            else:
                # Strategy 2: use dual nozzles with the largest available size
                n_nozzles_tube = 2
                rho_v2_tube = nozzle_rho_v_squared(m_dot_tube, rho_t, candidate, n_nozzles_tube)
                nozzle_id_tube = candidate
                nozzle_auto_corrected_tube = True

            if nozzle_auto_corrected_tube:
                dP_tube_nozzle = 2.0 * nozzle_dP_Pa(m_dot_tube, rho_t, nozzle_id_tube, n_nozzles_tube)
                correction_desc = (
                    f"nozzle upsized {original_nozzle_id_tube*1000:.1f}→{nozzle_id_tube*1000:.1f} mm"
                )
                if n_nozzles_tube > 1:
                    correction_desc += f" × {n_nozzles_tube} nozzles"
                warnings.append(
                    f"Tube nozzle ρv² exceeded TEMA limit ({_RHO_V2_LIMIT:.0f} kg/m·s²) — "
                    f"auto-corrected: {correction_desc} "
                    f"(ρv² now {rho_v2_tube:.0f} kg/m·s²)"
                )

        # 3e. Total tube-side ΔP
        dP_tube_total = dP_tube_friction + dP_tube_minor + dP_tube_nozzle

        # ── 4. SHELL-SIDE PRESSURE DROP (Bell's Method) ──────────

        # TEMA clearances
        from hx_engine.app.data.tema_tables import get_tema_clearances
        clearances = get_tema_clearances(g.shell_diameter_m)
        delta_tb = clearances["delta_tb_m"]
        delta_sb = clearances["delta_sb_m"]

        # Bundle-to-shell clearance
        # For floating head: delta_bs ≈ 50–75 mm. Use D_s − D_otl estimate.
        delta_bs = g.shell_diameter_m * 0.05  # ~5% of shell ID as default

        # Inlet/outlet baffle spacing defaults
        L_i = getattr(g, "inlet_baffle_spacing_m", None) or g.baffle_spacing_m
        L_o = getattr(g, "outlet_baffle_spacing_m", None) or g.baffle_spacing_m

        # Number of sealing strip pairs
        N_ss = getattr(g, "n_sealing_strip_pairs", None) or 0

        # Layout angle
        layout_angle = _resolve_layout_angle(g.pitch_layout)

        # Shell-side wall viscosity (P2-25): try to resolve a real value at
        # the estimated wall temperature; fall back to bulk only when the
        # property backend or the wall-T estimate is unavailable.
        T_bulk_shell = _shell_bulk_temperature(state)
        T_wall_shell = _estimate_shell_wall_temperature(state, T_bulk_shell)
        shell_fluid_name = (
            state.hot_fluid_name if state.shell_side_fluid == "hot"
            else state.cold_fluid_name
        )
        shell_pressure_Pa = (
            state.P_hot_Pa if state.shell_side_fluid == "hot"
            else state.P_cold_Pa
        )
        mu_s_wall, mu_s_wall_basis, mu_s_wall_fail_reason = (
            await _resolve_shell_wall_viscosity(
                shell_fluid_name, T_wall_shell, shell_pressure_Pa, mu_s,
            )
        )
        if (
            mu_s_wall_basis == "approx_bulk"
            and mu_s > _MU_VISCOUS_THRESHOLD_PA_S
        ):
            warnings.append(
                f"shell-side wall viscosity unavailable "
                f"({mu_s_wall_fail_reason}); Sieder-Tate correction "
                f"defaulted to 1.0 — ΔP and h may drift ±15% for "
                f"μ_bulk={mu_s * 1000:.1f} cP"
            )

        # GeometrySpec stores baffle_cut as fraction; bell_delaware needs %
        baffle_cut_pct = g.baffle_cut * 100.0

        bell_result = shell_side_dP(
            shell_id_m=g.shell_diameter_m,
            tube_od_m=d_o,
            tube_pitch_m=g.tube_pitch_m,
            layout_angle_deg=layout_angle,
            n_tubes=n_tubes,
            tube_passes=n_passes,
            baffle_cut_pct=baffle_cut_pct,
            baffle_spacing_central_m=g.baffle_spacing_m,
            baffle_spacing_inlet_m=L_i,
            baffle_spacing_outlet_m=L_o,
            n_baffles=n_baffles,
            n_sealing_strip_pairs=N_ss,
            delta_tb_m=delta_tb,
            delta_sb_m=delta_sb,
            delta_bundle_shell_m=delta_bs,
            density_kg_m3=rho_s,
            viscosity_Pa_s=mu_s,
            viscosity_wall_Pa_s=mu_s_wall,
            mass_flow_kg_s=m_dot_shell,
            pitch_ratio=g.pitch_ratio,
        )

        dP_shell_crossflow = bell_result["dP_crossflow_Pa"]
        dP_shell_window = bell_result["dP_window_Pa"]
        dP_shell_end = bell_result["dP_end_Pa"]
        Fb_prime = bell_result["Fb_prime"]
        FL_prime = bell_result["FL_prime"]

        # Shell nozzle losses
        nozzle_id_shell = get_default_nozzle_diameter_m(g.shell_diameter_m)
        n_nozzles_shell = 1
        nozzle_auto_corrected_shell = False
        original_nozzle_id_shell = nozzle_id_shell

        dP_shell_nozzle = 2.0 * nozzle_dP_Pa(m_dot_shell, rho_s, nozzle_id_shell, n_nozzles_shell)
        rho_v2_shell = nozzle_rho_v_squared(m_dot_shell, rho_s, nozzle_id_shell, n_nozzles_shell)

        # Auto-correct: upsize nozzle if ρv² exceeds TEMA limit
        if rho_v2_shell > _RHO_V2_LIMIT:
            candidate = nozzle_id_shell
            while rho_v2_shell > _RHO_V2_LIMIT:
                bigger = get_next_larger_nozzle_diameter_m(candidate)
                if bigger is None:
                    break
                candidate = bigger
                rho_v2_shell = nozzle_rho_v_squared(m_dot_shell, rho_s, candidate, 1)

            if rho_v2_shell <= _RHO_V2_LIMIT:
                nozzle_id_shell = candidate
                nozzle_auto_corrected_shell = True
            else:
                n_nozzles_shell = 2
                rho_v2_shell = nozzle_rho_v_squared(m_dot_shell, rho_s, candidate, n_nozzles_shell)
                nozzle_id_shell = candidate
                nozzle_auto_corrected_shell = True

            if nozzle_auto_corrected_shell:
                dP_shell_nozzle = 2.0 * nozzle_dP_Pa(m_dot_shell, rho_s, nozzle_id_shell, n_nozzles_shell)
                correction_desc = (
                    f"nozzle upsized {original_nozzle_id_shell*1000:.1f}→{nozzle_id_shell*1000:.1f} mm"
                )
                if n_nozzles_shell > 1:
                    correction_desc += f" × {n_nozzles_shell} nozzles"
                warnings.append(
                    f"Shell nozzle ρv² exceeded TEMA limit ({_RHO_V2_LIMIT:.0f} kg/m·s²) — "
                    f"auto-corrected: {correction_desc} "
                    f"(ρv² now {rho_v2_shell:.0f} kg/m·s²)"
                )

        dP_shell_total = bell_result["dP_shell_Pa"] + dP_shell_nozzle

        warnings.extend(bell_result.get("warnings", []))

        # ── 5. CROSS-CHECKS ──────────────────────────────────────

        # 5a. Simplified Delaware (Serth)
        try:
            sd_result = simplified_delaware_shell_dP(
                shell_id_m=g.shell_diameter_m,
                tube_od_m=d_o,
                tube_pitch_m=g.tube_pitch_m,
                layout_angle_deg=layout_angle,
                baffle_spacing_m=g.baffle_spacing_m,
                n_baffles=n_baffles,
                mass_flow_kg_s=m_dot_shell,
                density_kg_m3=rho_s,
                viscosity_Pa_s=mu_s,
                viscosity_wall_Pa_s=mu_s_wall,
            )
            dP_shell_sd = sd_result["dP_shell_Pa"]
        except Exception as exc:
            logger.warning("Simplified Delaware cross-check failed: %s", exc)
            dP_shell_sd = None

        # 5b. Kern ΔP cross-check
        pitch_layout_str = "triangular" if layout_angle in (30, 60) else "square"
        try:
            kern_result = kern_shell_side_dP(
                shell_id_m=g.shell_diameter_m,
                tube_od_m=d_o,
                tube_pitch_m=g.tube_pitch_m,
                pitch_layout=pitch_layout_str,
                baffle_spacing_m=g.baffle_spacing_m,
                n_baffles=n_baffles,
                viscosity_Pa_s=mu_s,
                viscosity_wall_Pa_s=mu_s_wall,
                density_kg_m3=rho_s,
                mass_flow_kg_s=m_dot_shell,
            )
            dP_kern = kern_result["dP_kern_Pa"]
        except Exception as exc:
            logger.warning("Kern ΔP cross-check failed: %s", exc)
            dP_kern = None

        # 5c. Divergence
        bell_vs_kern_pct = None
        if dP_kern is not None and bell_result["dP_shell_Pa"] > 0:
            bell_vs_kern_pct = (
                abs(bell_result["dP_shell_Pa"] - dP_kern)
                / bell_result["dP_shell_Pa"] * 100.0
            )

        # ── 6. WARNINGS ──────────────────────────────────────────

        if bell_vs_kern_pct is not None and bell_vs_kern_pct > 30:
            warnings.append(
                f"Bell/Kern shell-side ΔP divergence: {bell_vs_kern_pct:.1f}% "
                "— verify geometry or baffle spacing"
            )

        if dP_tube_total > 0.85 * _DP_TUBE_LIMIT_PA:
            warnings.append(
                f"Tube-side ΔP {dP_tube_total:.0f} Pa is within 15% of "
                f"{_DP_TUBE_LIMIT_PA:.0f} Pa limit"
            )

        if dP_shell_total > 0.85 * _DP_SHELL_LIMIT_PA:
            warnings.append(
                f"Shell-side ΔP {dP_shell_total:.0f} Pa is within 15% of "
                f"{_DP_SHELL_LIMIT_PA:.0f} Pa limit"
            )

        if v_tube < 0.8:
            warnings.append(
                f"Tube velocity {v_tube:.2f} m/s < 0.8 m/s — fouling risk"
            )
        elif v_tube > 2.5:
            warnings.append(
                f"Tube velocity {v_tube:.2f} m/s > 2.5 m/s — erosion risk"
            )

        if rho_v2_tube > 1500:
            warnings.append(
                f"Tube nozzle ρv² = {rho_v2_tube:.0f} > 1500 — "
                "impingement plate recommended"
            )
        if rho_v2_shell > 1500:
            warnings.append(
                f"Shell nozzle ρv² = {rho_v2_shell:.0f} > 1500 — "
                "impingement plate recommended"
            )

        # ── 7. Write to state ─────────────────────────────────────
        state.dP_tube_Pa = dP_tube_total
        state.dP_shell_Pa = dP_shell_total
        state.dP_tube_friction_Pa = dP_tube_friction
        state.dP_tube_minor_Pa = dP_tube_minor
        state.dP_tube_nozzle_Pa = dP_tube_nozzle
        state.dP_shell_crossflow_Pa = dP_shell_crossflow
        state.dP_shell_window_Pa = dP_shell_window
        state.dP_shell_end_Pa = dP_shell_end
        state.dP_shell_nozzle_Pa = dP_shell_nozzle
        state.Fb_prime_dP = Fb_prime
        state.FL_prime_dP = FL_prime
        state.nozzle_id_tube_m = nozzle_id_tube
        state.nozzle_id_shell_m = nozzle_id_shell
        state.rho_v2_tube_nozzle = rho_v2_tube
        state.rho_v2_shell_nozzle = rho_v2_shell
        state.dP_shell_simplified_delaware_Pa = dP_shell_sd
        state.dP_shell_kern_Pa = dP_kern
        state.dP_shell_bell_vs_kern_pct = bell_vs_kern_pct
        state.n_nozzles_tube = n_nozzles_tube
        state.n_nozzles_shell = n_nozzles_shell
        state.nozzle_auto_corrected_tube = nozzle_auto_corrected_tube
        state.nozzle_auto_corrected_shell = nozzle_auto_corrected_shell

        # P2-25: expose wall-μ basis on state so Step 16 (and the UI) can show it
        state.mu_s_wall_Pa_s = mu_s_wall
        state.mu_s_wall_basis = mu_s_wall_basis
        state.mu_s_wall_fail_reason = mu_s_wall_fail_reason

        # ── 8. Build outputs dict ─────────────────────────────────
        outputs: dict = {
            "dP_tube_Pa": dP_tube_total,
            "dP_shell_Pa": dP_shell_total,
            "dP_tube_friction_Pa": dP_tube_friction,
            "dP_tube_minor_Pa": dP_tube_minor,
            "dP_tube_nozzle_Pa": dP_tube_nozzle,
            "dP_shell_crossflow_Pa": dP_shell_crossflow,
            "dP_shell_window_Pa": dP_shell_window,
            "dP_shell_end_Pa": dP_shell_end,
            "dP_shell_nozzle_Pa": dP_shell_nozzle,
            "Fb_prime_dP": Fb_prime,
            "FL_prime_dP": FL_prime,
            "nozzle_id_tube_m": nozzle_id_tube,
            "nozzle_id_shell_m": nozzle_id_shell,
            "rho_v2_tube_nozzle": rho_v2_tube,
            "rho_v2_shell_nozzle": rho_v2_shell,
            "dP_shell_simplified_delaware_Pa": dP_shell_sd,
            "dP_shell_kern_Pa": dP_kern,
            "dP_shell_bell_vs_kern_pct": bell_vs_kern_pct,
            "n_nozzles_tube": n_nozzles_tube,
            "n_nozzles_shell": n_nozzles_shell,
            "nozzle_auto_corrected_tube": nozzle_auto_corrected_tube,
            "nozzle_auto_corrected_shell": nozzle_auto_corrected_shell,
            "mu_s_wall_Pa_s": mu_s_wall,
            "mu_s_wall_basis": mu_s_wall_basis,
            "mu_s_wall_fail_reason": mu_s_wall_fail_reason,
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        dp_tube = result.outputs.get("dP_tube_Pa")
        dp_shell = result.outputs.get("dP_shell_Pa")
        rv2_tube = result.outputs.get("rho_v2_tube_nozzle")
        rv2_shell = result.outputs.get("rho_v2_shell_nozzle")
        velocity = state.tube_velocity_m_s
        if dp_tube is not None:
            lines.append(f"dP_tube = {dp_tube:.0f} Pa")
        if dp_shell is not None:
            lines.append(f"dP_shell = {dp_shell:.0f} Pa")
        if rv2_tube is not None:
            lines.append(f"Nozzle ρv² (tube) = {rv2_tube:.0f} kg/m·s²")
        if rv2_shell is not None:
            lines.append(f"Nozzle ρv² (shell) = {rv2_shell:.0f} kg/m·s²")
        if velocity is not None:
            lines.append(f"Tube velocity = {velocity:.3f} m/s")
        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────

def _shell_bulk_temperature(state: "DesignState") -> float | None:
    """Mean shell-side bulk temperature in °C, or None if inputs missing."""
    if state.shell_side_fluid == "hot":
        T_in, T_out = state.T_hot_in_C, state.T_hot_out_C
    else:
        T_in, T_out = state.T_cold_in_C, state.T_cold_out_C
    if T_in is None or T_out is None:
        return None
    return (T_in + T_out) / 2.0


def _estimate_shell_wall_temperature(
    state: "DesignState", T_bulk_shell: float | None,
) -> float | None:
    """Estimate shell-side wall temperature from a film resistance split.

    T_wall_shell ≈ T_bulk_shell − (h_shell / (h_shell + h_tube))
                                 × (T_bulk_shell − T_bulk_tube)
    Returns None when any required input is missing — callers fall back
    to bulk and surface a fail_reason so the engineer sees the limitation.
    """
    if T_bulk_shell is None:
        return None
    if state.h_shell_W_m2K is None or state.h_tube_W_m2K is None:
        return None

    if state.shell_side_fluid == "hot":
        T_in_t, T_out_t = state.T_cold_in_C, state.T_cold_out_C
    else:
        T_in_t, T_out_t = state.T_hot_in_C, state.T_hot_out_C
    if T_in_t is None or T_out_t is None:
        return None
    T_bulk_tube = (T_in_t + T_out_t) / 2.0

    h_total = state.h_shell_W_m2K + state.h_tube_W_m2K
    if h_total <= 0:
        return None
    fraction = state.h_shell_W_m2K / h_total
    return T_bulk_shell - fraction * (T_bulk_shell - T_bulk_tube)


async def _resolve_shell_wall_viscosity(
    fluid_name: str | None,
    T_wall: float | None,
    pressure_Pa: float | None,
    mu_bulk: float,
) -> tuple[float, str, str | None]:
    """Resolve shell-side μ_wall.

    Returns ``(mu_wall, basis, fail_reason)`` where ``basis`` is
    ``"computed"`` when a real value was retrieved and ``"approx_bulk"``
    when we silently fell back to ``mu_bulk``. ``fail_reason`` is set
    only on fallback so callers can decide whether to WARN.
    """
    if fluid_name is None:
        return mu_bulk, "approx_bulk", "shell_side_fluid_name_unavailable"
    if T_wall is None:
        return mu_bulk, "approx_bulk", "wall_temperature_unavailable"
    try:
        wall_props = await get_fluid_properties(fluid_name, T_wall, pressure_Pa)
    except Exception as exc:  # noqa: BLE001 — propagate as fail_reason
        return mu_bulk, "approx_bulk", f"viscosity_backend_error:{exc}"
    mu_wall = getattr(wall_props, "viscosity_Pa_s", None)
    if mu_wall is None or mu_wall <= 0:
        return mu_bulk, "approx_bulk", "viscosity_backend_no_value"
    return mu_wall, "computed", None


def _resolve_layout_angle(pitch_layout: str | None) -> int:
    """Convert pitch_layout string to angle in degrees."""
    if pitch_layout is None:
        return 30  # default triangular
    pl = pitch_layout.lower().strip()
    if "tri" in pl or "30" in pl:
        return 30
    if "rot" in pl and "tri" in pl or "60" in pl:
        return 60
    if "rot" in pl and "sq" in pl or "45" in pl:
        return 45
    if "sq" in pl or "90" in pl:
        return 90
    return 30  # default
