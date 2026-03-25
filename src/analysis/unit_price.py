"""Unit price analysis for mirror trade data.

Compares declared unit values against global commodity price benchmarks
and flags significant deviations that may indicate over/under-invoicing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "analysis.yaml"


@dataclass
class UnitPriceBenchmark:
    """Benchmark unit price for a commodity."""

    commodity_code: str
    description: str
    benchmark_price_usd_per_kg: float
    price_low_usd_per_kg: float
    price_high_usd_per_kg: float
    source: str
    period: str  # period the benchmark applies to


@dataclass
class UnitPriceDeviation:
    """Result of unit price comparison against benchmark."""

    commodity_code: str
    period: str
    exporter_code: int
    importer_code: int

    # Declared unit prices
    export_unit_price: float | None
    import_unit_price: float | None

    # Benchmark
    benchmark_price: float
    benchmark_low: float
    benchmark_high: float

    # Deviations from benchmark (as ratio: declared / benchmark)
    export_deviation_ratio: float | None
    import_deviation_ratio: float | None

    # Flags
    export_flag: str  # "normal", "low", "high", "extreme"
    import_flag: str
    flags: list[str] = field(default_factory=list)


class UnitPriceAnalyzer:
    """Analyzes unit prices against commodity benchmarks.

    Compares declared unit values (trade value / quantity) against expected
    price ranges for each commodity. Significant deviations may indicate
    over-invoicing or under-invoicing.
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        benchmarks: list[UnitPriceBenchmark] | None = None,
    ) -> None:
        config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

        # In-memory benchmark store, keyed by (commodity_code, period)
        self._benchmarks: dict[tuple[str, str], UnitPriceBenchmark] = {}
        if benchmarks:
            for b in benchmarks:
                self._benchmarks[(b.commodity_code, b.period)] = b

        self._min_d_rel = self._config.get("min_d_rel_to_flag", 0.10)

    def add_benchmark(self, benchmark: UnitPriceBenchmark) -> None:
        """Register a price benchmark for a commodity and period."""
        self._benchmarks[(benchmark.commodity_code, benchmark.period)] = benchmark

    def add_benchmarks_from_data(
        self,
        commodity_code: str,
        description: str,
        unit_prices: list[float],
        period: str,
        source: str = "computed_from_data",
    ) -> UnitPriceBenchmark | None:
        """Compute a benchmark from observed unit prices across corridors.

        Uses the interquartile range of observed unit prices as the
        acceptable range.

        Args:
            commodity_code: HS code.
            description: Commodity description.
            unit_prices: Observed unit prices from multiple corridors.
            period: Period this benchmark applies to.
            source: Description of data source.

        Returns:
            Created benchmark, or None if insufficient data.
        """
        prices = [p for p in unit_prices if p > 0]
        if len(prices) < 5:
            return None

        arr = np.array(prices)
        median = float(np.median(arr))
        q25 = float(np.percentile(arr, 25))
        q75 = float(np.percentile(arr, 75))
        iqr = q75 - q25

        benchmark = UnitPriceBenchmark(
            commodity_code=commodity_code,
            description=description,
            benchmark_price_usd_per_kg=median,
            price_low_usd_per_kg=max(0.0, q25 - 1.5 * iqr),
            price_high_usd_per_kg=q75 + 1.5 * iqr,
            source=source,
            period=period,
        )
        self._benchmarks[(commodity_code, period)] = benchmark
        return benchmark

    def get_benchmark(
        self,
        commodity_code: str,
        period: str,
    ) -> UnitPriceBenchmark | None:
        """Look up benchmark for a commodity and period.

        Falls back to the most recent benchmark for the commodity if an
        exact period match is not found.
        """
        # Exact match
        if (commodity_code, period) in self._benchmarks:
            return self._benchmarks[(commodity_code, period)]

        # Fallback: most recent period for same commodity
        candidates = [
            (p, b) for (c, p), b in self._benchmarks.items()
            if c == commodity_code and p <= period
        ]
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        return None

    def analyze_unit_price(
        self,
        commodity_code: str,
        period: str,
        exporter_code: int,
        importer_code: int,
        export_unit_price: float | None,
        import_unit_price: float | None,
    ) -> UnitPriceDeviation | None:
        """Compare declared unit prices against benchmark.

        Args:
            commodity_code: HS code.
            period: Trade period.
            exporter_code: Exporter country code.
            importer_code: Importer country code.
            export_unit_price: Exporter-declared unit price (USD/kg).
            import_unit_price: Importer-declared unit price (USD/kg).

        Returns:
            UnitPriceDeviation result, or None if no benchmark available
            or both unit prices are unavailable.
        """
        benchmark = self.get_benchmark(commodity_code, period)
        if benchmark is None:
            return None

        if export_unit_price is None and import_unit_price is None:
            return None

        bp = benchmark.benchmark_price_usd_per_kg
        flags: list[str] = []

        # Export deviation
        export_ratio: float | None = None
        export_flag = "normal"
        if export_unit_price is not None and bp > 0:
            export_ratio = export_unit_price / bp
            export_flag = self._classify_deviation(
                export_unit_price, benchmark
            )
            if export_flag in ("low", "extreme_low"):
                flags.append("export_underpriced")
            elif export_flag in ("high", "extreme_high"):
                flags.append("export_overpriced")

        # Import deviation
        import_ratio: float | None = None
        import_flag = "normal"
        if import_unit_price is not None and bp > 0:
            import_ratio = import_unit_price / bp
            import_flag = self._classify_deviation(
                import_unit_price, benchmark
            )
            if import_flag in ("low", "extreme_low"):
                flags.append("import_underpriced")
            elif import_flag in ("high", "extreme_high"):
                flags.append("import_overpriced")

        # Price divergence between export and import unit prices
        if (export_unit_price is not None and import_unit_price is not None
                and export_unit_price > 0 and import_unit_price > 0):
            midpoint = (export_unit_price + import_unit_price) / 2.0
            price_gap = abs(import_unit_price - export_unit_price) / midpoint
            if price_gap > 0.5:
                flags.append("unit_price_divergence")

        return UnitPriceDeviation(
            commodity_code=commodity_code,
            period=period,
            exporter_code=exporter_code,
            importer_code=importer_code,
            export_unit_price=export_unit_price,
            import_unit_price=import_unit_price,
            benchmark_price=bp,
            benchmark_low=benchmark.price_low_usd_per_kg,
            benchmark_high=benchmark.price_high_usd_per_kg,
            export_deviation_ratio=export_ratio,
            import_deviation_ratio=import_ratio,
            export_flag=export_flag,
            import_flag=import_flag,
            flags=flags,
        )

    def _classify_deviation(
        self,
        price: float,
        benchmark: UnitPriceBenchmark,
    ) -> str:
        """Classify a price deviation from benchmark."""
        if price < 0:
            return "invalid"

        low = benchmark.price_low_usd_per_kg
        high = benchmark.price_high_usd_per_kg
        bp = benchmark.benchmark_price_usd_per_kg

        if bp == 0:
            return "normal"

        # Extreme: more than 3x the IQR range beyond the benchmark bounds
        iqr_range = high - low if high > low else bp * 0.5
        extreme_low = max(0, low - 2.0 * iqr_range)
        extreme_high = high + 2.0 * iqr_range

        if price < extreme_low:
            return "extreme_low"
        if price < low:
            return "low"
        if price > extreme_high:
            return "extreme_high"
        if price > high:
            return "high"
        return "normal"

    def screen_discrepancies(
        self,
        discrepancies: list[Any],
    ) -> list[UnitPriceDeviation]:
        """Screen a list of DiscrepancyResults for unit price anomalies.

        Args:
            discrepancies: List of DiscrepancyResult objects from MirrorAnalyzer.

        Returns:
            List of UnitPriceDeviation results for pairs with benchmarks.
        """
        results: list[UnitPriceDeviation] = []
        for d in discrepancies:
            result = self.analyze_unit_price(
                commodity_code=d.commodity_code,
                period=d.period,
                exporter_code=d.exporter_code,
                importer_code=d.importer_code,
                export_unit_price=d.export_unit_price,
                import_unit_price=d.import_unit_price,
            )
            if result is not None and result.flags:
                results.append(result)
        return results
