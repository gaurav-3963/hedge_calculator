# V1.1 Specification — Cash Flow Hedge Accounting Calculator

## 1. Overview

A Streamlit-based calculator implementing **IFRS 9 cash flow hedge accounting** for forward foreign exchange contracts. For each hedge relationship the tool accepts inception data once, then per-period spot/forward rates each month, and produces:

- Derivative fair value (MTM) each period
- Effectiveness test result (cumulative lower-of method)
- OCI vs P&L split for the period
- Full set of journal entries (Dr/Cr lines)
- An append-only audit log row

## 2. V1 Scope

| Dimension | V1 | Deferred to |
|---|---|---|
| Hedging instrument | Forward FX contracts only | V2: options, swaps |
| Hedged item | Forecasted FX transaction (sale / purchase / interest) | — |
| Risk type | Spot FX rate risk | — |
| Effectiveness method | Dollar-offset, cumulative lower-of | V2: regression |
| Number of hedges | One at a time | V2: portfolio view |
| Spot rate source | Manual entry + optional API fetch per period | — |
| Output channels | In-app tables + CSV download | V2: Excel, PDF |

## 3. Inception Input Schema

This is the hedge designation memo captured once at trade date. IFRS 9 requires formal documentation of all of these.

### IFRS 9 mandatory

| Field | Type | Example | Notes |
|---|---|---|---|
| `hedge_id` | str | `CFH-2026-001` | Unique, user-defined |
| `inception_date` | date | 2026-01-15 | Trade date |
| `hedge_type` | enum | `cash_flow` | Fixed in V1 |
| `hedging_instrument` | enum | `forward` | Fixed in V1 |
| `direction` | enum | `buy_foreign` / `sell_foreign` | Drives sign of FV |
| `notional_foreign` | Decimal | 100000 | In foreign currency |
| `foreign_ccy` | str | `USD` | ISO 4217 |
| `functional_ccy` | str | `INR` | Reporting currency |
| `contract_rate` | Decimal | 84.50 | Forward rate locked at inception (K) |
| `inception_spot` | Decimal | 83.20 | Spot at trade date |
| `maturity_date` | date | 2026-12-31 | Contract settlement |
| `hedged_item_desc` | str | "USD 100k forecast export receivable" | Free text |
| `hedged_item_nature` | enum | `forecast_sale`, `forecast_purchase`, `forecast_interest` | Drives reclassification account |
| `expected_transaction_date` | date | 2026-12-28 | When forecast CF occurs |
| `risk_hedged` | enum | `fx_spot_risk` | Fixed in V1 |
| `hedge_ratio_pct` | Decimal | 0.80 | Fraction of notional hedged, 0 < x ≤ 1 (e.g. 0.80 = 80%) |
| `economic_relationship` | str (long) | — | Justification text |
| `effectiveness_method` | enum | `dollar_offset` | Fixed in V1 |
| `discount_rate_annual` | Decimal | 0.070 | For DCF (e.g. 7.0%). **Default 0 = simplified mode, DF always 1** |
| `oci_treatment` | Literal | `reclassify_to_pnl` / `basis_adjustment` | `basis_adjustment` only for `forecast_purchase`; see §6.5 |
| `counterparty` | str | "HDFC Bank" | Bank / broker name |

### Optional

| Field | Notes |
|---|---|
| `sources_of_ineffectiveness` | Free text, per IFRS 9.B6.4.x |
| `tenor_days` | Derived: `maturity_date − inception_date` |

## 4. Per-Period Input Schema

Collected each month-end until maturity.

| Field | Type | Notes |
|---|---|---|
| `period_number` | int | 1, 2, 3, … |
| `period_end_date` | date | Month-end |
| `spot_rate` | Decimal | Manual OR fetched from API |
| `days_to_maturity` | int | Derived from `period_end_date` and `maturity_date` |

> `forward_rate_remaining` (reserved for V2): the model field exists on `PeriodInput` but is always `None` in V1. The V1 UI does not expose it. Calculations fall back to `spot_rate` when it is `None`.

## 5. Calculation Engine

All arithmetic uses `Decimal` with `getcontext().prec = 28`. No `float`.

### 5.1 Discount factor

When `discount_rate_annual == 0` (simplified mode), `DF_t = 1` (no discounting).
Otherwise (full-DCF mode):
```
DF_t = 1 / (1 + r × days_to_maturity / 365)
```

### 5.2 Fair value of the forward

Scaled by `hedge_ratio_pct`. For a `buy_foreign` position:
```
FV_t = Notional × HedgeRatio × (CurrentRate_t − K) × DF_t
```
For `sell_foreign`, flip sign:
```
FV_t = Notional × HedgeRatio × (K − CurrentRate_t) × DF_t
```
`CurrentRate_t` is the market forward rate (`forward_rate_remaining`) when provided, otherwise `spot_rate`.

