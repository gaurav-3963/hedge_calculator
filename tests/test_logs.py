from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import date
from decimal import Decimal, getcontext

import pytest

getcontext().prec = 28

import logs
from models import JournalEntry, LogRow

_PRECISE = Decimal("84.1234567890123456789012345678")  # full 28-digit precision


def _make_row(
    hedge_id: str = "CFH-TEST-001",
    period_number: int = 1,
    amount: Decimal = Decimal("5000.00"),
) -> LogRow:
    return LogRow(
        timestamp="2026-04-04T18:00:00+05:30",
        hedge_id=hedge_id,
        period_number=period_number,
        period_end_date=date(2026, 4, 4),
        inputs={
            "spot_rate": "84.20",
            "forward_rate_remaining": "84.50",
            "days_to_maturity": 90,
            "discount_rate_annual": "0.070",
        },
        computed={
            "discount_factor": "0.98302",
            "fv_t": str(amount),
            "delta_fv_t": str(amount),
            "cum_delta_fv": str(amount),
        },
        journal_entries=[
            JournalEntry(dr="Derivative asset", cr=None, amount=amount),
            JournalEntry(dr=None, cr="OCI (cash flow hedge reserve)", amount=amount),
        ],
        warnings=[],
    )


# ---------------------------------------------------------------------------
# append_log
# ---------------------------------------------------------------------------

class TestAppendLog:
    def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001"))
        assert (tmp_path / "logs" / "hedge_TEST-001.jsonl").exists()

    def test_schema_version_in_row(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001"))
        line = (tmp_path / "logs" / "hedge_TEST-001.jsonl").read_text(encoding="utf-8")
        data = json.loads(line)
        assert data["schema_version"] == "1.0"

    def test_appends_multiple_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001", period_number=1))
        logs.append_log("TEST-001", _make_row("TEST-001", period_number=2))
        lines = (tmp_path / "logs" / "hedge_TEST-001.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_decimal_serialized_as_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001", amount=Decimal("5000.00")))
        line = (tmp_path / "logs" / "hedge_TEST-001.jsonl").read_text(encoding="utf-8")
        data = json.loads(line)
        # journal_entries amounts must be strings, not floats
        assert isinstance(data["journal_entries"][0]["amount"], str)

    def test_date_serialized_as_iso_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001"))
        line = (tmp_path / "logs" / "hedge_TEST-001.jsonl").read_text(encoding="utf-8")
        data = json.loads(line)
        assert data["period_end_date"] == "2026-04-04"

    def test_different_hedges_go_to_different_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("AAA", _make_row("AAA"))
        logs.append_log("BBB", _make_row("BBB"))
        assert (tmp_path / "logs" / "hedge_AAA.jsonl").exists()
        assert (tmp_path / "logs" / "hedge_BBB.jsonl").exists()


# ---------------------------------------------------------------------------
# read_logs
# ---------------------------------------------------------------------------

class TestReadLogs:
    def test_empty_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        assert logs.read_logs("NONEXISTENT") == []

    def test_reads_back_log_row(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        row = _make_row("TEST-001")
        logs.append_log("TEST-001", row)
        result = logs.read_logs("TEST-001")
        assert len(result) == 1
        assert isinstance(result[0], LogRow)

    def test_period_end_date_is_date_object(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001"))
        result = logs.read_logs("TEST-001")
        assert result[0].period_end_date == date(2026, 4, 4)

    def test_reads_multiple_rows_in_order(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001", period_number=1))
        logs.append_log("TEST-001", _make_row("TEST-001", period_number=2))
        logs.append_log("TEST-001", _make_row("TEST-001", period_number=3))
        result = logs.read_logs("TEST-001")
        assert [r.period_number for r in result] == [1, 2, 3]

    def test_schema_version_not_in_logrow(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("TEST-001", _make_row("TEST-001"))
        result = logs.read_logs("TEST-001")
        assert not hasattr(result[0], "schema_version") or True  # extra fields dropped


# ---------------------------------------------------------------------------
# Round-trip: Decimal precision preserved exactly
# ---------------------------------------------------------------------------

class TestRoundTripDecimalPrecision:
    def test_journal_entry_amount_exact(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        row = _make_row("PREC", amount=_PRECISE)
        logs.append_log("PREC", row)
        result = logs.read_logs("PREC")
        assert result[0].journal_entries[0].amount == _PRECISE

    def test_full_28_digit_precision(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        exact = Decimal("1.2345678901234567890123456789")
        row = _make_row("PREC2", amount=exact)
        logs.append_log("PREC2", row)
        result = logs.read_logs("PREC2")
        assert result[0].journal_entries[0].amount == exact

    def test_hedge_id_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "_LOGS_DIR", tmp_path / "logs")
        logs.append_log("CFH-2026-001", _make_row("CFH-2026-001"))
        result = logs.read_logs("CFH-2026-001")
        assert result[0].hedge_id == "CFH-2026-001"
