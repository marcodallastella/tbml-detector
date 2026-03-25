"""Severity scoring for flagged trade flows.

Implements the scoring rubric from detection-spec.md, combining magnitude of
discrepancy, statistical anomaly, persistence, corridor risk, and commodity
risk into a composite 0-100 severity score.
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.analysis.anomaly import AnomalyFlags
from src.analysis.mirror import DiscrepancyResult
from src.analysis.unit_price import UnitPriceDeviation

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "analysis.yaml"

# Results table schema
RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analysis_results (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_code           INTEGER NOT NULL,
    partner_code            INTEGER NOT NULL,
    commodity_code          TEXT NOT NULL,
    commodity_description   TEXT,
    period                  TEXT NOT NULL,
    reported_value          REAL,
    mirror_value            REAL,
    discrepancy_abs         REAL,
    discrepancy_pct         REAL,
    z_score                 REAL,
    severity_score          INTEGER,
    severity_magnitude      INTEGER,
    severity_statistical    INTEGER,
    severity_persistence    INTEGER,
    severity_corridor_risk  INTEGER,
    severity_commodity_risk INTEGER,
    severity_adjustments    INTEGER,
    priority_tier           TEXT,
    flags                   TEXT,  -- JSON list of triggered typologies
    notes                   TEXT,
    analyzed_at             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(reporter_code, partner_code, commodity_code, period)
);

CREATE INDEX IF NOT EXISTS idx_results_severity
    ON analysis_results(severity_score DESC);

CREATE INDEX IF NOT EXISTS idx_results_period
    ON analysis_results(period);

CREATE INDEX IF NOT EXISTS idx_results_commodity
    ON analysis_results(commodity_code);

CREATE INDEX IF NOT EXISTS idx_results_tier
    ON analysis_results(priority_tier);
"""


@dataclass
class SeverityScore:
    """Composite severity score with component breakdown."""

    magnitude: int  # 0-20
    statistical_anomaly: int  # 0-20
    persistence: int  # 0-20
    corridor_risk: int  # 0-20
    commodity_risk: int  # 0-20
    adjustments: int  # negative adjustments
    total: int  # 0-100

    @property
    def tier(self) -> str:
        """Priority tier based on total score."""
        if self.total >= 80:
            return "critical"
        if self.total >= 60:
            return "high"
        if self.total >= 40:
            return "medium"
        if self.total >= 20:
            return "low"
        return "noise"


@dataclass
class ScoredResult:
    """A fully scored analysis result ready for output."""

    # Identifiers
    reporter_code: int
    partner_code: int
    commodity_code: str
    commodity_description: str
    period: str

    # Values
    reported_value: float  # exporter-reported
    mirror_value: float  # importer-reported
    discrepancy_abs: float
    discrepancy_pct: float  # d_rel as percentage

    # Analysis
    z_score: float | None
    severity: SeverityScore
    flags: list[str] = field(default_factory=list)
    notes: str = ""


