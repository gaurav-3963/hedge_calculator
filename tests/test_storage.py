from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from decimal import Decimal, getcontext

import pytest

getcontext().prec = 28

import storage
from models import HedgeInception
from tests.fixtures import HEDGE_BUY, HEDGE_SELL


# ---------------------------------------------------------------------------
# save_hedge
# ---------------------------------------------------------------------------

class TestSaveHedge:
    def test_creates_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        path = storage.save_hedge(HEDGE_SELL)
        assert path.exists()
        assert path.suffix == ".json"

    def test_filename_matches_hedge_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        path = storage.save_hedge(HEDGE_SELL)
        assert path.stem == HEDGE_SELL.hedge_id

    def test_file_is_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        path = storage.save_hedge(HEDGE_SELL)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["hedge_id"] == HEDGE_SELL.hedge_id

    def test_decimal_serialized_as_string_not_float(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        path = storage.save_hedge(HEDGE_SELL)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Pydantic v2 serializes Decimal as string in JSON
        assert isinstance(data["notional_foreign"], str)
        assert isinstance(data["contract_rate"], str)
        assert isinstance(data["discount_rate_annual"], str)

    def test_creates_hedges_directory(self, tmp_path, monkeypatch):
        target = tmp_path / "new_hedges_dir"
        monkeypatch.setattr(storage, "_HEDGES_DIR", target)
        assert not target.exists()
        storage.save_hedge(HEDGE_SELL)
        assert target.exists()


# ---------------------------------------------------------------------------
# load_hedge
# ---------------------------------------------------------------------------

class TestLoadHedge:
    def test_returns_hedge_inception(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_SELL)
        result = storage.load_hedge(HEDGE_SELL.hedge_id)
        assert isinstance(result, HedgeInception)

    def test_hedge_id_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_SELL)
        result = storage.load_hedge(HEDGE_SELL.hedge_id)
        assert result.hedge_id == HEDGE_SELL.hedge_id

    def test_decimal_fields_are_decimal_type(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_SELL)
        result = storage.load_hedge(HEDGE_SELL.hedge_id)
        assert isinstance(result.notional_foreign, Decimal)
        assert isinstance(result.contract_rate, Decimal)
        assert isinstance(result.discount_rate_annual, Decimal)


# ---------------------------------------------------------------------------
# list_hedges
# ---------------------------------------------------------------------------

class TestListHedges:
    def test_empty_when_no_hedges(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        assert storage.list_hedges() == []

    def test_empty_when_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "nonexistent")
        assert storage.list_hedges() == []

    def test_lists_saved_hedge_ids(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_SELL)
        storage.save_hedge(HEDGE_BUY)
        ids = storage.list_hedges()
        assert HEDGE_SELL.hedge_id in ids
        assert HEDGE_BUY.hedge_id in ids

    def test_returns_sorted_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_BUY)
        storage.save_hedge(HEDGE_SELL)
        ids = storage.list_hedges()
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Round-trip: save + load produces identical model
# ---------------------------------------------------------------------------

class TestRoundTrip:
    @pytest.mark.parametrize("hedge", [HEDGE_SELL, HEDGE_BUY])
    def test_model_dump_identical(self, hedge, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        saved_path = storage.save_hedge(hedge)
        loaded = storage.load_hedge(saved_path.stem)
        assert loaded.model_dump() == hedge.model_dump()

    def test_decimal_precision_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_SELL)
        loaded = storage.load_hedge(HEDGE_SELL.hedge_id)
        assert loaded.contract_rate == HEDGE_SELL.contract_rate
        assert loaded.inception_spot == HEDGE_SELL.inception_spot
        assert loaded.discount_rate_annual == HEDGE_SELL.discount_rate_annual
        assert loaded.notional_foreign == HEDGE_SELL.notional_foreign

    def test_stem_equals_hedge_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        path = storage.save_hedge(HEDGE_SELL)
        assert path.stem == HEDGE_SELL.hedge_id

    def test_enums_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "_HEDGES_DIR", tmp_path / "hedges")
        storage.save_hedge(HEDGE_SELL)
        loaded = storage.load_hedge(HEDGE_SELL.hedge_id)
        assert loaded.direction == HEDGE_SELL.direction
        assert loaded.hedged_item_nature == HEDGE_SELL.hedged_item_nature
        assert loaded.effectiveness_method == HEDGE_SELL.effectiveness_method
