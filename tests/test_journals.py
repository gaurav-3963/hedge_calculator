from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal, getcontext

import pytest

getcontext().prec = 28

from journals import (
    _BANK_AP,
    _CASH,
    _DERIVATIVE_ASSET,
    _DERIVATIVE_LIABILITY,
    _INVENTORY,
    _OCI_ACCOUNT,
    _PNL_ACCOUNT,
    generate_entries,
)
from models import HedgedItemNature, JournalEntry, PeriodComputed
from tests.fixtures import HEDGE_BUY, HEDGE_SELL

_ZERO = Decimal("0")


def _make_period(**overrides) -> PeriodComputed:
    base = dict(
        discount_factor=Decimal("0.98"),
        fv_t=Decimal("5000"),
        delta_fv_t=Decimal("5000"),
        cum_delta_fv=Decimal("5000"),
        hyp_t=Decimal("4500"),
        delta_hyp_t=Decimal("4500"),
        cum_delta_hyp=Decimal("4500"),
        cum_effective=Decimal("4500"),
        cum_ineffective=Decimal("500"),
        oci_this_period=Decimal("4500"),
        pnl_this_period=Decimal("500"),
        ratio=Decimal("1.11"),
        ratio_in_band=True,
    )
    base.update(overrides)
    return PeriodComputed(**base)


def _total_dr(entries: list[JournalEntry]) -> Decimal:
    return sum((e.amount for e in entries if e.dr is not None), _ZERO)


def _total_cr(entries: list[JournalEntry]) -> Decimal:
    return sum((e.amount for e in entries if e.cr is not None), _ZERO)


def assert_balanced(entries: list[JournalEntry]) -> None:
    dr, cr = _total_dr(entries), _total_cr(entries)
    assert dr == cr, f"Unbalanced: Dr={dr} Cr={cr}"


# ── Case 1: SPEC 6.1 — positive ΔFV ─────────────────────────────────────────

class TestCase1PositiveDeltaFV:
    def setup_method(self):
        self.period = _make_period(delta_fv_t=Decimal("5000"), oci_this_period=Decimal("4500"), pnl_this_period=Decimal("500"))
        self.entries = generate_entries(HEDGE_SELL, self.period)

    def test_derivative_asset_is_debited(self):
        assert _DERIVATIVE_ASSET in [e.dr for e in self.entries]

    def test_oci_is_credited(self):
        assert _OCI_ACCOUNT in [e.cr for e in self.entries]

    def test_pnl_is_credited(self):
        assert _PNL_ACCOUNT in [e.cr for e in self.entries]

    def test_amounts(self):
        dr = next(e for e in self.entries if e.dr == _DERIVATIVE_ASSET)
        assert dr.amount == Decimal("5000")
        cr_oci = next(e for e in self.entries if e.cr == _OCI_ACCOUNT)
        assert cr_oci.amount == Decimal("4500")
        cr_pnl = next(e for e in self.entries if e.cr == _PNL_ACCOUNT)
        assert cr_pnl.amount == Decimal("500")

    def test_balanced(self):
        assert_balanced(self.entries)

    def test_no_liability_entry(self):
        assert _DERIVATIVE_LIABILITY not in [e.cr for e in self.entries]


# ── Case 2: SPEC 6.2 — negative ΔFV ─────────────────────────────────────────

class TestCase2NegativeDeltaFV:
    def setup_method(self):
        self.period = _make_period(
            fv_t=Decimal("-5000"), delta_fv_t=Decimal("-5000"),
            cum_delta_fv=Decimal("-5000"), hyp_t=Decimal("-4500"),
            cum_delta_hyp=Decimal("-4500"), cum_effective=Decimal("-4500"),
            cum_ineffective=Decimal("-500"), oci_this_period=Decimal("-4500"),
            pnl_this_period=Decimal("-500"),
        )
        self.entries = generate_entries(HEDGE_SELL, self.period)

    def test_derivative_liability_is_credited(self):
        assert _DERIVATIVE_LIABILITY in [e.cr for e in self.entries]

    def test_oci_is_debited(self):
        assert _OCI_ACCOUNT in [e.dr for e in self.entries]

    def test_pnl_is_debited(self):
        assert _PNL_ACCOUNT in [e.dr for e in self.entries]

    def test_amounts(self):
        cr_liab = next(e for e in self.entries if e.cr == _DERIVATIVE_LIABILITY)
        assert cr_liab.amount == Decimal("5000")
        dr_oci = next(e for e in self.entries if e.dr == _OCI_ACCOUNT)
        assert dr_oci.amount == Decimal("4500")
        dr_pnl = next(e for e in self.entries if e.dr == _PNL_ACCOUNT)
        assert dr_pnl.amount == Decimal("500")

    def test_balanced(self):
        assert_balanced(self.entries)


