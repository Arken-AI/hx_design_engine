"""Step 07 — Tube-Side Heat Transfer Coefficient.

Computes velocity, Re, Pr, selects the appropriate Nusselt correlation
(Hausen for laminar, Gnielinski for transition/turbulent), applies a
viscosity correction via a rough T_wall estimate, and returns h_tube.

ai_mode = CONDITIONAL — AI is only called when:
  1. Velocity < 0.8 m/s (fouling risk)
  2. Velocity > 2.5 m/s (erosion risk)
  3. Transition zone (2300 < Re < 10000)
  4. h_i outside typical range (< 50 or > 15000 W/m²K)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hx_engine.app.adapters.thermo_adapter import get_fluid_properties
from hx_engine.app.correlations.gnielinski import tube_side_h
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_07_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState


class Step07TubeSideH(BaseStep):
    """Step 7: Tube-side heat transfer coefficient calculation."""

    step_id: int = 7
    step_name: str = "Tube-Side Heat Transfer Coefficient"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Return list of missing fields required from Steps 1–6."""
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
            if state.geometry.tube_id_m is None:
                missing.append("geometry.tube_id_m")
            if state.geometry.n_tubes is None:
                missing.append("geometry.n_tubes")
            if state.geometry.n_passes is None:
                missing.append("geometry.n_passes")
            if state.geometry.tube_length_m is None:
                missing.append("geometry.tube_length_m")

        # Fluid properties — need the tube-side stream's props
        # We check both since we don't know which side is tube yet
        if state.hot_fluid_props is None:
            missing.append("hot_fluid_props")
        if state.cold_fluid_props is None:
            missing.append("cold_fluid_props")

        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute tube-side heat transfer coefficient."""

        # 1. Pre-condition checks
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                7,
                f"Step 7 requires the following from Steps 1-6: "
                f"{', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Identify tube-side fluid
        tube_side = "cold" if state.shell_side_fluid == "hot" else "hot"

        if tube_side == "hot":
            m_dot = state.m_dot_hot_kg_s
            fluid_props = state.hot_fluid_props
            fluid_name = state.hot_fluid_name
            T_tube_in = state.T_hot_in_C
            T_tube_out = state.T_hot_out_C
            T_shell_in = state.T_cold_in_C
            T_shell_out = state.T_cold_out_C
            pressure_Pa = state.P_hot_Pa
        else:
            m_dot = state.m_dot_cold_kg_s
            fluid_props = state.cold_fluid_props
            fluid_name = state.cold_fluid_name
            T_tube_in = state.T_cold_in_C
            T_tube_out = state.T_cold_out_C
            T_shell_in = state.T_hot_in_C
            T_shell_out = state.T_hot_out_C
            pressure_Pa = state.P_cold_Pa

        # 3. Compute mean temperatures
        T_mean_tube = (T_tube_in + T_tube_out) / 2.0
        T_mean_shell = (T_shell_in + T_shell_out) / 2.0

        # Assign to hot/cold mean based on tube side
        if tube_side == "hot":
            T_mean_hot = T_mean_tube
            T_mean_cold = T_mean_shell
        else:
            T_mean_hot = T_mean_shell
            T_mean_cold = T_mean_tube

        # 4. Extract geometry
        D_i = state.geometry.tube_id_m
        L = state.geometry.tube_length_m
        n_tubes = state.geometry.n_tubes
        n_passes = state.geometry.n_passes

        # 5. Compute velocity
        A_cross_per_tube = math.pi / 4.0 * D_i ** 2
        tubes_per_pass = n_tubes / n_passes
        A_flow = tubes_per_pass * A_cross_per_tube
        rho = fluid_props.density_kg_m3
        velocity = m_dot / (rho * A_flow)

        # 6. Compute Re and extract Pr
        mu = fluid_props.viscosity_Pa_s
        Re = rho * velocity * D_i / mu
        Pr = fluid_props.Pr
        k = fluid_props.k_W_mK

        # 7. Get μ_wall via thermo adapter
        T_wall_est = (T_mean_tube + T_mean_shell) / 2.0
        mu_wall: float | None = None
        try:
            wall_props = get_fluid_properties(
                fluid_name, T_wall_est, pressure_Pa,
            )
            mu_wall = wall_props.viscosity_Pa_s
        except Exception:
            warnings.append(
                f"Could not retrieve wall properties at T_wall≈{T_wall_est:.1f}°C "
                f"for {fluid_name}; viscosity correction skipped"
            )

        # 8. Call correlation
        htc_result = tube_side_h(Re, Pr, D_i, L, k, mu, mu_wall)

        # Collect correlation warnings
        warnings.extend(htc_result["warnings"])

        # 9. Regime-specific warnings
        if 2300 < Re < 4000:
            warnings.append(
                f"Transition zone (Re={Re:.0f}): flow genuinely unstable"
            )
        if velocity < 0.8:
            warnings.append(
                f"Low velocity ({velocity:.2f} m/s): fouling risk"
            )
        if velocity > 2.5:
            warnings.append(
                f"High velocity ({velocity:.2f} m/s): erosion risk"
            )

        # 10. Cache values for _conditional_ai_trigger
        self._velocity = velocity
        self._Re = Re
        self._h_i = htc_result["h_i"]

        # 11. Write state directly
        state.h_tube_W_m2K = htc_result["h_i"]
        state.tube_velocity_m_s = velocity
        state.Re_tube = Re
        state.Pr_tube = Pr
        state.Nu_tube = htc_result["Nu"]
        state.flow_regime_tube = htc_result["flow_regime"]
        state.T_mean_hot_C = T_mean_hot
        state.T_mean_cold_C = T_mean_cold

        # 12. Build outputs dict
        outputs: dict = {
            "h_tube_W_m2K": htc_result["h_i"],
            "tube_velocity_m_s": velocity,
            "Re_tube": Re,
            "Pr_tube": Pr,
            "Nu_tube": htc_result["Nu"],
            "flow_regime_tube": htc_result["flow_regime"],
            "method": htc_result["method"],
            "f_petukhov": htc_result["f_petukhov"],
            "viscosity_correction": htc_result["viscosity_correction"],
            "T_wall_estimated_C": T_wall_est,
            "mu_wall_Pa_s": mu_wall,
            "dittus_boelter_Nu": htc_result["dittus_boelter_Nu"],
            "dittus_boelter_divergence_pct": htc_result["dittus_boelter_divergence_pct"],
            "T_mean_hot_C": T_mean_hot,
            "T_mean_cold_C": T_mean_cold,
        }

        # Escalation hints
        escalation_hints: list[dict] = []
        if velocity < 0.8:
            escalation_hints.append({
                "trigger": "low_velocity",
                "recommendation": (
                    f"Tube velocity {velocity:.2f} m/s is below 0.8 m/s — "
                    f"fouling risk. Consider increasing n_passes or reducing n_tubes."
                ),
            })
        if velocity > 2.5:
            escalation_hints.append({
                "trigger": "high_velocity",
                "recommendation": (
                    f"Tube velocity {velocity:.2f} m/s exceeds 2.5 m/s — "
                    f"erosion risk. Consider reducing n_passes."
                ),
            })
        if 2300 < Re < 10000:
            escalation_hints.append({
                "trigger": "transition_zone",
                "recommendation": (
                    f"Re = {Re:.0f} is in the transition zone. "
                    f"Flow is unstable; consider geometry changes to push "
                    f"Re above 10000."
                ),
            })
        if escalation_hints:
            outputs["escalation_hints"] = escalation_hints

        # 13. Return StepResult
        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Conditional AI trigger
    # ------------------------------------------------------------------

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Trigger AI review for edge cases in tube-side HTC.

        Note: state.in_convergence_loop is already checked by
        BaseStep._should_call_ai() before this method is called.

        Returns True if ANY of:
          1. Velocity < 0.8 m/s (fouling risk)
          2. Velocity > 2.5 m/s (erosion risk)
          3. 2300 < Re < 10000 (transition zone)
          4. h_i outside typical range (< 50 or > 15000 W/m²K)
        """
        velocity = getattr(self, "_velocity", None)
        Re = getattr(self, "_Re", None)
        h_i = getattr(self, "_h_i", None)

        if velocity is not None and velocity < 0.8:
            return True
        if velocity is not None and velocity > 2.5:
            return True
        if Re is not None and 2300 < Re < 10000:
            return True
        if h_i is not None and (h_i < 50 or h_i > 15000):
            return True

        return False
