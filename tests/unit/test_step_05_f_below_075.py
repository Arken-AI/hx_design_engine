"""Tests for Step 05 F-factor < 0.75 scenarios.

Research-backed test cases using real fluid pairs whose temperature
configurations produce F < 0.75 in 1-2 TEMA exchangers.

Physical explanation: The Bowman (1940) F-factor formula hits a domain
violation (denominator argument ≤ 0) when thermal effectiveness P is
too high relative to R — i.e., close-approach or near-temperature-cross
configurations. In these cases, compute_f_factor() returns 0.0.

Fluid pairs tested (all with n_passes=2, shell_passes=1):
  1. Ethanol / Water   — 80→50°C hot, 45→65°C cold  (R=1.50, P=0.571)
  2. Glycol  / Water   — 60→30°C hot, 25→50°C cold  (R=1.20, P=0.714)
  3. Crude   / Water   — 120→60°C hot, 55→90°C cold (R=1.71, P=0.538)
  4. DEG     / Water   — 95→55°C hot, 50→75°C cold  (R=1.60, P=0.556)
  5. AcOH    / AcOH    — 120→80°C hot, 75→100°C cold (R=1.60, P=0.556)
  6. Auto-correction   — 100→20.5°C hot, 0→26.5°C cold (R=3.0, P=0.265)
     F_1shell=0.706 (<0.75), F_2shell=0.946 — auto-corrects to 2 shells
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.correlations.lmtd import compute_f_factor
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, GeometrySpec
from hx_engine.app.steps.step_05_lmtd import Step05LMTD


# ---------------------------------------------------------------------------
# Shared geometry (realistic TEMA geometry, n_passes=2)
# ---------------------------------------------------------------------------

def _geom(shell_passes: int = 1) -> GeometrySpec:
    return GeometrySpec(
        n_passes=2,
        shell_passes=shell_passes,
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        shell_diameter_m=0.489,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        n_tubes=158,
    )


def _state(
    T_hot_in: float,
    T_hot_out: float,
    T_cold_in: float,
    T_cold_out: float,
    shell_passes: int = 1,
    Q_W: float = 1_000_000.0,
) -> DesignState:
    return DesignState(
        T_hot_in_C=T_hot_in,
        T_hot_out_C=T_hot_out,
        T_cold_in_C=T_cold_in,
        T_cold_out_C=T_cold_out,
        Q_W=Q_W,
        geometry=_geom(shell_passes),
    )


@pytest.fixture
def step() -> Step05LMTD:
    return Step05LMTD()


# ===========================================================================
# Section A: Pure F-factor math — verify domain violations return 0.0
# ===========================================================================

class TestFFactorDomainViolations:
    """Verify compute_f_factor returns 0.0 for known infeasible R/P pairs."""

    # R=1.50, P=0.571 — ethanol/water  (B < 0 in Bowman formula)
    def test_ethanol_water_r150_p0571_1shell_zero(self):
        F = compute_f_factor(1.50, 0.571, n_shell_passes=1)
        assert F == pytest.approx(0.0, abs=1e-6), (
            f"Expected domain violation (F=0.0), got F={F:.4f}"
        )

    def test_ethanol_water_r150_p0571_2shell_below_075(self):
        F = compute_f_factor(1.50, 0.571, n_shell_passes=2)
        assert F < 0.75, f"F_2shell={F:.4f} should be < 0.75"
        assert F > 0.0, f"F_2shell={F:.4f} should be a valid non-zero value"
        # Analytically computed: R=1.5, P=0.571 equivalent single-shell P₁≈0.458
        assert F == pytest.approx(0.496, abs=0.01)

    # R=1.20, P=0.714 — glycol/water  (both shells infeasible)
    def test_glycol_water_r120_p0714_1shell_zero(self):
        F = compute_f_factor(1.20, 0.714, n_shell_passes=1)
        assert F == pytest.approx(0.0, abs=1e-6)

    def test_glycol_water_r120_p0714_2shell_also_zero(self):
        """Both shell configurations infeasible for glycol/water."""
        F = compute_f_factor(1.20, 0.714, n_shell_passes=2)
        assert F == pytest.approx(0.0, abs=1e-6)

    # R=1.714, P=0.538 — crude/water near temperature cross
    def test_crude_water_cross_r171_p0538_1shell_zero(self):
        F = compute_f_factor(1.714, 0.538, n_shell_passes=1)
        assert F == pytest.approx(0.0, abs=1e-6)

    def test_crude_water_cross_r171_p0538_2shell_zero(self):
        F = compute_f_factor(1.714, 0.538, n_shell_passes=2)
        assert F == pytest.approx(0.0, abs=1e-6)

    # R=3.0, P=0.265 — borderline case: 1-shell F below 0.75, 2-shell F > 0.75
    def test_r3_p0265_1shell_below_075(self):
        F = compute_f_factor(3.0, 0.265, n_shell_passes=1)
        assert 0.0 < F < 0.75, f"Expected 0 < F < 0.75, got {F:.4f}"
        assert F == pytest.approx(0.706, abs=0.005)

    def test_r3_p0265_2shell_above_075(self):
        """2-shell pass rescues the design for R=3, P=0.265."""
        F = compute_f_factor(3.0, 0.265, n_shell_passes=2)
        assert F >= 0.75, f"Expected F >= 0.75 with 2 shells, got {F:.4f}"
        assert F == pytest.approx(0.946, abs=0.005)


# ===========================================================================
# Section B: Step 05 execute() with F < 0.75 scenarios
# ===========================================================================

class TestStep05FBelow075Execute:
    """Integration tests for Step05LMTD.execute() with infeasible temperatures.

    These cases now correctly raise CalculationError since
    F=0.0 domain violations and infeasible F values (<0.75) must
    not flow silently through the pipeline.
    """

    # --- Case 1: Ethanol/Water (F_1=0.0 domain, F_2=0.488) ---

    @pytest.mark.asyncio
    async def test_ethanol_water_raises_calculation_error(self, step):
        """Step must raise CalculationError for infeasible F-factor."""
        state = _state(80, 50, 45, 65)
        with pytest.raises(CalculationError, match="infeasible"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_ethanol_water_error_message_has_r_and_p(self, step):
        """Error message must contain R and P values for diagnostics."""
        state = _state(80, 50, 45, 65)
        with pytest.raises(CalculationError) as exc_info:
            await step.execute(state)
        msg = str(exc_info.value)
        assert "R=" in msg
        assert "P=" in msg

    @pytest.mark.asyncio
    async def test_ethanol_water_error_mentions_domain_violation(self, step):
        """Error message must indicate domain violation for F_1shell=0.0."""
        state = _state(80, 50, 45, 65)
        with pytest.raises(CalculationError) as exc_info:
            await step.execute(state)
        assert "domain violation" in str(exc_info.value).lower()

    # --- Case 2: Glycol/Water (F_1=0, F_2=0 — both domain violations) ---

    @pytest.mark.asyncio
    async def test_glycol_water_both_shells_raise(self, step):
        """Glycol/water: both shell configs are domain violations → raises."""
        state = _state(60, 30, 25, 50)
        with pytest.raises(CalculationError, match="infeasible"):
            await step.execute(state)

    # --- Case 3: Crude Oil/Water near-temperature-cross ---

    @pytest.mark.asyncio
    async def test_crude_water_near_cross_raises(self, step):
        """120→60°C crude, 55→90°C water: near temperature cross → raises."""
        state = _state(120, 60, 55, 90)
        with pytest.raises(CalculationError, match="infeasible"):
            await step.execute(state)

    # --- Case 4: DEG/Water (common industrial coolant pair) ---

    @pytest.mark.asyncio
    async def test_deg_water_tight_approach_raises(self, step):
        """95→55°C DEG, 50→75°C water: F infeasible → raises."""
        state = _state(95, 55, 50, 75)
        with pytest.raises(CalculationError, match="infeasible"):
            await step.execute(state)

    # --- Case 5: Acetic Acid / Acetic Acid heat recovery ---

    @pytest.mark.asyncio
    async def test_acetic_acid_heat_recovery_raises(self, step):
        """120→80°C acetic acid, 75→100°C acetic acid: R=1.6, P=0.556 → raises."""
        state = _state(120, 80, 75, 100)
        with pytest.raises(CalculationError, match="infeasible"):
            await step.execute(state)


# ===========================================================================
# Section C: Auto-correction path for F_1shell < 0.75 but F_2shell >= 0.75
# ===========================================================================

class TestStep05AutoCorrectionF1Below075:
    """When F_1shell < 0.75 but F_2shell >= 0.75, auto-correction must trigger."""

    @pytest.mark.asyncio
    async def test_r3_p0265_auto_corrects_to_2_shells(self, step):
        """R=3.0, P=0.265: F_1=0.706 (<0.75), F_2=0.946 (>0.75) → must auto-correct."""
        # T_hot: 100→20.5°C, T_cold: 0→26.5°C
        # R = (100-20.5)/(26.5-0) = 79.5/26.5 = 3.0
        # P = (26.5-0)/(100-0) = 0.265
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)

        assert result.outputs["auto_corrected"] is True, (
            "Expected auto-correction to 2 shell passes when F_1<0.75 but F_2>=0.75"
        )
        assert result.outputs["shell_passes"] == 2
        assert result.outputs["F_factor"] >= 0.75, (
            f"After auto-correction, F must be >= 0.75, got {result.outputs['F_factor']:.4f}"
        )
        assert state.geometry.shell_passes == 2, "Geometry must be updated to 2 shell passes"

    @pytest.mark.asyncio
    async def test_r3_p0265_corrected_f_near_0946(self, step):
        """After auto-correction, F_factor should be ≈ 0.946."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        assert result.outputs["F_factor"] == pytest.approx(0.946, abs=0.01)

    @pytest.mark.asyncio
    async def test_r3_p0265_warning_mentions_shell_increase(self, step):
        """Warning should mention the shell pass change (F improved)."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        has_shell_warning = any(
            "shell" in w.lower() or "2 shell" in w.lower()
            for w in result.warnings
        )
        assert has_shell_warning, f"Expected shell-pass warning, got: {result.warnings}"

    @pytest.mark.asyncio
    async def test_r3_p0265_effective_lmtd_nonzero(self, step):
        """After auto-correction, effective_LMTD must be > 0."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        assert result.outputs["effective_LMTD"] > 0, (
            f"effective_LMTD = {result.outputs['effective_LMTD']:.4f} after correction"
        )

    @pytest.mark.asyncio
    async def test_r3_p0265_ai_trigger_fires(self, step):
        """F_1shell < 0.85 should trigger the AI conditional check."""
        state = _state(100, 20.5, 0, 26.5)
        await step.execute(state)
        # After execute, _F_factor is cached on step
        assert step._conditional_ai_trigger(state) is True or \
               step._F_factor < 0.85, "AI should be triggered for borderline F"


