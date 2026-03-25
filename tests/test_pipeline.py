"""Unit tests for the data pipeline: cleaning, storage, and API normalization."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.cleaning import TradeCleaner, DEFAULT_CIF_FOB_RATIO
from src.pipeline.comtrade_api import ComtradeAPI
from src.pipeline.storage import TradeStorage
from tests.conftest import fixture_to_raw_records, load_fixture_into_db


# ============================================================================
# TradeCleaner tests
# ============================================================================


class TestTradeCleaner:
    """Tests for data cleaning and normalization."""

    def test_clean_basic_export(self, cleaner: TradeCleaner) -> None:
        """A valid export record should be cleaned with FOB = trade_value."""
        record = {
            "reporter_code": 156,
            "partner_code": 276,
            "commodity_code": "8542",
            "flow_code": 2,  # Export
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 1_000_000.0,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": 5000.0,
            "qty": 5000.0,
            "qty_unit_code": 1,  # kg
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["trade_value_usd"] == 1_000_000.0
        assert result["fob_value_usd"] == 1_000_000.0  # FOB = trade_value for exports
        assert result["unit_price_usd"] == pytest.approx(200.0)
        assert result["is_confidential"] == 0

    def test_clean_import_cif_to_fob(self, cleaner: TradeCleaner) -> None:
        """Import records should have FOB derived from CIF using the ratio."""
        record = {
            "reporter_code": 276,
            "partner_code": 156,
            "commodity_code": "8542",
            "flow_code": 1,  # Import
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 1_060_000.0,
            "cif_value_usd": 1_060_000.0,
            "fob_value_usd": None,
            "net_weight_kg": 5000.0,
            "qty": 5000.0,
            "qty_unit_code": 1,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        expected_fob = 1_060_000.0 / DEFAULT_CIF_FOB_RATIO
        assert result["fob_value_usd"] == pytest.approx(expected_fob, rel=1e-4)

    def test_clean_missing_essential_fields_returns_none(self, cleaner: TradeCleaner) -> None:
        """Records with missing essential fields should be discarded."""
        record = {
            "reporter_code": None,
            "partner_code": 276,
            "commodity_code": "8542",
            "flow_code": 2,
            "period": "2021",
        }
        assert cleaner.clean_record(record) is None

    def test_confidential_detection_zero_value(self, cleaner: TradeCleaner) -> None:
        """Zero trade value for known-confidential commodities should be flagged."""
        record = {
            "reporter_code": 840,
            "partner_code": 682,
            "commodity_code": "2709",  # Petroleum crude — known confidential
            "flow_code": 1,
            "period": "2020",
            "frequency": "A",
            "trade_value_usd": 0,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": None,
            "qty": None,
            "qty_unit_code": None,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["is_confidential"] == 1

    def test_confidential_detection_null_value(self, cleaner: TradeCleaner) -> None:
        """Null trade value for known-confidential commodities should be flagged."""
        record = {
            "reporter_code": 36,
            "partner_code": 156,
            "commodity_code": "2601",  # Iron ore — known confidential
            "flow_code": 2,
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": None,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": None,
            "qty": None,
            "qty_unit_code": None,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["is_confidential"] == 1

    def test_non_confidential_zero_value(self, cleaner: TradeCleaner) -> None:
        """Zero value for non-confidential commodities should NOT be flagged confidential."""
        record = {
            "reporter_code": 156,
            "partner_code": 276,
            "commodity_code": "6110",  # Textiles — not typically confidential
            "flow_code": 2,
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 0,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": None,
            "qty": None,
            "qty_unit_code": None,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["is_confidential"] == 0

    def test_re_export_flagging(self, cleaner: TradeCleaner) -> None:
        """Flow codes 3 and 4 should set is_re_export = 1."""
        record = {
            "reporter_code": 702,
            "partner_code": 276,
            "commodity_code": "8542",
            "flow_code": 3,  # Re-export
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 500_000.0,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": 100.0,
            "qty": None,
            "qty_unit_code": None,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["is_re_export"] == 1

    def test_aggregate_partner_note(self, cleaner: TradeCleaner) -> None:
        """Aggregate partners (World, EU, Areas NES) should be noted."""
        for partner_code in (0, 97, 899):
            record = {
                "reporter_code": 156,
                "partner_code": partner_code,
                "commodity_code": "8542",
                "flow_code": 2,
                "period": "2021",
                "frequency": "A",
                "trade_value_usd": 1_000_000.0,
                "cif_value_usd": None,
                "fob_value_usd": None,
                "net_weight_kg": 100.0,
                "qty": None,
                "qty_unit_code": None,
            }
            result = cleaner.clean_record(record)
            assert result is not None
            assert "Aggregate partner" in (result["cleaning_notes"] or "")

    def test_unit_price_calculation_by_weight(self, cleaner: TradeCleaner) -> None:
        """Unit price should be trade_value / weight when weight is available."""
        record = {
            "reporter_code": 156,
            "partner_code": 276,
            "commodity_code": "7108",
            "flow_code": 2,
            "period": "2020",
            "frequency": "A",
            "trade_value_usd": 40_000_000.0,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": 1000.0,
            "qty": None,
            "qty_unit_code": None,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["unit_price_usd"] == pytest.approx(40_000.0)

    def test_quality_score_full_data(self, cleaner: TradeCleaner) -> None:
        """Record with all data present should get quality score 1.0."""
        record = {
            "reporter_code": 156,
            "partner_code": 276,
            "commodity_code": "8542",
            "flow_code": 2,
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 1_000_000.0,
            "cif_value_usd": None,
            "fob_value_usd": 1_000_000.0,
            "net_weight_kg": 5000.0,
            "qty": 5000.0,
            "qty_unit_code": 1,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["quality_score"] == 1.0

    def test_quality_score_missing_data(self, cleaner: TradeCleaner) -> None:
        """Record with missing weight/qty should get lower quality score."""
        record = {
            "reporter_code": 156,
            "partner_code": 276,
            "commodity_code": "8542",
            "flow_code": 2,
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 1_000_000.0,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": None,
            "qty": None,
            "qty_unit_code": None,
        }
        result = cleaner.clean_record(record)
        assert result is not None
        assert result["quality_score"] < 1.0

    def test_clean_records_batch(self, cleaner: TradeCleaner) -> None:
        """Batch cleaning should filter out invalid records and return cleaned ones."""
        records = [
            {
                "reporter_code": 156, "partner_code": 276, "commodity_code": "8542",
                "flow_code": 2, "period": "2021", "frequency": "A",
                "trade_value_usd": 1_000_000.0, "cif_value_usd": None,
                "fob_value_usd": None, "net_weight_kg": 100.0,
                "qty": None, "qty_unit_code": None,
            },
            {
                "reporter_code": None, "partner_code": 276, "commodity_code": "8542",
                "flow_code": 2, "period": "2021",
            },  # Missing reporter — should be discarded
        ]
        cleaned = cleaner.clean_records(records)
        assert len(cleaned) == 1

    def test_negative_value_treated_as_none(self, cleaner: TradeCleaner) -> None:
        """Negative trade values should be treated as None."""
        assert cleaner._clean_value(-100.0) is None
        assert cleaner._clean_value(0.0) == 0.0
        assert cleaner._clean_value(100.0) == 100.0


# ============================================================================
# ComtradeAPI normalization tests
# ============================================================================


class TestComtradeAPINormalization:
    """Tests for the API record normalization logic (no network calls)."""

    def test_normalize_record(self) -> None:
        """API record fields should map to our internal schema."""
        raw = {
            "reporterCode": 156,
            "partnerCode": 276,
            "cmdCode": "8542",
            "flowCode": 2,
            "period": 2021,
            "freqCode": "A",
            "primaryValue": 1_000_000.0,
            "cifvalue": None,
            "fobvalue": 1_000_000.0,
            "netWgt": 5000.0,
            "qty": 5000.0,
            "qtyUnitCode": 1,
            "qtyUnitAbbr": "kg",
            "customsCode": None,
            "motCode": 1,
            "motDesc": "Sea",
            "classificationCode": "HS",
            "refYear": 2021,
            "datasetCode": "HS2021",
        }
        normalized = ComtradeAPI.normalize_record(raw)
        assert normalized["reporter_code"] == 156
        assert normalized["partner_code"] == 276
        assert normalized["commodity_code"] == "8542"
        assert normalized["flow_code"] == 2
        assert normalized["period"] == "2021"
        assert normalized["trade_value_usd"] == 1_000_000.0
        assert normalized["is_re_export"] == 0

    def test_normalize_re_export(self) -> None:
        """Re-export flow codes should set is_re_export."""
        raw = {"reporterCode": 702, "partnerCode": 276, "cmdCode": "8542",
               "flowCode": 3, "period": 2021, "freqCode": "A",
               "primaryValue": 500_000.0}
        normalized = ComtradeAPI.normalize_record(raw)
        assert normalized["is_re_export"] == 1

    def test_join_codes_single(self) -> None:
        """Single code should be returned as string."""
        assert ComtradeAPI._join_codes(156) == "156"
        assert ComtradeAPI._join_codes("8542") == "8542"

    def test_join_codes_list(self) -> None:
        """List of codes should be comma-separated."""
        assert ComtradeAPI._join_codes([156, 276]) == "156,276"
        assert ComtradeAPI._join_codes(["8542", "8541"]) == "8542,8541"

    def test_is_world_or_nes(self) -> None:
        """World (0) and Areas NES (899) should be detected."""
        assert ComtradeAPI.is_world_or_nes(0) is True
        assert ComtradeAPI.is_world_or_nes(899) is True
        assert ComtradeAPI.is_world_or_nes(156) is False


# ============================================================================
# TradeStorage tests
# ============================================================================


class TestTradeStorage:
    """Tests for SQLite storage layer."""

    def test_initialize_creates_tables(self, storage: TradeStorage) -> None:
        """Initialization should create all required tables and views."""
        tables = storage.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "countries" in table_names
        assert "commodities" in table_names
        assert "trade_records" in table_names
        assert "cleaned_records" in table_names
        assert "fetch_log" in table_names

        views = storage.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
        view_names = {row["name"] for row in views}
        assert "mirror_pairs" in view_names
        assert "phantom_exports" in view_names
        assert "phantom_imports" in view_names

    def test_upsert_country(self, storage: TradeStorage) -> None:
        """Country upsert should insert and update."""
        storage.upsert_country(156, "China", iso3="CHN")
        row = storage.conn.execute(
            "SELECT * FROM countries WHERE country_code = 156"
        ).fetchone()
        assert row["name"] == "China"
        assert row["iso3"] == "CHN"

        # Update
        storage.upsert_country(156, "People's Republic of China", iso3="CHN")
        row = storage.conn.execute(
            "SELECT * FROM countries WHERE country_code = 156"
        ).fetchone()
        assert row["name"] == "People's Republic of China"

    def test_upsert_commodity(self, storage: TradeStorage) -> None:
        """Commodity upsert should insert and update."""
        storage.upsert_commodity("7108", "Gold", hs_level=4)
        row = storage.conn.execute(
            "SELECT * FROM commodities WHERE commodity_code = '7108'"
        ).fetchone()
        assert row["description"] == "Gold"
        assert row["hs_level"] == 4

    def test_insert_raw_records(self, storage: TradeStorage) -> None:
        """Raw records should be inserted into trade_records table."""
        storage.upsert_country(156, "China", "CHN")
        storage.upsert_country(276, "Germany", "DEU")
        storage.upsert_commodity("8542", "Electronic integrated circuits", hs_level=4)

        records = [{
            "reporter_code": 156,
            "partner_code": 276,
            "commodity_code": "8542",
            "flow_code": 2,
            "period": "2021",
            "frequency": "A",
            "trade_value_usd": 1_000_000.0,
            "cif_value_usd": None,
            "fob_value_usd": 1_000_000.0,
            "net_weight_kg": 5000.0,
            "qty": 5000.0,
            "qty_unit_code": 1,
            "qty_unit_desc": "kg",
            "is_re_export": 0,
            "is_confidential": 0,
            "customs_code": None,
            "mot_code": None,
            "mot_desc": None,
            "classification": "HS",
            "ref_year": 2021,
            "dataset_code": "test",
        }]
        count = storage.insert_raw_records(records)
        assert count == 1
        assert storage.get_record_count()["raw_records"] == 1

    def test_insert_cleaned_records(self, storage: TradeStorage) -> None:
        """Cleaned records should link back to raw records."""
        storage.upsert_country(156, "China", "CHN")
        storage.upsert_country(276, "Germany", "DEU")
        storage.upsert_commodity("8542", "Electronic ICs", hs_level=4)

        raw = [{
            "reporter_code": 156, "partner_code": 276,
            "commodity_code": "8542", "flow_code": 2,
            "period": "2021", "frequency": "A",
            "trade_value_usd": 1_000_000.0, "cif_value_usd": None,
            "fob_value_usd": 1_000_000.0, "net_weight_kg": 5000.0,
            "qty": 5000.0, "qty_unit_code": 1, "qty_unit_desc": "kg",
            "is_re_export": 0, "is_confidential": 0,
            "customs_code": None, "mot_code": None, "mot_desc": None,
            "classification": "HS", "ref_year": 2021, "dataset_code": "test",
        }]
        storage.insert_raw_records(raw)

        cleaner = TradeCleaner()
        cleaned = cleaner.clean_records(raw)
        count = storage.insert_cleaned_records(cleaned)
        assert count == 1
        assert storage.get_record_count()["cleaned_records"] == 1

    def test_fetch_log(self, storage: TradeStorage) -> None:
        """Fetch logging and is_fetched should work together."""
        assert storage.is_fetched(156, "2021") is False
        storage.log_fetch(reporter_code=156, period="2021", frequency="A", record_count=100)
        assert storage.is_fetched(156, "2021") is True

    def test_fetch_log_with_error(self, storage: TradeStorage) -> None:
        """Error fetches should not count as fetched."""
        storage.log_fetch(
            reporter_code=156, period="2021", frequency="A",
            status="error", error_message="API timeout",
        )
        assert storage.is_fetched(156, "2021") is False

    def test_export_to_csv(self, storage: TradeStorage, tmp_path: Path) -> None:
        """Export should write a valid CSV file."""
        storage.upsert_country(156, "China", "CHN")
        storage.upsert_country(276, "Germany", "DEU")
        storage.upsert_commodity("8542", "ICs", hs_level=4)

        raw = [{
            "reporter_code": 156, "partner_code": 276,
            "commodity_code": "8542", "flow_code": 2,
            "period": "2021", "frequency": "A",
            "trade_value_usd": 1_000_000.0, "cif_value_usd": None,
            "fob_value_usd": 1_000_000.0, "net_weight_kg": 5000.0,
            "qty": 5000.0, "qty_unit_code": 1, "qty_unit_desc": "kg",
            "is_re_export": 0, "is_confidential": 0,
            "customs_code": None, "mot_code": None, "mot_desc": None,
            "classification": "HS", "ref_year": 2021, "dataset_code": "test",
        }]
        storage.insert_raw_records(raw)

        output = tmp_path / "export.csv"
        count = storage.export_to_csv(output, table="trade_records")
        assert count == 1
        assert output.exists()

    def test_mirror_pairs_view_excludes_aggregates(self, storage: TradeStorage) -> None:
        """Mirror pairs view should exclude World, EU, and Areas NES partners."""
        storage.upsert_country(156, "China", "CHN")
        storage.upsert_country(0, "World", "WLD", is_group=True)
        storage.upsert_commodity("8542", "ICs", hs_level=4)

        # Export to World — should not appear in mirror_pairs
        raw_export = {
            "reporter_code": 156, "partner_code": 0,
            "commodity_code": "8542", "flow_code": 2,
            "period": "2021", "frequency": "A",
            "trade_value_usd": 50_000_000_000.0, "cif_value_usd": None,
            "fob_value_usd": 50_000_000_000.0, "net_weight_kg": 1000000.0,
            "qty": 1000000.0, "qty_unit_code": 1, "qty_unit_desc": "kg",
            "is_re_export": 0, "is_confidential": 0,
            "customs_code": None, "mot_code": None, "mot_desc": None,
            "classification": "HS", "ref_year": 2021, "dataset_code": "test",
        }
        storage.insert_raw_records([raw_export])
        cleaner = TradeCleaner()
        cleaned = cleaner.clean_records([raw_export])
        storage.insert_cleaned_records(cleaned)

        pairs = storage.get_mirror_pairs()
        assert len(pairs) == 0


# ============================================================================
# Fixture loading tests
# ============================================================================


class TestFixtureLoading:
    """Tests that fixture data loads correctly into the database."""

    def test_load_venezuela_gold_fixture(self, storage: TradeStorage) -> None:
        """Venezuela gold fixture should load all records."""
        count = load_fixture_into_db(storage, "venezuela_gold")
        assert count == 20  # 20 rows in data.csv

    def test_load_phantom_shipment_fixture(self, storage: TradeStorage) -> None:
        """Phantom shipment fixture should load all records."""
        count = load_fixture_into_db(storage, "phantom_shipment")
        assert count == 6

    def test_load_confidential_fixture(self, storage: TradeStorage) -> None:
        """Confidential fixture should load and flag confidential records."""
        count = load_fixture_into_db(storage, "confidential")
        assert count > 0

        # Check that zero-value petroleum records are flagged confidential
        rows = storage.conn.execute(
            "SELECT * FROM cleaned_records WHERE commodity_code = '2709' AND is_confidential = 1"
        ).fetchall()
        assert len(rows) > 0
