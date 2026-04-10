"""Tests for Step06InitialU execute() and geometry updates.

Physics invariants enforced in every test:
  - A_required = Q_W / (U_mid × F × LMTD)
  - N_tubes_required = ceil(A_required / (π × d_o × L))
  - Tube OD, tube length, pitch layout, n_passes are NEVER changed by Step 6
  - U_mid comes from fluid-pair lookup table
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_06_initial_u import Step06InitialU


def _make_geometry(**overrides) -> GeometrySpec:
    """Standard Step 4 geometry — 3/4" tubes, triangular pitch, 2-pass."""
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        shell_diameter_m=0.489,
        n_tubes=158,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _make_state(
    hot_fluid="water",
    cold_fluid="water",
    Q_W=1_000_000.0,
    LMTD_K=30.0,
    F_factor=0.9,
    geometry=None,
    hot_props=None,
    cold_props=None,
    shell_side_fluid="hot",
    **kwargs,
) -> DesignState:
    """Create a DesignState pre-populated through Step 5."""
    if geometry is None:
        geometry = _make_geometry()
    return DesignState(
        hot_fluid_name=hot_fluid,
        cold_fluid_name=cold_fluid,
        Q_W=Q_W,
        LMTD_K=LMTD_K,
        F_factor=F_factor,
        geometry=geometry,
        hot_fluid_props=hot_props,
        cold_fluid_props=cold_props,
        shell_side_fluid=shell_side_fluid,
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        **kwargs,
    )


@pytest.fixture
def step():
    return Step06InitialU()