> Sign convention: positive FV ⇒ derivative asset; negative FV ⇒ derivative liability.

### 5.3 Change in derivative FV
```
ΔFV_t = FV_t − FV_{t-1}        (FV_0 := 0)
CumΔFV_t = Σ ΔFV_i  (i = 1..t)
```

### 5.4 Hypothetical derivative

A perfect off-market forward struck at inception spot. Scaled by `hedge_ratio_pct`.
```
Hyp_t = Notional × HedgeRatio × (Spot_t − InceptionSpot) × DF_t   (buy_foreign)
Hyp_t = Notional × HedgeRatio × (InceptionSpot − Spot_t) × DF_t   (sell_foreign)
ΔHyp_t = Hyp_t − Hyp_{t-1}
CumΔHyp_t = Σ ΔHyp_i
```

### 5.5 Cumulative lower-of (the effectiveness split)
IFRS 9 requires the cumulative effective portion to be the *lesser* of cumulative derivative change and cumulative hypothetical change, preserving sign.
```
CumEffective_t   = sign(CumΔFV_t) × min(|CumΔFV_t|, |CumΔHyp_t|)
CumIneffective_t = CumΔFV_t − CumEffective_t
```

### 5.6 Period movements (what hits OCI and P&L this period)
```
OCI_this_period = CumEffective_t   − CumEffective_{t-1}
PnL_this_period = CumIneffective_t − CumIneffective_{t-1}
```

### 5.7 Dollar-offset ratio (diagnostic only)
```
Ratio_t = |CumΔFV_t| / |CumΔHyp_t|     (undefined if CumΔHyp_t == 0)
```
Flag `ratio_in_band = (0.80 ≤ Ratio_t ≤ 1.25)`. IFRS 9 removed the strict 80–125% bright line, but it remains a useful warning signal.

> **V1.1 change:** ratio is now cumulative (not period-level). Cumulative offset is the correct IFRS 9 diagnostic for the lower-of method.

### 5.8 At maturity — two treatments

See §6.3–§6.5 for journal entries. The `oci_treatment` field controls which path is taken:

- **`reclassify_to_pnl`** (default): settle derivative, reclassify OCI balance to P&L via the hedged item's income statement line.
- **`basis_adjustment`** (forecast_purchase only): settle derivative, recognise the purchased asset at spot, adjust its cost basis by the cumulative OCI reserve.

## 6. Journal Entry Templates

Signs below assume a `buy_foreign` hedge; mirror for `sell_foreign`.

### 6.1 Period-end MTM — ΔFV positive
```
Dr  Derivative asset                     ΔFV_t
    Cr  OCI (cash flow hedge reserve)        OCI_this_period
    Cr  P&L — hedge ineffectiveness          PnL_this_period
```

### 6.2 Period-end MTM — ΔFV negative
```
Dr  OCI (cash flow hedge reserve)        |OCI_this_period|
Dr  P&L — hedge ineffectiveness          |PnL_this_period|
    Cr  Derivative liability                 |ΔFV_t|
```

### 6.3 At maturity — derivative settlement
```
Dr  Cash                                 FV_maturity        (if FV positive)
    Cr  Derivative asset                     closing_balance

    — OR if FV negative —

Dr  Derivative liability                 closing_balance
    Cr  Cash                                 |FV_maturity|
```

### 6.4 At maturity — reclassify OCI to P&L (`oci_treatment = reclassify_to_pnl`)
```
Dr  OCI (cash flow hedge reserve)        closing_OCI_balance
    Cr  Revenue / COGS / Interest            closing_OCI_balance
```
(Account depends on `hedged_item_nature`.)

### 6.5 At maturity — basis adjustment (`oci_treatment = basis_adjustment`)

IFRS 9.6.5.11(d) — applies to forecast purchase hedges. The derivative gain/loss adjusts the cost of the purchased asset.

**Step 1 — Recognise purchase at spot:**
```
Dr  Inventory                            Notional × HedgeRatio × SpotAtMaturity
    Cr  Bank / Accounts Payable              Notional × HedgeRatio × SpotAtMaturity
```

**Step 2 — Adjust cost basis by cumulative OCI reserve:**
```
Dr  OCI (cash flow hedge reserve)        CumEffective   (if OCI positive)
    Cr  Inventory                            CumEffective

    — OR if OCI negative —

Dr  Inventory                            |CumEffective|
    Cr  OCI (cash flow hedge reserve)        |CumEffective|
```

Net effect: the inventory is recognised at the effective hedged rate (K × HedgeRatio), rather than the spot rate.

## 7. Log Schema

Each period produces exactly one line in `logs/hedge_<hedge_id>.jsonl`:

