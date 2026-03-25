"""Unit tests for analytics: discrepancy math, anomaly detection, unit price, scoring."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.analysis.anomaly import AnomalyDetector, AnomalyFlags, ZScoreResult
from src.analysis.mirror import MirrorAnalyzer, DiscrepancyResult
from src.analysis.scoring import SeverityScorer, SeverityScore
from src.analysis.unit_price import UnitPriceAnalyzer, UnitPriceBenchmark

CONFIG_PATH = Path(__file__).parent.parent / "config" / "analysis.yaml"


# ============================================================================
# Mirror discrepancy math tests
# ============================================================================


class TestDiscrepancyMath:
    """Tests for the core discrepancy formulas."""

    def test_d_rel_symmetric_values(self) -> None:
        """Equal values should produce zero discrepancy."""
        assert MirrorAnalyzer.compute_d_rel(100.0, 100.0) == 0.0

    def test_d_rel_import_over(self) -> None:
        """Import > export should give positive d_rel."""
        d = MirrorAnalyzer.compute_d_rel(v_imp=150.0, v_exp=100.0)
        # (150 - 100) / ((150+100)/2) = 50 / 125 = 0.4
        assert d == pytest.approx(0.4)

    def test_d_rel_export_over(self) -> None:
        """Export > import should give negative d_rel."""
        d = MirrorAnalyzer.compute_d_rel(v_imp=50.0, v_exp=100.0)
        # (50 - 100) / ((50+100)/2) = -50/75 = -0.6667
        assert d == pytest.approx(-2 / 3)

    def test_d_rel_both_zero(self) -> None:
        """Both values zero should produce zero discrepancy."""
        assert MirrorAnalyzer.compute_d_rel(0.0, 0.0) == 0.0

    def test_d_log_positive_values(self) -> None:
        """Log ratio should be ln(v_imp / v_exp)."""
        d = MirrorAnalyzer.compute_d_log(200.0, 100.0)
        assert d == pytest.approx(math.log(2.0))

    def test_d_log_equal_values(self) -> None:
        """Equal values should produce log ratio of 0."""
        d = MirrorAnalyzer.compute_d_log(100.0, 100.0)
        assert d == pytest.approx(0.0)

    def test_d_log_zero_value_returns_none(self) -> None:
        """Non-positive values should return None."""
        assert MirrorAnalyzer.compute_d_log(0.0, 100.0) is None
        assert MirrorAnalyzer.compute_d_log(100.0, 0.0) is None
        assert MirrorAnalyzer.compute_d_log(-1.0, 100.0) is None

    def test_q_rel_with_values(self) -> None:
        """Quantity discrepancy should use midpoint normalization."""
        q = MirrorAnalyzer.compute_q_rel(200.0, 100.0)
        # (200 - 100) / ((200+100)/2) = 100/150 = 0.6667
        assert q == pytest.approx(2 / 3)

    def test_q_rel_none_inputs(self) -> None:
        """None inputs should return None."""
        assert MirrorAnalyzer.compute_q_rel(None, 100.0) is None
        assert MirrorAnalyzer.compute_q_rel(100.0, None) is None

    def test_up_rel_with_values(self) -> None:
        """Unit price discrepancy between import and export."""
        up = MirrorAnalyzer.compute_up_rel(200.0, 10.0, 100.0, 10.0)
        # up_imp = 200/10 = 20, up_exp = 100/10 = 10
        # (20 - 10) / ((20+10)/2) = 10/15 = 0.6667
        assert up == pytest.approx(2 / 3)

    def test_up_rel_zero_quantity_returns_none(self) -> None:
        """Zero quantity should return None."""
        assert MirrorAnalyzer.compute_up_rel(200.0, 0, 100.0, 10.0) is None


class TestCIFFOBAdjustment:
    """Tests for CIF/FOB normalization."""

    def test_default_ratio(self) -> None:
        """Default CIF/FOB ratio should be ~1.07."""
        analyzer = MirrorAnalyzer.__new__(MirrorAnalyzer)
        analyzer._config = {"cif_fob": {"default_ratio": 1.07, "ratios": {}}}
        ratio = analyzer.get_cif_fob_ratio()
        assert ratio == pytest.approx(1.07)

    def test_transport_mode_ratio(self) -> None:
        """Specific transport mode ratios should override default."""
        analyzer = MirrorAnalyzer.__new__(MirrorAnalyzer)
        analyzer._config = {
            "cif_fob": {
                "default_ratio": 1.07,
                "ratios": {"air": 1.15, "maritime_bulk": 1.07},
            }
        }
        assert analyzer.get_cif_fob_ratio("air") == pytest.approx(1.15)
        assert analyzer.get_cif_fob_ratio("maritime_bulk") == pytest.approx(1.07)

    def test_adjust_cif_fob(self) -> None:
        """CIF/FOB adjustment should divide import value by ratio."""
        analyzer = MirrorAnalyzer.__new__(MirrorAnalyzer)
        analyzer._config = {"cif_fob": {"default_ratio": 1.10, "ratios": {}}}
        adjusted, ratio = analyzer.adjust_cif_fob(110.0)
        assert ratio == pytest.approx(1.10)
        assert adjusted == pytest.approx(100.0)


# ============================================================================
# Anomaly detection tests
# ============================================================================


class TestAnomalyDetector:
    """Tests for z-score, Benford's law, asymmetry, and rolling window."""

    @pytest.fixture
    def detector(self) -> AnomalyDetector:
        return AnomalyDetector(config_path=CONFIG_PATH)

    def test_z_score_corridor_insufficient_history(self, detector: AnomalyDetector) -> None:
        """Z-score should return None with insufficient history."""
        result = detector.z_score_corridor(0.5, [0.1, 0.2, 0.15])
        assert result.sufficient_history is False
        assert result.z_score is None

    def test_z_score_corridor_normal(self, detector: AnomalyDetector) -> None:
        """Normal observation should have low z-score."""
        history = [0.05, 0.06, 0.04, 0.07, 0.05, 0.06, 0.04]
        result = detector.z_score_corridor(0.05, history)
        assert result.sufficient_history is True
        assert result.z_score is not None
        assert abs(result.z_score) < 2.0

    def test_z_score_corridor_extreme(self, detector: AnomalyDetector) -> None:
        """Extreme outlier should produce high z-score."""
        history = [0.05, 0.06, 0.04, 0.07, 0.05, 0.06, 0.04]
        result = detector.z_score_corridor(2.0, history)
        assert result.sufficient_history is True
        assert result.z_score is not None
        assert abs(result.z_score) > 5.0

    def test_z_score_uses_robust_statistics(self, detector: AnomalyDetector) -> None:
        """Z-score should use median and MAD, not mean and std."""
        # History with an outlier — robust stats should be unaffected
        history = [0.05, 0.06, 0.04, 0.07, 0.05, 0.06, 100.0]
        result = detector.z_score_corridor(0.05, history)
        assert result.baseline_median is not None
        # Median should be near 0.05-0.06, not pulled by outlier
        assert result.baseline_median < 1.0

    def test_classify_z_score(self, detector: AnomalyDetector) -> None:
        """Z-score classification should match thresholds."""
        assert detector.classify_z_score(None) == "unknown"
        assert detector.classify_z_score(1.0) == "normal"
        assert detector.classify_z_score(2.5) == "elevated"
        assert detector.classify_z_score(3.5) == "high"
        assert detector.classify_z_score(6.0) == "extreme"
        assert detector.classify_z_score(-3.5) == "high"  # absolute value

    def test_benford_too_few_samples(self, detector: AnomalyDetector) -> None:
        """Benford's test should return None with < min_samples."""
        result = detector.benford_test([100.0, 200.0, 300.0])
        assert result is None

    def test_benford_conforming_data(self, detector: AnomalyDetector) -> None:
        """Natural data following Benford's law should conform."""
        import random
        random.seed(42)
        # Generate Benford-distributed first digits
        values = []
        for _ in range(500):
            d = random.choices(range(1, 10), weights=[math.log10(1 + 1 / d) for d in range(1, 10)])[0]
            values.append(d * 10 ** random.randint(3, 8) + random.randint(0, 999))
        result = detector.benford_test(values)
        assert result is not None
        assert result.conforms is True

    def test_benford_non_conforming_data(self, detector: AnomalyDetector) -> None:
        """Uniform-distributed data should fail Benford's test."""
        import random
        random.seed(42)
        # Uniform distribution of first digits
        values = [random.randint(1, 9) * 10 ** random.randint(5, 8) for _ in range(500)]
        result = detector.benford_test(values)
        assert result is not None
        assert result.conforms == False

    def test_asymmetry_test_no_bias(self, detector: AnomalyDetector) -> None:
        """Symmetric discrepancies around zero should not be asymmetric."""
        series = [0.05, -0.03, 0.02, -0.04, 0.01, -0.06, 0.03, -0.02, 0.04, -0.05]
        result = detector.asymmetry_test(series)
        assert result is not None
        assert result.is_asymmetric == False

    def test_asymmetry_test_with_bias(self, detector: AnomalyDetector) -> None:
        """Consistently positive discrepancies should be detected as asymmetric."""
        series = [0.15, 0.20, 0.18, 0.22, 0.19, 0.25, 0.21]
        result = detector.asymmetry_test(series)
        assert result is not None
        assert result.is_asymmetric == True
        assert result.direction == "import_over"

    def test_rolling_zscore(self, detector: AnomalyDetector) -> None:
        """Rolling z-score should detect a shift in the series."""
        series = [0.05] * 15 + [2.0]  # stable, then spike
        periods = [str(2005 + i) for i in range(16)]
        results = detector.rolling_zscore(series, periods, window=12)
        assert len(results) == 16
        # First window entries should have None z-score
        assert results[0].z_score is None
        # Last entry (the spike) should have high z-score
        assert results[-1].z_score is not None
        assert abs(results[-1].z_score) > 3.0

    def test_correlation_check(self, detector: AnomalyDetector) -> None:
        """Perfect positive correlation should have r near 1."""
        declared = [10.0, 20.0, 30.0, 40.0, 50.0]
        reference = [11.0, 21.0, 31.0, 41.0, 51.0]
        result = detector.correlation_check(declared, reference)
        assert result is not None
        assert result.correlation > 0.99

    def test_correlation_check_insufficient_data(self, detector: AnomalyDetector) -> None:
        """Correlation with < 3 values should return None."""
        result = detector.correlation_check([1.0, 2.0], [1.0, 2.0])
        assert result is None


