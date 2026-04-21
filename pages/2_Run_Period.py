from __future__ import annotations

import calendar
import io
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

getcontext().prec = 28

import pandas as pd
import streamlit as st

import calculations
import journals
import logs
import storage
from models import JournalEntry, LogRow, PeriodInput

_ZERO = Decimal("0")
_TWO_DP = Decimal("0.01")
_FOUR_DP = Decimal("0.0001")
_SIX_DP = Decimal("0.000001")

# Column widths and headers for the schedule st.columns table
_SCHED_WIDTHS = [2.0, 1.2, 1.2, 1.5, 1.8, 1.5, 1.8, 1.5, 1.5, 1.5, 1.5, 0.7]
_SCHED_HEADERS = [
    "Month", "Spot", "Fwd K", "Monthly MTM", "Cum Actual MTM",
    "\u0394Hypo", "Cum Hypo MTM", "Effectiveness %", "Ineffective",
    "OCI Balance", "P&L", "Journal",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _m(v: Optional[Decimal]) -> str:
    if v is None:
        return ""
    return str(v.quantize(_TWO_DP, ROUND_HALF_EVEN))


def _r(v: Optional[Decimal]) -> str:
    if v is None:
        return ""
    return str(v.quantize(_FOUR_DP, ROUND_HALF_EVEN))


def _df(v: Optional[Decimal]) -> str:
    if v is None:
        return ""
    return str(v.quantize(_SIX_DP, ROUND_HALF_EVEN))


def _pct(v: Optional[Decimal]) -> str:
    if v is None:
        return "N/A"
    return f"{float(v) * 100:.1f}%"


def _amt(v: Decimal) -> str:
    return f"{float(v):,.2f}"


def _next_month(d: date, cap: date) -> date:
    month = d.month + 1
    year = d.year
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    return min(date(year, month, min(d.day, last_day)), cap)


def _prior_state(rows: list[LogRow]) -> dict:
    if not rows:
        z = _ZERO
        return dict(
            prev_fv=z,
            prev_hyp=z,
            prev_cum_delta_fv=z,
            prev_cum_delta_hyp=z,
            prev_cum_effective=z,
            prev_cum_ineffective=z,
        )
    c = rows[-1].computed
    return dict(
        prev_fv=Decimal(c["fv_t"]),
        prev_hyp=Decimal(c["hyp_t"]),
        prev_cum_delta_fv=Decimal(c["cum_delta_fv"]),
        prev_cum_delta_hyp=Decimal(c["cum_delta_hyp"]),
        prev_cum_effective=Decimal(c["cum_effective"]),
        prev_cum_ineffective=Decimal(c["cum_ineffective"]),
    )


def _entries_text(entries: list[JournalEntry]) -> str:
    parts = []
    for e in entries:
        acct = e.dr if e.dr else e.cr
        side = "Dr" if e.dr else "Cr"
        parts.append(f"{side} {acct}")
    return "; ".join(parts)


def _build_schedule_df(rows: list[LogRow], contract_rate: Decimal) -> pd.DataFrame:
    """CSV export only — includes semicolon-joined Entries string."""
    records = []
    prev_cum_hyp = Decimal("0")
    for row in rows:
        c, inp = row.computed, row.inputs
        ratio_raw = c.get("ratio")
        ratio_dec = Decimal(ratio_raw) if ratio_raw not in (None, "None") else None
        cum_hyp = Decimal(c.get("cum_delta_hyp", "0"))
        delta_hyp = cum_hyp - prev_cum_hyp
        prev_cum_hyp = cum_hyp
        records.append({
            "Month": str(row.period_end_date),
            "Spot": float(inp.get("spot_rate", 0)),
            "Fwd K": float(contract_rate),
            "Monthly MTM": float(c.get("delta_fv_t", 0)),
            "Cum Actual MTM": float(c.get("cum_delta_fv", 0)),
            "\u0394Hypo": float(delta_hyp),
            "Cum Hypo MTM": float(cum_hyp),
            "Effectiveness %": _pct(ratio_dec),
            "Ineffective": float(c.get("cum_ineffective", 0)),
            "OCI Balance": float(c.get("cum_effective", 0)),
            "P&L": float(c.get("pnl_this_period", 0)),
            "Entries": _entries_text(row.journal_entries),
        })
    return pd.DataFrame(records)


def _render_journal_table(entries: list[JournalEntry]) -> None:
    rows: list[dict] = []
    total_dr = _ZERO
    total_cr = _ZERO
    for e in entries:
        amt = _m(e.amount)
        rows.append({
            "Account": e.dr if e.dr else e.cr,
            "Dr": amt if e.dr else "",
            "Cr": amt if e.cr else "",
        })
        if e.dr:
            total_dr += e.amount
        if e.cr:
            total_cr += e.amount
    rows.append({"Account": "TOTAL", "Dr": _m(total_dr), "Cr": _m(total_cr)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


@st.dialog("Journal Entries", width="large")
def show_journal_modal(row: LogRow, hedge_id: str, hedge_desc: str) -> None:
    st.subheader(f"Period {row.period_number} \u2014 {row.period_end_date}")
    st.caption(f"{hedge_id} \u00b7 {hedge_desc}")

    if not row.journal_entries:
        st.info("No entries for this period (zero-movement period).")
        return

    rows_display: list[dict] = []
    for je in row.journal_entries:
        if je.dr:
            rows_display.append({"Account": je.dr, "Debit": _amt(je.amount), "Credit": ""})
        else:
            rows_display.append({"Account": je.cr, "Debit": "", "Credit": _amt(je.amount)})

    total_dr = sum(je.amount for je in row.journal_entries if je.dr)
    total_cr = sum(je.amount for je in row.journal_entries if je.cr)
    rows_display.append({"Account": "TOTAL", "Debit": _amt(total_dr), "Credit": _amt(total_cr)})

    st.dataframe(pd.DataFrame(rows_display), hide_index=True, use_container_width=True)

    # Plain-text block for copy-paste into accounting systems
    lines: list[str] = []
    for je in row.journal_entries:
        if je.dr:
            lines.append(f"Dr  {je.dr:<44}  {_amt(je.amount):>16}")
        else:
            lines.append(f"    Cr  {je.cr:<40}  {_amt(je.amount):>16}")
    st.code("\n".join(lines), language=None)


# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Run Period", layout="wide")

if "open_journal_period" not in st.session_state:
    st.session_state.open_journal_period = None

c_title, c_home = st.columns([5, 1])
with c_title:
    st.title("Run Period")
with c_home:
    st.write("")
    st.write("")
    if st.button("\u2190 Home", use_container_width=True):
        st.switch_page("app.py")

# ── Hedge selector ────────────────────────────────────────────────────────────

hedge_ids = storage.list_hedges()
if not hedge_ids:
    st.info("No hedges found.")
    if st.button("Create First Hedge"):
        st.switch_page("pages/1_New_Hedge.py")
    st.stop()

default_idx = 0
cid = st.session_state.get("current_hedge_id")
if cid and cid in hedge_ids:
    default_idx = hedge_ids.index(cid)

selected_id = st.selectbox("Select Hedge", hedge_ids, index=default_idx)
st.session_state.current_hedge_id = selected_id

try:
    hedge = storage.load_hedge(selected_id)
except Exception as exc:
    st.error(f"Could not load hedge: {exc}")
    st.stop()

# ── Hedge summary card ────────────────────────────────────────────────────────

with st.expander("Hedge Summary", expanded=False):
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        direction_label = (
            "Buy Foreign \u2014 import"
            if hedge.direction.value == "buy_foreign"
            else "Sell Foreign \u2014 export"
        )
        st.write(f"**Direction:** {direction_label}")
        st.write(f"**Counterparty:** {hedge.counterparty}")
        st.write(f"**Description:** {hedge.hedged_item_desc}")
        oci_label = (
            "Basis Adjustment (IFRS 9.6.5.11(d))"
            if hedge.oci_treatment == "basis_adjustment"
            else "Reclassify to P&L"
        )
        st.write(f"**OCI Treatment:** {oci_label}")
    with sc2:
        st.write(f"**Notional:** {hedge.foreign_ccy} {float(hedge.notional_foreign):,.0f}")
        st.write(f"**Hedge Ratio:** {float(hedge.hedge_ratio_pct):.0%}")
        st.write(f"**Contract Rate (K):** {_r(hedge.contract_rate)} {hedge.functional_ccy}/{hedge.foreign_ccy}")
        st.write(f"**Inception Spot:** {_r(hedge.inception_spot)}")
        disc_str = f"{float(hedge.discount_rate_annual):.2%} p.a." if hedge.discount_rate_annual else "0 (simplified mode)"
        st.write(f"**Discount Rate:** {disc_str}")
    with sc3:
        st.write(f"**Inception:** {hedge.inception_date}")
        st.write(f"**Maturity:** {hedge.maturity_date}")
        st.write(f"**Tenor:** {hedge.tenor_days} days")
        nature_label = hedge.hedged_item_nature.value.replace("_", " ").title()
        st.write(f"**Nature:** {nature_label}")

# ── Load log state (no caching — always fresh from disk) ─────────────────────

rows = logs.read_logs(selected_id)
n_periods = len(rows)
is_completed = bool(rows) and rows[-1].period_end_date >= hedge.maturity_date
next_period_number = rows[-1].period_number + 1 if rows else 1

# ── Status row ────────────────────────────────────────────────────────────────

st_c1, st_c2, st_c3 = st.columns(3)
with st_c1:
    if is_completed:
        st.success(f"\U0001f7e2 Matured \u2014 {n_periods} period(s) on record.")
    else:
        st.info(f"\U0001f535 Next period: **{next_period_number}**")

if rows:
    last = rows[-1].computed
    ratio_raw = last.get("ratio")
    ratio_dec = Decimal(ratio_raw) if ratio_raw not in (None, "None") else None
    ratio_in_band = last.get("ratio_in_band")
    band_icon = "\u2705" if ratio_in_band is True else ("\u26a0\ufe0f" if ratio_in_band is False else "")
    with st_c2:
        st.metric(f"Latest Effectiveness {band_icon}", _pct(ratio_dec))
    with st_c3:
        st.metric("OCI Reserve Balance", _m(Decimal(last.get("cum_effective", "0"))))

# ── Period input ──────────────────────────────────────────────────────────────

if not is_completed:
    st.divider()
    st.subheader(f"Period {next_period_number} \u2014 Inputs")

    suggested_date = (
        _next_month(rows[-1].period_end_date, hedge.maturity_date)
        if rows
        else _next_month(hedge.inception_date, hedge.maturity_date)
    )

    fc1, fc2 = st.columns(2)
    with fc1:
        period_end_date = st.date_input(
            "Period End Date \u2a2f",
            value=suggested_date,
            min_value=hedge.inception_date,
            max_value=hedge.maturity_date + timedelta(days=30),
            help="Month-end reporting date for this period",
        )
    with fc2:
        spot_rate_str = st.text_input(
            f"Spot Rate ({hedge.functional_ccy} per 1 {hedge.foreign_ccy}) \u2a2f",
            value="",
            placeholder="e.g. 95.50",
            help="Enter the month-end spot rate. Press Tab or click outside after typing.",
        )

        spot_rate: Optional[Decimal] = None
        spot_error: Optional[str] = None
        if spot_rate_str.strip():
            try:
                spot_rate = Decimal(spot_rate_str.strip())
                if spot_rate <= _ZERO:
                    spot_error = "Spot rate must be positive."
                    spot_rate = None
            except InvalidOperation:
                spot_error = f"'{spot_rate_str}' is not a valid number."

        if spot_error:
            st.error(spot_error)

        st.caption(
            f"Days to maturity is auto-derived: Maturity {hedge.maturity_date} \u2212 Period End Date. "
            "Final-period settlement and OCI reclassification entries are generated automatically "
            "when the period end date reaches or passes maturity."
        )

    compute_btn = st.button(
        "Compute Period",
        type="primary",
        use_container_width=True,
        disabled=(spot_rate is None),
    )

    # ── Computation ───────────────────────────────────────────────────────────

    if compute_btn and spot_rate is not None:
        period_end = period_end_date
        days_to_mat = max(0, (hedge.maturity_date - period_end).days)
        is_maturity = period_end >= hedge.maturity_date

        if rows and period_end <= rows[-1].period_end_date:
            st.error(
                f"Period end date must be after the last recorded period "
                f"({rows[-1].period_end_date})."
            )
            st.stop()

        period_input = PeriodInput(
            period_number=next_period_number,
            period_end_date=period_end,
            spot_rate=spot_rate,
            forward_rate_remaining=None,
            days_to_maturity=days_to_mat,
        )

        try:
            result = calculations.compute_period(
                hedge, period_input, **_prior_state(rows)
            )
        except Exception as exc:
            st.error(f"Computation error: {exc}")
            st.stop()

        period_warnings: list[str] = []
        if result.ratio_in_band is False:
            period_warnings.append(
                f"Dollar-offset ratio {_pct(result.ratio)} is outside the "
                "80\u2013125\u202f% band (IFRS\u202f9.B6.4.3). Review hedge effectiveness."
            )
        if is_maturity:
            nature_label = hedge.hedged_item_nature.value.replace("_", " ")
            period_warnings.append(
                f"Final period \u2014 derivative settled at cash; "
                f"cumulative OCI reclassified to {nature_label}."
            )

        spot_at_mat = spot_rate if is_maturity else None
        entries = journals.generate_entries(
            hedge, result, is_maturity=is_maturity, spot_at_maturity=spot_at_mat
        )

        log_row = LogRow(
            timestamp=datetime.now(timezone.utc).isoformat(),
            hedge_id=hedge.hedge_id,
            period_number=next_period_number,
            period_end_date=period_end,
            inputs={
                "spot_rate": str(period_input.spot_rate),
                "forward_rate_remaining": None,
                "days_to_maturity": days_to_mat,
                "discount_rate_annual": str(hedge.discount_rate_annual),
            },
            computed={
                "discount_factor": str(result.discount_factor),
                "fv_t": str(result.fv_t),
                "delta_fv_t": str(result.delta_fv_t),
                "cum_delta_fv": str(result.cum_delta_fv),
                "hyp_t": str(result.hyp_t),
                "delta_hyp_t": str(result.delta_hyp_t),
                "cum_delta_hyp": str(result.cum_delta_hyp),
                "cum_effective": str(result.cum_effective),
                "cum_ineffective": str(result.cum_ineffective),
                "oci_this_period": str(result.oci_this_period),
                "pnl_this_period": str(result.pnl_this_period),
                "ratio": str(result.ratio) if result.ratio is not None else None,
                "ratio_in_band": result.ratio_in_band,
            },
            journal_entries=entries,
            warnings=period_warnings,
        )
        logs.append_log(hedge.hedge_id, log_row)

        # ── Display results ───────────────────────────────────────────────────

        for w in period_warnings:
            st.warning(w)

        st.success(f"Period {next_period_number} computed and logged.")

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Fair Value (FV\u209c)", _m(result.fv_t))
        mc2.metric("\u0394FV (this period)", _m(result.delta_fv_t))
        mc3.metric("OCI (this period)", _m(result.oci_this_period))
        mc4.metric("P&L ineffectiveness", _m(result.pnl_this_period))

        mc5, mc6, mc7, mc8 = st.columns(4)
        mc5.metric("Cumulative Effective", _m(result.cum_effective))
        mc6.metric("Cumulative Ineffective", _m(result.cum_ineffective))
        mc7.metric("Discount Factor", _df(result.discount_factor))
        if result.ratio is not None:
            band_icon = "\u2705" if result.ratio_in_band else "\u26a0\ufe0f"
            mc8.metric(f"Effectiveness {band_icon}", _pct(result.ratio))
        else:
            mc8.metric("Effectiveness", "N/A (\u0394Hyp = 0)")

        st.subheader(f"Journal Entries \u2014 Period {next_period_number}")
        _render_journal_table(entries)

# ── Cumulative schedule ───────────────────────────────────────────────────────

all_rows = logs.read_logs(selected_id)
if all_rows:
    st.divider()
    st.subheader("Cumulative Schedule")

    # Header row
    hcols = st.columns(_SCHED_WIDTHS)
    for hc, title in zip(hcols, _SCHED_HEADERS):
        hc.markdown(f"**{title}**")

    st.divider()

    # Data rows — "Journal" column holds a 📋 button per row
    prev_cum_hyp = Decimal("0")
    for row in all_rows:
        c, inp = row.computed, row.inputs
        ratio_raw = c.get("ratio")
        ratio_dec = Decimal(ratio_raw) if ratio_raw not in (None, "None") else None
        cum_hyp = Decimal(c.get("cum_delta_hyp", "0"))
        delta_hyp = cum_hyp - prev_cum_hyp
        prev_cum_hyp = cum_hyp

        dcols = st.columns(_SCHED_WIDTHS)
        dcols[0].write(str(row.period_end_date))
        dcols[1].write(_r(Decimal(inp.get("spot_rate", "0"))))
        dcols[2].write(_r(hedge.contract_rate))
        dcols[3].write(_m(Decimal(c.get("delta_fv_t", "0"))))
        dcols[4].write(_m(Decimal(c.get("cum_delta_fv", "0"))))
        dcols[5].write(_m(delta_hyp))
        dcols[6].write(_m(cum_hyp))
        dcols[7].write(_pct(ratio_dec))
        dcols[8].write(_m(Decimal(c.get("cum_ineffective", "0"))))
        dcols[9].write(_m(Decimal(c.get("cum_effective", "0"))))
        dcols[10].write(_m(Decimal(c.get("pnl_this_period", "0"))))
        if dcols[11].button("\U0001f4cb", key=f"view_{row.period_number}"):
            st.session_state.open_journal_period = row.period_number

    # Open modal if a row was clicked
    if st.session_state.open_journal_period is not None:
        selected_row = next(
            r for r in all_rows
            if r.period_number == st.session_state.open_journal_period
        )
        show_journal_modal(selected_row, hedge.hedge_id, hedge.hedged_item_desc)
        st.session_state.open_journal_period = None

    # CSV export uses the dataframe build (preserves semicolon-joined entries)
    st.divider()
    csv_df = _build_schedule_df(all_rows, hedge.contract_rate)
    csv_buf = io.StringIO()
    csv_df.to_csv(csv_buf, index=False)
    st.download_button(
        label="\u2193 Download Schedule CSV",
        data=csv_buf.getvalue(),
        file_name=f"schedule_{selected_id}.csv",
        mime="text/csv",
    )