class SeverityScorer:
    """Computes severity scores and manages the output results table.

    Implements the 5-component scoring rubric from the detection specification
    and writes results to both SQLite and exportable formats.
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

        severity_config = self._config.get("severity", {})
        self._risk_points = severity_config.get("corridor_risk_points", {})
        self._commodity_risk = severity_config.get("commodity_risk", {})
        self._commodity_ranges = severity_config.get("commodity_risk_ranges", [])
        self._re_export_adj = severity_config.get("re_export_adjustment", -10)
        self._rounding_adj = severity_config.get("rounding_adjustment", -5)

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize_results_table(self) -> None:
        """Create the analysis_results table if it doesn't exist."""
        self.conn.executescript(RESULTS_TABLE_SQL)

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Component scoring
    # ------------------------------------------------------------------

    def _score_magnitude(self, d_rel: float) -> int:
        """Component 1: Magnitude of discrepancy (0-20)."""
        abs_d = abs(d_rel)
        if abs_d > 1.0:
            return 20
        if abs_d > 0.50:
            return 15
        if abs_d > 0.25:
            return 10
        if abs_d > 0.10:
            return 5
        return 0

    def _score_statistical(self, z_score: float | None) -> int:
        """Component 2: Statistical anomaly (0-20)."""
        if z_score is None:
            return 5  # unknown baseline = moderate default
        abs_z = abs(z_score)
        if abs_z > 5.0:
            return 20
        if abs_z > 4.0:
            return 15
        if abs_z > 3.0:
            return 10
        if abs_z > 2.0:
            return 5
        return 0

    def _score_persistence(self, consecutive_periods: int) -> int:
        """Component 3: Persistence over time (0-20)."""
        if consecutive_periods >= 6:
            return 20
        if consecutive_periods >= 4:
            return 15
        if consecutive_periods >= 3:
            return 10
        if consecutive_periods >= 2:
            return 5
        return 0

    def _score_corridor_risk(self, risk_factors: list[str]) -> int:
        """Component 4: Corridor risk profile (0-20)."""
        total = sum(self._risk_points.get(f, 0) for f in risk_factors)
        return min(20, total)

    def _score_commodity_risk(self, commodity_code: str) -> int:
        """Component 5: Commodity risk profile (0-20)."""
        # Extract HS chapter (first 2 digits)
        hs_chapter_str = commodity_code[:2] if len(commodity_code) >= 2 else commodity_code
        try:
            hs_chapter = int(hs_chapter_str)
        except ValueError:
            return self._commodity_risk.get("default", 5)

        # Check specific chapter
        score = self._commodity_risk.get(str(hs_chapter), None)
        if score is not None:
            return score

        # Check ranges
        for r in self._commodity_ranges:
            if r["start"] <= hs_chapter <= r["end"]:
                return r["score"]

        return self._commodity_risk.get("default", 5)

    # ------------------------------------------------------------------
    # Persistence calculation
    # ------------------------------------------------------------------

    def count_consecutive_periods(
        self,
        d_rel_series: list[float],
        threshold: float = 0.10,
    ) -> int:
        """Count consecutive periods where |d_rel| exceeds threshold in the same direction.

        Counts backwards from the most recent period.

        Args:
            d_rel_series: Time-ordered relative discrepancies.
            threshold: Minimum |d_rel| to count as significant.

        Returns:
            Number of consecutive significant periods from the end.
        """
        if not d_rel_series:
            return 0

        # Determine direction of most recent period
        last = d_rel_series[-1]
        if abs(last) < threshold:
            return 0

        direction_positive = last > 0
        count = 0

        for val in reversed(d_rel_series):
            if abs(val) >= threshold and (val > 0) == direction_positive:
                count += 1
            else:
                break

        return count

    # ------------------------------------------------------------------
    # Composite scoring
    # ------------------------------------------------------------------

    def compute_severity(
        self,
        d_rel: float,
        z_score: float | None,
        consecutive_periods: int,
        corridor_risk_factors: list[str],
        commodity_code: str,
        re_export_flag: bool = False,
        rounding_flag: bool = False,
    ) -> SeverityScore:
        """Compute composite severity score per the rubric.

        Args:
            d_rel: Relative discrepancy after normalization.
            z_score: Z-score against corridor history (None if unavailable).
            consecutive_periods: Consecutive periods of significant discrepancy.
            corridor_risk_factors: List of risk factor keys.
            commodity_code: HS code for commodity risk lookup.
            re_export_flag: True if re-export corridor.
            rounding_flag: True if discrepancy is likely rounding artifact.

        Returns:
            SeverityScore with component breakdown and total.
        """
        magnitude = self._score_magnitude(d_rel)
        statistical = self._score_statistical(z_score)
        persistence = self._score_persistence(consecutive_periods)
        corridor_risk = self._score_corridor_risk(corridor_risk_factors)
        commodity_risk = self._score_commodity_risk(commodity_code)

        adjustments = 0
        if re_export_flag:
            adjustments += self._re_export_adj
        if rounding_flag:
            adjustments += self._rounding_adj

        total = max(0, min(100,
            magnitude + statistical + persistence +
            corridor_risk + commodity_risk + adjustments
        ))

        return SeverityScore(
            magnitude=magnitude,
            statistical_anomaly=statistical,
            persistence=persistence,
            corridor_risk=corridor_risk,
            commodity_risk=commodity_risk,
            adjustments=adjustments,
            total=total,
        )

    def score_discrepancy(
        self,
        discrepancy: DiscrepancyResult,
        anomaly_flags: AnomalyFlags,
        corridor_history: list[DiscrepancyResult],
        corridor_risk_factors: list[str] | None = None,
        commodity_description: str = "",
    ) -> ScoredResult:
        """Score a single discrepancy with full context.

        Args:
            discrepancy: The mirror discrepancy result.
            anomaly_flags: Anomaly detection results.
            corridor_history: Historical discrepancies for persistence calc.
            corridor_risk_factors: Risk factors for the corridor.
            commodity_description: Human-readable commodity name.

        Returns:
            ScoredResult ready for output.
        """
        if corridor_risk_factors is None:
            corridor_risk_factors = []

        # Z-score from anomaly flags
        z_score = (
            anomaly_flags.z_score_corridor.z_score
            if anomaly_flags.z_score_corridor else None
        )

        # Persistence: count consecutive significant periods
        d_rel_history = [r.d_rel for r in corridor_history]
        consecutive = self.count_consecutive_periods(
            d_rel_history + [discrepancy.d_rel]
        )

        # Check for rounding artifact
        rounding_flag = self._is_rounding_artifact(discrepancy)

        severity = self.compute_severity(
            d_rel=discrepancy.d_rel,
            z_score=z_score,
            consecutive_periods=consecutive,
            corridor_risk_factors=corridor_risk_factors,
            commodity_code=discrepancy.commodity_code,
            re_export_flag=discrepancy.is_re_export,
            rounding_flag=rounding_flag,
        )

        # Combine all flags
        all_flags = list(anomaly_flags.flags)
        all_flags.extend(discrepancy.data_quality_flags)
        if rounding_flag:
            all_flags.append("rounding_artifact")

        # Build notes
        notes_parts: list[str] = []
        if discrepancy.is_re_export:
            notes_parts.append("re-export corridor")
        if discrepancy.is_confidential:
            notes_parts.append("confidential flow involved")
        if z_score is not None:
            notes_parts.append(f"z-score={z_score:.2f}")
        if consecutive > 1:
            notes_parts.append(f"{consecutive} consecutive periods")

        return ScoredResult(
            reporter_code=discrepancy.exporter_code,
            partner_code=discrepancy.importer_code,
            commodity_code=discrepancy.commodity_code,
            commodity_description=commodity_description,
            period=discrepancy.period,
            reported_value=discrepancy.export_value_usd,
            mirror_value=discrepancy.import_value_usd,
            discrepancy_abs=discrepancy.d_abs,
            discrepancy_pct=discrepancy.d_rel * 100.0,
            z_score=z_score,
            severity=severity,
            flags=all_flags,
            notes="; ".join(notes_parts),
        )

    def _is_rounding_artifact(self, d: DiscrepancyResult) -> bool:
        """Check if discrepancy is likely a rounding artifact.

        Flags pairs where both values end in 000 and the discrepancy is < 1%.
        """
        if abs(d.d_rel) >= 0.01:
            return False
        exp_rounded = (d.export_value_usd % 1000) == 0
        imp_rounded = (d.import_value_usd % 1000) == 0
        return exp_rounded and imp_rounded

    # ------------------------------------------------------------------
    # Output: store and export
    # ------------------------------------------------------------------

    def store_results(self, results: list[ScoredResult]) -> int:
        """Write scored results to the analysis_results SQLite table.

        Args:
            results: List of ScoredResult objects.

        Returns:
            Number of results stored.
        """
        self.initialize_results_table()
        count = 0
        for r in results:
            try:
                self.conn.execute(
                    """INSERT OR REPLACE INTO analysis_results (
                        reporter_code, partner_code, commodity_code,
                        commodity_description, period, reported_value,
                        mirror_value, discrepancy_abs, discrepancy_pct,
                        z_score, severity_score, severity_magnitude,
                        severity_statistical, severity_persistence,
                        severity_corridor_risk, severity_commodity_risk,
                        severity_adjustments, priority_tier, flags, notes,
                        analyzed_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, datetime('now')
                    )""",
                    (
                        r.reporter_code, r.partner_code, r.commodity_code,
                        r.commodity_description, r.period, r.reported_value,
                        r.mirror_value, r.discrepancy_abs, r.discrepancy_pct,
                        r.z_score, r.severity.total, r.severity.magnitude,
                        r.severity.statistical_anomaly, r.severity.persistence,
                        r.severity.corridor_risk, r.severity.commodity_risk,
                        r.severity.adjustments, r.severity.tier,
                        json.dumps(r.flags), r.notes,
                    ),
                )
                count += 1
            except sqlite3.Error as e:
                logger.warning("Failed to store result: %s — %s", r, e)

        self.conn.commit()
        logger.info("Stored %d analysis results", count)
        return count

    def export_csv(
        self,
        output_path: str | Path,
        min_severity: int = 0,
        tier: str | None = None,
    ) -> int:
        """Export analysis results to CSV.

        Args:
            output_path: Path for output CSV file.
            min_severity: Minimum severity score to include.
            tier: Filter by priority tier (critical/high/medium/low/noise).

        Returns:
            Number of rows exported.
        """
        query = "SELECT * FROM analysis_results WHERE severity_score >= ?"
        params: list[Any] = [min_severity]

        if tier:
            query += " AND priority_tier = ?"
            params.append(tier)

        query += " ORDER BY severity_score DESC"

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            logger.warning("No results to export")
            return 0

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        columns = [desc[0] for desc in cursor.description]
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(tuple(row))

        logger.info("Exported %d results to %s", len(rows), output_path)
        return len(rows)

    def export_json(
        self,
        output_path: str | Path,
        min_severity: int = 0,
        tier: str | None = None,
    ) -> int:
        """Export analysis results to JSON.

        Args:
            output_path: Path for output JSON file.
            min_severity: Minimum severity score to include.
            tier: Filter by priority tier.

        Returns:
            Number of records exported.
        """
        query = "SELECT * FROM analysis_results WHERE severity_score >= ?"
        params: list[Any] = [min_severity]

        if tier:
            query += " AND priority_tier = ?"
            params.append(tier)

        query += " ORDER BY severity_score DESC"

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            logger.warning("No results to export")
            return 0

        columns = [desc[0] for desc in cursor.description]
        records = []
        for row in rows:
            record = dict(zip(columns, tuple(row)))
            # Parse flags JSON string back to list
            if "flags" in record and isinstance(record["flags"], str):
                try:
                    record["flags"] = json.loads(record["flags"])
                except json.JSONDecodeError:
                    pass
            records.append(record)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(records, f, indent=2, default=str)

        logger.info("Exported %d results to %s", len(records), output_path)
        return len(records)

    def get_results(
        self,
        min_severity: int = 0,
        tier: str | None = None,
        commodity_code: str | None = None,
        reporter_code: int | None = None,
        partner_code: int | None = None,
        period: str | None = None,
    ) -> list[sqlite3.Row]:
        """Query stored analysis results with filters.

        Returns:
            List of result rows from analysis_results table.
        """
        query = "SELECT * FROM analysis_results WHERE severity_score >= ?"
        params: list[Any] = [min_severity]

        if tier:
            query += " AND priority_tier = ?"
            params.append(tier)
        if commodity_code:
            query += " AND commodity_code = ?"
            params.append(commodity_code)
        if reporter_code:
            query += " AND reporter_code = ?"
            params.append(reporter_code)
        if partner_code:
            query += " AND partner_code = ?"
            params.append(partner_code)
        if period:
            query += " AND period = ?"
            params.append(period)

        query += " ORDER BY severity_score DESC"
        return self.conn.execute(query, params).fetchall()
