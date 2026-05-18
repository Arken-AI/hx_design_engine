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
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from hx_engine.app.adapters.thermo_adapter import (
    get_fluid_properties,
    get_freezing_or_pour_point,
    get_saturation_props,
)
from hx_engine.app.core.exceptions import CalculationError, PropertyResolutionRequired
from hx_engine.app.models.design_state import FluidProperties
from pydantic import ValidationError as PydanticValidationError
from hx_engine.app.models.step_result import AIDecisionEnum, AIReview, AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

_CRUDE_ALIASES = frozenset({"crude", "crude oil"})

_WATER_ALIASES = frozenset({
    "water", "cooling water", "chilled water", "hot water",
    "boiler water", "sea water", "seawater", "condensate",
})

# ── P2-18: viscosity-variation severity bands (μ_max / μ_min over ΔT) ──
_MU_VARIATION_WARN = 2.0      # warn engineer in StepResult
_MU_VARIATION_AI = 5.0        # also trigger conditional AI review
_MU_VARIATION_ESCALATE = 10.0 # rule failure → ESCALATE (correctable=False)

# ── P2-19: freezing-point soft-margin band (T_min - T_freeze) ──────────
_FREEZE_MARGIN_WARN_K = 5.0

# Engineering impact text for AI property suggestion escalation cards.
# Rendered verbatim in the frontend — use plain prose, no markdown.
IMPACT_TEXT: dict[str, str] = {
    "density_kg_m3":  "Density affects mass flow rates, velocity calculations, and Reynolds number.",
    "viscosity_Pa_s": "Viscosity strongly affects Reynolds number, heat-transfer coefficients, and pressure drop.",
    "cp_J_kgK":       "Specific heat affects required duty and NTU calculations.",
    "k_W_mK":         "Thermal conductivity affects the Prandtl number and convective heat-transfer coefficient.",
}


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
        except PropertyResolutionRequired:
            # Let the confidence gate bubble up to execute() for structured
            # escalation — do NOT wrap in CalculationError.
            raise
        except CalculationError as exc:
            raise CalculationError(
                3,
                f"Could not retrieve properties for '{fluid_name}' at "
                f"T={T_mean_C:.1f}°C: {exc.message}",
                cause=exc,
            ) from exc
        except PydanticValidationError as exc:
            # Pydantic ValidationError here means the thermo backend returned
            # non-physical values (e.g. negative viscosity or Cp from CoolProp
            # operating outside its EOS envelope) that failed FluidProperties
            # field validators. Surface as a typed CalculationError so the
            # pipeline reports a meaningful step-3 error rather than
            # "Unexpected error in step 3". Other exception types are
            # intentionally NOT caught — they indicate programming bugs that
            # must surface unmodified.
            raise CalculationError(
                3,
                f"Non-physical properties returned for '{fluid_name}' at "
                f"T={T_mean_C:.1f}°C — {exc}",
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
        # Three-level lookup priority (EPIC-XSTACK-2026-007-S2):
        # Level 1: user_provided_* (engineer manual entry) — absolute priority
        # Level 2: approved AI estimate (Slice 1)
        # Level 3: adapter chain
        hot_pres_exc: PropertyResolutionRequired | None = None
        cold_pres_exc: PropertyResolutionRequired | None = None

        # Level 1 (new, Slice 2): user_provided_* takes absolute priority
        if state.user_provided_hot_props is not None:
            hot_props = state.user_provided_hot_props
            state.hot_fluid_props = hot_props  # ensure downstream steps see user values
            if state.user_property_temp_hot_C is not None:
                delta_T = abs(T_mean_hot - state.user_property_temp_hot_C)
                if delta_T > 15.0:
                    warnings.append(
                        f"Hot fluid: user-provided properties were measured at "
                        f"{state.user_property_temp_hot_C:.1f}\u00b0C but the current mean "
                        f"temperature is {T_mean_hot:.1f}\u00b0C (\u0394T = {delta_T:.1f}\u00b0C > 15\u00b0C). "
                        f"Temperature-sensitive properties (viscosity, k) may have drifted "
                        f"\u2014 consider providing updated values."
                    )
                else:
                    state.notes.append(
                        f"Hot fluid: re-using engineer-provided properties "
                        f"(\u0394T from reference = {delta_T:.1f}\u00b0C < 15\u00b0C \u2014 within acceptable range)."
                    )
        # Level 2 (existing, Slice 1): approved AI estimate
        elif (
            state.hot_fluid_props is not None
            and state.hot_fluid_props.property_source in (
                "user_approved_estimate", "user_provided",
            )
        ):
            hot_props = state.hot_fluid_props
        # Level 3: adapter chain
        else:
            try:
                hot_props = await self._resolve_fluid(
                    state.hot_fluid_name, T_mean_hot, state.P_hot_Pa,
                )
            except PropertyResolutionRequired as exc:
                hot_pres_exc = exc
                hot_props = None

        # --- Resolve cold fluid properties ---
        # Level 1 (new, Slice 2): user_provided_* takes absolute priority
        if state.user_provided_cold_props is not None:
            cold_props = state.user_provided_cold_props
            state.cold_fluid_props = cold_props  # ensure downstream steps see user values
            if state.user_property_temp_cold_C is not None:
                delta_T = abs(T_mean_cold - state.user_property_temp_cold_C)
                if delta_T > 15.0:
                    warnings.append(
                        f"Cold fluid: user-provided properties were measured at "
                        f"{state.user_property_temp_cold_C:.1f}\u00b0C but the current mean "
                        f"temperature is {T_mean_cold:.1f}\u00b0C (\u0394T = {delta_T:.1f}\u00b0C > 15\u00b0C). "
                        f"Temperature-sensitive properties (viscosity, k) may have drifted "
                        f"\u2014 consider providing updated values."
                    )
                else:
                    state.notes.append(
                        f"Cold fluid: re-using engineer-provided properties "
                        f"(\u0394T from reference = {delta_T:.1f}\u00b0C < 15\u00b0C \u2014 within acceptable range)."
                    )
        # Level 2 (existing, Slice 1): approved AI estimate
        elif (
            state.cold_fluid_props is not None
            and state.cold_fluid_props.property_source in (
                "user_approved_estimate", "user_provided",
            )
        ):
            cold_props = state.cold_fluid_props
        # Level 3: adapter chain
        else:
            try:
                cold_props = await self._resolve_fluid(
                    state.cold_fluid_name, T_mean_cold, state.P_cold_Pa,
                )
            except PropertyResolutionRequired as exc:
                cold_pres_exc = exc
                cold_props = None

        # --- Gate: if either side failed confidence check, escalate ---
        if hot_pres_exc is not None or cold_pres_exc is not None:
            return self._build_property_escalation(
                state,
                hot_pres_exc=hot_pres_exc,
                cold_pres_exc=cold_pres_exc,
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

        # --- P2-18: viscosity variation across ΔT (per side) ---
        viscosity_variation = await self._check_viscosity_variation_both_sides(
            state, warnings,
        )

        # --- P2-19: freezing-point margin (per side) ---
        freezing_check = self._check_freezing_points(state, warnings)
        self._freezing_check = freezing_check

        # --- P2-20: density-drift check vs the inlet density used for
        # volumetric→mass flow conversion. Bulk-mean ρ from this step is
        # the "honest" value for sizing — a > 2 % drift means the flow
        # was specified at a temperature where ρ differs noticeably from
        # the operating range and the user should confirm.
        flow_density_drift = self._check_flow_density_drift(
            state, hot_props, cold_props, warnings,
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
            "viscosity_variation": viscosity_variation,
            "freezing_check": freezing_check,
            "flow_density_drift": flow_density_drift,
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=True,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # EPIC-XSTACK-2026-007-S1: Property escalation helpers
    # ------------------------------------------------------------------

    def _build_property_escalation(
        self,
        state: "DesignState",
        *,
        hot_pres_exc: PropertyResolutionRequired | None,
        cold_pres_exc: PropertyResolutionRequired | None,
    ) -> StepResult:
        """Build a StepResult(ESCALATE) when fluid properties need review.

        Stores the pending exceptions on the step instance so
        ``apply_user_override()`` can access the AI estimates.
        """
        self._pending_hot_request = hot_pres_exc
        self._pending_cold_request = cold_pres_exc

        fluids_payload: list[dict] = []
        reasoning_parts: list[str] = []

        for exc, side in [(hot_pres_exc, "hot"), (cold_pres_exc, "cold")]:
            if exc is None:
                continue
            fluid_entry: dict = {
                "fluid_name": exc.fluid_name,
                "side": side,
                "temperature_C": exc.temperature_C,
                "confidence": exc.confidence,
                "ai_estimate": None,
            }
            if exc.ai_estimate is not None:
                est = exc.ai_estimate
                fluid_entry["ai_estimate"] = {
                    "density_kg_m3": est.density_kg_m3,
                    "viscosity_Pa_s": est.viscosity_Pa_s,
                    "cp_J_kgK": est.cp_J_kgK,
                    "k_W_mK": est.k_W_mK,
                    "Pr": est.Pr,
                    "property_source": est.property_source,
                    "property_confidence": est.property_confidence,
                }
                reasoning_parts.append(
                    f"'{exc.fluid_name}' ({side}) at T={exc.temperature_C:.1f}°C — "
                    f"AI confidence {exc.confidence:.0%} (threshold {exc.threshold:.0%}). "
                    f"Please review the AI estimate before proceeding."
                )
            else:
                reasoning_parts.append(
                    f"'{exc.fluid_name}' ({side}) at T={exc.temperature_C:.1f}°C — "
                    f"no AI estimate available (no API key or AI call failed). "
                    f"Please provide fluid properties manually."
                )
            fluids_payload.append(fluid_entry)

        threshold = (hot_pres_exc or cold_pres_exc).threshold  # type: ignore[union-attr]

        property_request_payload = {
            "fluids": fluids_payload,
            "required_properties": [
                "density_kg_m3",
                "viscosity_Pa_s",
                "cp_J_kgK",
                "k_W_mK",
            ],
            "threshold": threshold,
        }

        reasoning = " | ".join(reasoning_parts)

        review = AIReview(
            decision=AIDecisionEnum.ESCALATE,
            reasoning=reasoning,
            options=[
                "Approve the AI estimate and continue",
                "Enter my own measured or datasheet values",
                "Use a substitute fluid (coming soon)",
            ],
            option_ratings=[7, 3, 3],
            recommendation=(
                "Review the AI-estimated fluid properties in the table below. "
                "If they look reasonable for your application, approve them to continue. "
                "For critical designs, supply measured values."
            ),
            event_subtype="property_request",
            property_request_payload=property_request_payload,
        )

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs={
                "_event_subtype": "property_request",
                "_property_request_payload": property_request_payload,
            },
            validation_passed=False,
            warnings=[],
            ai_review=review,
        )

    def apply_user_override(
        self,
        state: "DesignState",
        option_index: int,
        text: str = "",
    ) -> None:
        """Handle engineer's response to a property escalation.

        Option 0 — "Approve the AI estimate":
            Stamps ``property_source = "user_approved_estimate"`` and
            ``approval_timestamp`` on the AI estimate, then writes it to
            ``state.hot_fluid_props`` / ``state.cold_fluid_props``.

        Returns None to signal "re-run this step" (``pipeline_runner``
        convention for ``apply_user_override``).
        """
        if option_index == 0 or "approve" in (text or "").lower():
            now_iso = datetime.now(tz=timezone.utc).isoformat()

            for exc, attr in [
                (self._pending_hot_request, "hot_fluid_props"),
                (self._pending_cold_request, "cold_fluid_props"),
            ]:
                if exc is None:
                    continue
                estimate = exc.ai_estimate
                if estimate is None:
                    logger.warning(
                        "Engineer approved property estimate for '%s' (%s side) "
                        "but no AI estimate was available — skipping.",
                        exc.fluid_name,
                        attr.split("_")[0],
                    )
                    continue
                # Stamp approved provenance
                estimate = estimate.model_copy(update={
                    "property_source": "user_approved_estimate",
                    "approval_timestamp": now_iso,
                })
                setattr(state, attr, estimate)
                logger.info(
                    "Engineer approved AI estimate for '%s' (%s) — "
                    "approval_timestamp=%s, confidence=%.2f",
                    exc.fluid_name, attr, now_iso, exc.confidence,
                )
        elif option_index == 1:
            # Option 1: engineer wants to supply their own property values.
            # ``text`` may be a JSON string or a free-text key=value string;
            # the structured path is preferred (backend proxy sends JSON).
            self._apply_manual_properties(state, text)

        else:
            logger.info(
                "Engineer chose option %d for property escalation — "
                "no handler implemented; step will re-run.",
                option_index,
            )

        return None  # signal: re-run step 3

    # ------------------------------------------------------------------
    # EPIC-XSTACK-2026-007-S2: manual property entry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_user_props(
        user_props: "FluidProperties",
        adapter_props: "FluidProperties",
    ) -> "FluidProperties":
        """Overlay user-supplied fields on top of adapter-resolved fields.

        Only non-None fields from *user_props* replace the adapter values;
        all other metadata (phase, Pr, etc.) is taken from *adapter_props*.
        This ensures user-provided measurements take unconditional priority
        while the adapter fills in any unspecified properties.
        """
        merged_data = adapter_props.model_dump()
        for field in ("density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK"):
            val = getattr(user_props, field, None)
            if val is not None:
                merged_data[field] = val
        merged_data["property_source"] = "user_provided"
        merged_data["property_provided_at"] = user_props.property_provided_at
        return FluidProperties(**merged_data)

    def _apply_manual_properties(
        self,
        state: "DesignState",
        text: str,
    ) -> None:
        """Parse the engineer's manual property payload and store it.

        The payload may arrive as:
          - A JSON-encoded dict from the backend proxy
          - A free-text "key=value" string (fallback)

        Expected JSON structure (from backend proxy):
          { "fluid_side": "hot"|"cold", "properties": { ... } }

        Missing property keys are allowed; partial sets are stored as-is.
        Step 3's execute() merges user-provided fields with adapter-resolved
        fields via _merge_user_props() when only some properties are supplied.
        """
        import json

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {}

        # Try structured JSON first
        if text and text.strip().startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Step 3: manual-entry text is not valid JSON; skipping.")
                return
        else:
            logger.info(
                "Step 3: apply_user_override(option=1) called with non-JSON text — "
                "no manual properties stored; pipeline will re-escalate."
            )
            return

        fluid_side = payload.get("fluid_side", "").lower()
        props_dict = payload.get("properties", {})

        if fluid_side not in ("hot", "cold"):
            logger.warning(
                "Step 3 manual entry: fluid_side '%s' unrecognised — skipping.",
                fluid_side,
            )
            return

        if not props_dict:
            logger.warning("Step 3 manual entry: empty properties dict — skipping.")
            return

        # Build FluidProperties — Pydantic enforces physical bounds.
        # ValidationError here means the backend pre-check was bypassed or
        # the user sent out-of-range values; log and return (pipeline re-escalates).
        try:
            fp = FluidProperties(
                density_kg_m3=props_dict.get("density_kg_m3"),
                viscosity_Pa_s=props_dict.get("viscosity_Pa_s"),
                cp_J_kgK=props_dict.get("cp_J_kgK"),
                k_W_mK=props_dict.get("k_W_mK"),
                property_source="user_provided",
                property_provided_at=now_iso,
            )
        except PydanticValidationError as exc:
            logger.warning(
                "Step 3 manual entry: property validation failed — %s", exc
            )
            return

        # Determine mean temperature at which properties were provided.
        # Use whatever is currently cached (just computed in execute()).
        T_mean: float | None = (
            getattr(state, "T_mean_hot_C", None)
            if fluid_side == "hot"
            else getattr(state, "T_mean_cold_C", None)
        )

        if fluid_side == "hot":
            state.user_provided_hot_props = fp
            state.hot_fluid_props = fp
            if T_mean is not None:
                state.user_property_temp_hot_C = T_mean
        else:
            state.user_provided_cold_props = fp
            state.cold_fluid_props = fp
            if T_mean is not None:
                state.user_property_temp_cold_C = T_mean

        fluid_name = (
            state.hot_fluid_name if fluid_side == "hot" else state.cold_fluid_name
        )
        logger.info(
            "Engineer provided manual properties for '%s' (%s side) — "
            "source=user_provided, provided_at=%s",
            fluid_name, fluid_side, now_iso,
        )

    def _apply_ai_correction_with_gate(
        self,
        state: "DesignState",
        fluid_side: str,
        field: str,
        corrected_value: float,
        reason: str,
    ) -> None:
        """Guard for AI-generated property corrections (EPIC-XSTACK-2026-007-S2).

        Per the AI Confirmation Workflow specification (17 May 2026), ARKEN
        must NEVER silently apply AI-generated corrections to fluid properties.

        Case A — user already provided this field:
            Block the correction silently; append a note to state.notes.

        Case B — adapter-estimated field:
            Emit a PropertyEscalationEvent and pause for user confirmation.
            (Implemented via re-raising a sub-exception that base.py handles;
            in the current architecture this stores the pending correction on
            the step instance and marks the pipeline as waiting.)
        """
        user_props = (
            state.user_provided_hot_props
            if fluid_side == "hot"
            else state.user_provided_cold_props
        )
        user_value = getattr(user_props, field, None) if user_props is not None else None

        if user_value is not None:
            # Case A: user-provided field — block correction
            state.notes.append(
                f"AI correction to {field} ({fluid_side} side) blocked — "
                f"user-provided value takes precedence."
            )
            logger.info(
                "AI correction to %s (%s side) blocked — user-provided value takes precedence.",
                field, fluid_side,
            )
            return

        # Case B: adapter-estimated field — emit escalation payload for base.py
        # Store on the instance; base.py's on_review_accepted / correction loop
        # will detect this and emit the appropriate SSE event.
        existing_props = (
            state.hot_fluid_props if fluid_side == "hot" else state.cold_fluid_props
        )
        current_value = getattr(existing_props, field, None) if existing_props else None

        self._pending_ai_correction = {
            "fluid_side": fluid_side,
            "field": field,
            "proposed_value": corrected_value,
            "current_value": current_value,
            "reason": reason,
            "engineering_impact": IMPACT_TEXT.get(field, ""),
        }
        logger.info(
            "AI correction to %s (%s side) deferred for user confirmation — "
            "proposed=%.6g, current=%.6g",
            field, fluid_side, corrected_value, current_value or 0,
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
        4. Per-side viscosity variation across ΔT ≥ _MU_VARIATION_AI (P2-18)
        5. Freezing-point margin < _FREEZE_MARGIN_WARN_K or unresolved (P2-19)
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

        # P2-18: viscosity variation across ΔT on either side
        mu_var = getattr(self, "_viscosity_variation", None) or {}
        for side_info in mu_var.values():
            if side_info is None:
                continue
            mu_ratio = side_info.get("mu_ratio")
            if mu_ratio is not None and mu_ratio >= _MU_VARIATION_AI:
                return True

        # P2-19: marginal or unresolved freezing point on either side
        freeze = getattr(self, "_freezing_check", None) or {}
        for side_info in freeze.values():
            if side_info is None:
                continue
            if side_info.get("freeze_property_source") == "unresolved":
                return True
            margin = side_info.get("margin_K")
            if margin is not None and margin < _FREEZE_MARGIN_WARN_K:
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
    # P2-18: Viscosity variation across ΔT
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_viscosity_variation_one_side(
        fluid_name: str,
        T_in_C: float,
        T_out_C: float,
        pressure_Pa: float | None,
    ) -> dict | None:
        """Sample viscosity at inlet, mean and outlet temperatures.

        Returns a dict with ``mu_in``, ``mu_mean``, ``mu_out`` and
        ``mu_ratio = max / min``, or ``None`` if any backend lookup fails
        (defensive — caller logs INFO and continues).
        """
        T_mean_C = 0.5 * (T_in_C + T_out_C)
        try:
            p_in = await get_fluid_properties(fluid_name, T_in_C, pressure_Pa)
            p_mean = await get_fluid_properties(fluid_name, T_mean_C, pressure_Pa)
            p_out = await get_fluid_properties(fluid_name, T_out_C, pressure_Pa)
        except Exception:  # noqa: BLE001 — backend gap, no silent pass
            return None

        mus = (p_in.viscosity_Pa_s, p_mean.viscosity_Pa_s, p_out.viscosity_Pa_s)
        if any(m is None or m <= 0 for m in mus):
            return None

        mu_in, mu_mean, mu_out = mus
        return {
            "mu_in_Pa_s": mu_in,
            "mu_mean_Pa_s": mu_mean,
            "mu_out_Pa_s": mu_out,
            "mu_ratio": max(mus) / min(mus),
        }

    async def _check_viscosity_variation_both_sides(
        self,
        state: "DesignState",
        warnings: list[str],
    ) -> dict[str, dict | None]:
        """Compute per-side μ variation and emit WARN strings by band.

        Stores the result on ``self._viscosity_variation`` so the
        conditional AI trigger can read it without re-sampling.
        """
        result: dict[str, dict | None] = {}
        sides = (
            ("hot", state.hot_fluid_name, state.T_hot_in_C,
             state.T_hot_out_C, state.P_hot_Pa),
            ("cold", state.cold_fluid_name, state.T_cold_in_C,
             state.T_cold_out_C, state.P_cold_Pa),
        )
        for side, name, T_in, T_out, P in sides:
            info = await self._check_viscosity_variation_one_side(
                name, T_in, T_out, P,
            )
            result[side] = info
            if info is None:
                logger.info(
                    "Viscosity variation skipped for %s side ('%s') — "
                    "backend gap; no silent pass.",
                    side, name,
                )
                continue

            ratio = info["mu_ratio"]
            label = side.capitalize()
            if ratio >= _MU_VARIATION_ESCALATE:
                warnings.append(
                    f"{label} fluid viscosity varies {ratio:.1f}× across ΔT "
                    f"(μ {info['mu_in_Pa_s']:.4f} → {info['mu_out_Pa_s']:.4f} Pa·s) — "
                    f"≥ {_MU_VARIATION_ESCALATE:.0f}× will be escalated by Layer 2."
                )
            elif ratio >= _MU_VARIATION_AI:
                warnings.append(
                    f"{label} fluid viscosity varies {ratio:.1f}× across ΔT — "
                    f"≥ {_MU_VARIATION_AI:.0f}× triggers AI review; "
                    f"consider segmented calculation."
                )
            elif ratio >= _MU_VARIATION_WARN:
                warnings.append(
                    f"{label} fluid viscosity varies {ratio:.1f}× across ΔT — "
                    f"verify Sieder-Tate wall correction in Step 7."
                )

        self._viscosity_variation = result
        return result

    # ------------------------------------------------------------------
    # P2-19: Freezing-point margin
    # ------------------------------------------------------------------

    @staticmethod
    def _check_freezing_points(
        state: "DesignState",
        warnings: list[str],
    ) -> dict[str, dict]:
        """Compute per-side ``T_freeze`` and operating margin.

        Returns ``{side: {"T_min_K", "T_freeze_K", "margin_K",
        "freeze_property_source"}}``.  Layer 2 rule
        ``_rule_above_freezing_point`` reads this; soft warnings (margin
        < ``_FREEZE_MARGIN_WARN_K``) are appended here.
        """
        sides = (
            ("hot", state.hot_fluid_name, state.T_hot_in_C,
             state.T_hot_out_C, state.P_hot_Pa),
            ("cold", state.cold_fluid_name, state.T_cold_in_C,
             state.T_cold_out_C, state.P_cold_Pa),
        )
        result: dict[str, dict] = {}
        for side, name, T_in, T_out, P in sides:
            T_min_C = min(T_in, T_out)
            T_min_K = T_min_C + 273.15
            T_freeze_K, source = get_freezing_or_pour_point(name, P)
            margin_K = (
                T_min_K - T_freeze_K if T_freeze_K is not None else None
            )
            result[side] = {
                "T_min_K": T_min_K,
                "T_freeze_K": T_freeze_K,
                "margin_K": margin_K,
                "freeze_property_source": source,
            }

            label = side.capitalize()
            if T_freeze_K is None:
                logger.info(
                    "Freezing point unresolved for %s side ('%s') — "
                    "no silent pass; AI will be consulted.",
                    side, name,
                )
                warnings.append(
                    f"{label} fluid '{name}': freezing/pour point could not be "
                    f"resolved from any backend. AI review will be requested."
                )
            elif margin_K is not None and margin_K <= 0:
                # Layer 2 rule will fail; emit a clear engineer-readable note.
                warnings.append(
                    f"{label} fluid '{name}': T_min={T_min_C:.1f}°C is at or below "
                    f"the freezing/pour point ({T_freeze_K - 273.15:.1f}°C, "
                    f"source={source}). Layer 2 will escalate."
                )
            elif margin_K is not None and margin_K < _FREEZE_MARGIN_WARN_K:
                warnings.append(
                    f"{label} fluid '{name}': operating margin above "
                    f"freezing/pour point is only {margin_K:.1f} K "
                    f"(< {_FREEZE_MARGIN_WARN_K:.0f} K). Verify freeze-protection "
                    f"design (source={source})."
                )

        return result

    # ------------------------------------------------------------------
    # P2-20: Density-drift check vs validator-side conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _check_flow_density_drift(
        state: "DesignState",
        hot_props,
        cold_props,
        warnings: list[str],
    ) -> dict[str, float]:
        """Compare bulk-mean ρ to the inlet ρ used for m_dot conversion.

        Drift exceeding :data:`DENSITY_DRIFT_WARN_PCT` (2 %) → soft WARN.
        The mass flow is **not** silently corrected here — the validator's
        choice (inlet density) remains the contract; this surfaces cases
        where the user should reconsider the flow specification or supply
        m_dot directly.
        """
        from hx_engine.app.core.volumetric_flow import DENSITY_DRIFT_WARN_PCT

        drift: dict[str, float] = {}
        for side, audit, props in (
            ("hot", state.hot_flow_input, hot_props),
            ("cold", state.cold_flow_input, cold_props),
        ):
            if not audit:
                continue
            rho_inlet = audit.get("density_kg_m3")
            rho_mean = getattr(props, "density_kg_m3", None)
            if not rho_inlet or not rho_mean:
                continue
            pct = abs(rho_mean - rho_inlet) / rho_inlet * 100.0
            drift[side] = pct
            if pct > DENSITY_DRIFT_WARN_PCT:
                warnings.append(
                    f"{side.capitalize()} fluid: bulk-mean density "
                    f"{rho_mean:.1f} kg/m³ differs from the inlet density "
                    f"{rho_inlet:.1f} kg/m³ used to convert "
                    f"{audit['value']} {audit['unit']} → kg/s "
                    f"({pct:.1f}% drift > {DENSITY_DRIFT_WARN_PCT:.0f}%). "
                    f"Mass flow was held constant at the inlet value; "
                    f"confirm this matches the metered basis or supply "
                    f"m_dot_{side}_kg_s directly."
                )

        return drift

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

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        for label, key in [("Hot", "hot_fluid_props"), ("Cold", "cold_fluid_props")]:
            props = result.outputs.get(key)
            if props is None:
                continue
            mu = getattr(props, "viscosity_Pa_s", None)
            cp = getattr(props, "cp_J_kgK", None)
            k = getattr(props, "k_W_mK", None)
            pr = getattr(props, "Pr", None)
            source = getattr(props, "property_source", None) or "unknown"
            confidence = getattr(props, "property_confidence", None)
            lines.append(f"{label} — property_source = {source}" + (
                f", confidence = {confidence:.0%}" if confidence is not None else ""
            ))
            if all(v is not None and v > 0 for v in (mu, cp, k, pr)):
                expected_pr = mu * cp / k
                delta_pct = abs(pr - expected_pr) / expected_pr * 100
                lines.append(
                    f"{label} — Pr_computed = μ×Cp/k = {expected_pr:.2f}, "
                    f"Pr_stored = {pr:.2f}, delta = {delta_pct:.1f}%"
                )
        return "\n".join(lines)


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


