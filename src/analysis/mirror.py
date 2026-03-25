"""Core mirror discrepancy computation.

Computes gaps between Country A's reported exports to B and Country B's
reported imports from A, with CIF/FOB normalization and time-lag correction.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "analysis.yaml"


@dataclass
class DiscrepancyResult:
    """Result of mirror discrepancy computation for a single pair."""

    exporter_code: int
    importer_code: int
    commodity_code: str
    period: str
    frequency: str

    # Raw reported values
    export_value_usd: float
    import_value_usd: float
    export_weight_kg: float | None
    import_weight_kg: float | None
    export_qty: float | None
    import_qty: float | None
    export_unit_price: float | None
    import_unit_price: float | None

    # CIF/FOB adjusted
    import_value_adjusted: float
    cif_fob_ratio_used: float

    # Discrepancy metrics
    d_abs: float  # V_imp - V_exp
    d_rel: float  # midpoint-normalized relative discrepancy
    d_rel_raw: float  # before CIF/FOB adjustment
    d_log: float | None  # ln(V_imp / V_exp), None if either <= 0
    q_rel: float | None  # quantity discrepancy
    up_rel: float | None  # unit price discrepancy

    # Quality flags
    export_quality: float | None = None
    import_quality: float | None = None
    is_re_export: bool = False
    is_confidential: bool = False
    data_quality_flags: list[str] = field(default_factory=list)

    # Database record IDs for traceability
    export_record_id: int | None = None
    import_record_id: int | None = None


@dataclass
class SmoothedResult:
    """Discrepancy result after lag-correction smoothing."""

    period: str
    v_exp: float
    v_imp_adjusted: float
    v_exp_smoothed: float
    v_imp_smoothed: float
    d_rel_smoothed: float


class MirrorAnalyzer:
    """Computes mirror trade discrepancies from the SQLite database.

    Reads from the mirror_pairs and phantom views created by the pipeline,
    applies CIF/FOB normalization, and optionally applies lag correction.
    """

    def __init__(
        self,
        db_path: str | Path,
        config_path: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # CIF/FOB adjustment
    # ------------------------------------------------------------------

    def get_cif_fob_ratio(self, transport_mode: str | None = None) -> float:
        """Look up CIF/FOB ratio for a given transport mode."""
        cif_config = self._config.get("cif_fob", {})
        if transport_mode:
            ratios = cif_config.get("ratios", {})
            return ratios.get(transport_mode, cif_config.get("default_ratio", 1.07))
        return cif_config.get("default_ratio", 1.07)

    def adjust_cif_fob(
        self,
        v_imp: float,
        transport_mode: str | None = None,
    ) -> tuple[float, float]:
        """Adjust import value downward by CIF/FOB ratio.

        Returns:
            Tuple of (adjusted_value, ratio_used).
        """
        ratio = self.get_cif_fob_ratio(transport_mode)
        return v_imp / ratio, ratio

    # ------------------------------------------------------------------
    # Discrepancy formulas
    # ------------------------------------------------------------------

    @staticmethod
    def compute_d_rel(v_imp: float, v_exp: float) -> float:
        """Midpoint-normalized relative discrepancy."""
        midpoint = (v_imp + v_exp) / 2.0
        if midpoint == 0:
            return 0.0
        return (v_imp - v_exp) / midpoint

    @staticmethod
    def compute_d_log(v_imp: float, v_exp: float) -> float | None:
        """Log ratio discrepancy. None if either value is non-positive."""
        if v_imp <= 0 or v_exp <= 0:
            return None
        return math.log(v_imp / v_exp)

    @staticmethod
    def compute_q_rel(q_imp: float | None, q_exp: float | None) -> float | None:
        """Midpoint-normalized quantity discrepancy."""
        if q_imp is None or q_exp is None:
            return None
        midpoint = (q_imp + q_exp) / 2.0
        if midpoint == 0:
            return None
        return (q_imp - q_exp) / midpoint

    @staticmethod
    def compute_up_rel(
        v_imp: float, q_imp: float | None,
        v_exp: float, q_exp: float | None,
    ) -> float | None:
        """Unit price discrepancy."""
        if q_imp is None or q_exp is None or q_imp == 0 or q_exp == 0:
            return None
        up_imp = v_imp / q_imp
        up_exp = v_exp / q_exp
        midpoint = (up_imp + up_exp) / 2.0
        if midpoint == 0:
            return None
        return (up_imp - up_exp) / midpoint

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def compute_discrepancies(
        self,
        commodity_code: str | None = None,
        period: str | None = None,
        exporter_code: int | None = None,
        importer_code: int | None = None,
        min_value_usd: float | None = None,
    ) -> list[DiscrepancyResult]:
        """Compute mirror discrepancies for all matching pairs.

        Reads from the mirror_pairs view and applies CIF/FOB normalization.

        Args:
            commodity_code: Filter by HS code.
            period: Filter by period (YYYY or YYYYMM).
            exporter_code: Filter by exporter country code.
            importer_code: Filter by importer country code.
            min_value_usd: Minimum trade value to include.

        Returns:
            List of DiscrepancyResult objects sorted by |d_abs| descending.
        """
        # Apply default min value based on frequency
        if min_value_usd is None:
            min_value_usd = self._config.get("min_value_thresholds", {}).get(
                "annual_usd", 10_000
            )

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

        rows = self.conn.execute(query, params).fetchall()
        results: list[DiscrepancyResult] = []

        for row in rows:
            v_exp = row["export_value_usd"] or 0.0
            v_imp = row["import_value_usd"] or 0.0

            # Raw discrepancy before adjustment
            d_rel_raw = self.compute_d_rel(v_imp, v_exp)

            # CIF/FOB adjustment
            v_imp_adj, ratio = self.adjust_cif_fob(v_imp)

            # Discrepancy metrics after adjustment
            d_abs = v_imp_adj - v_exp
            d_rel = self.compute_d_rel(v_imp_adj, v_exp)
            d_log = self.compute_d_log(v_imp_adj, v_exp)

            # Quantity metrics
            q_exp = row["export_qty"]
            q_imp = row["import_qty"]
            q_rel = self.compute_q_rel(q_imp, q_exp)

            # Unit price metrics — use weight if qty unavailable
            exp_qty_for_up = q_exp if q_exp else row["export_weight_kg"]
            imp_qty_for_up = q_imp if q_imp else row["import_weight_kg"]
            up_rel = self.compute_up_rel(v_imp_adj, imp_qty_for_up, v_exp, exp_qty_for_up)

            # Quality flags
            quality_flags: list[str] = []
            if row["export_is_confidential"] or row["import_is_confidential"]:
                quality_flags.append("confidential_flow")
            if row["export_is_re_export"] or row["import_is_re_export"]:
                quality_flags.append("re_export_involved")
            if q_exp is None and q_imp is None:
                quality_flags.append("no_quantity_data")

            results.append(DiscrepancyResult(
                exporter_code=row["exporter_code"],
                importer_code=row["importer_code"],
                commodity_code=row["commodity_code"],
                period=row["period"],
                frequency=row["frequency"],
                export_value_usd=v_exp,
                import_value_usd=v_imp,
                export_weight_kg=row["export_weight_kg"],
                import_weight_kg=row["import_weight_kg"],
                export_qty=q_exp,
                import_qty=q_imp,
                export_unit_price=row["export_unit_price"],
                import_unit_price=row["import_unit_price"],
                import_value_adjusted=v_imp_adj,
                cif_fob_ratio_used=ratio,
                d_abs=d_abs,
                d_rel=d_rel,
                d_rel_raw=d_rel_raw,
                d_log=d_log,
                q_rel=q_rel,
                up_rel=up_rel,
                export_quality=row["export_quality"],
                import_quality=row["import_quality"],
                is_re_export=bool(row["export_is_re_export"] or row["import_is_re_export"]),
                is_confidential=bool(row["export_is_confidential"] or row["import_is_confidential"]),
                data_quality_flags=quality_flags,
                export_record_id=row["export_record_id"],
                import_record_id=row["import_record_id"],
            ))

        return results

    def get_corridor_history(
        self,
        exporter_code: int,
        importer_code: int,
        commodity_code: str,
    ) -> list[DiscrepancyResult]:
        """Get all historical discrepancies for a specific corridor.

        Returns results sorted by period ascending for time-series analysis.
        """
        results = self.compute_discrepancies(
            commodity_code=commodity_code,
            exporter_code=exporter_code,
            importer_code=importer_code,
            min_value_usd=0,  # include all for history
        )
        results.sort(key=lambda r: r.period)
        return results

    def apply_lag_correction(
        self,
        corridor_results: list[DiscrepancyResult],
    ) -> list[SmoothedResult]:
        """Apply rolling window smoothing to absorb reporting lags.

        Args:
            corridor_results: Results for a single corridor, sorted by period.

        Returns:
            Smoothed results with lag-corrected discrepancy metrics.
        """
        if not corridor_results:
            return []

        frequency = corridor_results[0].frequency
        lag_config = self._config.get("lag_correction", {})

        if frequency == "A":
            window = lag_config.get("annual_smoothing_window", 2)
        else:
            window = lag_config.get("monthly_smoothing_window", 3)

        timeseries = [
            {
                "period": r.period,
                "v_exp": r.export_value_usd,
                "v_imp_adjusted": r.import_value_adjusted,
            }
            for r in corridor_results
        ]

        smoothed: list[SmoothedResult] = []
        for i in range(len(timeseries)):
            start = max(0, i - window + 1)
            chunk = timeseries[start: i + 1]
            v_exp_sum = sum(r["v_exp"] for r in chunk)
            v_imp_sum = sum(r["v_imp_adjusted"] for r in chunk)
            v_exp_avg = v_exp_sum / len(chunk)
            v_imp_avg = v_imp_sum / len(chunk)
            midpoint = (v_exp_sum + v_imp_sum) / 2.0
            d_rel_smoothed = (v_imp_sum - v_exp_sum) / midpoint if midpoint > 0 else 0.0

            smoothed.append(SmoothedResult(
                period=timeseries[i]["period"],
                v_exp=timeseries[i]["v_exp"],
                v_imp_adjusted=timeseries[i]["v_imp_adjusted"],
                v_exp_smoothed=v_exp_avg,
                v_imp_smoothed=v_imp_avg,
                d_rel_smoothed=d_rel_smoothed,
            ))

        return smoothed

    def get_phantom_shipments(
        self,
        period: str | None = None,
        min_value_usd: float | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get phantom exports and imports (one-sided flows).

        Returns:
            Dict with keys 'phantom_exports' and 'phantom_imports',
            each containing a list of row dicts.
        """
        params_exp: list[Any] = []
        params_imp: list[Any] = []
        query_exp = "SELECT * FROM phantom_exports WHERE 1=1"
        query_imp = "SELECT * FROM phantom_imports WHERE 1=1"

        if period:
            query_exp += " AND period = ?"
            query_imp += " AND period = ?"
            params_exp.append(period)
            params_imp.append(period)
        if min_value_usd is not None:
            query_exp += " AND trade_value_usd >= ?"
            query_imp += " AND trade_value_usd >= ?"
            params_exp.append(min_value_usd)
            params_imp.append(min_value_usd)

        query_exp += " ORDER BY trade_value_usd DESC"
        query_imp += " ORDER BY trade_value_usd DESC"

        exports = self.conn.execute(query_exp, params_exp).fetchall()
        imports = self.conn.execute(query_imp, params_imp).fetchall()

        return {
            "phantom_exports": [dict(row) for row in exports],
            "phantom_imports": [dict(row) for row in imports],
        }
