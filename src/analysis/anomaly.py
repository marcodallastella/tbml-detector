"""Anomaly detection algorithms for mirror trade analysis.

Implements z-score detection against historical corridor baselines,
Benford's law analysis, rolling window deviation, asymmetry testing,
and correlation analysis.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy import stats

from src.analysis.mirror import DiscrepancyResult, MirrorAnalyzer

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "analysis.yaml"

# Benford's law expected first-digit frequencies
BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


@dataclass
class ZScoreResult:
    """Z-score analysis result for a corridor observation."""

    z_score: float | None
    baseline_median: float | None
    baseline_mad: float | None
    history_length: int
    sufficient_history: bool


@dataclass
class RollingZScoreResult:
    """Rolling z-score for a single period in a time series."""

    period: str
    z_score: float | None


@dataclass
class BenfordResult:
    """Result of Benford's law first-digit test."""

    chi2: float
    p_value: float
    mad: float  # mean absolute deviation from expected frequencies
    n_samples: int
    conforms: bool  # True if p_value >= threshold


@dataclass
class AsymmetryResult:
    """Result of directional asymmetry test."""

    statistic: float
    p_value: float
    direction: str  # "import_over" or "export_over"
    median_discrepancy: float
    is_asymmetric: bool  # True if p_value < 0.05


@dataclass
class CorrelationResult:
    """Result of correlation analysis."""

    correlation: float
    p_value: float
    method: str


@dataclass
class AnomalyFlags:
    """Combined anomaly detection results for a single observation."""

    z_score_corridor: ZScoreResult | None = None
    z_score_rolling: float | None = None
    benford: BenfordResult | None = None
    asymmetry: AsymmetryResult | None = None
    flags: list[str] = field(default_factory=list)