# ── Case 3: SPEC 6.3 — maturity settlement ───────────────────────────────────

class TestCase3MaturitySettlementPositiveFV:
    def setup_method(self):
        self.period = _make_period(
            fv_t=Decimal("5000"), delta_fv_t=Decimal("500"),
            oci_this_period=Decimal("450"), pnl_this_period=Decimal("50"),
            cum_effective=Decimal("4500"),
        )
        self.entries = generate_entries(HEDGE_SELL, self.period, is_maturity=True)

    def test_cash_is_debited(self):
        assert _CASH in [e.dr for e in self.entries]

    def test_derivative_asset_is_credited(self):
        assert _DERIVATIVE_ASSET in [e.cr for e in self.entries]

    def test_cash_amount(self):
        assert next(e for e in self.entries if e.dr == _CASH).amount == Decimal("5000")

    def test_balanced(self):
        assert_balanced(self.entries)


class TestCase3MaturitySettlementNegativeFV:
    def setup_method(self):
        self.period = _make_period(
            fv_t=Decimal("-3000"), delta_fv_t=Decimal("-300"),
            oci_this_period=Decimal("-270"), pnl_this_period=Decimal("-30"),
            cum_effective=Decimal("-2800"), cum_ineffective=Decimal("-200"),
            cum_delta_fv=Decimal("-3000"),
        )
        self.entries = generate_entries(HEDGE_SELL, self.period, is_maturity=True)

    def test_derivative_liability_is_debited(self):
        assert _DERIVATIVE_LIABILITY in [e.dr for e in self.entries]

    def test_cash_is_credited(self):
        assert _CASH in [e.cr for e in self.entries]

    def test_liability_amount(self):
        assert next(e for e in self.entries if e.dr == _DERIVATIVE_LIABILITY).amount == Decimal("3000")

    def test_balanced(self):
        assert_balanced(self.entries)


# ── Case 4: SPEC 6.4 — OCI reclassification (reclassify_to_pnl) ──────────────

