"""Step 01 — State Hydration.

Reads pre-validated values from DesignState and emits them as outputs
so the audit trail and downstream steps receive a clean record of
what entered the pipeline.

NL parsing and physics validation have moved to POST /requirements
(hx_engine/app/core/requirements_validator.py). By the time the
pipeline starts, inputs are guaranteed valid by the HMAC token or
inline validation in POST /design.

ai_mode = NONE — no AI review needed; inputs are already validated.
"""

from __future__ import annotations

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep


class Step01Requirements(BaseStep):
    step_id: int = 1
    step_name: str = "Process Requirements"
    ai_mode: AIModeEnum = AIModeEnum.NONE

    async def execute(self, state: DesignState) -> StepResult:
        """Read validated inputs from DesignState and emit as outputs."""
        outputs = {
            "hot_fluid_name":     state.hot_fluid_name,
            "cold_fluid_name":    state.cold_fluid_name,
            "T_hot_in_C":         state.T_hot_in_C,
            "T_hot_out_C":        state.T_hot_out_C,
            "T_cold_in_C":        state.T_cold_in_C,
            "T_cold_out_C":       state.T_cold_out_C,
            "m_dot_hot_kg_s":     state.m_dot_hot_kg_s,
            "m_dot_cold_kg_s":    state.m_dot_cold_kg_s,
            "P_hot_Pa":           state.P_hot_Pa,
            "P_cold_Pa":          state.P_cold_Pa,
            "tema_preference":    state.tema_preference,
            "missing_T_cold_out": state.T_cold_out_C is None,
            "missing_m_dot_cold": state.m_dot_cold_kg_s is None,
        }
        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=True,
        )