# ===========================================================================
# Section D: Physics invariants must hold even when F < 0.75
# ===========================================================================

class TestStep05FBelow075PhysicsInvariants:
    """Physics invariants that must hold regardless of F value."""

    @pytest.mark.asyncio
    async def test_effective_lmtd_equals_f_times_lmtd(self, step):
        """effective_LMTD = F_factor × LMTD_K must always hold exactly.
        Use the auto-correctable case (R=3, P=0.265) which succeeds."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        expected = result.outputs["F_factor"] * result.outputs["LMTD_K"]
        assert result.outputs["effective_LMTD"] == pytest.approx(expected, rel=1e-10)

    @pytest.mark.asyncio
    async def test_lmtd_positive_for_feasible_case(self, step):
        """LMTD must be > 0 for the auto-correctable borderline case."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        assert result.outputs["LMTD_K"] > 0

    @pytest.mark.asyncio
    async def test_infeasible_cases_raise_calculation_error(self, step):
        """All infeasible cases must raise CalculationError, not flow through."""
        infeasible_cases = [
            (80, 50, 45, 65),   # ethanol/water
            (60, 30, 25, 50),   # glycol/water
            (120, 60, 55, 90),  # crude/water
            (95, 55, 50, 75),   # DEG/water
            (120, 80, 75, 100), # acetic acid
        ]
        for temps in infeasible_cases:
            s = _state(*temps)
            with pytest.raises(CalculationError):
                await step.execute(s)

    @pytest.mark.asyncio
    async def test_f_factor_in_0_to_1_for_feasible(self, step):
        """F_factor must be in [0, 1] for the auto-correctable case."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        F = result.outputs["F_factor"]
        assert 0.0 <= F <= 1.0

    @pytest.mark.asyncio
    async def test_temperatures_unchanged_infeasible(self, step):
        """Step 05 must never modify temps even when it raises."""
        state = _state(80, 50, 45, 65)
        with pytest.raises(CalculationError):
            await step.execute(state)
        assert state.T_hot_in_C == 80.0
        assert state.T_hot_out_C == 50.0
        assert state.T_cold_in_C == 45.0
        assert state.T_cold_out_C == 65.0

    @pytest.mark.asyncio
    async def test_q_w_unchanged_infeasible(self, step):
        """Step 05 must never modify Q_W even when it raises."""
        state = _state(80, 50, 45, 65, Q_W=2_500_000.0)
        with pytest.raises(CalculationError):
            await step.execute(state)
        assert state.Q_W == 2_500_000.0

    @pytest.mark.asyncio
    async def test_r_positive_when_computed(self, step):
        """R must be > 0 for the feasible auto-corrected case."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        R = result.outputs.get("R")
        if R is not None:
            assert R > 0, f"R={R:.4f} must be > 0"

    @pytest.mark.asyncio
    async def test_p_in_valid_range_when_computed(self, step):
        """P must be in (0, 1) for the feasible auto-corrected case."""
        state = _state(100, 20.5, 0, 26.5)
        result = await step.execute(state)
        P = result.outputs.get("P")
        if P is not None:
            assert 0 < P < 1, f"P={P:.4f} must be in (0, 1)"