class TestCase4MaturityOCIReclass:
    def _period(self, cum_effective: Decimal) -> PeriodComputed:
        cum_delta_fv = cum_effective + Decimal("200")
        return _make_period(
            fv_t=cum_delta_fv, delta_fv_t=Decimal("500"),
            oci_this_period=Decimal("450"), pnl_this_period=Decimal("50"),
            cum_delta_fv=cum_delta_fv, cum_effective=cum_effective,
            cum_ineffective=Decimal("200"),
        )

    def test_forecast_sale_credits_revenue(self):
        entries = generate_entries(HEDGE_SELL, self._period(Decimal("4500")), is_maturity=True)
        assert "Revenue" in [e.cr for e in entries]

    def test_forecast_purchase_reclassify_credits_cogs(self):
        # Use a purchase hedge with reclassify_to_pnl (NOT basis_adjustment)
        purchase_reclass = HEDGE_SELL.model_copy(
            update={
                "hedged_item_nature": HedgedItemNature.forecast_purchase,
                "oci_treatment": "reclassify_to_pnl",
            }
        )
        entries = generate_entries(purchase_reclass, self._period(Decimal("4500")), is_maturity=True)
        assert "COGS / Inventory" in [e.cr for e in entries]

    def test_forecast_interest_credits_interest(self):
        hedge_interest = HEDGE_SELL.model_copy(
            update={"hedged_item_nature": HedgedItemNature.forecast_interest}
        )
        entries = generate_entries(hedge_interest, self._period(Decimal("4500")), is_maturity=True)
        assert "Interest income / expense" in [e.cr for e in entries]

    def test_positive_oci_debits_oci_account(self):
        entries = generate_entries(HEDGE_SELL, self._period(Decimal("4500")), is_maturity=True)
        assert _OCI_ACCOUNT in [e.dr for e in entries]

    def test_negative_oci_credits_oci_account(self):
        period = _make_period(
            fv_t=Decimal("-4700"), delta_fv_t=Decimal("-500"),
            oci_this_period=Decimal("-450"), pnl_this_period=Decimal("-50"),
            cum_delta_fv=Decimal("-4700"), cum_effective=Decimal("-4500"),
            cum_ineffective=Decimal("-200"),
        )
        entries = generate_entries(HEDGE_SELL, period, is_maturity=True)
        assert _OCI_ACCOUNT in [e.cr for e in entries]

    def test_reclass_amount_equals_cum_effective(self):
        cum_eff = Decimal("4321.99")
        entries = generate_entries(HEDGE_SELL, self._period(cum_eff), is_maturity=True)
        dr_oci = next(e for e in entries if e.dr == _OCI_ACCOUNT and e.cr is None)
        assert dr_oci.amount == cum_eff

    def test_balanced(self):
        assert_balanced(generate_entries(HEDGE_SELL, self._period(Decimal("4500")), is_maturity=True))

    def test_balanced_negative_oci(self):
        period = _make_period(
            fv_t=Decimal("-4700"), delta_fv_t=Decimal("-500"),
            oci_this_period=Decimal("-450"), pnl_this_period=Decimal("-50"),
            cum_delta_fv=Decimal("-4700"), cum_effective=Decimal("-4500"),
            cum_ineffective=Decimal("-200"),
        )
        assert_balanced(generate_entries(HEDGE_SELL, period, is_maturity=True))


# ── Case 4b: Basis-adjustment maturity (petroleum scenario) ──────────────────

class TestCase4BasisAdjustmentMaturity:
    """
    Petroleum Jun period: spot_at_maturity=96, notional=10000, ratio=0.80
    FV_t = 21600 (positive), cum_effective = 21600.

    Expected entries:
      Period MTM (positive delta_fv=16000):
        Dr  Derivative asset           16,000
        Cr  OCI (CFHR)                 16,000
      Settlement (fv_t=21600 > 0):
        Dr  Cash                       21,600
        Cr  Derivative asset           21,600
      Basis adjustment:
        Dr  Inventory                 768,000   (10000 × 0.80 × 96)
        Cr  Bank / Accounts Payable   768,000
        Dr  OCI (CFHR)                 21,600
        Cr  Inventory                  21,600
    """
    def setup_method(self):
        # Jun period state (after May: prev_cum_effective=5600, prev_fv=5600)
        self.period = _make_period(
            fv_t=Decimal("21600"),
            delta_fv_t=Decimal("16000"),      # 21600 - 5600
            cum_delta_fv=Decimal("21600"),
            hyp_t=Decimal("24000"),
            delta_hyp_t=Decimal("16000"),
            cum_delta_hyp=Decimal("24000"),
            cum_effective=Decimal("21600"),
            cum_ineffective=Decimal("0"),
            oci_this_period=Decimal("16000"),  # 21600 - 5600
            pnl_this_period=Decimal("0"),
            ratio=Decimal("0.90"),
            ratio_in_band=True,
        )
        self.entries = generate_entries(
            HEDGE_BUY, self.period, is_maturity=True,
            spot_at_maturity=Decimal("96"),
        )

    def test_purchase_recognition_dr_inventory(self):
        # Dr Inventory 768,000
        inv_dr = [e for e in self.entries if e.dr == _INVENTORY]
        amounts = [e.amount for e in inv_dr]
        assert Decimal("768000") in amounts

    def test_purchase_recognition_cr_bank_ap(self):
        # Cr Bank/AP 768,000
        ap_cr = [e for e in self.entries if e.cr == _BANK_AP]
        amounts = [e.amount for e in ap_cr]
        assert Decimal("768000") in amounts

    def test_settlement_dr_cash(self):
        # Dr Cash 21,600
        cash_dr = [e for e in self.entries if e.dr == _CASH]
        assert any(e.amount == Decimal("21600") for e in cash_dr)

    def test_settlement_cr_derivative_asset(self):
        # Cr Derivative asset 21,600
        da_cr = [e for e in self.entries if e.cr == _DERIVATIVE_ASSET]
        assert any(e.amount == Decimal("21600") for e in da_cr)

    def test_basis_adjustment_dr_oci(self):
        # Dr OCI 21,600
        oci_dr = [e for e in self.entries if e.dr == _OCI_ACCOUNT]
        assert any(e.amount == Decimal("21600") for e in oci_dr)

    def test_basis_adjustment_cr_inventory(self):
        # Cr Inventory 21,600
        inv_cr = [e for e in self.entries if e.cr == _INVENTORY]
        assert any(e.amount == Decimal("21600") for e in inv_cr)

    def test_purchase_amount_calculation(self):
        # 10000 × 0.80 × 96 = 768,000
        assert Decimal("10000") * Decimal("0.80") * Decimal("96") == Decimal("768000")

    def test_total_debits_equal_credits(self):
        assert_balanced(self.entries)

    def test_no_cogs_inventory_account(self):
        # basis_adjustment uses "Inventory", not the reclassify "COGS / Inventory"
        all_accounts = [e.dr for e in self.entries] + [e.cr for e in self.entries]
        assert "COGS / Inventory" not in all_accounts

    def test_no_revenue_account(self):
        all_accounts = [e.dr for e in self.entries] + [e.cr for e in self.entries]
        assert "Revenue" not in all_accounts


