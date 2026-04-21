from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Optional

from models import HedgedItemNature, HedgeInception, JournalEntry, PeriodComputed

getcontext().prec = 28

_ZERO = Decimal("0")

_OCI_ACCOUNT = "OCI (cash flow hedge reserve)"
_PNL_ACCOUNT = "P&L \u2014 hedge ineffectiveness"
_DERIVATIVE_ASSET = "Derivative asset"
_DERIVATIVE_LIABILITY = "Derivative liability"
_CASH = "Cash"
_INVENTORY = "Inventory"
_BANK_AP = "Bank / Accounts Payable"

_RECLASS_ACCOUNTS: dict[HedgedItemNature, str] = {
    HedgedItemNature.forecast_sale: "Revenue",
    HedgedItemNature.forecast_purchase: "COGS / Inventory",
    HedgedItemNature.forecast_interest: "Interest income / expense",
}


def _oci_lines(amount: Decimal) -> list[JournalEntry]:
    if amount > _ZERO:
        return [JournalEntry(dr=None, cr=_OCI_ACCOUNT, amount=amount)]
    if amount < _ZERO:
        return [JournalEntry(dr=_OCI_ACCOUNT, cr=None, amount=-amount)]
    return []


def _pnl_lines(amount: Decimal) -> list[JournalEntry]:
    if amount > _ZERO:
        return [JournalEntry(dr=None, cr=_PNL_ACCOUNT, amount=amount)]
    if amount < _ZERO:
        return [JournalEntry(dr=_PNL_ACCOUNT, cr=None, amount=-amount)]
    return []


def _entries_positive_delta_fv(period: PeriodComputed) -> list[JournalEntry]:
    # IFRS 9 SPEC 6.1 — derivative gain: Dr Derivative asset, Cr OCI, Cr P&L
    entries: list[JournalEntry] = [
        JournalEntry(dr=_DERIVATIVE_ASSET, cr=None, amount=period.delta_fv_t),
    ]
    entries.extend(_oci_lines(period.oci_this_period))
    entries.extend(_pnl_lines(period.pnl_this_period))
    return entries


def _entries_negative_delta_fv(period: PeriodComputed) -> list[JournalEntry]:
    # IFRS 9 SPEC 6.2 — derivative loss: Dr OCI, Dr P&L, Cr Derivative liability
    entries: list[JournalEntry] = [
        JournalEntry(dr=None, cr=_DERIVATIVE_LIABILITY, amount=-period.delta_fv_t),
    ]
    entries.extend(_oci_lines(period.oci_this_period))
    entries.extend(_pnl_lines(period.pnl_this_period))
    return entries


def _entries_maturity_settlement(period: PeriodComputed) -> list[JournalEntry]:
    # IFRS 9 SPEC 6.3 — cash settlement of derivative at maturity
    if period.fv_t > _ZERO:
        return [
            JournalEntry(dr=_CASH, cr=None, amount=period.fv_t),
            JournalEntry(dr=None, cr=_DERIVATIVE_ASSET, amount=period.fv_t),
        ]
    if period.fv_t < _ZERO:
        amt = -period.fv_t
        return [
            JournalEntry(dr=_DERIVATIVE_LIABILITY, cr=None, amount=amt),
            JournalEntry(dr=None, cr=_CASH, amount=amt),
        ]
    return []


def _entries_maturity_oci_reclass(
    hedge: HedgeInception, period: PeriodComputed
) -> list[JournalEntry]:
    # IFRS 9 SPEC 6.4 — reclassify cumulative OCI balance to P&L
    reclass_account = _RECLASS_ACCOUNTS[hedge.hedged_item_nature]
    oci_balance = period.cum_effective
    if oci_balance > _ZERO:
        return [
            JournalEntry(dr=_OCI_ACCOUNT, cr=None, amount=oci_balance),
            JournalEntry(dr=None, cr=reclass_account, amount=oci_balance),
        ]
    if oci_balance < _ZERO:
        amt = -oci_balance
        return [
            JournalEntry(dr=reclass_account, cr=None, amount=amt),
            JournalEntry(dr=None, cr=_OCI_ACCOUNT, amount=amt),
        ]
    return []


def _entries_maturity_basis_adjustment(
    hedge: HedgeInception,
    period: PeriodComputed,
    spot_at_maturity: Optional[Decimal],
) -> list[JournalEntry]:
    # Basis-adjustment treatment (IFRS 9.6.5.11(d)) for forecast purchase hedges.
    # 1. Recognise the purchased item at spot: Dr Inventory / Cr Bank-AP
    # 2. Adjust cost basis by cumulative OCI: Dr OCI-CFHR / Cr Inventory
    entries: list[JournalEntry] = []

    if spot_at_maturity is not None:
        purchase_amt = hedge.notional_foreign * hedge.hedge_ratio_pct * spot_at_maturity
        entries.extend([
            JournalEntry(dr=_INVENTORY, cr=None, amount=purchase_amt),
            JournalEntry(dr=None, cr=_BANK_AP, amount=purchase_amt),
        ])

    oci_balance = period.cum_effective
    if oci_balance > _ZERO:
        entries.extend([
            JournalEntry(dr=_OCI_ACCOUNT, cr=None, amount=oci_balance),
            JournalEntry(dr=None, cr=_INVENTORY, amount=oci_balance),
        ])
    elif oci_balance < _ZERO:
        amt = -oci_balance
        entries.extend([
            JournalEntry(dr=_INVENTORY, cr=None, amount=amt),
            JournalEntry(dr=None, cr=_OCI_ACCOUNT, amount=amt),
        ])

    return entries


def generate_entries(
    hedge: HedgeInception,
    period: PeriodComputed,
    is_maturity: bool = False,
    spot_at_maturity: Optional[Decimal] = None,
) -> list[JournalEntry]:
    if (
        not is_maturity
        and period.delta_fv_t == _ZERO
        and period.oci_this_period == _ZERO
        and period.pnl_this_period == _ZERO
    ):
        return []
    entries: list[JournalEntry] = []
    if period.delta_fv_t >= _ZERO:
        entries.extend(_entries_positive_delta_fv(period))
    else:
        entries.extend(_entries_negative_delta_fv(period))
    if is_maturity:
        entries.extend(_entries_maturity_settlement(period))
        if hedge.oci_treatment == "basis_adjustment":
            entries.extend(
                _entries_maturity_basis_adjustment(hedge, period, spot_at_maturity)
            )
        else:
            entries.extend(_entries_maturity_oci_reclass(hedge, period))
    return entries
