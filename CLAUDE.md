# Project Conventions — Cash Flow Hedge Calculator

Claude Code reads this file at the start of every session. These rules are non-negotiable.

## Stack

- Python 3.11 or higher
- Streamlit for the UI
- Pydantic v2 for data models
- pytest for tests
- `Decimal` for all financial arithmetic — see rules below

## Non-negotiable rules

1. **All financial math uses `Decimal`, never `float`.** Float rounding will silently corrupt effectiveness ratios over a multi-month hedge. Every module that touches money begins with:
   ```python
   from decimal import Decimal, getcontext
   getcontext().prec = 28
   ```
   Pydantic model fields for monetary amounts are typed `Decimal`, not `float`.

2. **`calculations.py` is a pure function library.** No I/O, no Streamlit imports, no logging, no file access. This keeps it trivially unit-testable and replayable from a log row.

3. **Every period computation produces exactly one log row.** Never compute silently. If logging fails, the whole period fails loudly.

4. **Type everything.** Every function signature has type hints. Every data structure is a Pydantic model. `mypy --strict` passes.

## Coding conventions

- Module names use `snake_case`.
- Variable names match the terminology in `SPEC.md` exactly — `cum_effective` not `accumulated_eff`, `delta_fv_t` not `dfv`.
- Sign convention: **positive FV = derivative asset** (company has a gain); **negative = derivative liability**. The `direction` field (`buy_foreign` / `sell_foreign`) flips signs inside `calculations.py`, not at the UI layer.
- Dates are always `datetime.date` objects in logic. Strings (ISO-8601) appear only at serialization boundaries (JSON log rows, CSV export).
- Currency codes are ISO 4217, uppercase, three letters.
- Rounding for display: 2 decimal places for money, 4 for rates, 6 for discount factors. Use `Decimal.quantize` with `ROUND_HALF_EVEN` (banker's rounding).

## Testing

- `pytest tests/` must pass before any commit.
- New calculation logic requires at least one golden-number fixture in `tests/fixtures.py`, sourced from a published IFRS 9 illustrative example.
- Run `pytest -q` often; it's cheap.

## File and workspace rules

- Never commit anything under `logs/` or `hedges/` — these hold runtime output and user data.
- `.gitignore` excludes: `logs/`, `hedges/`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `*.pyc`.
- Never log the full notional amount in plain text if a secrets scanner is present — use the hedge_id as the identifier in any external surface.

## Where to look

- **`SPEC.md`** — functional spec: input schemas, formulas, journal templates, log format.
- **`README.md`** — how to install and run locally.
- **IFRS 9 references** — all formulas in `calculations.py` carry a comment pointing to the standard paragraph (e.g. `# IFRS 9 B6.5.5`).

## What Claude Code should *not* do without asking

- Add a new Python dependency.
- Change a public function signature in `calculations.py` or `models.py` (these are the testable surface).
- Modify files under `tests/fixtures.py` — the golden numbers are the ground truth.
- Introduce threading, async, or a new web framework.