# ===========================================================================
# Section E: Validation rule behavior for F < 0.75
# ===========================================================================

class TestStep05ValidationRuleF075:
    """Verify the validation rule correctly flags F < 0.75."""

    def test_rule_catches_f_zero(self):
        """F_factor=0.0 must fail _rule_f_factor_minimum."""
        from hx_engine.app.core.validation_rules import check, clear_rules
        from hx_engine.app.models.step_result import StepResult
        import hx_engine.app.steps.step_05_rules  # noqa: F401 (triggers registration)
        from hx_engine.app.steps.step_05_rules import register_step5_rules

        clear_rules()
        register_step5_rules()

        result = StepResult(
            step_id=5,
            step_name="LMTD & F-Factor",
            outputs={
                "LMTD_K": 9.10, "F_factor": 0.0,
                "effective_LMTD": 0.0, "R": 1.5, "P": 0.571,
                "shell_passes": 1, "auto_corrected": False,
            },
        )
        vr = check(5, result)
        assert not vr.passed, "Rule check must fail for F=0.0"
        assert any("< 0.75" in e for e in vr.errors), (
            f"Expected '< 0.75' in errors, got: {vr.errors}"
        )
        clear_rules()

    def test_rule_catches_f_0488(self):
        """F_factor=0.488 must fail — below 0.75 infeasibility threshold."""
        from hx_engine.app.core.validation_rules import check, clear_rules
        from hx_engine.app.models.step_result import StepResult
        from hx_engine.app.steps.step_05_rules import register_step5_rules

        clear_rules()
        register_step5_rules()

        result = StepResult(
            step_id=5,
            step_name="LMTD & F-Factor",
            outputs={
                "LMTD_K": 9.10, "F_factor": 0.488,
                "effective_LMTD": 4.44, "R": 1.5, "P": 0.571,
                "shell_passes": 2, "auto_corrected": False,
            },
        )
        vr = check(5, result)
        assert not vr.passed
        clear_rules()

    def test_rule_passes_f_exactly_075(self):
        """F_factor=0.75 is exactly at the boundary — must pass."""
        from hx_engine.app.core.validation_rules import check, clear_rules
        from hx_engine.app.models.step_result import StepResult
        from hx_engine.app.steps.step_05_rules import register_step5_rules

        clear_rules()
        register_step5_rules()

        result = StepResult(
            step_id=5,
            step_name="LMTD & F-Factor",
            outputs={
                "LMTD_K": 30.0, "F_factor": 0.75,
                "effective_LMTD": 22.5, "R": 2.0, "P": 0.3,
                "shell_passes": 1, "auto_corrected": False,
            },
        )
        vr = check(5, result)
        assert vr.passed, f"F=0.75 exactly should pass, errors: {vr.errors}"
        clear_rules()

    def test_rule_passes_f_0706_after_autocorrection(self):
        """F_factor=0.706 (R=3, P=0.265 1-shell) fails; only auto-corrected 0.946 should appear in pipeline."""
        from hx_engine.app.core.validation_rules import check, clear_rules
        from hx_engine.app.models.step_result import StepResult
        from hx_engine.app.steps.step_05_rules import register_step5_rules

        clear_rules()
        register_step5_rules()

        # Before auto-correction (1-shell F=0.706): would fail
        result = StepResult(
            step_id=5,
            step_name="LMTD & F-Factor",
            outputs={
                "LMTD_K": 41.51, "F_factor": 0.706,
                "effective_LMTD": 29.31, "R": 3.0, "P": 0.265,
                "shell_passes": 1, "auto_corrected": False,
            },
        )
        vr_before = check(5, result)
        assert not vr_before.passed, "F=0.706 is below minimum, must fail before correction"

        # After auto-correction (2-shell F=0.946): passes
        result.outputs["F_factor"] = 0.946
        result.outputs["shell_passes"] = 2
        result.outputs["auto_corrected"] = True
        result.outputs["effective_LMTD"] = 0.946 * 41.51

        vr_after = check(5, result)
        assert vr_after.passed, f"F=0.946 after correction must pass; errors: {vr_after.errors}"
        clear_rules()


