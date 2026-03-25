"""Integration tests: full pipeline on fixture datasets.

Verifies that loading fixtures through the pipeline and running analysis
produces the correct flags and severity assessments.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.anomaly import AnomalyDetector, AnomalyFlags, ZScoreResult
from src.analysis.mirror import MirrorAnalyzer
from src.analysis.scoring import SeverityScorer, ScoredResult
from src.analysis.unit_price import UnitPriceAnalyzer, UnitPriceBenchmark
from src.pipeline.cleaning import TradeCleaner
from src.pipeline.storage import TradeStorage
from tests.conftest import load_fixture_into_db, CONFIG_PATH


# ============================================================================
# Helpers
# ============================================================================


def setup_fixture_db(tmp_path: Path, fixture_name: str) -> TradeStorage:
    """Create a database and load a fixture into it."""
    db_path = tmp_path / f"{fixture_name}.db"
    storage = TradeStorage(db_path=db_path)
    storage.initialize()
    load_fixture_into_db(storage, fixture_name)
    return storage


# ============================================================================
# Venezuelan Gold — Flagship Case
# ============================================================================


class TestVenezuelaGold:
    """Integration tests for the Venezuelan gold laundering case.

    This is the flagship validation case. The tool MUST flag this corridor
    as severely anomalous with high severity.
    """

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "venezuela_gold")

    def test_fixture_loads_all_records(self, db: TradeStorage) -> None:
        """All 20 fixture rows should be loaded."""
        counts = db.get_record_count()
        assert counts["raw_records"] == 20
        assert counts["cleaned_records"] == 20

    def test_mirror_pairs_curacao_switzerland(self, db: TradeStorage) -> None:
        """Curacao->Switzerland corridor should have mirror pairs with large discrepancies."""
        pairs = db.get_mirror_pairs(
            commodity_code="7108",
            exporter_code=531,  # Curacao
            importer_code=756,  # Switzerland
        )
        assert len(pairs) > 0
        for pair in pairs:
            export_val = pair["export_value_usd"]
            import_val = pair["import_value_usd"]
            # Curacao reports much larger exports than Switzerland reports imports
            assert export_val > import_val
            gap_ratio = abs(pair["value_gap_ratio"])
            assert gap_ratio > 0.5  # > 50% discrepancy

    def test_phantom_imports_venezuela_curacao(self, db: TradeStorage) -> None:
        """Venezuela reports minimal exports; Curacao reports massive imports.

        Due to the extreme magnitude difference, the Venezuela->Curacao flow
        should appear in mirror_pairs but with very large discrepancy. Both
        sides report, but Venezuela reports only a tiny fraction.
        """
        pairs = db.get_mirror_pairs(
            commodity_code="7108",
            exporter_code=862,  # Venezuela
            importer_code=531,  # Curacao
        )
        # The reverse direction: Curacao imports from Venezuela
        reverse_pairs = db.get_mirror_pairs(
            commodity_code="7108",
            exporter_code=531,  # Curacao (as importer-reported "exports" to Ven)
            importer_code=862,  # Venezuela
        )
        # At least one direction should show data
        total_pairs = len(pairs) + len(reverse_pairs)
        assert total_pairs > 0

    def test_severity_scoring_flags_critical(self, db: TradeStorage, tmp_path: Path) -> None:
        """Venezuelan gold corridor must be scored as HIGH or CRITICAL severity.

        This is the core validation assertion for the project.
        """
        db_path = tmp_path / "venezuela_gold.db"
        analyzer = MirrorAnalyzer(db_path=db_path, config_path=CONFIG_PATH)
        scorer = SeverityScorer(db_path=db_path, config_path=CONFIG_PATH)

        # Get Curacao->Switzerland mirror pairs
        discrepancies = analyzer.compute_discrepancies(
            commodity_code="7108",
            exporter_code=531,  # Curacao
            importer_code=756,  # Switzerland
            min_value_usd=0,
        )

        assert len(discrepancies) > 0, "Should find Curacao->Switzerland discrepancies"

        scored_results: list[ScoredResult] = []
        for d in discrepancies:
            # Get corridor history for persistence
            history = [x for x in discrepancies if x.period < d.period]

            # Build anomaly flags (simplified — no full history for z-score)
            anomaly = AnomalyFlags(
                z_score_corridor=ZScoreResult(
                    z_score=None,
                    baseline_median=None,
                    baseline_mad=None,
                    history_length=len(history),
                    sufficient_history=False,
                ),
                flags=[],
            )

            result = scorer.score_discrepancy(
                discrepancy=d,
                anomaly_flags=anomaly,
                corridor_history=history,
                corridor_risk_factors=["secrecy_jurisdiction"],
                commodity_description="Gold",
            )
            scored_results.append(result)

        # The most recent years should score HIGH or CRITICAL
        latest = max(scored_results, key=lambda r: r.period)
        assert latest.severity.tier in ("high", "critical"), (
            f"Venezuelan gold corridor should be HIGH or CRITICAL, "
            f"got {latest.severity.tier} (score={latest.severity.total})"
        )

        # Discrepancy should be very large
        assert abs(latest.discrepancy_pct) > 50.0, (
            f"Discrepancy percentage should be > 50%, got {latest.discrepancy_pct:.1f}%"
        )

    def test_discrepancy_grows_over_time(self, db: TradeStorage, tmp_path: Path) -> None:
        """The Curacao->Switzerland discrepancy should grow from 2015 to 2019."""
        db_path = tmp_path / "venezuela_gold.db"
        analyzer = MirrorAnalyzer(db_path=db_path, config_path=CONFIG_PATH)

        history = analyzer.get_corridor_history(
            exporter_code=531,  # Curacao
            importer_code=756,  # Switzerland
            commodity_code="7108",
        )
        assert len(history) >= 4

        # Absolute discrepancy should generally increase
        abs_gaps = [(r.period, abs(r.d_abs)) for r in history]
        abs_gaps.sort(key=lambda x: x[0])
        # Last year's gap should be larger than the first year's
        assert abs_gaps[-1][1] > abs_gaps[0][1]


# ============================================================================
# Phantom Shipment
# ============================================================================


class TestPhantomShipment:
    """Integration tests for the China->Syria phantom shipment case."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "phantom_shipment")

    def test_all_records_load(self, db: TradeStorage) -> None:
        """All 6 fixture rows should load."""
        counts = db.get_record_count()
        assert counts["raw_records"] == 6

    def test_phantom_exports_detected(self, db: TradeStorage) -> None:
        """China's exports to Syria should appear as phantom exports (no partner data)."""
        phantoms = db.get_phantom_exports()
        assert len(phantoms) > 0
        # All phantom exports should be from China (156) to Syria (760)
        for p in phantoms:
            assert p["exporter_code"] == 156
            assert p["importer_code"] == 760

    def test_no_mirror_pairs(self, db: TradeStorage) -> None:
        """There should be zero mirror pairs since Syria doesn't report."""
        pairs = db.get_mirror_pairs(
            commodity_code="8429",
            exporter_code=156,
            importer_code=760,
        )
        assert len(pairs) == 0

    def test_phantom_value_is_large(self, db: TradeStorage) -> None:
        """Total phantom export value should be ~$572M."""
        phantoms = db.get_phantom_exports()
        total = sum(p["trade_value_usd"] for p in phantoms)
        assert total > 500_000_000  # > $500M


