"""
Golden-number fixtures for IFRS 9 hedge accounting tests.

Scenario A — HEDGE_SELL (sell_foreign, full-DCF mode)
  USD 100,000 export forward at 84.50 INR/USD, 7% discount, 100% hedge ratio.
  Used for direction / sign / discounting tests.

Scenario B — HEDGE_BUY / petroleum (buy_foreign, simplified mode)
  USD 10,000 petroleum purchase forward: contract 93.30, inception spot 93.00.
  80% hedge ratio, no discounting (DF=1), no separate forward curve.
  Periods Feb–Jun 2026, spot = [94, 95, 91, 94, 96].
  Golden numbers verified against reference Excel (IFRS 9 illustrative example).
"""
from decimal import Decimal
from datetime import date

from models import (
    Direction,
    EffectivenessMethod,
    HedgedItemNature,
    HedgeInception,
    HedgingInstrument,
    HedgeType,
    PeriodInput,
    RiskHedged,
)

# ── Scenario A: sell_foreign, full-DCF ───────────────────────────────────────

HEDGE_SELL = HedgeInception(
    hedge_id="CFH-TEST-001",
    inception_date=date(2026, 1, 1),
    hedge_type=HedgeType.cash_flow,
    hedging_instrument=HedgingInstrument.forward,
    direction=Direction.sell_foreign,
    notional_foreign=Decimal("100000"),
    foreign_ccy="USD",
    functional_ccy="INR",
    contract_rate=Decimal("84.50"),
    inception_spot=Decimal("83.20"),
    maturity_date=date(2026, 7, 4),
    hedged_item_desc="USD 100k forecast export receivable",
    hedged_item_nature=HedgedItemNature.forecast_sale,
    expected_transaction_date=date(2026, 7, 1),
    risk_hedged=RiskHedged.fx_spot_risk,
    hedge_ratio_pct=Decimal("1"),
    economic_relationship="FX forward offsets FX exposure on forecast USD sale",
    effectiveness_method=EffectivenessMethod.dollar_offset,
    discount_rate_annual=Decimal("0.070"),
    counterparty="HDFC Bank",
)

# Scenario A periods (explicit forward rates, full-DCF)
P1_INPUT = {
    "period_number": 1,
    "period_end_date": date(2026, 4, 4),
    "spot_rate": Decimal("84.20"),
    "forward_rate_remaining": Decimal("84.50"),
    "days_to_maturity": 90,
}

P2_INPUT = {
    "period_number": 2,
    "period_end_date": date(2026, 5, 4),
    "spot_rate": Decimal("85.00"),
    "forward_rate_remaining": Decimal("85.20"),
    "days_to_maturity": 60,
}

P3_INPUT = {
    "period_number": 3,
    "period_end_date": date(2026, 6, 3),
    "spot_rate": Decimal("85.50"),
    "forward_rate_remaining": Decimal("85.60"),
    "days_to_maturity": 30,
}

# ── Scenario B: petroleum purchase, simplified mode (DF=1, fwd=None) ─────────

HEDGE_BUY = HedgeInception(
    hedge_id="CFH-TEST-002",
    inception_date=date(2026, 1, 1),
    hedge_type=HedgeType.cash_flow,
    hedging_instrument=HedgingInstrument.forward,
    direction=Direction.buy_foreign,
    notional_foreign=Decimal("10000"),
    foreign_ccy="USD",
    functional_ccy="INR",
    contract_rate=Decimal("93.30"),
    inception_spot=Decimal("93.00"),
    maturity_date=date(2026, 7, 30),
    hedged_item_desc="USD 10k petroleum import",
    hedged_item_nature=HedgedItemNature.forecast_purchase,
    expected_transaction_date=date(2026, 7, 28),
    risk_hedged=RiskHedged.fx_spot_risk,
    hedge_ratio_pct=Decimal("0.80"),
    economic_relationship=(
        "FX forward at 80% covers expected USD petroleum purchase; "
        "spot risk on notional × ratio is economically offset."
    ),
    effectiveness_method=EffectivenessMethod.dollar_offset,
    discount_rate_annual=Decimal("0"),
    counterparty="SBI",
    oci_treatment="basis_adjustment",
)

# Petroleum periods — forward_rate_remaining=None → spot used for FV
PETRO_FEB = PeriodInput(
    period_number=1,
    period_end_date=date(2026, 2, 28),
    spot_rate=Decimal("94"),
    forward_rate_remaining=None,
    days_to_maturity=152,
)
PETRO_MAR = PeriodInput(
    period_number=2,
    period_end_date=date(2026, 3, 31),
    spot_rate=Decimal("95"),
    forward_rate_remaining=None,
    days_to_maturity=121,
)
PETRO_APR = PeriodInput(
    period_number=3,
    period_end_date=date(2026, 4, 30),
    spot_rate=Decimal("91"),
    forward_rate_remaining=None,
    days_to_maturity=91,
)
PETRO_MAY = PeriodInput(
    period_number=4,
    period_end_date=date(2026, 5, 31),
    spot_rate=Decimal("94"),
    forward_rate_remaining=None,
    days_to_maturity=60,
)
PETRO_JUN = PeriodInput(
    period_number=5,
    period_end_date=date(2026, 6, 30),
    spot_rate=Decimal("96"),
    forward_rate_remaining=None,
    days_to_maturity=30,
)

# Golden results from reference Excel (IFRS 9 illustrative example)
# Notation: all monetary values in INR.
PETRO_GOLDEN = {
    "feb": {
        "cum_delta_fv":    Decimal("5600"),
        "cum_delta_hyp":   Decimal("8000"),
        "cum_effective":   Decimal("5600"),
        "cum_ineffective": Decimal("0"),
        "oci_this_period": Decimal("5600"),
        "pnl_this_period": Decimal("0"),
        "ratio":           Decimal("0.70"),
    },
    "mar": {
        "cum_delta_fv":    Decimal("13600"),
        "cum_delta_hyp":   Decimal("16000"),
        "cum_effective":   Decimal("13600"),
        "cum_ineffective": Decimal("0"),
        "oci_this_period": Decimal("8000"),
        "pnl_this_period": Decimal("0"),
        "ratio":           Decimal("0.85"),
    },
    "apr": {
        "cum_delta_fv":    Decimal("-18400"),
        "cum_delta_hyp":   Decimal("-16000"),
        "cum_effective":   Decimal("-16000"),
        "cum_ineffective": Decimal("-2400"),
        "oci_this_period": Decimal("-29600"),
        "pnl_this_period": Decimal("-2400"),
        "ratio":           Decimal("1.15"),
    },
    "may": {
        "cum_delta_fv":    Decimal("5600"),
        "cum_delta_hyp":   Decimal("8000"),
        "cum_effective":   Decimal("5600"),
        "cum_ineffective": Decimal("0"),
        "oci_this_period": Decimal("21600"),
        "pnl_this_period": Decimal("2400"),
        "ratio":           Decimal("0.70"),
    },
    "jun": {
        "cum_delta_fv":    Decimal("21600"),
        "cum_delta_hyp":   Decimal("24000"),
        "cum_effective":   Decimal("21600"),
        "cum_ineffective": Decimal("0"),
        "oci_this_period": Decimal("16000"),
        "pnl_this_period": Decimal("0"),
        "ratio":           Decimal("0.90"),
    },
}
