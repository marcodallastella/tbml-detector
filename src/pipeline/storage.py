"""SQLite storage layer for UN Comtrade trade data."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default paths relative to project root
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "comtrade.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "comtrade_schema.sql"
LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "pipeline.log"


def _setup_pipeline_logger() -> logging.Logger:
    """Configure file logger for pipeline operations."""
    pipeline_log = logging.getLogger("pipeline_ops")
    if not pipeline_log.handlers:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(LOG_PATH)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        pipeline_log.addHandler(handler)
        pipeline_log.setLevel(logging.INFO)
    return pipeline_log


class TradeStorage:
    """SQLite storage for trade records with mirror analysis support."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ops_log = _setup_pipeline_logger()
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy connection with row factory."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def initialize(self) -> None:
        """Create tables from schema SQL file."""
        schema_sql = SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        self._ops_log.info("Database initialized at %s", self.db_path)

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ========================================================================
    # Reference Data
    # ========================================================================

    def upsert_country(
        self, country_code: int, name: str, iso3: str | None = None,
        is_group: bool = False, notes: str | None = None,
    ) -> None:
        """Insert or update a country reference record."""
        self.conn.execute(
            """INSERT INTO countries (country_code, iso3, name, is_group, notes)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(country_code) DO UPDATE SET
                   iso3 = excluded.iso3,
                   name = excluded.name,
                   is_group = excluded.is_group,
                   notes = excluded.notes""",
            (country_code, iso3, name, int(is_group), notes),
        )
        self.conn.commit()

    def upsert_commodity(
        self, commodity_code: str, description: str,
        parent_code: str | None = None, hs_level: int = 2,
        section: str | None = None,
    ) -> None:
        """Insert or update a commodity reference record."""
        self.conn.execute(
            """INSERT INTO commodities (commodity_code, description, parent_code, hs_level, section)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(commodity_code) DO UPDATE SET
                   description = excluded.description,
                   parent_code = excluded.parent_code,
                   hs_level = excluded.hs_level,
                   section = excluded.section""",
            (commodity_code, description, parent_code, hs_level, section),
        )
        self.conn.commit()

    # ========================================================================
    # Trade Records
    # ========================================================================

    def _ensure_reference_data(
        self, records: list[dict[str, Any]], raw_json_records: list[dict[str, Any]] | None,
    ) -> None:
        """Auto-upsert country and commodity stubs from API response data.

        Prevents FOREIGN KEY failures when inserting trade records before the
        reference tables have been populated.
        """
        for i, rec in enumerate(records):
            raw = raw_json_records[i] if raw_json_records and i < len(raw_json_records) else {}

            # Countries: reporter and partner
            for code_key, desc_key, iso_key in [
                ("reporter_code", "reporterDesc", "reporterISO"),
                ("partner_code", "partnerDesc", "partnerISO"),
            ]:
                code = rec.get(code_key)
                if code is None:
                    continue
                name = raw.get(desc_key) or str(code)
                iso3 = raw.get(iso_key)
                self.conn.execute(
                    """INSERT INTO countries (country_code, iso3, name)
                       VALUES (?, ?, ?)
                       ON CONFLICT(country_code) DO UPDATE SET
                           iso3 = COALESCE(excluded.iso3, countries.iso3),
                           name = CASE WHEN excluded.name != '' AND excluded.name != CAST(countries.country_code AS TEXT)
                                       THEN excluded.name ELSE countries.name END""",
                    (code, iso3, name),
                )

            # Commodity
            commodity_code = rec.get("commodity_code")
            if commodity_code:
                description = raw.get("cmdDesc") or commodity_code
                hs_level = len(str(commodity_code).rstrip("0") or commodity_code)
                hs_level = 2 if hs_level <= 2 else (4 if hs_level <= 4 else 6)
                self.conn.execute(
                    """INSERT INTO commodities (commodity_code, description, hs_level)
                       VALUES (?, ?, ?)
                       ON CONFLICT(commodity_code) DO UPDATE SET
                           description = CASE WHEN excluded.description != excluded.commodity_code
                                              THEN excluded.description ELSE commodities.description END""",
                    (commodity_code, description, hs_level),
                )

        self.conn.commit()

    def insert_raw_records(
        self, records: list[dict[str, Any]], raw_json_records: list[dict[str, Any]] | None = None,
    ) -> int:
        """Insert normalized raw trade records into trade_records table.

        Uses INSERT OR REPLACE to handle duplicates via the UNIQUE constraint.

        Args:
            records: Normalized records (from ComtradeAPI.normalize_record).
            raw_json_records: Optional original API responses for audit trail.

        Returns:
            Number of records inserted/updated.
        """
        self._ensure_reference_data(records, raw_json_records)
        count = 0
        for i, record in enumerate(records):
            raw_json = None
            if raw_json_records and i < len(raw_json_records):
                raw_json = json.dumps(raw_json_records[i])

            try:
                self.conn.execute(
                    """INSERT OR REPLACE INTO trade_records (
                        reporter_code, partner_code, commodity_code, flow_code,
                        period, frequency, trade_value_usd, cif_value_usd,
                        fob_value_usd, net_weight_kg, qty, qty_unit_code,
                        qty_unit_desc, is_re_export, is_confidential,
                        customs_code, mot_code, mot_desc, classification,
                        ref_year, dataset_code, raw_json, updated_at
                    ) VALUES (
                        :reporter_code, :partner_code, :commodity_code, :flow_code,
                        :period, :frequency, :trade_value_usd, :cif_value_usd,
                        :fob_value_usd, :net_weight_kg, :qty, :qty_unit_code,
                        :qty_unit_desc, :is_re_export, :is_confidential,
                        :customs_code, :mot_code, :mot_desc, :classification,
                        :ref_year, :dataset_code, :raw_json, datetime('now')
                    )""",
                    {**record, "raw_json": raw_json},
                )
                count += 1
            except sqlite3.Error as e:
                logger.warning("Failed to insert record: %s — %s", record, e)

        self.conn.commit()
        self._ops_log.info("Inserted/updated %d raw records", count)
        return count

    def insert_cleaned_records(
        self, cleaned_records: list[dict[str, Any]],
    ) -> int:
        """Insert cleaned records, linking back to raw records by unique key.

        Args:
            cleaned_records: Records from TradeCleaner.clean_records().

        Returns:
            Number of records inserted/updated.
        """
        count = 0
        for record in cleaned_records:
            # Look up the raw record ID
            row = self.conn.execute(
                """SELECT id FROM trade_records
                   WHERE reporter_code = ? AND partner_code = ?
                     AND commodity_code = ? AND flow_code = ? AND period = ?""",
                (
                    record["reporter_code"], record["partner_code"],
                    record["commodity_code"], record["flow_code"],
                    record["period"],
                ),
            ).fetchone()

            raw_id = row["id"] if row else None
            if raw_id is None:
                logger.warning(
                    "No raw record found for cleaned record: %s/%s/%s/%s/%s",
                    record["reporter_code"], record["partner_code"],
                    record["commodity_code"], record["flow_code"],
                    record["period"],
                )
                continue

            try:
                self.conn.execute(
                    """INSERT OR REPLACE INTO cleaned_records (
                        raw_record_id, reporter_code, partner_code,
                        commodity_code, flow_code, period, frequency,
                        trade_value_usd, fob_value_usd, net_weight_kg,
                        qty_normalized, qty_unit_normalized, unit_price_usd,
                        is_re_export, is_confidential, has_quantity,
                        has_weight, quality_score, cleaning_notes, cleaned_at
                    ) VALUES (
                        :raw_record_id, :reporter_code, :partner_code,
                        :commodity_code, :flow_code, :period, :frequency,
                        :trade_value_usd, :fob_value_usd, :net_weight_kg,
                        :qty_normalized, :qty_unit_normalized, :unit_price_usd,
                        :is_re_export, :is_confidential, :has_quantity,
                        :has_weight, :quality_score, :cleaning_notes,
                        datetime('now')
                    )""",
                    {**record, "raw_record_id": raw_id},
                )
                count += 1
            except sqlite3.Error as e:
                logger.warning("Failed to insert cleaned record: %s — %s", record, e)

        self.conn.commit()
        self._ops_log.info("Inserted/updated %d cleaned records", count)
        return count

    # ========================================================================
    # Fetch Tracking
    # ========================================================================

    def log_fetch(
        self,
        reporter_code: int,
        period: str,
        frequency: str,
        partner_code: int | None = None,
        commodity_code: str | None = None,
        flow_code: int | None = None,
        record_count: int = 0,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Log a fetch operation for incremental update tracking."""
        self.conn.execute(
            """INSERT INTO fetch_log (
                reporter_code, partner_code, commodity_code, flow_code,
                period, frequency, record_count, status, error_message,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                reporter_code, partner_code, commodity_code, flow_code,
                period, frequency, record_count, status, error_message,
            ),
        )
        self.conn.commit()
        self._ops_log.info(
            "Fetch logged: reporter=%s partner=%s period=%s status=%s count=%d",
            reporter_code, partner_code, period, status, record_count,
        )

    def is_fetched(
        self,
        reporter_code: int,
        period: str,
        partner_code: int | None = None,
        commodity_code: str | None = None,
    ) -> bool:
        """Check if data for a given query has already been fetched."""
        query = """SELECT 1 FROM fetch_log
                   WHERE reporter_code = ? AND period = ? AND status = 'success'"""
        params: list[Any] = [reporter_code, period]

        if partner_code is not None:
            query += " AND partner_code = ?"
            params.append(partner_code)
        if commodity_code is not None:
            query += " AND commodity_code = ?"
            params.append(commodity_code)

        return self.conn.execute(query, params).fetchone() is not None

    # ========================================================================
    # Mirror Analysis Queries
    # ========================================================================

    def get_mirror_pairs(
        self,
        commodity_code: str | None = None,
        period: str | None = None,
        exporter_code: int | None = None,
        importer_code: int | None = None,
        min_value_usd: float | None = None,
    ) -> list[sqlite3.Row]:
        """Query mirror pairs with optional filters.

        Returns rows from the mirror_pairs view.
        """
        query = "SELECT * FROM mirror_pairs WHERE 1=1"
        params: list[Any] = []

        if commodity_code:
            query += " AND commodity_code = ?"
            params.append(commodity_code)
        if period:
            query += " AND period = ?"
            params.append(period)
        if exporter_code:
            query += " AND exporter_code = ?"
            params.append(exporter_code)
        if importer_code:
            query += " AND importer_code = ?"
            params.append(importer_code)
        if min_value_usd is not None:
            query += " AND (export_value_usd >= ? OR import_value_usd >= ?)"
            params.extend([min_value_usd, min_value_usd])

        query += " ORDER BY ABS(value_gap_usd) DESC"

        return self.conn.execute(query, params).fetchall()

    def get_phantom_exports(
        self,
        period: str | None = None,
        min_value_usd: float | None = None,
    ) -> list[sqlite3.Row]:
        """Get exports with no matching import (phantom shipments)."""
        query = "SELECT * FROM phantom_exports WHERE 1=1"
        params: list[Any] = []
        if period:
            query += " AND period = ?"
            params.append(period)
        if min_value_usd is not None:
            query += " AND trade_value_usd >= ?"
            params.append(min_value_usd)
        query += " ORDER BY trade_value_usd DESC"
        return self.conn.execute(query, params).fetchall()

    def get_phantom_imports(
        self,
        period: str | None = None,
        min_value_usd: float | None = None,
    ) -> list[sqlite3.Row]:
        """Get imports with no matching export (phantom shipments)."""
        query = "SELECT * FROM phantom_imports WHERE 1=1"
        params: list[Any] = []
        if period:
            query += " AND period = ?"
            params.append(period)
        if min_value_usd is not None:
            query += " AND trade_value_usd >= ?"
            params.append(min_value_usd)
        query += " ORDER BY trade_value_usd DESC"
        return self.conn.execute(query, params).fetchall()

    def get_available_periods(self) -> list[str]:
        """Get all periods available in the database."""
        rows = self.conn.execute(
            "SELECT DISTINCT period FROM trade_records ORDER BY period"
        ).fetchall()
        return [row["period"] for row in rows]

    def get_record_count(self) -> dict[str, int]:
        """Get counts of raw and cleaned records."""
        raw = self.conn.execute("SELECT COUNT(*) as c FROM trade_records").fetchone()
        cleaned = self.conn.execute("SELECT COUNT(*) as c FROM cleaned_records").fetchone()
        return {
            "raw_records": raw["c"] if raw else 0,
            "cleaned_records": cleaned["c"] if cleaned else 0,
        }

    # ========================================================================
    # Export
    # ========================================================================

    def export_to_csv(
        self, output_path: str | Path, table: str = "cleaned_records",
        query: str | None = None,
    ) -> int:
        """Export records to CSV file.

        Args:
            output_path: Path for output CSV file.
            table: Table name to export (default: cleaned_records).
            query: Optional custom SQL query. Overrides table param.

        Returns:
            Number of rows exported.
        """
        import csv

        sql = query or f"SELECT * FROM {table}"
        cursor = self.conn.execute(sql)
        rows = cursor.fetchall()

        if not rows:
            logger.warning("No data to export")
            return 0

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        columns = [description[0] for description in cursor.description]
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(tuple(row))

        self._ops_log.info("Exported %d rows to %s", len(rows), output_path)
        return len(rows)
