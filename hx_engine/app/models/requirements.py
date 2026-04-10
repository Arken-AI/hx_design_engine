"""Shared request/response models for /requirements and /design endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DesignRequest(BaseModel):
    """Payload for POST /api/v1/hx/requirements and POST /api/v1/hx/design."""

    # --- Identification ---
    user_id: str
    org_id: Optional[str] = None
    mode: str = "design"  # "design" | "rating"

    # --- Audit only — never parsed by any pipeline step ---
    raw_request: Optional[str] = Field(
        default=None,
        description="Original natural-language text, stored for audit. Never parsed by the engine.",
    )

    # --- Required thermal inputs ---
    hot_fluid_name: Optional[str] = None
    cold_fluid_name: Optional[str] = None
    T_hot_in_C: Optional[float] = None
    T_cold_in_C: Optional[float] = None
    m_dot_hot_kg_s: Optional[float] = None

    # --- Optional — Step 2 derives missing values via energy balance ---
    T_hot_out_C: Optional[float] = None
    T_cold_out_C: Optional[float] = None
    m_dot_cold_kg_s: Optional[float] = None

    # --- Optional with defaults (101325 Pa = atmospheric) ---
    P_hot_Pa: Optional[float] = None
    P_cold_Pa: Optional[float] = None

    # --- Purely optional ---
    tema_preference: Optional[str] = None

    # --- Token from /requirements (stateless HMAC proof) ---
    token: Optional[str] = Field(
        default=None,
        description="HMAC token from POST /requirements. If absent, /design runs inline validation.",
    )

    def to_validation_dict(self) -> dict[str, Any]:
        """Return the canonical dict used for Layer 1/2 validation and token signing.

        Excludes audit-only and routing fields (raw_request, token, user_id, org_id, mode).
        """
        return {
            k: v for k, v in self.model_dump().items()
            if k not in {"raw_request", "token", "user_id", "org_id", "mode"}
            and v is not None
        }


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    suggestion: str = ""
    valid_range: str = ""


class RequirementsResponse(BaseModel):
    """Response from POST /api/v1/hx/requirements."""

    valid: bool
    token: Optional[str] = None
    user_message: Optional[str] = None
    design_input: Optional[dict[str, Any]] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[ValidationErrorDetail] = Field(default_factory=list)