```json
{
  "timestamp": "2026-06-30T18:32:11+05:30",
  "hedge_id": "CFH-2026-001",
  "period_number": 3,
  "period_end_date": "2026-06-30",
  "inputs": {
    "spot_rate": "84.20",
    "forward_rate_remaining": "84.50",
    "days_to_maturity": 184,
    "discount_rate_annual": "0.070"
  },
  "computed": {
    "discount_factor": "0.965940",
    "fv_t": "30000.00",
    "delta_fv_t": "5000.00",
    "cum_delta_fv": "30000.00",
    "hyp_t": "28000.00",
    "delta_hyp_t": "4500.00",
    "cum_delta_hyp": "28000.00",
    "cum_effective": "28000.00",
    "cum_ineffective": "2000.00",
    "oci_this_period": "4500.00",
    "pnl_this_period": "500.00",
    "ratio": "1.0714",
    "ratio_in_band": true
  },
  "journal_entries": [
    {"dr": "Derivative asset", "cr": null, "amount": "5000.00"},
    {"dr": null, "cr": "OCI (cash flow hedge reserve)", "amount": "4500.00"},
    {"dr": null, "cr": "P&L \u2014 hedge ineffectiveness", "amount": "500.00"}
  ],
  "warnings": []
}
```

`forward_rate_remaining` is `null` in simplified mode (spot used for FV).
Line-delimited JSON gives you `grep`, `jq`, replay, and append-only durability for free.

## 8. File Structure

```
hedge_calculator/
├── app.py                       # Streamlit UI entry point
├── models.py                    # Pydantic: Hedge, Period, JournalEntry, LogRow
├── calculations.py              # Pure math: DF, FV, ΔFV, lower-of, effectiveness
├── journals.py                  # Template → JournalEntry list
├── logs.py                      # JSONL append-only logger
├── storage.py                   # Save/load hedges as JSON on disk
├── fx_api.py                    # Optional spot fetch (exchangerate.host)
├── tests/
│   ├── __init__.py
│   ├── test_calculations.py     # Golden-number cases from IFRS 9 examples
│   ├── test_journals.py
│   └── fixtures.py
├── logs/                        # .gitignored; runtime output
├── hedges/                      # .gitignored; saved hedge definitions
├── CLAUDE.md
├── SPEC.md                      # this file
├── README.md
└── requirements.txt
```

## 9. Dependencies

```
streamlit>=1.31
pydantic>=2.5
pandas>=2.1
requests>=2.31
pytest>=8.0
```

## 10. Testing Strategy

- **Golden numbers.** `tests/fixtures.py` reproduces worked examples from published IFRS 9 illustrative guides (PwC / KPMG / BDO). Every calculation has a verified reference output asserted to bit-exactness.
- **Pure-function tests.** Everything in `calculations.py` is side-effect-free, so tests are one-line asserts.
- **Property tests (optional).** `hypothesis` can verify that `CumEffective + CumIneffective == CumΔFV` always holds.

## 11. Non-goals for V1

- Option or swap hedging
- Regression-based or non-statistical qualitative effectiveness
- Multi-hedge portfolio view
- PDF / Excel export (CSV only)
- Currency-rate ML forecasting
- Counterparty credit valuation adjustment (CVA / DVA)
- Net investment hedges, fair value hedges

---

## Appendix A — Simplified Mode vs Full-DCF Mode

| Feature | V1 (Simplified Mode) | V2 (Full-DCF Mode — future) |
|---|---|---|
| Discount factor | Always 1 | `1 / (1 + r × d/365)` |
| How to activate | Default; `discount_rate_annual = 0` | Set `discount_rate_annual > 0` AND provide forward curve |
| Forward rate input | Not exposed in UI — spot used for FV | Per-period market forward rate required |
| UI change needed | None | Add forward rate input to Run Period page |
| Code change needed | None | `forward_rate_remaining` already wired in `calculations.py` |
| Typical use | Illustrative examples, short-dated hedges | Long-dated hedges, precise P&L attribution |

V1 is simplified-mode only. To enable full-DCF in V2:
1. Add the forward rate `number_input` back to `pages/2_Run_Period.py`.
2. Pass the value as `forward_rate_remaining` instead of `None` when constructing `PeriodInput`.
3. Set a non-zero `discount_rate_annual` at hedge inception.

No changes to `calculations.py`, `journals.py`, or `models.py` are required — the logic is already implemented and tested.

---

## Appendix B — Hedge Ratio and Partial Hedges

`hedge_ratio_pct` (range 0 < x ≤ 1) scales both `FV_t` and `Hyp_t` identically. A ratio below 100% designates only a fraction of the notional as the hedged item — the un-hedged portion is not included in the effectiveness test.

**Example:** 10,000 USD notional, 80% ratio — the designated hedged item is USD 8,000. FV and Hyp are computed on USD 8,000 × the rate differential. The effectiveness ratio reflects only that portion.
