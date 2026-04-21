from __future__ import annotations

import sys
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

import logs
import storage

st.set_page_config(
    page_title="Cash Flow Hedge Calculator",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_btn = st.columns([5, 1])
with col_title:
    st.title("Cash Flow Hedge Accounting Calculator")
    st.caption("IFRS 9 \u00b7 Forward FX \u00b7 Cumulative Dollar-Offset Method")
with col_btn:
    st.write("")
    st.write("")
    if st.button("+ New Hedge", type="primary", use_container_width=True):
        st.switch_page("pages/1_New_Hedge.py")

st.divider()

# ── Hedge list ────────────────────────────────────────────────────────────────
hedge_ids = storage.list_hedges()

if not hedge_ids:
    st.info(
        "No hedges yet.  \n"
        "Click **+ New Hedge** to designate your first hedge relationship."
    )
    st.stop()

for hedge_id in hedge_ids:
    try:
        hedge = storage.load_hedge(hedge_id)
    except Exception as exc:
        st.error(f"**{hedge_id}** — failed to load: {exc}")
        continue

    rows = logs.read_logs(hedge_id)
    n_periods = len(rows)
    is_matured = bool(rows) and rows[-1].period_end_date >= hedge.maturity_date
    next_period = (rows[-1].period_number + 1) if rows else 1

    if is_matured:
        status_icon = "\U0001f7e2"
        status_text = f"Matured \u2014 {n_periods} period(s) complete"
    else:
        status_icon = "\U0001f535"
        status_text = f"Period {next_period} due"

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([3, 3, 2, 2])

        with c1:
            st.subheader(hedge_id)
            direction_label = (
                "Buy Foreign \u2014 import hedge"
                if hedge.direction.value == "buy_foreign"
                else "Sell Foreign \u2014 export hedge"
            )
            st.caption(direction_label)
            st.write(f"**Counterparty:** {hedge.counterparty}")
            st.write(f"**Hedged item:** {hedge.hedged_item_desc}")

        with c2:
            notional_fmt = f"{float(hedge.notional_foreign):,.0f}"
            st.metric("Notional", f"{hedge.foreign_ccy} {notional_fmt}")
            rate_fmt = hedge.contract_rate.quantize(Decimal("0.0001"), ROUND_HALF_EVEN)
            st.metric(
                "Contract Rate",
                f"{rate_fmt} {hedge.functional_ccy}/{hedge.foreign_ccy}",
            )

        with c3:
            st.write(f"**Inception:** {hedge.inception_date}")
            st.write(f"**Maturity:** {hedge.maturity_date}")
            st.write(f"**Tenor:** {hedge.tenor_days} days")
            nature_label = hedge.hedged_item_nature.value.replace("_", " ").title()
            st.write(f"**Nature:** {nature_label}")

        with c4:
            st.write(f"{status_icon} **{status_text}**")
            if n_periods:
                st.write(f"**Periods logged:** {n_periods}")
            st.write("")
            if not is_matured:
                if st.button("Run Period \u2192", key=f"run_{hedge_id}", use_container_width=True):
                    st.session_state.current_hedge_id = hedge_id
                    st.switch_page("pages/2_Run_Period.py")
            else:
                if st.button("View Schedule", key=f"view_{hedge_id}", use_container_width=True):
                    st.session_state.current_hedge_id = hedge_id
                    st.switch_page("pages/2_Run_Period.py")
