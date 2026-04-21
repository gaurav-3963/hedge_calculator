"""
Tests for calculations.py — all golden numbers verified against reference Excel.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal, getcontext

import pytest

getcontext().prec = 28

from calculations import (
    compute_period,
    cumulative_lower_of,
    discount_factor,
    dollar_offset_ratio,
    fair_value,
    hypothetical_derivative,
)
from models import Direction, PeriodInput
from tests.fixtures import (
    HEDGE_BUY,
    HEDGE_SELL,
    P1_INPUT,
    P2_INPUT,
    P3_INPUT,
    PETRO_APR,
    PETRO_FEB,
    PETRO_JUN,
    PETRO_MAR,
    PETRO_MAY,
    PETRO_GOLDEN,
)

_ZERO = Decimal("0")
_ONE = Decimal("1")

_INIT_STATE = dict(
    prev_fv=_ZERO,
    prev_hyp=_ZERO,
    prev_cum_delta_fv=_ZERO,
    prev_cum_delta_hyp=_ZERO,
    prev_cum_effective=_ZERO,
    prev_cum_ineffective=_ZERO,
)


# ── discount_factor ───────────────────────────────────────────────────────────

class TestDiscountFactor:
    def test_zero_rate_returns_one(self):
        # Simplified mode: any days, zero rate → DF = 1
        assert discount_factor(Decimal("0"), 90) == _ONE
        assert discount_factor(Decimal("0"), 0) == _ONE

    def test_zero_days(self):
        assert discount_factor(Decimal("0.07"), 0) == _ONE

    def test_known_value_90d(self):
        expected = _ONE / (_ONE + Decimal("0.07") * Decimal("90") / Decimal("365"))
        assert discount_factor(Decimal("0.07"), 90) == expected

    def test_known_value_365d(self):
        expected = _ONE / (_ONE + Decimal("0.07"))
        assert discount_factor(Decimal("0.07"), 365) == expected

    def test_result_between_zero_and_one_for_positive_rate(self):
        df = discount_factor(Decimal("0.05"), 180)
        assert _ZERO < df < _ONE


# ── fair_value ────────────────────────────────────────────────────────────────

class TestFairValue:
    def test_buy_foreign_at_par(self):
        fv = fair_value(Decimal("100000"), _ONE, Decimal("84.50"), Decimal("84.50"), Decimal("0.98"), Direction.buy_foreign)
        assert fv == _ZERO

    def test_buy_foreign_gain(self):
        fv = fair_value(Decimal("100000"), _ONE, Decimal("85.00"), Decimal("84.50"), _ONE, Direction.buy_foreign)
        assert fv == Decimal("50000")

    def test_sell_foreign_gain(self):
        fv = fair_value(Decimal("100000"), _ONE, Decimal("84.00"), Decimal("84.50"), _ONE, Direction.sell_foreign)
        assert fv == Decimal("50000")

    def test_buy_vs_sell_are_mirror(self):
        fv_buy = fair_value(Decimal("100000"), _ONE, Decimal("85.50"), Decimal("84.50"), Decimal("0.98"), Direction.buy_foreign)
        fv_sell = fair_value(Decimal("100000"), _ONE, Decimal("85.50"), Decimal("84.50"), Decimal("0.98"), Direction.sell_foreign)
        assert fv_buy == -fv_sell

    def test_hedge_ratio_scales_fv(self):
        fv_full = fair_value(Decimal("10000"), _ONE, Decimal("94"), Decimal("93.30"), _ONE, Direction.buy_foreign)
        fv_80pct = fair_value(Decimal("10000"), Decimal("0.80"), Decimal("94"), Decimal("93.30"), _ONE, Direction.buy_foreign)
        assert fv_80pct == fv_full * Decimal("0.80")

    def test_petroleum_feb_fv(self):
        # 10000 × 0.80 × (94 − 93.30) × 1 = 5600
        fv = fair_value(Decimal("10000"), Decimal("0.80"), Decimal("94"), Decimal("93.30"), _ONE, Direction.buy_foreign)
        assert fv == Decimal("5600")


# ── hypothetical_derivative ───────────────────────────────────────────────────

class TestHypotheticalDerivative:
    def test_buy_at_inception_spot(self):
        hyp = hypothetical_derivative(Decimal("100000"), _ONE, Decimal("83.20"), Decimal("83.20"), Decimal("0.98"), Direction.buy_foreign)
        assert hyp == _ZERO

    def test_sell_at_inception_spot(self):
        hyp = hypothetical_derivative(Decimal("100000"), _ONE, Decimal("83.20"), Decimal("83.20"), Decimal("0.98"), Direction.sell_foreign)
        assert hyp == _ZERO

    def test_buy_vs_sell_mirror(self):
        h_buy = hypothetical_derivative(Decimal("100000"), _ONE, Decimal("85.00"), Decimal("83.20"), _ONE, Direction.buy_foreign)
        h_sell = hypothetical_derivative(Decimal("100000"), _ONE, Decimal("85.00"), Decimal("83.20"), _ONE, Direction.sell_foreign)
        assert h_buy == -h_sell

    def test_sell_spot_rises_negative_hyp(self):
        hyp = hypothetical_derivative(Decimal("100000"), _ONE, Decimal("85.00"), Decimal("83.20"), _ONE, Direction.sell_foreign)
        assert hyp < _ZERO

    def test_hedge_ratio_scales_hyp(self):
        h_full = hypothetical_derivative(Decimal("10000"), _ONE, Decimal("94"), Decimal("93.00"), _ONE, Direction.buy_foreign)
        h_80 = hypothetical_derivative(Decimal("10000"), Decimal("0.80"), Decimal("94"), Decimal("93.00"), _ONE, Direction.buy_foreign)
        assert h_80 == h_full * Decimal("0.80")

    def test_petroleum_feb_hyp(self):
        # 10000 × 0.80 × (94 − 93.00) × 1 = 8000
        hyp = hypothetical_derivative(Decimal("10000"), Decimal("0.80"), Decimal("94"), Decimal("93.00"), _ONE, Direction.buy_foreign)
        assert hyp == Decimal("8000")


# ── cumulative_lower_of ───────────────────────────────────────────────────────

class TestCumulativeLowerOf:
    def test_zero_delta_fv(self):
        eff, ineff = cumulative_lower_of(_ZERO, Decimal("1000"))
        assert eff == _ZERO and ineff == _ZERO

    def test_perfectly_effective(self):
        eff, ineff = cumulative_lower_of(Decimal("5000"), Decimal("5000"))
        assert eff == Decimal("5000") and ineff == _ZERO

    def test_over_hedge(self):
        eff, ineff = cumulative_lower_of(Decimal("6000"), Decimal("5000"))
        assert eff == Decimal("5000") and ineff == Decimal("1000")

    def test_under_hedge(self):
        eff, ineff = cumulative_lower_of(Decimal("4000"), Decimal("5000"))
        assert eff == Decimal("4000") and ineff == _ZERO

    def test_sign_preserved_negative(self):
        eff, ineff = cumulative_lower_of(Decimal("-5000"), Decimal("-6000"))
        assert eff == Decimal("-5000") and ineff == _ZERO

    def test_identity_cum_eff_plus_ineff_equals_cum_delta_fv(self):
        for cdv, cdh in [
            (Decimal("3000"), Decimal("2500")),
            (Decimal("-3000"), Decimal("-4000")),
            (Decimal("0"), Decimal("500")),
            (Decimal("8000"), Decimal("8000")),
        ]:
            eff, ineff = cumulative_lower_of(cdv, cdh)
            assert eff + ineff == cdv


# ── dollar_offset_ratio (cumulative) ─────────────────────────────────────────

class TestDollarOffsetRatio:
    def test_undefined_when_cum_hyp_zero(self):
        assert dollar_offset_ratio(Decimal("1000"), _ZERO) is None

    def test_perfect_ratio(self):
        assert dollar_offset_ratio(Decimal("1000"), Decimal("1000")) == _ONE

    def test_ratio_absolute_values(self):
        r1 = dollar_offset_ratio(Decimal("-800"), Decimal("1000"))
        r2 = dollar_offset_ratio(Decimal("800"), Decimal("-1000"))
        assert r1 == r2 == Decimal("0.8")

    def test_petroleum_feb_ratio(self):
        # |5600| / |8000| = 0.70
        r = dollar_offset_ratio(Decimal("5600"), Decimal("8000"))
        assert r == Decimal("0.70")

    def test_petroleum_apr_ratio(self):
        # |-18400| / |-16000| = 1.15
        r = dollar_offset_ratio(Decimal("-18400"), Decimal("-16000"))
        assert r == Decimal("1.15")


# ── compute_period — integration ──────────────────────────────────────────────

class TestComputePeriod:
    def _p(self, raw: dict) -> PeriodInput:
        return PeriodInput(**raw)

    def test_period1_sell_fv_at_par(self):
        result = compute_period(HEDGE_SELL, self._p(P1_INPUT), **_INIT_STATE)
        assert result.fv_t == _ZERO
        assert result.delta_fv_t == _ZERO

    def test_period1_sell_hyp_negative(self):
        result = compute_period(HEDGE_SELL, self._p(P1_INPUT), **_INIT_STATE)
        assert result.hyp_t < _ZERO

    def test_period2_sell_fv_negative(self):
        result = compute_period(HEDGE_SELL, self._p(P2_INPUT), **_INIT_STATE)
        assert result.fv_t < _ZERO

    def test_buy_fv_positive_when_spot_above_contract(self):
        # petroleum buy_foreign: spot=94 > contract=93.30 → positive FV
        result = compute_period(HEDGE_BUY, PETRO_FEB, **_INIT_STATE)
        assert result.fv_t > _ZERO

    def test_forward_fallback_to_spot_when_none(self):
        # PETRO periods have forward_rate_remaining=None; FV should use spot
        result_none_fwd = compute_period(HEDGE_BUY, PETRO_FEB, **_INIT_STATE)
        explicit_spot = PeriodInput(
            period_number=1,
            period_end_date=PETRO_FEB.period_end_date,
            spot_rate=PETRO_FEB.spot_rate,
            forward_rate_remaining=PETRO_FEB.spot_rate,  # explicit = same as spot
            days_to_maturity=PETRO_FEB.days_to_maturity,
        )
        result_explicit = compute_period(HEDGE_BUY, explicit_spot, **_INIT_STATE)
        assert result_none_fwd.fv_t == result_explicit.fv_t

    def test_discount_factor_applied_in_fv(self):
        p = PeriodInput(**P2_INPUT)  # HEDGE_SELL has 7% rate, 60 days
        result = compute_period(HEDGE_SELL, p, **_INIT_STATE)
        df = result.discount_factor
        assert _ZERO < df < _ONE
        # sell_foreign: FV = notional × 1 × (contract − fwd) × DF
        undiscounted = Decimal("100000") * (Decimal("84.50") - Decimal("85.20"))
        assert result.fv_t == undiscounted * df

    def test_discount_factor_is_one_when_rate_zero(self):
        result = compute_period(HEDGE_BUY, PETRO_FEB, **_INIT_STATE)
        assert result.discount_factor == _ONE

    def test_cum_eff_plus_ineff_equals_cum_delta_fv(self):
        state: dict = dict(_INIT_STATE)
        for raw in [P1_INPUT, P2_INPUT, P3_INPUT]:
            result = compute_period(HEDGE_SELL, PeriodInput(**raw), **state)
            assert result.cum_effective + result.cum_ineffective == result.cum_delta_fv
            state = dict(
                prev_fv=result.fv_t, prev_hyp=result.hyp_t,
                prev_cum_delta_fv=result.cum_delta_fv,
                prev_cum_delta_hyp=result.cum_delta_hyp,
                prev_cum_effective=result.cum_effective,
                prev_cum_ineffective=result.cum_ineffective,
            )

    def test_oci_accumulates_correctly(self):
        state: dict = dict(_INIT_STATE)
        total_oci = _ZERO
        result = None
        for raw in [P1_INPUT, P2_INPUT, P3_INPUT]:
            result = compute_period(HEDGE_SELL, PeriodInput(**raw), **state)
            total_oci += result.oci_this_period
            state = dict(
                prev_fv=result.fv_t, prev_hyp=result.hyp_t,
                prev_cum_delta_fv=result.cum_delta_fv,
                prev_cum_delta_hyp=result.cum_delta_hyp,
                prev_cum_effective=result.cum_effective,
                prev_cum_ineffective=result.cum_ineffective,
            )
        assert total_oci == result.cum_effective


# ── Petroleum golden-number tests (Excel reference) ──────────────────────────

def _run_petroleum_chain() -> dict:
    """Run all 5 petroleum periods and return results keyed by month."""
    state: dict = dict(_INIT_STATE)
    results = {}
    for name, period in [
        ("feb", PETRO_FEB), ("mar", PETRO_MAR), ("apr", PETRO_APR),
        ("may", PETRO_MAY), ("jun", PETRO_JUN),
    ]:
        r = compute_period(HEDGE_BUY, period, **state)
        results[name] = r
        state = dict(
            prev_fv=r.fv_t, prev_hyp=r.hyp_t,
            prev_cum_delta_fv=r.cum_delta_fv,
            prev_cum_delta_hyp=r.cum_delta_hyp,
            prev_cum_effective=r.cum_effective,
            prev_cum_ineffective=r.cum_ineffective,
        )
    return results


class TestComputePeriodPetroleumGolden:
    """Golden-number assertions against reference Excel (IFRS 9 illustrative)."""

    @pytest.fixture(scope="class")
    def chain(self):
        return _run_petroleum_chain()

    @pytest.mark.parametrize("month,field,expected", [
        ("feb", "cum_delta_fv",    Decimal("5600")),
        ("feb", "cum_delta_hyp",   Decimal("8000")),
        ("feb", "cum_effective",   Decimal("5600")),
        ("feb", "cum_ineffective", Decimal("0")),
        ("feb", "oci_this_period", Decimal("5600")),
        ("feb", "pnl_this_period", Decimal("0")),

        ("mar", "cum_delta_fv",    Decimal("13600")),
        ("mar", "cum_delta_hyp",   Decimal("16000")),
        ("mar", "cum_effective",   Decimal("13600")),
        ("mar", "cum_ineffective", Decimal("0")),
        ("mar", "oci_this_period", Decimal("8000")),
        ("mar", "pnl_this_period", Decimal("0")),

        ("apr", "cum_delta_fv",    Decimal("-18400")),
        ("apr", "cum_delta_hyp",   Decimal("-16000")),
        ("apr", "cum_effective",   Decimal("-16000")),
        ("apr", "cum_ineffective", Decimal("-2400")),
        ("apr", "oci_this_period", Decimal("-29600")),
        ("apr", "pnl_this_period", Decimal("-2400")),

        ("may", "cum_delta_fv",    Decimal("5600")),
        ("may", "cum_delta_hyp",   Decimal("8000")),
        ("may", "cum_effective",   Decimal("5600")),
        ("may", "cum_ineffective", Decimal("0")),
        ("may", "oci_this_period", Decimal("21600")),
        ("may", "pnl_this_period", Decimal("2400")),

        ("jun", "cum_delta_fv",    Decimal("21600")),
        ("jun", "cum_delta_hyp",   Decimal("24000")),
        ("jun", "cum_effective",   Decimal("21600")),
        ("jun", "cum_ineffective", Decimal("0")),
        ("jun", "oci_this_period", Decimal("16000")),
        ("jun", "pnl_this_period", Decimal("0")),
    ])
    def test_golden_value(self, chain, month, field, expected):
        actual = getattr(chain[month], field)
        assert actual == expected, (
            f"Period {month} {field}: expected {expected}, got {actual}"
        )

    @pytest.mark.parametrize("month,expected_ratio", [
        ("feb", Decimal("0.70")),
        ("mar", Decimal("0.85")),
        ("apr", Decimal("1.15")),
        ("may", Decimal("0.70")),
        ("jun", Decimal("0.90")),
    ])
    def test_golden_ratio(self, chain, month, expected_ratio):
        actual = chain[month].ratio
        assert actual is not None
        # Compare to 2 dp — the reference rounds to 2 significant figures
        actual_rounded = actual.quantize(Decimal("0.01"))
        assert actual_rounded == expected_ratio, (
            f"Period {month} ratio: expected {expected_ratio}, got {actual_rounded}"
        )

    def test_invariant_holds_all_periods(self, chain):
        for month, r in chain.items():
            assert r.cum_effective + r.cum_ineffective == r.cum_delta_fv, (
                f"Invariant broken at {month}"
            )
