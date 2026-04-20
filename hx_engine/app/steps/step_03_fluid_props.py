"""Step 03 — Collect Fluid Properties.

Takes fluid names and temperatures from Steps 1–2, calls the thermo adapter
for both fluids at their bulk mean temperature, validates the results, and
populates hot_fluid_props / cold_fluid_props on the DesignState.

Detects phase regime (liquid, vapor, condensing, evaporating) by comparing
inlet/outlet temperatures against the saturation temperature at operating
pressure. Sets hot_phase / cold_phase and n_increments on DesignState.

ai_mode = CONDITIONAL — AI is only called when property anomalies are detected.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hx_engine.app.adapters.thermo_adapter import (
    get_fluid_properties,
    get_saturation_props,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import FluidProperties
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

_CRUDE_ALIASES = frozenset({"crude", "crude oil"})

_WATER_ALIASES = frozenset({
    "water", "cooling water", "chilled water", "hot water",
    "boiler water", "sea water", "seawater", "condensate",
})


class Step03FluidProperties(BaseStep):
    step_id: int = 3
    step_name: str = "Fluid Properties"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # Piece 1: Mean temperature calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_mean_temp(T_in_C: float | None, T_out_C: float | None) -> float:
        """Arithmetic mean of inlet and outlet temperatures.

        All property lookups are temperature-dependent — wrong mean temp
        cascades errors through Steps 4–16.

        Raises CalculationError if either temperature is None.
        """
        if T_in_C is None:
            raise CalculationError(3, "Cannot compute mean temperature: T_in is missing")
        if T_out_C is None:
            raise CalculationError(3, "Cannot compute mean temperature: T_out is missing")
        return (T_in_C + T_out_C) / 2.0

    # ------------------------------------------------------------------
    # Piece 2: Single-fluid property retrieval wrapper
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_fluid(
        fluid_name: str,
        T_mean_C: float,
        pressure_Pa: float | None,
    ) -> FluidProperties:
        """Resolve a fluid name to thermophysical properties via the adapter.

        Delegates to ``thermo_adapter.get_fluid_properties()`` and re-raises
        any errors with step_id=3.  Handles bare "crude" by assuming
        "crude oil" (generic API gravity).
        """
        if not fluid_name or not fluid_name.strip():
            raise CalculationError(
                3, "Fluid name is empty — cannot look up properties"
            )

        normalised = fluid_name.strip().lower()

        # Special case: bare "crude" → try "crude oil"
        if normalised == "crude":
            logger.warning(
                "Bare 'crude' specified — assuming 'crude oil' (generic API gravity)."
            )
            fluid_name = "crude oil"

        try:
            return await get_fluid_properties(fluid_name, T_mean_C, pressure_Pa)
        except CalculationError as exc:
            raise CalculationError(
                3,
                f"Could not retrieve properties for '{fluid_name}' at "
                f"T={T_mean_C:.1f}°C: {exc.message}",
                cause=exc,
            ) from exc

    # ------------------------------------------------------------------
    # Piece 3 + 6: Core execute logic with corner-case warnings
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute fluid properties for both hot and cold sides.

        1. Pre-condition check (all required fields from Steps 1–2)
        2. Compute bulk mean temperatures
        3. Resolve properties via thermo adapter
        4. Collect corner-case warnings
        5. Return StepResult (does NOT mutate state)
        """
        warnings: list[str] = []

        # --- Pre-condition check ---
        missing = []
        if not state.hot_fluid_name:
            missing.append("hot_fluid_name")
        if not state.cold_fluid_name:
            missing.append("cold_fluid_name")
        if state.T_hot_in_C is None:
            missing.append("T_hot_in_C")
        if state.T_hot_out_C is None:
            missing.append("T_hot_out_C")
        if state.T_cold_in_C is None:
            missing.append("T_cold_in_C")
        if state.T_cold_out_C is None:
            missing.append("T_cold_out_C")
        if missing:
            raise CalculationError(
                3,
                f"Step 3 requires the following from Steps 1-2: "
                f"{', '.join(missing)}",
            )

        # --- Compute mean temperatures ---
        T_mean_hot = self._compute_mean_temp(
            state.T_hot_in_C, state.T_hot_out_C,
        )
        T_mean_cold = self._compute_mean_temp(
            state.T_cold_in_C, state.T_cold_out_C,
        )

        # --- Track pressure provenance ---
        # Liquids tolerate a 1 atm fallback; gases do not (density scales
        # linearly with P). We tag the source so a Layer 2 rule can
        # escalate when a vapor phase is detected with no user pressure.
        hot_pressure_source = "user" if state.P_hot_Pa is not None else "default_1atm"
        cold_pressure_source = "user" if state.P_cold_Pa is not None else "default_1atm"

        # --- C2: crude oil / crude warning ---
        for name in (state.hot_fluid_name, state.cold_fluid_name):
            if name and name.strip().lower() in _CRUDE_ALIASES:
                warnings.append(
                    "Assuming generic crude oil properties (API ~33). "
                    "Specify API gravity or crude type "
                    "(e.g. 'Arab Light') for accuracy."
                )

        # --- Resolve hot fluid properties ---
        hot_props = await self._resolve_fluid(
            state.hot_fluid_name, T_mean_hot, state.P_hot_Pa,
        )

        # --- Resolve cold fluid properties ---
        cold_props = await self._resolve_fluid(
            state.cold_fluid_name, T_mean_cold, state.P_cold_Pa,
        )

        # Store for conditional AI trigger (Piece 4)
        self._hot_props = hot_props
        self._cold_props = cold_props

        # --- C2c: petroleum correlation range warning ---
        _PETRO_TEMP_LIMIT = 350.0
        for label, props, T_in in [
            ("Hot", hot_props, state.T_hot_in_C),
            ("Cold", cold_props, state.T_cold_in_C),
        ]:
            if (
                props.property_source
                and "petroleum" in props.property_source
                and T_in is not None
                and T_in >= _PETRO_TEMP_LIMIT
            ):
                warnings.append(
                    f"{label} fluid: inlet temperature {T_in:.0f}°C is at or "
                    f"beyond the petroleum correlation validity range "
                    f"(~{_PETRO_TEMP_LIMIT:.0f}°C). Viscosity and other property "
                    f"predictions may be unreliable — consider providing "
                    f"measured values for critical designs."
                )

        # --- C2b: property confidence warnings ---
        for label, props, fluid_name in [
            ("Hot", hot_props, state.hot_fluid_name),
            ("Cold", cold_props, state.cold_fluid_name),
        ]:
            if props.property_confidence is not None and props.property_confidence < 0.80:
                warnings.append(
                    f"{label} fluid '{fluid_name}': property confidence "
                    f"{props.property_confidence:.0%} (source: {props.property_source}). "
                    f"Viscosity is the most sensitive parameter — consider "
                    f"providing measured values for critical designs."
                )
            elif props.property_source and "petroleum" in (props.property_source or ""):
                # Even named crudes get a note — correlations, not measured data
                warnings.append(
                    f"{label} fluid '{fluid_name}': properties from "
                    f"{props.property_source} correlations "
                    f"(confidence: {props.property_confidence:.0%}). "
                    f"Viscosity uncertainty is ±30–50% for petroleum correlations."
                )

        # --- C3: water near phase change ---
        for name, T_mean, P in [
            (state.hot_fluid_name, T_mean_hot, state.P_hot_Pa),
            (state.cold_fluid_name, T_mean_cold, state.P_cold_Pa),
        ]:
            norm = (name or "").strip().lower()
            p_eff = P if P is not None else 101325.0
            if norm in _WATER_ALIASES and p_eff <= 101325.0:
                if T_mean < 5.0:
                    warnings.append(
                        f"Water at T_mean={T_mean:.1f}°C is near freezing. "
                        "Verify single-phase operation."
                    )
                elif T_mean > 95.0:
                    warnings.append(
                        f"Water at T_mean={T_mean:.1f}°C is near boiling "
                        "at 1 atm. Verify single-phase operation."
                    )

        # --- C4: high viscosity → Sieder-Tate warning ---
        for label, props in [("Hot", hot_props), ("Cold", cold_props)]:
            if props.viscosity_Pa_s is not None and props.viscosity_Pa_s > 0.1:
                warnings.append(
                    f"{label} fluid has high viscosity "
                    f"(μ={props.viscosity_Pa_s:.4f} Pa·s). "
                    "Sieder-Tate wall viscosity correction "
                    "may be needed in Step 7."
                )

        # --- C5: Cp variation across temperature range ---
        await self._check_cp_variation(
            state.hot_fluid_name, state.T_hot_in_C, state.T_hot_out_C,
            state.P_hot_Pa, "Hot", warnings,
        )
        await self._check_cp_variation(
            state.cold_fluid_name, state.T_cold_in_C, state.T_cold_out_C,
            state.P_cold_Pa, "Cold", warnings,
        )

        # --- C6: Phase regime detection ---
        hot_phase, cold_phase, n_increments = self._detect_phase_regimes(
            hot_props, cold_props,
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
            state.P_hot_Pa, state.P_cold_Pa,
            state.hot_fluid_name, state.cold_fluid_name,
            warnings,
        )

        outputs = {
            "hot_fluid_props": hot_props,
            "cold_fluid_props": cold_props,
            "T_mean_hot_C": T_mean_hot,
            "T_mean_cold_C": T_mean_cold,
            "hot_phase": hot_phase,
            "cold_phase": cold_phase,
            "n_increments": n_increments,
            "hot_pressure_source": hot_pressure_source,
            "cold_pressure_source": cold_pressure_source,
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=True,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Piece 4: Conditional AI trigger
    # ------------------------------------------------------------------

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Trigger AI review when property anomalies are detected.

        Checks:
        1. Prandtl number outside typical engineering range [0.7, 500]
        2. Extreme viscosity ratio (> 100:1) between sides
        3. Density near Pydantic bound edges (< 100 or > 1800 kg/m³)
        """
        hot = getattr(self, "_hot_props", None)
        cold = getattr(self, "_cold_props", None)
        if hot is None or cold is None:
            return False

        # Pr outside engineering range [0.7, 500]
        for props in (hot, cold):
            if props.Pr is not None and (props.Pr < 0.7 or props.Pr > 500):
                return True

        # Extreme viscosity ratio
        if (
            hot.viscosity_Pa_s is not None
            and cold.viscosity_Pa_s is not None
            and hot.viscosity_Pa_s > 0
            and cold.viscosity_Pa_s > 0
        ):
            ratio = max(
                hot.viscosity_Pa_s / cold.viscosity_Pa_s,
                cold.viscosity_Pa_s / hot.viscosity_Pa_s,
            )
            if ratio > 100:
                return True

        # Property near Pydantic bound edges
        for props in (hot, cold):
            if props.density_kg_m3 is not None:
                if props.density_kg_m3 < 100 or props.density_kg_m3 > 1800:
                    return True

        return False

    # ------------------------------------------------------------------
    # Piece 6 helper: Cp variation check
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_cp_variation(
        fluid_name: str,
        T_in_C: float,
        T_out_C: float,
        pressure_Pa: float | None,
        label: str,
        warnings: list[str],
    ) -> None:
        """Warn if Cp varies > 15% between inlet and outlet temperatures."""
        try:
            props_in = await get_fluid_properties(fluid_name, T_in_C, pressure_Pa)
            props_out = await get_fluid_properties(fluid_name, T_out_C, pressure_Pa)
            if (
                props_in.cp_J_kgK is not None
                and props_out.cp_J_kgK is not None
                and props_in.cp_J_kgK > 0
            ):
                variation = (
                    abs(props_out.cp_J_kgK - props_in.cp_J_kgK)
                    / props_in.cp_J_kgK
                )
                if variation > 0.15:
                    warnings.append(
                        f"{label} fluid Cp varies "
                        f">{variation * 100:.0f}% across temperature range "
                        f"({props_in.cp_J_kgK:.0f} → "
                        f"{props_out.cp_J_kgK:.0f} J/kg·K). "
                        "Consider segmented calculation."
                    )
        except Exception:
            pass  # Non-fatal — skip warning if property lookup fails

    # ------------------------------------------------------------------
    # Piece 7: Phase regime detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_phase_regimes(
        hot_props: FluidProperties,
        cold_props: FluidProperties,
        T_hot_in: float,
        T_hot_out: float,
        T_cold_in: float,
        T_cold_out: float,
        P_hot_Pa: float | None,
        P_cold_Pa: float | None,
        hot_fluid_name: str,
        cold_fluid_name: str,
        warnings: list[str],
    ) -> tuple[str, str, int]:
        """Detect phase regime for each stream.

        Compares inlet/outlet temperatures against T_sat from the property
        backend. Returns (hot_phase, cold_phase, n_increments).

        Phase regimes:
          "liquid"      — both T_in and T_out below T_sat
          "vapor"       — both T_in and T_out above T_sat
          "condensing"  — T_in > T_sat and T_out < T_sat (hot side loses heat)
          "evaporating" — T_in < T_sat and T_out > T_sat (cold side gains heat)

        n_increments:
          1 for single-phase (both sides liquid or vapor)
          10 for two-phase (condensing or evaporating)
        """
        hot_phase = _detect_single_stream_phase(
            hot_props, T_hot_in, T_hot_out, P_hot_Pa, hot_fluid_name,
            is_hot_side=True,
        )
        cold_phase = _detect_single_stream_phase(
            cold_props, T_cold_in, T_cold_out, P_cold_Pa, cold_fluid_name,
            is_hot_side=False,
        )

        # Determine n_increments
        has_phase_change = hot_phase in ("condensing", "evaporating") or \
            cold_phase in ("condensing", "evaporating")
        n_increments = 10 if has_phase_change else 1

        # Warnings for phase change
        if hot_phase == "condensing":
            warnings.append(
                f"Hot fluid '{hot_fluid_name}' is condensing "
                f"(T_in={T_hot_in:.1f}°C > T_sat={hot_props.T_sat_C:.1f}°C > "
                f"T_out={T_hot_out:.1f}°C). "
                f"Incremental calculation with {n_increments} segments will be used."
            )
        if hot_phase == "vapor":
            warnings.append(
                f"Hot fluid '{hot_fluid_name}' is in gas phase "
                f"(density={hot_props.density_kg_m3:.1f} kg/m³). "
                f"Gas-phase correlations will be applied."
            )
        if cold_phase == "evaporating":
            warnings.append(
                f"Cold fluid '{cold_fluid_name}' is evaporating "
                f"(T_in={T_cold_in:.1f}°C < T_sat={cold_props.T_sat_C:.1f}°C < "
                f"T_out={T_cold_out:.1f}°C). "
                f"Incremental calculation with {n_increments} segments will be used."
            )
        if cold_phase == "vapor":
            warnings.append(
                f"Cold fluid '{cold_fluid_name}' is in gas phase "
                f"(density={cold_props.density_kg_m3:.1f} kg/m³). "
                f"Gas-phase correlations will be applied."
            )

        return hot_phase, cold_phase, n_increments


def _detect_single_stream_phase(
    props: FluidProperties,
    T_in: float,
    T_out: float,
    P_Pa: float | None,
    fluid_name: str,
    is_hot_side: bool,
) -> str:
    """Detect phase regime for a single stream.

    Uses T_sat from the property backend if available. Falls back to
    density-based heuristic if T_sat is not available.
    """
    T_sat = props.T_sat_C

    if T_sat is not None:
        # Check for condensation (hot side: T_in above sat, T_out below)
        if is_hot_side and T_in > T_sat and T_out < T_sat:
            return "condensing"
        # Check for evaporation (cold side: T_in below sat, T_out above)
        if not is_hot_side and T_in < T_sat and T_out > T_sat:
            return "evaporating"
        # Both above T_sat → vapor
        if T_in > T_sat + 1.0 and T_out > T_sat + 1.0:
            return "vapor"
        # Both below T_sat → liquid
        if T_in < T_sat - 1.0 and T_out < T_sat - 1.0:
            return "liquid"

    # Fallback: use phase from property backend
    if props.phase == "vapor":
        return "vapor"
    if props.phase == "two_phase":
        return "condensing" if is_hot_side else "evaporating"

    # Default: density-based heuristic
    if props.density_kg_m3 is not None and props.density_kg_m3 < 50.0:
        return "vapor"

    return "liquid"