# ============================================================================
# Unit price analysis tests
# ============================================================================


class TestUnitPriceAnalyzer:
    """Tests for unit price benchmark comparison."""

    @pytest.fixture
    def analyzer(self) -> UnitPriceAnalyzer:
        a = UnitPriceAnalyzer(config_path=CONFIG_PATH)
        a.add_benchmark(UnitPriceBenchmark(
            commodity_code="3004",
            description="Medicaments",
            benchmark_price_usd_per_kg=100.0,
            price_low_usd_per_kg=50.0,
            price_high_usd_per_kg=200.0,
            source="test",
            period="2020",
        ))
        return a

    def test_normal_price(self, analyzer: UnitPriceAnalyzer) -> None:
        """Price within benchmark range should flag as normal."""
        result = analyzer.analyze_unit_price(
            commodity_code="3004", period="2020",
            exporter_code=276, importer_code=566,
            export_unit_price=120.0, import_unit_price=130.0,
        )
        assert result is not None
        assert result.export_flag == "normal"
        assert result.import_flag == "normal"
        assert len(result.flags) == 0

    def test_overpriced_export(self, analyzer: UnitPriceAnalyzer) -> None:
        """Export price far above benchmark should be flagged."""
        result = analyzer.analyze_unit_price(
            commodity_code="3004", period="2020",
            exporter_code=756, importer_code=566,
            export_unit_price=800.0,  # 8x benchmark
            import_unit_price=800.0,
        )
        assert result is not None
        assert result.export_flag in ("high", "extreme_high")
        assert "export_overpriced" in result.flags

    def test_underpriced_import(self, analyzer: UnitPriceAnalyzer) -> None:
        """Import price far below benchmark should be flagged."""
        result = analyzer.analyze_unit_price(
            commodity_code="3004", period="2020",
            exporter_code=276, importer_code=566,
            export_unit_price=100.0,
            import_unit_price=5.0,  # 0.05x benchmark
        )
        assert result is not None
        assert "import_underpriced" in result.flags

    def test_unit_price_divergence(self, analyzer: UnitPriceAnalyzer) -> None:
        """Large gap between export and import unit prices should be flagged."""
        result = analyzer.analyze_unit_price(
            commodity_code="3004", period="2020",
            exporter_code=276, importer_code=566,
            export_unit_price=100.0,
            import_unit_price=300.0,  # 3x export price
        )
        assert result is not None
        assert "unit_price_divergence" in result.flags

    def test_no_benchmark_returns_none(self, analyzer: UnitPriceAnalyzer) -> None:
        """Missing benchmark should return None."""
        result = analyzer.analyze_unit_price(
            commodity_code="9999", period="2020",
            exporter_code=276, importer_code=566,
            export_unit_price=100.0, import_unit_price=100.0,
        )
        assert result is None

    def test_benchmark_period_fallback(self, analyzer: UnitPriceAnalyzer) -> None:
        """Benchmark lookup should fall back to earlier period."""
        # Benchmark registered for 2020 should be found when looking up 2021
        result = analyzer.analyze_unit_price(
            commodity_code="3004", period="2021",
            exporter_code=276, importer_code=566,
            export_unit_price=100.0, import_unit_price=100.0,
        )
        assert result is not None

    def test_add_benchmarks_from_data(self) -> None:
        """Computing benchmark from observed prices should set IQR-based bounds."""
        a = UnitPriceAnalyzer(config_path=CONFIG_PATH)
        prices = [90.0, 95.0, 100.0, 105.0, 110.0, 100.0, 98.0, 102.0]
        b = a.add_benchmarks_from_data("7108", "Gold", prices, "2020")
        assert b is not None
        assert b.benchmark_price_usd_per_kg == pytest.approx(100.0)
        assert b.price_low_usd_per_kg < 90.0
        assert b.price_high_usd_per_kg > 110.0

    def test_add_benchmarks_insufficient_data(self) -> None:
        """Benchmark computation with < 5 prices should return None."""
        a = UnitPriceAnalyzer(config_path=CONFIG_PATH)
        b = a.add_benchmarks_from_data("7108", "Gold", [100.0, 110.0], "2020")
        assert b is None


