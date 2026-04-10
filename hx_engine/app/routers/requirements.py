"""Requirements router — stateless physics feasibility gate.

POST /api/v1/hx/requirements
  Layer 1: schema + completeness checks
  Layer 2: physics feasibility (deterministic, no AI)
  Returns: HMAC token for /design, structured errors for Claude to relay

No session created. No DB write. Idempotent.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from hx_engine.app.core.requirements_validator import (
    build_user_message,
    sign_token,
    validate_requirements,
)
from hx_engine.app.models.requirements import (
    DesignRequest,
    RequirementsResponse,
    ValidationErrorDetail,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["requirements"])


@router.post("/requirements", response_model=RequirementsResponse)
async def validate_design_requirements(req: DesignRequest) -> RequirementsResponse:
    """Validate design inputs before creating a session.

    Claude calls this first, then calls POST /design with the returned token.
    Direct API callers can also use this to pre-validate inputs.
    """
    validation_dict = req.to_validation_dict()
    result = validate_requirements(validation_dict)

    if not result.valid:
        logger.info(
            "Requirements validation failed for user=%s: %d error(s)",
            req.user_id,
            len(result.errors),
        )
        body = RequirementsResponse(
            valid=False,
            errors=[
                ValidationErrorDetail(
                    field=e.field,
                    message=e.message,
                    suggestion=e.suggestion,
                    valid_range=e.valid_range,
                )
                for e in result.errors
            ],
        )
        return JSONResponse(
            status_code=422,
            content=body.model_dump(),
        )

    # Validation passed — sign a token and build the success response
    token = sign_token(validation_dict)
    user_message = build_user_message(validation_dict, result.warnings)

    logger.info(
        "Requirements valid for user=%s, token issued",
        req.user_id,
    )

    return RequirementsResponse(
        valid=True,
        token=token,
        user_message=user_message,
        design_input=validation_dict,
        warnings=[w.message for w in result.warnings],
    )