# ── Balance invariant (parametrized) ─────────────────────────────────────────

class TestBalanceInvariant:
    @pytest.mark.parametrize("delta,oci,pnl,fv,cum_eff", [
        (Decimal("5000"),  Decimal("4500"),  Decimal("500"),  Decimal("5000"),  Decimal("4500")),
        (Decimal("-5000"), Decimal("-4500"), Decimal("-500"), Decimal("-5000"), Decimal("-4500")),
        (Decimal("0"),     Decimal("0"),     Decimal("0"),    Decimal("0"),     Decimal("0")),
        (Decimal("6000"),  Decimal("5000"),  Decimal("1000"), Decimal("6000"),  Decimal("5000")),
        (Decimal("-3000"), Decimal("1000"),  Decimal("-4000"), Decimal("-3000"), Decimal("1000")),
    ])
    def test_non_maturity_balanced(self, delta, oci, pnl, fv, cum_eff):
        period = _make_period(
            fv_t=fv, delta_fv_t=delta, cum_delta_fv=delta,
            oci_this_period=oci, pnl_this_period=pnl,
            cum_effective=cum_eff, cum_ineffective=delta - cum_eff,
        )
        assert_balanced(generate_entries(HEDGE_SELL, period))

    @pytest.mark.parametrize("delta,oci,pnl,fv,cum_eff", [
        (Decimal("5000"),  Decimal("4500"),  Decimal("500"),  Decimal("5000"),  Decimal("4500")),
        (Decimal("-5000"), Decimal("-4500"), Decimal("-500"), Decimal("-5000"), Decimal("-4500")),
    ])
    def test_maturity_reclass_balanced(self, delta, oci, pnl, fv, cum_eff):
        period = _make_period(
            fv_t=fv, delta_fv_t=delta, cum_delta_fv=delta,
            oci_this_period=oci, pnl_this_period=pnl,
            cum_effective=cum_eff, cum_ineffective=delta - cum_eff,
        )
        assert_balanced(generate_entries(HEDGE_SELL, period, is_maturity=True))

    def test_maturity_basis_adjustment_balanced(self):
        period = _make_period(
            fv_t=Decimal("21600"), delta_fv_t=Decimal("16000"),
            cum_delta_fv=Decimal("21600"), oci_this_period=Decimal("16000"),
            pnl_this_period=Decimal("0"), cum_effective=Decimal("21600"),
            cum_ineffective=Decimal("0"),
        )
        assert_balanced(
            generate_entries(HEDGE_BUY, period, is_maturity=True, spot_at_maturity=Decimal("96"))
        )