# ============================================================================
# Re-Export Hub (Legitimate)
# ============================================================================


class TestReExportHub:
    """Integration tests for the Singapore re-export case."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "reexport_hub")

    def test_taiwan_singapore_clean(self, db: TradeStorage) -> None:
        """Taiwan->Singapore should show small mirror discrepancy."""
        pairs = db.get_mirror_pairs(
            commodity_code="8542",
            exporter_code=158,  # Taiwan
            importer_code=702,  # Singapore
        )
        assert len(pairs) > 0
        for pair in pairs:
            gap = abs(pair["value_gap_ratio"]) if pair["value_gap_ratio"] else 0
            assert gap < 0.05  # < 5% discrepancy = normal CIF/FOB spread

    def test_singapore_germany_has_discrepancy(self, db: TradeStorage) -> None:
        """Singapore->Germany should show significant discrepancy (re-export effect)."""
        pairs = db.get_mirror_pairs(
            commodity_code="8542",
            exporter_code=702,  # Singapore
            importer_code=276,  # Germany
        )
        assert len(pairs) > 0
        for pair in pairs:
            gap = abs(pair["value_gap_ratio"]) if pair["value_gap_ratio"] else 0
            assert gap > 0.30  # > 30% discrepancy from re-export accounting


# ============================================================================
# Confidential Flows
# ============================================================================


class TestConfidentialFlows:
    """Integration tests for confidential/suppressed flow handling."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "confidential")

    def test_zero_value_petroleum_flagged_confidential(self, db: TradeStorage) -> None:
        """US petroleum imports with value=0 should be flagged as confidential."""
        rows = db.conn.execute(
            """SELECT * FROM cleaned_records
               WHERE reporter_code = 840 AND commodity_code = '2709'
                 AND is_confidential = 1"""
        ).fetchall()
        assert len(rows) > 0

    def test_confidential_excluded_from_mirror_pairs(self, db: TradeStorage) -> None:
        """Confidential records should NOT appear in mirror_pairs view."""
        # The mirror_pairs view filters out is_confidential = 1
        pairs = db.get_mirror_pairs(commodity_code="2709")
        # If any pairs exist, none should have confidential flags
        for pair in pairs:
            assert not pair["export_is_confidential"]
            assert not pair["import_is_confidential"]

    def test_null_value_records_handled(self, db: TradeStorage) -> None:
        """Records with NULL trade values (Canada petroleum) should be handled."""
        rows = db.conn.execute(
            """SELECT * FROM cleaned_records
               WHERE reporter_code = 124 AND commodity_code = '2709'"""
        ).fetchall()
        # These should either be inserted with is_confidential=1 or filtered
        # The key thing is they don't crash the pipeline
        # Canada's records have NULL values so they may be flagged confidential
        for row in rows:
            assert row["is_confidential"] == 1


