"""Tests for Piece 2: _compute_Q() pure heat-duty calculation."""

from __future__ import annotations

import pytest

from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty


class TestComputeQ:
    """Six tests guarding Q = ṁ × Cp × ΔT correctness."""

    def test_Q_known_water_case(self):
        """50 kg/s water, ΔT=60°C → Q ≈ 12.54 MW.

        Hand calculation: 50 × 4181 × 60 = 12,543,000 W.
        """
        Q = Step02HeatDuty._compute_Q(
            m_dot_kg_s=50.0,
            cp_J_kgK=4181.0,
            T_in_C=90.0,
            T_out_C=30.0,
        )
        assert Q == pytest.approx(12_543_000.0, rel=1e-6)

    def test_Q_known_oil_case(self):
        """50 kg/s crude oil, Cp=1900, ΔT=60°C → Q ≈ 5.7 MW.

        Hand calculation: 50 × 1900 × 60 = 5,700,000 W.
        """
        Q = Step02HeatDuty._compute_Q(
            m_dot_kg_s=50.0,
            cp_J_kgK=1900.0,
            T_in_C=150.0,
            T_out_C=90.0,
        )
        assert Q == pytest.approx(5_700_000.0, rel=1e-6)

    def test_Q_zero_delta_T(self):
        """ΔT = 0 → Q = 0 (no heat transfer, triggers downstream hard fail)."""
        Q = Step02HeatDuty._compute_Q(
            m_dot_kg_s=50.0,
            cp_J_kgK=4181.0,
            T_in_C=100.0,
            T_out_C=100.0,
        )
        assert Q == 0.0

    def test_Q_negative_delta_T_hot(self):
        """T_hot_in < T_hot_out → Q < 0 (hot side gaining heat).

        This is physically invalid for a cooler but _compute_Q is a pure
        math function — the caller / validation layer catches it.
        """
        Q = Step02HeatDuty._compute_Q(
            m_dot_kg_s=50.0,
            cp_J_kgK=4181.0,
            T_in_C=80.0,
            T_out_C=120.0,
        )
        assert Q < 0

    def test_Q_very_large(self):
        """500 kg/s, ΔT=200°C → Q ≈ 418.1 MW.

        Must not overflow; approaches the 500 MW soft cap.
        """
        Q = Step02HeatDuty._compute_Q(
            m_dot_kg_s=500.0,
            cp_J_kgK=4181.0,
            T_in_C=250.0,
            T_out_C=50.0,
        )
        expected = 500.0 * 4181.0 * 200.0  # 418,100,000 W
        assert Q == pytest.approx(expected, rel=1e-6)
        assert Q < 500_000_000  # Below 500 MW soft cap

    def test_Q_symmetry(self):
        """Hot-side heat released equals cold-side heat absorbed.

        Compute both sides with balanced flows/Cp/ΔT and verify they match.
        """
        Q_hot = Step02HeatDuty._compute_Q(
            m_dot_kg_s=50.0,
            cp_J_kgK=1900.0,
            T_in_C=150.0,
            T_out_C=90.0,
        )
        # Cold side: m_dot_cold chosen so Q_cold = Q_hot
        # Q_hot = 5,700,000 W ⇒ m_cold = Q_hot / (Cp_cold × ΔT_cold)
        #       = 5,700,000 / (4181 × 30) = 45.44 kg/s; ΔT_cold = 30°C
        m_dot_cold = Q_hot / (4181.0 * 30.0)
        Q_cold = Step02HeatDuty._compute_Q(
            m_dot_kg_s=m_dot_cold,
            cp_J_kgK=4181.0,
            T_in_C=60.0,   # T_cold_out
            T_out_C=30.0,  # T_cold_in
        )
        assert Q_hot > 0
        assert Q_cold > 0
        assert Q_hot == pytest.approx(Q_cold, rel=1e-9)


class TestStep02BuildAiContext:
    def test_returns_expected_keys(self):
        from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
        from hx_engine.app.models.design_state import DesignState
        from hx_engine.app.models.step_result import StepResult
        step = Step02HeatDuty()
        result = StepResult(step_id=2, step_name="Heat Duty", outputs={
            "Q_hot_W": 1_000_000.0, "Q_cold_W": 980_000.0,
            "Q_W": 990_000.0, "energy_imbalance_pct": 2.0,
        })
        ctx = step.build_ai_context(DesignState(), result)
        assert "Q_hot" in ctx
        assert "Q_cold" in ctx
        assert "Q_used" in ctx
        assert "Imbalance" in ctx

    def test_handles_missing_outputs(self):
        from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
        from hx_engine.app.models.design_state import DesignState
        from hx_engine.app.models.step_result import StepResult
        ctx = Step02HeatDuty().build_ai_context(DesignState(), StepResult(step_id=2, step_name="S", outputs={}))
        assert ctx == ""