# ===========================================================================
# Section F: AI trigger behavior for F < 0.75 scenarios
# ===========================================================================

class TestStep05AITriggerFBelow075:
    """AI trigger must fire for all F < 0.75 cases."""

    @pytest.mark.asyncio
    async def test_ai_triggered_ethanol_water(self, step):
        """F=0.0 (domain violation) raises, so test AI trigger via direct state."""
        step._F_factor = 0.0
        step._R = 1.5
        step._auto_corrected = False
        state = _state(80, 50, 45, 65)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_triggered_glycol_water(self, step):
        """Both shell configs are domain violations → test AI trigger directly."""
        step._F_factor = 0.0
        step._R = 1.2
        step._auto_corrected = False
        state = _state(60, 30, 25, 50)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_triggered_crude_water_cross(self, step):
        """Near temperature cross → test AI trigger directly."""
        step._F_factor = 0.0
        step._R = 1.714
        step._auto_corrected = False
        state = _state(120, 60, 55, 90)
        assert step._conditional_ai_trigger(state) is True

    def test_ai_trigger_direct_f_zero(self, step):
        """Setting _F_factor=0.0 directly triggers AI."""
        step._F_factor = 0.0
        step._R = 1.5
        step._auto_corrected = False
        state = _state(80, 50, 45, 65)
        assert step._conditional_ai_trigger(state) is True

    def test_ai_trigger_direct_f_0488(self, step):
        """F=0.488 (below 0.85, no auto-correction) triggers AI."""
        step._F_factor = 0.488
        step._R = 1.5
        step._auto_corrected = False
        state = _state(80, 50, 45, 65)
        assert step._conditional_ai_trigger(state) is True

    def test_ai_trigger_f_0706_no_correction(self, step):
        """F=0.706, no auto-correction: triggers AI (F < 0.85)."""
        step._F_factor = 0.706
        step._R = 3.0
        step._auto_corrected = False
        state = _state(100, 20.5, 0, 26.5)
        assert step._conditional_ai_trigger(state) is True

    def test_ai_no_trigger_after_good_autocorrection(self, step):
        """F=0.88 after auto-correction, approach=35°C, R=2.0: no AI trigger.

        Use benchmark temps (150→90°C hot, 30→55°C cold) so approach=35°C > 3°C.
        F=0.88 is >= 0.80 with auto_corrected=True → trigger 1 is False.
        R=2.0 <= 4.0 → trigger 2 is False. approach=35°C → trigger 3 is False.
        """
        step._F_factor = 0.88
        step._R = 2.0
        step._auto_corrected = True
        # approach = T_hot_out - T_cold_out = 90 - 55 = 35°C (well above 3°C)
        state = _state(150, 90, 30, 55, shell_passes=2)
        assert step._conditional_ai_trigger(state) is False