# ============================================================================
# EU Aggregate
# ============================================================================


class TestEUAggregate:
    """Integration tests for EU aggregate vs. member state reporting."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "eu_aggregate")

    def test_eu_aggregate_excluded_from_mirror(self, db: TradeStorage) -> None:
        """EU aggregate partner (code 97) should be excluded from mirror_pairs."""
        pairs = db.get_mirror_pairs()
        for pair in pairs:
            assert pair["exporter_code"] != 97
            assert pair["importer_code"] != 97

    def test_member_state_records_present(self, db: TradeStorage) -> None:
        """Individual EU member states should have records in the database."""
        counts = db.get_record_count()
        assert counts["cleaned_records"] > 0

        # Check that Germany (276) has import records from China (156)
        rows = db.conn.execute(
            """SELECT * FROM cleaned_records
               WHERE reporter_code = 276 AND partner_code = 156
                 AND flow_code = 1"""
        ).fetchall()
        assert len(rows) > 0


# ============================================================================
# No-Reporter Country
# ============================================================================


class TestNoReporter:
    """Integration tests for non-reporting country handling."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "no_reporter")

    def test_one_sided_data_loads(self, db: TradeStorage) -> None:
        """One-sided data (only reporter, no partner) should load fine."""
        counts = db.get_record_count()
        assert counts["cleaned_records"] > 0

    def test_no_mirror_pairs_for_dprk(self, db: TradeStorage) -> None:
        """No mirror pairs should exist since DPRK doesn't report."""
        pairs = db.get_mirror_pairs()
        assert len(pairs) == 0

    def test_phantom_exports_exist(self, db: TradeStorage) -> None:
        """China's exports to DPRK should appear as phantom exports."""
        phantoms = db.get_phantom_exports()
        china_to_dprk = [
            p for p in phantoms
            if p["exporter_code"] == 156 and p["importer_code"] == 408
        ]
        assert len(china_to_dprk) > 0