class TestStep06Execute:

    @pytest.mark.asyncio
    async def test_happy_path_water_water(self, step):
        """Water/water pair → U ~1200, area computed, shell found."""
        state = _make_state(hot_fluid="water", cold_fluid="water")
        result = await step.execute(state)

        U_mid = result.outputs["U_W_m2K"]
        assert U_mid == 1200  # water/water → U_mid = 1200

        # Verify area formula
        eff_LMTD = state.F_factor * state.LMTD_K  # was 0.9 * 30 = 27
        A_expected = state.Q_W / (U_mid * eff_LMTD)
        assert result.outputs["A_m2"] == pytest.approx(A_expected, rel=1e-6)

        # Shell was selected
        assert result.outputs["geometry"].n_tubes is not None
        assert result.outputs["geometry"].shell_diameter_m is not None

    @pytest.mark.asyncio
    async def test_happy_path_crude_oil_water(self, step):
        """Crude oil / cooling water → U ~300."""
        state = _make_state(hot_fluid="crude oil", cold_fluid="cooling water")
        result = await step.execute(state)

        assert result.outputs["U_W_m2K"] == 300  # crude/water → U_mid = 300
        assert result.outputs["A_m2"] > 0
        assert result.outputs["hot_fluid_type"] == "crude"
        assert result.outputs["cold_fluid_type"] == "water"

    @pytest.mark.asyncio
    async def test_lube_oil_water_uses_viscous_oil_u(self, step):
        """Lube oil / cooling water → U = 60 (viscous_oil), not 300 (heavy_organic)."""
        state = _make_state(hot_fluid="lubricating oil", cold_fluid="cooling water")
        result = await step.execute(state)

        assert result.outputs["U_W_m2K"] == 60
        assert result.outputs["hot_fluid_type"] == "viscous_oil"
        assert result.outputs["cold_fluid_type"] == "water"

    @pytest.mark.asyncio
    async def test_lube_oil_water_area_derived_from_u(self, step):
        """Area is derived from U = 60, not the heavy_organic U = 300."""
        state = _make_state(hot_fluid="lubricating oil", cold_fluid="cooling water")
        result = await step.execute(state)

        eff_LMTD = state.F_factor * state.LMTD_K
        A_expected = state.Q_W / (60 * eff_LMTD)
        assert result.outputs["A_m2"] == pytest.approx(A_expected, rel=1e-6)

    @pytest.mark.asyncio
    async def test_ethylene_glycol_water_unchanged(self, step):
        """Ethylene glycol / water → U = 300 (heavy_organic, not viscous_oil)."""
        state = _make_state(hot_fluid="ethylene glycol", cold_fluid="water")
        result = await step.execute(state)

        assert result.outputs["U_W_m2K"] == 300
        assert result.outputs["hot_fluid_type"] == "heavy_organic"

    @pytest.mark.asyncio
    async def test_gas_gas_pair(self, step):
        """Gas/gas → very low U (~25) → large area."""
        state = _make_state(
            hot_fluid="air",
            cold_fluid="nitrogen",
            Q_W=100_000.0,  # 100 kW
        )
        result = await step.execute(state)

        U_mid = result.outputs["U_W_m2K"]
        assert U_mid == 25  # gas/gas → U_mid = 25
        # Area should be much larger due to low U
        eff_LMTD = 0.9 * 30.0
        A_expected = 100_000.0 / (25 * eff_LMTD)
        assert result.outputs["A_m2"] == pytest.approx(A_expected, rel=1e-6)
        assert A_expected > 100  # large area

    @pytest.mark.asyncio
    async def test_precondition_missing_Q_W(self, step):
        """Missing Q_W → CalculationError."""
        state = _make_state(Q_W=None)
        with pytest.raises(CalculationError, match="Q_W"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_precondition_missing_geometry(self, step):
        """Missing geometry → CalculationError."""
        state = DesignState(
            hot_fluid_name="water",
            cold_fluid_name="water",
            Q_W=1e6,
            LMTD_K=30.0,
            F_factor=0.9,
        )
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_precondition_missing_LMTD(self, step):
        """Missing LMTD_K → CalculationError."""
        state = _make_state(LMTD_K=None)
        with pytest.raises(CalculationError, match="LMTD_K"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_precondition_missing_F_factor(self, step):
        """Missing F_factor → CalculationError."""
        state = _make_state(F_factor=None)
        with pytest.raises(CalculationError, match="F_factor"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_precondition_missing_hot_fluid_name(self, step):
        """Missing hot_fluid_name → CalculationError."""
        state = _make_state(hot_fluid=None)
        with pytest.raises(CalculationError, match="hot_fluid_name"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_precondition_missing_cold_fluid_name(self, step):
        """Missing cold_fluid_name → CalculationError."""
        state = _make_state(cold_fluid=None)
        with pytest.raises(CalculationError, match="cold_fluid_name"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_small_exchanger(self, step):
        """High U + small Q → tiny area → smallest shell."""
        state = _make_state(
            hot_fluid="steam",
            cold_fluid="water",
            Q_W=10_000.0,  # 10 kW
            LMTD_K=50.0,
            F_factor=1.0,
        )
        result = await step.execute(state)

        U_mid = result.outputs["U_W_m2K"]
        assert U_mid == 2500  # steam/water
        A = result.outputs["A_m2"]
        assert A < 1.0  # very small area
        assert A == pytest.approx(10_000.0 / (2500 * 50.0), rel=1e-6)

    @pytest.mark.asyncio
    async def test_outputs_populated(self, step):
        """All expected outputs present in result."""
        state = _make_state()
        result = await step.execute(state)

        assert "U_W_m2K" in result.outputs
        assert "A_m2" in result.outputs
        assert "U_range" in result.outputs
        assert "hot_fluid_type" in result.outputs
        assert "cold_fluid_type" in result.outputs
        assert "n_tubes_required" in result.outputs
        assert "A_provided_m2" in result.outputs
        assert "geometry" in result.outputs

        # U_range has expected keys
        u_range = result.outputs["U_range"]
        assert "U_low" in u_range
        assert "U_mid" in u_range
        assert "U_high" in u_range

    @pytest.mark.asyncio
    async def test_geometry_updated_correctly(self, step):
        """n_tubes, shell_diameter_m overwritten; tube_od_m, tube_length_m preserved."""
        state = _make_state()
        original_od = state.geometry.tube_od_m
        original_length = state.geometry.tube_length_m
        original_pitch = state.geometry.pitch_layout
        original_passes = state.geometry.n_passes
        original_pitch_ratio = state.geometry.pitch_ratio
        original_baffle_cut = state.geometry.baffle_cut

        result = await step.execute(state)

        updated_geom = result.outputs["geometry"]
        # Preserved fields
        assert updated_geom.tube_od_m == original_od
        assert updated_geom.tube_length_m == original_length
        assert updated_geom.pitch_layout == original_pitch
        assert updated_geom.n_passes == original_passes
        assert updated_geom.pitch_ratio == original_pitch_ratio
        assert updated_geom.baffle_cut == original_baffle_cut

        # Updated fields
        assert updated_geom.n_tubes is not None
        assert updated_geom.n_tubes >= 1
        assert updated_geom.shell_diameter_m is not None
        assert updated_geom.shell_diameter_m > 0
        assert updated_geom.baffle_spacing_m is not None

    @pytest.mark.asyncio
    async def test_state_updated_after_execute(self, step):
        """State fields U_W_m2K, A_m2, geometry are written during execute."""
        state = _make_state()
        await step.execute(state)

        assert state.U_W_m2K is not None
        assert state.U_W_m2K > 0
        assert state.A_m2 is not None
        assert state.A_m2 > 0
        assert state.geometry.n_tubes is not None

    @pytest.mark.asyncio
    async def test_a_provided_ge_a_required(self, step):
        """A_provided should be >= A_required (TEMA rounding up)."""
        state = _make_state()
        result = await step.execute(state)

        A_req = result.outputs["A_m2"]
        A_prov = result.outputs["A_provided_m2"]
        # A_provided may be less than A_required only if at max shell
        n_req = result.outputs["n_tubes_required"]
        geom = result.outputs["geometry"]
        if geom.n_tubes >= n_req:
            assert A_prov >= A_req - 0.01  # small tolerance

    @pytest.mark.asyncio
    async def test_effective_lmtd_zero_raises(self, step):
        """F * LMTD = 0 → CalculationError."""
        state = _make_state(F_factor=0.0, LMTD_K=30.0)
        with pytest.raises(CalculationError, match="Effective LMTD"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_fallback_fluid_pair_warns(self, step):
        """Unknown fluid pair → fallback U → warning."""
        state = _make_state(
            hot_fluid="some_exotic_fluid",
            cold_fluid="another_unknown_fluid",
        )
        result = await step.execute(state)

        assert any("fallback" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_baffle_spacing_viscous_shell(self, step):
        """Viscous shell-side fluid → baffle spacing = 0.5 × shell diameter."""
        hot_props = FluidProperties(
            density_kg_m3=900.0,
            viscosity_Pa_s=0.01,  # > 0.001 → viscous
            cp_J_kgK=2000.0,
            k_W_mK=0.14,
            Pr=142.9,
        )
        state = _make_state(
            hot_fluid="crude oil",
            cold_fluid="cooling water",
            hot_props=hot_props,
            shell_side_fluid="hot",
        )
        result = await step.execute(state)

        geom = result.outputs["geometry"]
        expected_baffle = 0.5 * geom.shell_diameter_m
        expected_baffle = max(0.05, min(2.0, expected_baffle))
        assert geom.baffle_spacing_m == pytest.approx(expected_baffle, rel=1e-6)

    @pytest.mark.asyncio
    async def test_baffle_spacing_clean_shell(self, step):
        """Clean shell-side fluid → baffle spacing = 0.4 × shell diameter."""
        cold_props = FluidProperties(
            density_kg_m3=998.0,
            viscosity_Pa_s=0.001,  # = 0.001 → not viscous
            cp_J_kgK=4180.0,
            k_W_mK=0.6,
            Pr=7.0,
        )
        state = _make_state(
            hot_fluid="water",
            cold_fluid="water",
            cold_props=cold_props,
            shell_side_fluid="cold",
        )
        result = await step.execute(state)

        geom = result.outputs["geometry"]
        expected_baffle = 0.4 * geom.shell_diameter_m
        expected_baffle = max(0.05, min(2.0, expected_baffle))
        assert geom.baffle_spacing_m == pytest.approx(expected_baffle, rel=1e-6)


class TestFE3AreaUncertaintyBand:
    """FE-3: area uncertainty band when tube-side confidence < 0.80."""

    @pytest.mark.asyncio
    async def test_band_computed_for_low_confidence(self, step):
        """Low tube-side confidence → A_required_low/high set on state."""
        hot_props = FluidProperties(
            density_kg_m3=870, viscosity_Pa_s=0.02,
            cp_J_kgK=2100, k_W_mK=0.13, Pr=300.0,
            property_source="petroleum-generic",
            property_confidence=0.65,
        )
        # hot is tube-side (shell_side_fluid="cold")
        state = _make_state(
            hot_fluid="lube oil",
            cold_fluid="water",
            hot_props=hot_props,
            shell_side_fluid="cold",
        )
        result = await step.execute(state)

        assert state.A_required_low_m2 is not None
        assert state.A_required_high_m2 is not None
        assert state.A_required_low_m2 < state.A_m2
        assert state.A_required_high_m2 > state.A_m2

    @pytest.mark.asyncio
    async def test_band_formula_correctness(self, step):
        """Band = A / (1 ± (1 - conf) × 0.25)."""
        conf = 0.65
        hot_props = FluidProperties(
            density_kg_m3=870, viscosity_Pa_s=0.02,
            cp_J_kgK=2100, k_W_mK=0.13, Pr=300.0,
            property_confidence=conf,
        )
        state = _make_state(
            hot_fluid="lube oil",
            cold_fluid="water",
            hot_props=hot_props,
            shell_side_fluid="cold",
        )
        await step.execute(state)

        unc = (1.0 - conf) * 0.25
        import math
        assert state.A_required_low_m2 == pytest.approx(state.A_m2 / (1.0 + unc), rel=1e-6)
        assert state.A_required_high_m2 == pytest.approx(state.A_m2 / (1.0 - unc), rel=1e-6)

    @pytest.mark.asyncio
    async def test_no_band_for_high_confidence(self, step):
        """Confidence >= 0.80 → no band (A_required_low/high remain None)."""
        hot_props = FluidProperties(
            density_kg_m3=990, viscosity_Pa_s=0.0008,
            cp_J_kgK=4186, k_W_mK=0.6, Pr=5.6,
            property_confidence=0.95,
        )
        state = _make_state(
            hot_fluid="water",
            cold_fluid="water",
            hot_props=hot_props,
            shell_side_fluid="cold",
        )
        await step.execute(state)

        assert state.A_required_low_m2 is None
        assert state.A_required_high_m2 is None

    @pytest.mark.asyncio
    async def test_no_band_when_tube_props_none(self, step):
        """tube_side_fluid_props=None → no crash, no band."""
        state = _make_state(
            hot_fluid="lube oil",
            cold_fluid="water",
            hot_props=None,  # no props
            shell_side_fluid="cold",
        )
        await step.execute(state)

        assert state.A_required_low_m2 is None
        assert state.A_required_high_m2 is None

    @pytest.mark.asyncio
    async def test_band_appears_in_outputs(self, step):
        """A_required_low/high_m2 appear in step outputs."""
        hot_props = FluidProperties(
            density_kg_m3=870, viscosity_Pa_s=0.02,
            cp_J_kgK=2100, k_W_mK=0.13, Pr=300.0,
            property_confidence=0.65,
        )
        state = _make_state(
            hot_fluid="lube oil",
            cold_fluid="water",
            hot_props=hot_props,
            shell_side_fluid="cold",
        )
        result = await step.execute(state)

        assert "A_required_low_m2" in result.outputs
        assert "A_required_high_m2" in result.outputs
        assert result.outputs["A_required_low_m2"] is not None


class TestFE2AreaAugment:
    """FE-2 area augment in Step 6: Rf scenario area impact percentages."""

    @pytest.mark.asyncio
    async def test_area_impact_warning_emitted(self, step):
        """Lube oil at lower-bound Rf + low confidence → area impact warning."""
        hot_props = FluidProperties(
            density_kg_m3=870, viscosity_Pa_s=0.02,
            cp_J_kgK=2100, k_W_mK=0.13, Pr=300.0,
            property_source="petroleum-generic",
            property_confidence=0.65,
        )
        state = _make_state(
            hot_fluid="lube oil",
            cold_fluid="water",
            hot_props=hot_props,
            shell_side_fluid="cold",
            R_f_hot_m2KW=0.000176,  # at lower bound
        )
        result = await step.execute(state)

        all_warnings = result.warnings + state.warnings
        assert any("scenario area impact" in w for w in all_warnings)
        # All three scenarios listed
        impact_warnings = [w for w in all_warnings if "scenario area impact" in w]
        assert any("(1)" in w and "(2)" in w and "(3)" in w for w in impact_warnings)

    @pytest.mark.asyncio
    async def test_no_area_impact_when_rf_above_lower_bound(self, step):
        """Rf above lower bound → no area impact warning."""
        hot_props = FluidProperties(
            density_kg_m3=870, viscosity_Pa_s=0.02,
            cp_J_kgK=2100, k_W_mK=0.13, Pr=300.0,
            property_confidence=0.65,
        )
        state = _make_state(
            hot_fluid="lube oil",
            cold_fluid="water",
            hot_props=hot_props,
            shell_side_fluid="cold",
            R_f_hot_m2KW=0.000352,  # above lower bound (0.000176)
        )
        result = await step.execute(state)

        all_warnings = result.warnings + state.warnings
        assert not any("scenario area impact" in w for w in all_warnings)
