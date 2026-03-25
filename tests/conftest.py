"""Shared fixtures for comtrade-mirror tests."""

from __future__ import annotations

import csv
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.cleaning import TradeCleaner
from src.pipeline.storage import TradeStorage

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "analysis.yaml"


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a path for a temporary SQLite database."""
    return tmp_path / "test_comtrade.db"


@pytest.fixture
def storage(tmp_db: Path) -> TradeStorage:
    """Return an initialized TradeStorage with an empty database."""
    s = TradeStorage(db_path=tmp_db)
    s.initialize()
    return s


@pytest.fixture
def cleaner() -> TradeCleaner:
    """Return a TradeCleaner with default config."""
    return TradeCleaner()


def load_fixture_csv(fixture_name: str) -> list[dict[str, Any]]:
    """Load a fixture CSV file and return as list of dicts."""
    csv_path = FIXTURES_DIR / fixture_name / "data.csv"
    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def fixture_to_raw_records(fixture_name: str) -> list[dict[str, Any]]:
    """Convert a fixture CSV into normalized raw records matching the pipeline schema.

    Maps fixture CSV columns to the internal record format expected by
    TradeStorage.insert_raw_records().
    """
    rows = load_fixture_csv(fixture_name)
    records: list[dict[str, Any]] = []

    for row in rows:
        flow = row.get("flow", "")
        flow_code = 2 if flow == "Export" else 1  # Import=1, Export=2

        trade_value = row.get("trade_value_usd", "")
        netweight = row.get("netweight_kg", "")
        qty = row.get("qty", "")

        records.append({
            "reporter_code": int(row["reporter_code"]),
            "partner_code": int(row["partner_code"]),
            "commodity_code": str(row["commodity_code"]),
            "flow_code": flow_code,
            "period": str(row["year"]),
            "frequency": "A",
            "trade_value_usd": float(trade_value) if trade_value not in ("", None) else None,
            "cif_value_usd": None,
            "fob_value_usd": None,
            "net_weight_kg": float(netweight) if netweight not in ("", None) else None,
            "qty": float(qty) if qty not in ("", None) else None,
            "qty_unit_code": 1 if row.get("qty_unit") == "kg" else None,
            "qty_unit_desc": row.get("qty_unit"),
            "is_re_export": 0,
            "is_confidential": 0,
            "customs_code": None,
            "mot_code": None,
            "mot_desc": None,
            "classification": "HS",
            "ref_year": int(row["year"]),
            "dataset_code": f"fixture_{fixture_name}",
        })

    return records


def load_fixture_into_db(
    storage: TradeStorage,
    fixture_name: str,
    cleaner: TradeCleaner | None = None,
) -> int:
    """Load a fixture CSV into the test database (raw + cleaned records).

    Also inserts required country and commodity reference data.

    Returns:
        Number of cleaned records inserted.
    """
    if cleaner is None:
        cleaner = TradeCleaner()

    rows = load_fixture_csv(fixture_name)
    raw_records = fixture_to_raw_records(fixture_name)

    # Insert reference data for countries and commodities
    seen_countries: set[int] = set()
    seen_commodities: set[str] = set()
    for row in rows:
        code = int(row["reporter_code"])
        if code not in seen_countries:
            storage.upsert_country(code, row["reporter_name"], row.get("reporter_iso"))
            seen_countries.add(code)
        pcode = int(row["partner_code"])
        if pcode not in seen_countries:
            storage.upsert_country(pcode, row["partner_name"], row.get("partner_iso"))
            seen_countries.add(pcode)
        ccode = str(row["commodity_code"])
        if ccode not in seen_commodities:
            hs_level = len(ccode) if len(ccode) in (2, 4, 6) else 4
            storage.upsert_commodity(ccode, row.get("commodity_description", ccode), hs_level=hs_level)
            seen_commodities.add(ccode)

    # Insert raw records
    storage.insert_raw_records(raw_records)

    # Clean and insert
    cleaned = cleaner.clean_records(raw_records)
    count = storage.insert_cleaned_records(cleaned)

    return count