# ============================================================================
# Pharma Over-Invoicing
# ============================================================================


class TestPharmaOverInvoicing:
    """Integration tests for the pharma unit price anomaly case."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> TradeStorage:
        return setup_fixture_db(tmp_path, "pharma_over_invoicing")

    def test_mirror_pairs_agree(self, db: TradeStorage) -> None:
        """Both sides should report similar values (no mirror discrepancy)."""
        pairs = db.get_mirror_pairs(commodity_code="3004")
        assert len(pairs) > 0
        for pair in pairs:
            gap = abs(pair["value_gap_ratio"]) if pair["value_gap_ratio"] else 0
            assert gap < 0.05  # < 5% — both sides agree

    def test_unit_price_anomaly_detected(self, db: TradeStorage, tmp_path: Path) -> None:
        """Unit prices should be flagged as anomalous vs. benchmark."""
        db_path = tmp_path / "pharma_over_invoicing.db"
        analyzer = MirrorAnalyzer(db_path=db_path, config_path=CONFIG_PATH)
        up_analyzer = UnitPriceAnalyzer(config_path=CONFIG_PATH)

        # Add pharma benchmark: ~$100/kg global average for HS 3004
        up_analyzer.add_benchmark(UnitPriceBenchmark(
            commodity_code="3004",
            description="Medicaments in measured doses",
            benchmark_price_usd_per_kg=100.0,
            price_low_usd_per_kg=50.0,
            price_high_usd_per_kg=200.0,
            source="WHO/global_benchmark",
            period="2019",
        ))

        discrepancies = analyzer.compute_discrepancies(
            commodity_code="3004",
            min_value_usd=0,
        )
        assert len(discrepancies) > 0

        deviations = up_analyzer.screen_discrepancies(discrepancies)
        # At least some corridors should have unit price flags
        assert len(deviations) > 0
        # Switzerland->Nigeria should be flagged for overpricing
        swiss_nigeria = [
            d for d in deviations
            if d.exporter_code == 756 and d.importer_code == 566
        ]
        assert len(swiss_nigeria) > 0
        for d in swiss_nigeria:
            assert any("overpriced" in f for f in d.flags)


# ============================================================================
# Cross-fixture: scoring consistency
# ============================================================================


class TestScoringConsistency:
    """Tests that severity scoring is consistent across different fixture types."""

    def test_phantom_more_severe_than_clean(self, tmp_path: Path) -> None:
        """A phantom shipment should score higher than a clean re-export discrepancy."""
        db_path_phantom = tmp_path / "phantom.db"
        db_path_reexport = tmp_path / "reexport.db"

        storage_p = TradeStorage(db_path=db_path_phantom)
        storage_p.initialize()
        load_fixture_into_db(storage_p, "phantom_shipment")
        storage_p.close()

        storage_r = TradeStorage(db_path=db_path_reexport)
        storage_r.initialize()
        load_fixture_into_db(storage_r, "reexport_hub")
        storage_r.close()

        scorer = SeverityScorer(db_path=db_path_phantom, config_path=CONFIG_PATH)

        # Phantom: machinery to sanctioned country — should be high severity
        phantom_severity = scorer.compute_severity(
            d_rel=2.0,  # 100% discrepancy (phantom)
            z_score=None,
            consecutive_periods=3,
            corridor_risk_factors=["non_reporting"],
            commodity_code="8429",  # Machinery
        )

        # Re-export: legitimate electronics via Singapore — should be lower
        reexport_severity = scorer.compute_severity(
            d_rel=0.44,
            z_score=1.5,
            consecutive_periods=3,
            corridor_risk_factors=["re_export_hub"],
            commodity_code="8542",
            re_export_flag=True,
        )

        assert phantom_severity.total > reexport_severity.total, (
            f"Phantom ({phantom_severity.total}) should score higher than "
            f"re-export ({reexport_severity.total})"
        )
