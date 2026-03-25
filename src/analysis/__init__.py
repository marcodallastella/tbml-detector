"""Mirror trade analysis and anomaly detection engine.

This package implements statistical detection of trade-based money laundering
(TBML) patterns using UN Comtrade bilateral mirror trade data.

Modules:
    mirror: Core mirror discrepancy computation with CIF/FOB and lag correction.
    anomaly: Statistical anomaly detection (z-score, Benford's law, rolling window).
    unit_price: Unit price analysis against commodity benchmarks.
    scoring: Severity scoring rubric combining multiple risk dimensions.
"""

from src.analysis.mirror import MirrorAnalyzer
from src.analysis.anomaly import AnomalyDetector
from src.analysis.unit_price import UnitPriceAnalyzer
from src.analysis.scoring import SeverityScorer

__all__ = [
    "MirrorAnalyzer",
    "AnomalyDetector",
    "UnitPriceAnalyzer",
    "SeverityScorer",
]