class AnomalyDetector:
    """Statistical anomaly detection for mirror trade discrepancies.

    Applies multiple detection algorithms per the detection specification:
    z-score against corridor history, rolling window deviation, Benford's
    law, and asymmetry testing.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

        z_config = self._config.get("z_score", {})
        self._min_history = z_config.get("min_history_years", 5)
        self._z_elevated = z_config.get("thresholds", {}).get("elevated", 2.0)
        self._z_high = z_config.get("thresholds", {}).get("high", 3.0)
        self._z_extreme = z_config.get("thresholds", {}).get("extreme", 5.0)
        self._rolling_window = z_config.get("rolling_window_months", 12)

        benford_config = self._config.get("benford", {})
        self._benford_min_samples = benford_config.get("min_samples", 50)
        self._benford_p_threshold = benford_config.get("p_value_threshold", 0.01)
        self._benford_mad_threshold = benford_config.get("mad_threshold", 0.015)

        asym_config = self._config.get("asymmetry", {})
        self._asymmetry_min_samples = asym_config.get("min_samples", 5)

    # ------------------------------------------------------------------
    # Z-score against historical corridor baseline
    # ------------------------------------------------------------------

    def z_score_corridor(
        self,
        d_rel_current: float,
        d_rel_history: list[float],
    ) -> ZScoreResult:
        """Compute z-score of current discrepancy against corridor history.

        Uses robust statistics (median and MAD) per the detection spec.

        Args:
            d_rel_current: Current period's relative discrepancy.
            d_rel_history: Historical relative discrepancies for the corridor.

        Returns:
            ZScoreResult with z-score and baseline statistics.
        """
        if len(d_rel_history) < self._min_history:
            return ZScoreResult(
                z_score=None,
                baseline_median=None,
                baseline_mad=None,
                history_length=len(d_rel_history),
                sufficient_history=False,
            )

        arr = np.array(d_rel_history)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))
        mad_scaled = mad * 1.4826  # consistency factor for normal distribution

        if mad_scaled < 1e-9:
            z = float("inf") if abs(d_rel_current - median) > 1e-9 else 0.0
        else:
            z = (d_rel_current - median) / mad_scaled

        return ZScoreResult(
            z_score=z,
            baseline_median=median,
            baseline_mad=mad_scaled,
            history_length=len(d_rel_history),
            sufficient_history=True,
        )

    # ------------------------------------------------------------------
    # Rolling window z-score
    # ------------------------------------------------------------------

    def rolling_zscore(
        self,
        d_rel_series: list[float],
        periods: list[str],
        window: int | None = None,
    ) -> list[RollingZScoreResult]:
        """Compute rolling z-score for each point using the preceding window.

        Detects regime changes in corridors (e.g., a clean corridor that
        suddenly develops persistent discrepancies).

        Args:
            d_rel_series: Time-ordered discrepancy values.
            periods: Corresponding period labels.
            window: Window size (defaults to config rolling_window_months).

        Returns:
            List of RollingZScoreResult (None z-score for first window entries).
        """
        if window is None:
            window = self._rolling_window

        results: list[RollingZScoreResult] = []
        for i in range(len(d_rel_series)):
            if i < window:
                results.append(RollingZScoreResult(period=periods[i], z_score=None))
                continue

            history = d_rel_series[i - window: i]
            arr = np.array(history)
            median = float(np.median(arr))
            mad = float(np.median(np.abs(arr - median))) * 1.4826

            if mad < 1e-9:
                z = float("inf") if abs(d_rel_series[i] - median) > 1e-9 else 0.0
            else:
                z = (d_rel_series[i] - median) / mad

            results.append(RollingZScoreResult(period=periods[i], z_score=z))

        return results

    # ------------------------------------------------------------------
    # Benford's law analysis
    # ------------------------------------------------------------------

    def benford_test(self, values: list[float]) -> BenfordResult | None:
        """Test whether first significant digits conform to Benford's Law.

        Uses chi-squared goodness-of-fit test.

        Args:
            values: Trade values to analyze.

        Returns:
            BenfordResult or None if insufficient samples.
        """
        if len(values) < self._benford_min_samples:
            return None

        # Extract first significant digit
        first_digits: list[int] = []
        for v in values:
            if v <= 0:
                continue
            s = f"{v:.10e}"
            for ch in s:
                if ch.isdigit() and ch != "0":
                    first_digits.append(int(ch))
                    break

        if len(first_digits) < self._benford_min_samples:
            return None

        n = len(first_digits)
        observed = np.zeros(9)
        for d in first_digits:
            observed[d - 1] += 1

        expected = np.array([BENFORD_EXPECTED[d] * n for d in range(1, 10)])
        chi2, p_value = stats.chisquare(observed, f_exp=expected)
        mad = float(np.mean(np.abs(
            observed / n - np.array([BENFORD_EXPECTED[d] for d in range(1, 10)])
        )))

        conforms = p_value >= self._benford_p_threshold and mad <= self._benford_mad_threshold

        return BenfordResult(
            chi2=float(chi2),
            p_value=float(p_value),
            mad=mad,
            n_samples=n,
            conforms=conforms,
        )

    # ------------------------------------------------------------------
    # Asymmetry test
    # ------------------------------------------------------------------

    def asymmetry_test(self, d_rel_series: list[float]) -> AsymmetryResult | None:
        """Test whether discrepancies are systematically biased in one direction.

        Uses Wilcoxon signed-rank test against zero.

        Args:
            d_rel_series: Historical relative discrepancies.

        Returns:
            AsymmetryResult or None if insufficient samples.
        """
        if len(d_rel_series) < self._asymmetry_min_samples:
            return None

        arr = np.array(d_rel_series)
        arr = arr[arr != 0]  # remove exact zeros
        if len(arr) < self._asymmetry_min_samples:
            return None

        stat, p_value = stats.wilcoxon(arr, alternative="two-sided")
        direction = "import_over" if float(np.median(arr)) > 0 else "export_over"

        return AsymmetryResult(
            statistic=float(stat),
            p_value=float(p_value),
            direction=direction,
            median_discrepancy=float(np.median(arr)),
            is_asymmetric=p_value < 0.05,
        )

    # ------------------------------------------------------------------
    # Correlation analysis
    # ------------------------------------------------------------------

    def correlation_check(
        self,
        declared_values: list[float],
        reference_values: list[float],
        method: str = "spearman",
    ) -> CorrelationResult | None:
        """Check correlation between declared values and a reference series.

        Useful for comparing unit prices against global commodity benchmarks.

        Args:
            declared_values: Declared trade values or unit prices.
            reference_values: Benchmark or expected values.
            method: "pearson" or "spearman".

        Returns:
            CorrelationResult or None if arrays are too short.
        """
        if len(declared_values) < 3 or len(declared_values) != len(reference_values):
            return None

        if method == "pearson":
            r, p = stats.pearsonr(declared_values, reference_values)
        else:
            r, p = stats.spearmanr(declared_values, reference_values)

        return CorrelationResult(
            correlation=float(r),
            p_value=float(p),
            method=method,
        )

    # ------------------------------------------------------------------
    # Combined analysis
    # ------------------------------------------------------------------

    def analyze_corridor(
        self,
        current: DiscrepancyResult,
        history: list[DiscrepancyResult],
    ) -> AnomalyFlags:
        """Run all anomaly detection algorithms on a corridor observation.

        Args:
            current: The current-period discrepancy result.
            history: Historical discrepancy results for the same corridor,
                     sorted by period ascending.

        Returns:
            AnomalyFlags combining all detection results.
        """
        flags: list[str] = []
        d_rel_history = [r.d_rel for r in history]

        # Z-score against corridor baseline
        z_result = self.z_score_corridor(current.d_rel, d_rel_history)
        if z_result.z_score is not None:
            abs_z = abs(z_result.z_score)
            if abs_z >= self._z_extreme:
                flags.append("z_score_extreme")
            elif abs_z >= self._z_high:
                flags.append("z_score_high")
            elif abs_z >= self._z_elevated:
                flags.append("z_score_elevated")

        # Rolling z-score (if enough monthly data)
        all_d_rel = d_rel_history + [current.d_rel]
        all_periods = [r.period for r in history] + [current.period]
        rolling_results = self.rolling_zscore(all_d_rel, all_periods)
        rolling_z = rolling_results[-1].z_score if rolling_results else None
        if rolling_z is not None and abs(rolling_z) >= self._z_high:
            flags.append("rolling_window_anomaly")

        # Benford's law on all trade values in the corridor
        all_values = [r.export_value_usd for r in history] + [r.import_value_usd for r in history]
        all_values += [current.export_value_usd, current.import_value_usd]
        benford = self.benford_test(all_values)
        if benford is not None and not benford.conforms:
            flags.append("benford_deviation")

        # Asymmetry test
        asymmetry = self.asymmetry_test(d_rel_history + [current.d_rel])
        if asymmetry is not None and asymmetry.is_asymmetric:
            flags.append("directional_asymmetry")

        return AnomalyFlags(
            z_score_corridor=z_result,
            z_score_rolling=rolling_z,
            benford=benford,
            asymmetry=asymmetry,
            flags=flags,
        )

    def classify_z_score(self, z_score: float | None) -> str:
        """Classify a z-score into severity tier."""
        if z_score is None:
            return "unknown"
        abs_z = abs(z_score)
        if abs_z >= self._z_extreme:
            return "extreme"
        if abs_z >= self._z_high:
            return "high"
        if abs_z >= self._z_elevated:
            return "elevated"
        return "normal"
