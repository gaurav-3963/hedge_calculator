from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Optional

from models import Direction, HedgeInception, PeriodComputed, PeriodInput

getcontext().prec = 28

_ZERO = Decimal("0")
_ONE = Decimal("1")
_365 = Decimal("365")
_LOW = Decimal("0.80")
_HIGH = Decimal("1.25")


def discount_factor(rate_annual: Decimal, days_to_maturity: int) -> Decimal:
    # IFRS 9 B6.5.5 — simple interest discounting; rate==0 ⟹ simplified mode, DF=1
    if rate_annual == _ZERO:
        return _ONE
    return _ONE / (_ONE + rate_annual * Decimal(days_to_maturity) / _365)


def fair_value(
    notional: Decimal,
    hedge_ratio_pct: Decimal,
    current_rate: Decimal,
    contract_rate: Decimal,
    df_t: Decimal,
    direction: Direction,
) -> Decimal:
    # IFRS 9 B6.5.4 — forward FV, scaled by hedge ratio
    if direction == Direction.buy_foreign:
        return notional * hedge_ratio_pct * (current_rate - contract_rate) * df_t
    return notional * hedge_ratio_pct * (contract_rate - current_rate) * df_t


def hypothetical_derivative(
    notional: Decimal,
    hedge_ratio_pct: Decimal,
    spot_t: Decimal,
    inception_spot: Decimal,
    df_t: Decimal,
    direction: Direction,
) -> Decimal:
    # IFRS 9 B6.5.5 — PV of hedged item change, scaled by hedge ratio
    if direction == Direction.buy_foreign:
        return notional * hedge_ratio_pct * (spot_t - inception_spot) * df_t
    return notional * hedge_ratio_pct * (inception_spot - spot_t) * df_t


def cumulative_lower_of(
    cum_delta_fv: Decimal, cum_delta_hyp: Decimal
) -> tuple[Decimal, Decimal]:
    # IFRS 9 6.5.11 — effective portion = lower of absolute cumulative values
    if cum_delta_fv == _ZERO:
        return _ZERO, _ZERO
    sign = _ONE if cum_delta_fv > _ZERO else Decimal("-1")
    cum_effective = sign * min(abs(cum_delta_fv), abs(cum_delta_hyp))
    cum_ineffective = cum_delta_fv - cum_effective
    return cum_effective, cum_ineffective


def dollar_offset_ratio(
    cum_delta_fv: Decimal, cum_delta_hyp: Decimal
) -> Optional[Decimal]:
    # IFRS 9 B6.4.3 — cumulative dollar-offset ratio; undefined when cumΔHyp == 0
    if cum_delta_hyp == _ZERO:
        return None
    return abs(cum_delta_fv) / abs(cum_delta_hyp)


def compute_period(
    hedge: HedgeInception,
    period_input: PeriodInput,
    prev_fv: Decimal,
    prev_hyp: Decimal,
    prev_cum_delta_fv: Decimal,
    prev_cum_delta_hyp: Decimal,
    prev_cum_effective: Decimal,
    prev_cum_ineffective: Decimal,
) -> PeriodComputed:
    df_t = discount_factor(hedge.discount_rate_annual, period_input.days_to_maturity)

    # Use market forward rate when available; fall back to spot (simplified mode)
    current_rate = (
        period_input.forward_rate_remaining
        if period_input.forward_rate_remaining is not None
        else period_input.spot_rate
    )

    fv_t = fair_value(
        hedge.notional_foreign,
        hedge.hedge_ratio_pct,
        current_rate,
        hedge.contract_rate,
        df_t,
        hedge.direction,
    )
    delta_fv_t = fv_t - prev_fv
    cum_delta_fv = prev_cum_delta_fv + delta_fv_t

    hyp_t = hypothetical_derivative(
        hedge.notional_foreign,
        hedge.hedge_ratio_pct,
        period_input.spot_rate,
        hedge.inception_spot,
        df_t,
        hedge.direction,
    )
    delta_hyp_t = hyp_t - prev_hyp
    cum_delta_hyp = prev_cum_delta_hyp + delta_hyp_t

    cum_effective, cum_ineffective = cumulative_lower_of(cum_delta_fv, cum_delta_hyp)

    oci_this_period = cum_effective - prev_cum_effective
    pnl_this_period = cum_ineffective - prev_cum_ineffective

    # Cumulative dollar-offset ratio (diagnostic)
    ratio = dollar_offset_ratio(cum_delta_fv, cum_delta_hyp)
    ratio_in_band = (_LOW <= ratio <= _HIGH) if ratio is not None else None

    return PeriodComputed(
        discount_factor=df_t,
        fv_t=fv_t,
        delta_fv_t=delta_fv_t,
        cum_delta_fv=cum_delta_fv,
        hyp_t=hyp_t,
        delta_hyp_t=delta_hyp_t,
        cum_delta_hyp=cum_delta_hyp,
        cum_effective=cum_effective,
        cum_ineffective=cum_ineffective,
        oci_this_period=oci_this_period,
        pnl_this_period=pnl_this_period,
        ratio=ratio,
        ratio_in_band=ratio_in_band,
    )
