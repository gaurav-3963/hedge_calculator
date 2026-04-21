from __future__ import annotations

from decimal import Decimal, getcontext
from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

getcontext().prec = 28


class HedgeType(str, Enum):
    cash_flow = "cash_flow"


class HedgingInstrument(str, Enum):
    forward = "forward"


class Direction(str, Enum):
    buy_foreign = "buy_foreign"
    sell_foreign = "sell_foreign"


class HedgedItemNature(str, Enum):
    forecast_sale = "forecast_sale"
    forecast_purchase = "forecast_purchase"
    forecast_interest = "forecast_interest"


class RiskHedged(str, Enum):
    fx_spot_risk = "fx_spot_risk"


class EffectivenessMethod(str, Enum):
    dollar_offset = "dollar_offset"


class HedgeInception(BaseModel):
    hedge_id: str
    inception_date: date
    hedge_type: HedgeType = HedgeType.cash_flow
    hedging_instrument: HedgingInstrument = HedgingInstrument.forward
    direction: Direction
    notional_foreign: Decimal
    foreign_ccy: str = Field(min_length=3, max_length=3)
    functional_ccy: str = Field(min_length=3, max_length=3)
    contract_rate: Decimal
    inception_spot: Decimal
    maturity_date: date
    hedged_item_desc: str
    hedged_item_nature: HedgedItemNature
    expected_transaction_date: date
    risk_hedged: RiskHedged = RiskHedged.fx_spot_risk
    # Single hedge-ratio field: 0 < hedge_ratio_pct ≤ 1  (replaces hedge_ratio_instrument / hedge_ratio_item)
    hedge_ratio_pct: Decimal = Decimal("1")
    economic_relationship: str
    effectiveness_method: EffectivenessMethod = EffectivenessMethod.dollar_offset
    # Optional: 0 = simplified mode (DF always 1); >0 = full-DCF mode
    discount_rate_annual: Decimal = Decimal("0")
    counterparty: str
    # OCI treatment at maturity. "basis_adjustment" only allowed for forecast_purchase.
    oci_treatment: Literal["reclassify_to_pnl", "basis_adjustment"] = "reclassify_to_pnl"
    sources_of_ineffectiveness: Optional[str] = None

    @field_validator("hedge_ratio_pct")
    @classmethod
    def _validate_hedge_ratio_pct(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") < v <= Decimal("1")):
            raise ValueError("hedge_ratio_pct must be in range (0, 1] — e.g. 0.80 for 80%")
        return v

    @model_validator(mode="after")
    def _check_invariants(self) -> "HedgeInception":
        if self.maturity_date <= self.inception_date:
            raise ValueError("maturity_date must be after inception_date")
        if (
            self.oci_treatment == "basis_adjustment"
            and self.hedged_item_nature != HedgedItemNature.forecast_purchase
        ):
            raise ValueError(
                "oci_treatment='basis_adjustment' is only permitted when "
                "hedged_item_nature='forecast_purchase'"
            )
        return self

    @property
    def tenor_days(self) -> int:
        return (self.maturity_date - self.inception_date).days

    model_config = {"arbitrary_types_allowed": True}


class PeriodInput(BaseModel):
    period_number: int = Field(ge=1)
    period_end_date: date
    spot_rate: Decimal
    # Reserved for V2 full-DCF mode. Not used in V1 simplified mode — always None.
    forward_rate_remaining: Optional[Decimal] = None
    days_to_maturity: int = Field(ge=0)

    model_config = {"arbitrary_types_allowed": True}


class PeriodComputed(BaseModel):
    discount_factor: Decimal
    fv_t: Decimal
    delta_fv_t: Decimal
    cum_delta_fv: Decimal
    hyp_t: Decimal
    delta_hyp_t: Decimal
    cum_delta_hyp: Decimal
    cum_effective: Decimal
    cum_ineffective: Decimal
    oci_this_period: Decimal
    pnl_this_period: Decimal
    ratio: Optional[Decimal]
    ratio_in_band: Optional[bool]

    model_config = {"arbitrary_types_allowed": True}


class JournalEntry(BaseModel):
    dr: Optional[str]
    cr: Optional[str]
    amount: Decimal

    model_config = {"arbitrary_types_allowed": True}


class LogRow(BaseModel):
    timestamp: str
    hedge_id: str
    period_number: int
    period_end_date: date
    inputs: dict
    computed: dict
    journal_entries: list[JournalEntry]
    warnings: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