# ============================================================================
# Severity scoring tests
# ============================================================================


class TestSeverityScoring:
    """Tests for the 5-component scoring rubric."""

    @pytest.fixture
    def scorer(self, tmp_db: Path) -> SeverityScorer:
        return SeverityScorer(db_path=tmp_db, config_path=CONFIG_PATH)

    def test_magnitude_scoring(self, scorer: SeverityScorer) -> None:
        """Magnitude component should scale with discrepancy size."""
        assert scorer._score_magnitude(0.05) == 0   # < 10%
        assert scorer._score_magnitude(0.15) == 5   # 10-25%
        assert scorer._score_magnitude(0.30) == 10  # 25-50%
        assert scorer._score_magnitude(0.60) == 15  # 50-100%
        assert scorer._score_magnitude(1.50) == 20  # > 100%

    def test_statistical_scoring(self, scorer: SeverityScorer) -> None:
        """Statistical component should scale with z-score."""
        assert scorer._score_statistical(None) == 5  # unknown = moderate default
        assert scorer._score_statistical(1.0) == 0
        assert scorer._score_statistical(2.5) == 5
        assert scorer._score_statistical(3.5) == 10
        assert scorer._score_statistical(4.5) == 15
        assert scorer._score_statistical(6.0) == 20

    def test_persistence_scoring(self, scorer: SeverityScorer) -> None:
        """Persistence component should scale with consecutive periods."""
        assert scorer._score_persistence(1) == 0
        assert scorer._score_persistence(2) == 5
        assert scorer._score_persistence(3) == 10
        assert scorer._score_persistence(4) == 15
        assert scorer._score_persistence(6) == 20

    def test_corridor_risk_scoring(self, scorer: SeverityScorer) -> None:
        """Corridor risk should sum risk factors, capped at 20."""
        assert scorer._score_corridor_risk([]) == 0
        score = scorer._score_corridor_risk(["secrecy_jurisdiction"])
        assert score == 5
        score = scorer._score_corridor_risk(["secrecy_jurisdiction", "narcotics_route"])
        assert score == 10
        # Cap at 20
        score = scorer._score_corridor_risk([
            "secrecy_jurisdiction", "narcotics_route",
            "non_reporting", "re_export_hub",
        ])
        assert score == min(20, 5 + 5 + 5 + 3)

    def test_commodity_risk_gold(self, scorer: SeverityScorer) -> None:
        """Gold (HS 71xx) should have high commodity risk."""
        score = scorer._score_commodity_risk("7108")
        assert score == 20

    def test_commodity_risk_electronics(self, scorer: SeverityScorer) -> None:
        """Electronics (HS 85xx) should have moderate commodity risk."""
        score = scorer._score_commodity_risk("8542")
        assert score == 12

    def test_commodity_risk_textiles(self, scorer: SeverityScorer) -> None:
        """Textiles (HS 50-63) should use range-based scoring."""
        score = scorer._score_commodity_risk("6110")
        assert score == 8

    def test_commodity_risk_default(self, scorer: SeverityScorer) -> None:
        """Unknown commodity should use default score."""
        score = scorer._score_commodity_risk("9999")
        assert score == 5

    def test_composite_severity_critical(self, scorer: SeverityScorer) -> None:
        """Maximal inputs should produce critical severity."""
        result = scorer.compute_severity(
            d_rel=1.5,            # 20 pts
            z_score=6.0,          # 20 pts
            consecutive_periods=6, # 20 pts
            corridor_risk_factors=["secrecy_jurisdiction", "narcotics_route"],  # 10 pts
            commodity_code="7108",  # 20 pts
        )
        assert result.total >= 80
        assert result.tier == "critical"

    def test_composite_severity_noise(self, scorer: SeverityScorer) -> None:
        """Minimal inputs should produce noise severity."""
        result = scorer.compute_severity(
            d_rel=0.05,           # 0 pts
            z_score=1.0,          # 0 pts
            consecutive_periods=1, # 0 pts
            corridor_risk_factors=[],  # 0 pts
            commodity_code="9999",  # 5 pts
        )
        assert result.total < 20
        assert result.tier == "noise"

    def test_re_export_adjustment(self, scorer: SeverityScorer) -> None:
        """Re-export flag should reduce severity by 10 points."""
        without = scorer.compute_severity(
            d_rel=0.60, z_score=3.5, consecutive_periods=3,
            corridor_risk_factors=[], commodity_code="8542",
        )
        with_re = scorer.compute_severity(
            d_rel=0.60, z_score=3.5, consecutive_periods=3,
            corridor_risk_factors=[], commodity_code="8542",
            re_export_flag=True,
        )
        assert with_re.total == without.total - 10
        assert with_re.adjustments == -10

    def test_severity_tier_boundaries(self, scorer: SeverityScorer) -> None:
        """Tier classification should match the boundary values."""
        assert SeverityScore(20, 20, 20, 20, 20, 0, 100).tier == "critical"
        assert SeverityScore(15, 15, 15, 15, 20, 0, 80).tier == "critical"
        assert SeverityScore(15, 15, 15, 15, 19, 0, 79).tier == "high"
        assert SeverityScore(10, 10, 10, 10, 20, 0, 60).tier == "high"
        assert SeverityScore(10, 10, 10, 10, 19, 0, 59).tier == "medium"
        assert SeverityScore(10, 10, 10, 10, 0, 0, 40).tier == "medium"
        assert SeverityScore(5, 5, 5, 0, 4, 0, 19).tier == "noise"

    def test_count_consecutive_periods(self, scorer: SeverityScorer) -> None:
        """Consecutive significant periods should be counted from the end."""
        series = [0.05, 0.03, 0.25, 0.30, 0.20]
        count = scorer.count_consecutive_periods(series, threshold=0.10)
        assert count == 3  # last three are >= 0.10

    def test_count_consecutive_periods_direction_change(self, scorer: SeverityScorer) -> None:
        """Direction changes should break the consecutive count."""
        series = [0.20, -0.25, 0.30, 0.20]
        count = scorer.count_consecutive_periods(series, threshold=0.10)
        assert count == 2  # last two are positive

    def test_count_consecutive_periods_empty(self, scorer: SeverityScorer) -> None:
        """Empty series should return 0."""
        assert scorer.count_consecutive_periods([]) == 0

    def test_rounding_artifact_detection(self, scorer: SeverityScorer) -> None:
        """Small discrepancy with rounded values should be a rounding artifact."""
        d = DiscrepancyResult(
            exporter_code=156, importer_code=276,
            commodity_code="8542", period="2021", frequency="A",
            export_value_usd=1_000_000.0, import_value_usd=1_005_000.0,
            export_weight_kg=100.0, import_weight_kg=100.0,
            export_qty=100.0, import_qty=100.0,
            export_unit_price=10_000.0, import_unit_price=10_050.0,
            import_value_adjusted=1_005_000.0, cif_fob_ratio_used=1.0,
            d_abs=5000.0, d_rel=0.005, d_rel_raw=0.005,
            d_log=None, q_rel=0.0, up_rel=0.005,
        )
        assert scorer._is_rounding_artifact(d) is True

    def test_not_rounding_artifact(self, scorer: SeverityScorer) -> None:
        """Large discrepancy should NOT be a rounding artifact."""
        d = DiscrepancyResult(
            exporter_code=156, importer_code=276,
            commodity_code="8542", period="2021", frequency="A",
            export_value_usd=1_000_000.0, import_value_usd=2_000_000.0,
            export_weight_kg=100.0, import_weight_kg=100.0,
            export_qty=100.0, import_qty=100.0,
            export_unit_price=10_000.0, import_unit_price=20_000.0,
            import_value_adjusted=2_000_000.0, cif_fob_ratio_used=1.0,
            d_abs=1_000_000.0, d_rel=0.667, d_rel_raw=0.667,
            d_log=0.693, q_rel=0.0, up_rel=0.667,
        )
        assert scorer._is_rounding_artifact(d) is False

    def test_store_and_retrieve_results(self, scorer: SeverityScorer) -> None:
        """Scored results should be stored and retrievable."""
        from src.analysis.scoring import ScoredResult

        scorer.initialize_results_table()
        results = [ScoredResult(
            reporter_code=531, partner_code=756,
            commodity_code="7108", commodity_description="Gold",
            period="2018",
            reported_value=400_000_000.0, mirror_value=42_000_000.0,
            discrepancy_abs=358_000_000.0, discrepancy_pct=162.0,
            z_score=8.5,
            severity=SeverityScore(20, 20, 20, 10, 20, 0, 90),
            flags=["z_score_extreme", "mirror_discrepancy"],
            notes="critical gold corridor",
        )]
        count = scorer.store_results(results)
        assert count == 1

        rows = scorer.get_results(min_severity=80)
        assert len(rows) == 1
        assert rows[0]["priority_tier"] == "critical"
        assert rows[0]["severity_score"] == 90

    def test_export_csv(self, scorer: SeverityScorer, tmp_path: Path) -> None:
        """CSV export should produce a file with results."""
        from src.analysis.scoring import ScoredResult

        scorer.initialize_results_table()
        results = [ScoredResult(
            reporter_code=531, partner_code=756,
            commodity_code="7108", commodity_description="Gold",
            period="2018",
            reported_value=400_000_000.0, mirror_value=42_000_000.0,
            discrepancy_abs=358_000_000.0, discrepancy_pct=162.0,
            z_score=8.5,
            severity=SeverityScore(20, 20, 20, 10, 20, 0, 90),
            flags=["z_score_extreme"],
            notes="test",
        )]
        scorer.store_results(results)

        output = tmp_path / "results.csv"
        count = scorer.export_csv(output, min_severity=0)
        assert count == 1
        assert output.exists()
