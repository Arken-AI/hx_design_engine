"""PropertyProvenanceBuilder — consolidates fluid-level provenance from DesignState.

Reads the final DesignState (after Step 16 completes) and returns a structured
dict describing where each fluid's thermophysical properties came from.

Limitation: This builder operates at fluid-level granularity (one source label
per fluid). Per-property source tracking (where each of density, viscosity, cp,
k can have a different source) requires a property_source_map schema change
and is deferred to a future story.

When user_provided_hot_props / user_provided_cold_props are set (Slice 2),
they take precedence over hot_fluid_props / cold_fluid_props. If a partial
override was stored (only some properties set), the other property values on
the user_provided object may be None — the builder handles this gracefully by
emitting {"value": None, ...} rather than raising.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState, FluidProperties

# ---------------------------------------------------------------------------
# Controlled source label vocabulary
# ---------------------------------------------------------------------------

SOURCE_LABELS: dict[Optional[str], str] = {
    "iapws": "IAPWS-IF97 Reference",
    "coolprop": "CoolProp Database",
    "petroleum_beggs_robinson": "Petroleum Correlation",
    "petroleum-named": "Petroleum Correlation",
    "petroleum_generic": "Petroleum (Generic)",
    "petroleum-generic": "Petroleum (Generic)",
    "specialty": "Specialty Database",
    "thermo": "Chemical Database",
    "mongodb_cached": "Cached Database",
    "user_provided": "Provided by Engineer",
    "user_approved_estimate": "AI Estimate (Approved)",
    "llm_estimated": "AI Estimate (Auto)",
    "derived": "Derived (Prandtl)",
    None: "Unknown",
}

# Properties emitted per-fluid (excludes Pr which is handled separately)
_SCALAR_PROPS = (
    "density_kg_m3",
    "viscosity_Pa_s",
    "cp_J_kgK",
    "k_W_mK",
)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class PropertyProvenanceBuilder:
    """Builds a per-fluid provenance dict from final DesignState.

    Usage::

        provenance = PropertyProvenanceBuilder.build(state)
        # Returns dict with "hot_fluid" and "cold_fluid" keys, or None if
        # neither fluid's props are available.
    """

    @classmethod
    def build(cls, state: "DesignState") -> Optional[dict[str, Any]]:
        """Build provenance from *state* after pipeline completion.

        Returns None only when both fluid prop objects are None (should not
        happen in a completed pipeline, but handled defensively).
        """
        hot_entry = cls._build_fluid_entry(
            fluid_name=state.hot_fluid_name,
            effective_props=state.user_provided_hot_props or state.hot_fluid_props,
            is_user_provided=state.user_provided_hot_props is not None,
        )
        cold_entry = cls._build_fluid_entry(
            fluid_name=state.cold_fluid_name,
            effective_props=state.user_provided_cold_props or state.cold_fluid_props,
            is_user_provided=state.user_provided_cold_props is not None,
        )

        if hot_entry is None and cold_entry is None:
            return None

        return {
            "hot_fluid": hot_entry,
            "cold_fluid": cold_entry,
        }

    @classmethod
    def _build_fluid_entry(
        cls,
        fluid_name: Optional[str],
        effective_props: "Optional[FluidProperties]",
        is_user_provided: bool,
    ) -> Optional[dict[str, Any]]:
        """Build a single-fluid provenance entry."""
        if effective_props is None:
            return None

        source = effective_props.property_source
        label = SOURCE_LABELS.get(source, SOURCE_LABELS[None])
        confidence = effective_props.property_confidence

        # Fluid-level timestamp
        if source == "user_provided":
            fluid_ts = effective_props.property_provided_at
        elif source == "user_approved_estimate":
            fluid_ts = effective_props.approval_timestamp
        else:
            fluid_ts = None

        properties: dict[str, Any] = {}

        # Scalar properties
        for prop in _SCALAR_PROPS:
            value = getattr(effective_props, prop, None)
            entry: dict[str, Any] = {
                "value": value,
                "source": source,
                "label": label,
                "confidence": confidence,
                "unapproved_ai": (
                    source == "llm_estimated"
                    and effective_props.approval_timestamp is None
                ),
                "timestamp": fluid_ts,
            }
            properties[prop] = entry

        # Prandtl number — derived unless user explicitly provided it
        pr_value = getattr(effective_props, "Pr", None)
        pr_user_set = is_user_provided and pr_value is not None

        if pr_user_set:
            properties["Pr"] = {
                "value": pr_value,
                "source": source,
                "label": label,
                "confidence": confidence,
                "unapproved_ai": (
                    source == "llm_estimated"
                    and effective_props.approval_timestamp is None
                ),
                "timestamp": fluid_ts,
            }
        else:
            properties["Pr"] = {
                "value": pr_value,
                "source": "derived",
                "label": SOURCE_LABELS["derived"],
                "note": "Computed from \u03bc, Cp, k",
                "confidence": None,
                "unapproved_ai": False,
                "timestamp": None,
            }

        return {
            "fluid_name": fluid_name,
            "source": source,
            "label": label,
            "confidence": confidence,
            "properties": properties,
        }
