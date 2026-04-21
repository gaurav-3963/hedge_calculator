from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from pydantic import ValidationError

import storage
from models import (
    Direction,
    EffectivenessMethod,
    HedgedItemNature,
    HedgeInception,
    HedgingInstrument,
    HedgeType,
    RiskHedged,
)

st.set_page_config(page_title="New Hedge", layout="wide")

if st.button("\u2190 Back to Home"):
    st.switch_page("app.py")

st.title("Designate New Hedge Relationship")
st.caption(
    "IFRS 9.6.5.4 \u2014 All fields below constitute formal hedge designation "
    "documentation and must be completed at inception."
)
st.divider()


_DIRECTION_LABELS = {
    "sell_foreign": "Sell Foreign \u2014 export hedge (company receives foreign currency)",
    "buy_foreign": "Buy Foreign \u2014 import hedge (company pays foreign currency)",
}

_NATURE_LABELS = {
    "forecast_sale": "Forecast Sale (revenue)",
    "forecast_purchase": "Forecast Purchase (COGS / inventory)",
    "forecast_interest": "Forecast Interest (income / expense)",
}

with st.form("new_hedge_form", border=True):

    # ── Section 1: Identification ─────────────────────────────────────────────
    with st.expander("1 \u00b7 Identification", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            hedge_id = st.text_input(
                "Hedge ID \u2a2f",
                placeholder="CFH-2026-001",
                help="Unique identifier for this hedge relationship",
            )
            inception_date = st.date_input(
                "Inception Date (Trade Date) \u2a2f",
                value=date.today(),
            )
        with c2:
            counterparty = st.text_input(
                "Counterparty \u2a2f",
                placeholder="HDFC Bank",
                help="Bank or broker providing the forward contract",
            )
            direction = st.radio(
                "Direction \u2a2f",
                options=["sell_foreign", "buy_foreign"],
                format_func=lambda x: _DIRECTION_LABELS[x],
                help="Drives the sign convention for fair value",
            )

    # ── Section 2: Notional & Rates ───────────────────────────────────────────
    with st.expander("2 \u00b7 Notional & Rates", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            notional_foreign_str = st.text_input(
                "Notional (foreign currency) \u2a2f",
                value="",
                placeholder="e.g. 100000",
                help="Total contract notional in the foreign currency.",
            )
            foreign_ccy = st.text_input(
                "Foreign Currency \u2a2f",
                value="USD",
                max_chars=3,
                help="ISO 4217 code, e.g. USD",
            )
        with c2:
            functional_ccy = st.text_input(
                "Functional Currency \u2a2f",
                value="INR",
                max_chars=3,
                help="Reporting / functional currency ISO 4217",
            )
            contract_rate_str = st.text_input(
                "Contract Rate K \u2a2f",
                value="",
                placeholder="e.g. 84.50",
                help="Forward rate locked in the contract.",
            )
        with c3:
            inception_spot_str = st.text_input(
                "Inception Spot Rate \u2a2f",
                value="",
                placeholder="e.g. 83.20",
                help="Spot rate on trade date.",
            )
            discount_rate_annual_str = st.text_input(
                "Discount Rate p.a.",
                value="0",
                placeholder="e.g. 0.070",
                help="Annual rate for PV discounting, e.g. 0.070 = 7%. Leave at 0 for simplified mode (no discounting, DF = 1).",
            )

    # ── Section 3: Dates & Hedged Item ────────────────────────────────────────
    with st.expander("3 \u00b7 Dates & Hedged Item", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            next_year = date.today().replace(year=date.today().year + 1)
            maturity_date = st.date_input(
                "Maturity Date \u2a2f",
                value=next_year,
                help="Contract settlement date",
            )
            expected_transaction_date = st.date_input(
                "Expected Transaction Date \u2a2f",
                value=next_year,
                help="When the forecast cash flow is expected to occur",
            )
        with c2:
            hedged_item_nature = st.selectbox(
                "Hedged Item Nature \u2a2f",
                options=[e.value for e in HedgedItemNature],
                format_func=lambda x: _NATURE_LABELS.get(x, x),
                help="Drives the reclassification account at maturity",
            )
            hedged_item_desc = st.text_input(
                "Hedged Item Description \u2a2f",
                placeholder="USD 100k forecast export receivable",
                help="Free text per IFRS 9.6.4.1(b)",
            )

    # ── Section 4: Effectiveness Documentation ────────────────────────────────
    with st.expander("4 \u00b7 Effectiveness Documentation", expanded=True):
        economic_relationship = st.text_area(
            "Economic Relationship (IFRS 9.B6.4) \u2a2f",
            placeholder=(
                "Describe the economic relationship between the hedging instrument "
                "and the hedged item, e.g.: 'The USD/INR forward mirrors the FX "
                "exposure on the forecast USD 100k export receivable. Both reference "
                "the same currency pair and mature within the same period.'"
            ),
            height=110,
        )
        c1, c2 = st.columns(2)
        with c1:
            hedge_ratio_pct_val = st.number_input(
                "Hedge Ratio %",
                min_value=1.0,
                max_value=100.0,
                step=1.0,
                format="%.1f",
                value=100.0,
                help="Percentage of notional amount hedged, e.g. 80 for 80% (stored as 0.80).",
            )
        with c2:
            oci_treatment = st.radio(
                "OCI Treatment at Maturity",
                options=["reclassify_to_pnl", "basis_adjustment"],
                format_func=lambda x: (
                    "Reclassify to P&L"
                    if x == "reclassify_to_pnl"
                    else "Basis Adjustment (IFRS 9.6.5.11(d))"
                ),
                help="'Basis Adjustment' only applies to Forecast Purchase hedges.",
            )

    # ── Section 5: Optional ───────────────────────────────────────────────────
    with st.expander("5 \u00b7 Optional Fields", expanded=False):
        sources_of_ineffectiveness = st.text_area(
            "Sources of Ineffectiveness (IFRS 9.B6.4.x)",
            placeholder=(
                "E.g. credit risk of the counterparty bank, timing mismatch "
                "between instrument maturity and expected transaction date\u2026"
            ),
            height=80,
        )

    st.info(
        "\U0001f512 **Fixed for V1:** "
        "Hedge type = Cash Flow \u00b7 "
        "Instrument = Forward FX \u00b7 "
        "Risk hedged = FX Spot Risk \u00b7 "
        "Effectiveness method = Dollar-Offset (Cumulative)"
    )

    submitted = st.form_submit_button(
        "Save Hedge Designation", type="primary", use_container_width=True
    )

# ── Handle submission outside the form ────────────────────────────────────────
if submitted:
    errors: list[str] = []

    hedge_id_clean = hedge_id.strip()
    if not hedge_id_clean:
        errors.append("Hedge ID is required.")
    elif hedge_id_clean in storage.list_hedges():
        errors.append(f"Hedge ID **{hedge_id_clean}** already exists. Choose a different ID.")

    if not counterparty.strip():
        errors.append("Counterparty is required.")
    if not hedged_item_desc.strip():
        errors.append("Hedged item description is required.")
    if not economic_relationship.strip():
        errors.append("Economic relationship documentation is required.")
    if len(foreign_ccy.strip()) != 3:
        errors.append("Foreign currency must be exactly 3 characters (ISO 4217).")
    if len(functional_ccy.strip()) != 3:
        errors.append("Functional currency must be exactly 3 characters (ISO 4217).")

    # Parse Decimal fields
    notional_val: Decimal | None = None
    if not notional_foreign_str.strip():
        errors.append("Notional is required.")
    else:
        try:
            notional_val = Decimal(notional_foreign_str.strip())
            if notional_val <= Decimal("0"):
                errors.append("Notional must be positive.")
                notional_val = None
        except InvalidOperation:
            errors.append(f"Notional '{notional_foreign_str}' is not a valid number.")

    contract_rate_val: Decimal | None = None
    if not contract_rate_str.strip():
        errors.append("Contract Rate is required.")
    else:
        try:
            contract_rate_val = Decimal(contract_rate_str.strip())
            if contract_rate_val <= Decimal("0"):
                errors.append("Contract Rate must be positive.")
                contract_rate_val = None
        except InvalidOperation:
            errors.append(f"Contract Rate '{contract_rate_str}' is not a valid number.")

    inception_spot_val: Decimal | None = None
    if not inception_spot_str.strip():
        errors.append("Inception Spot Rate is required.")
    else:
        try:
            inception_spot_val = Decimal(inception_spot_str.strip())
            if inception_spot_val <= Decimal("0"):
                errors.append("Inception Spot Rate must be positive.")
                inception_spot_val = None
        except InvalidOperation:
            errors.append(f"Inception Spot Rate '{inception_spot_str}' is not a valid number.")

    discount_rate_val: Decimal = Decimal("0")
    raw_dr = discount_rate_annual_str.strip()
    if raw_dr and raw_dr != "0":
        try:
            discount_rate_val = Decimal(raw_dr)
            if not (Decimal("0") <= discount_rate_val <= Decimal("1")):
                errors.append("Discount Rate must be between 0 and 1 (e.g. 0.070 for 7%).")
                discount_rate_val = Decimal("0")
        except InvalidOperation:
            errors.append(f"Discount Rate '{raw_dr}' is not a valid number.")

    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    try:
        hedge = HedgeInception(
            hedge_id=hedge_id_clean,
            inception_date=inception_date,
            hedge_type=HedgeType.cash_flow,
            hedging_instrument=HedgingInstrument.forward,
            direction=Direction(direction),
            notional_foreign=notional_val,  # type: ignore[arg-type]
            foreign_ccy=foreign_ccy.upper().strip(),
            functional_ccy=functional_ccy.upper().strip(),
            contract_rate=contract_rate_val,  # type: ignore[arg-type]
            inception_spot=inception_spot_val,  # type: ignore[arg-type]
            maturity_date=maturity_date,
            hedged_item_desc=hedged_item_desc.strip(),
            hedged_item_nature=HedgedItemNature(hedged_item_nature),
            expected_transaction_date=expected_transaction_date,
            risk_hedged=RiskHedged.fx_spot_risk,
            hedge_ratio_pct=Decimal(str(hedge_ratio_pct_val)) / Decimal("100"),
            oci_treatment=oci_treatment,
            economic_relationship=economic_relationship.strip(),
            effectiveness_method=EffectivenessMethod.dollar_offset,
            discount_rate_annual=discount_rate_val,
            counterparty=counterparty.strip(),
            sources_of_ineffectiveness=sources_of_ineffectiveness.strip() or None,
        )
    except ValidationError as exc:
        for err in exc.errors():
            field = " \u2192 ".join(str(x) for x in err["loc"])
            st.error(f"**{field}:** {err['msg']}")
        st.stop()
    except Exception as exc:
        st.error(f"Unexpected error building hedge model: {exc}")
        st.stop()

    try:
        storage.save_hedge(hedge)
    except Exception as exc:
        st.error(f"Failed to save hedge: {exc}")
        st.stop()

    st.toast(f"Hedge {hedge.hedge_id} saved!", icon="\u2705")
    st.switch_page("app.py")
