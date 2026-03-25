"""Data cleaning and normalization for UN Comtrade trade records."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Typical CIF/FOB ratio: imports (CIF) are ~5-10% higher than exports (FOB)
# due to insurance and freight costs.
DEFAULT_CIF_FOB_RATIO = 1.06

# Partner codes that should be excluded from mirror analysis
WORLD_CODE = 0
AREAS_NES_CODE = 899
EU_AGGREGATE_CODE = 97

# Known confidential commodity codes (HS 4-digit) where suppression is common
KNOWN_CONFIDENTIAL_HS = {"2709", "2710", "2612", "2844", "7108", "2601"}

# Quantity unit normalization mappings (Comtrade unit codes -> standard)
WEIGHT_UNITS: dict[int, tuple[str, float]] = {
    1: ("kg", 1.0),
    2: ("m", 1.0),           # meters
    3: ("m2", 1.0),          # square meters
    4: ("m3", 1.0),          # cubic meters
    5: ("units", 1.0),       # number of items
    6: ("pairs", 1.0),
    7: ("dozens", 12.0),     # convert to units
    8: ("l", 1.0),           # liters
    9: ("1000 kWh", 1.0),
    10: ("1000 units", 1000.0),
    11: ("carats", 0.0002),  # convert to kg
    12: ("kg", 1000.0),      # thousands of kg -> kg multiplier
}


class TradeCleaner:
    """Cleans and normalizes raw Comtrade trade records for mirror analysis."""

    def __init__(self, cif_fob_ratio: float = DEFAULT_CIF_FOB_RATIO) -> None:
        self.cif_fob_ratio = cif_fob_ratio

    def clean_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Clean a batch of normalized trade records.

        Args:
            records: List of records already normalized via ComtradeAPI.normalize_record().

        Returns:
            List of cleaned records ready for insertion into cleaned_records table.
        """
        cleaned: list[dict[str, Any]] = []
        for record in records:
            result = self.clean_record(record)
            if result is not None:
                cleaned.append(result)
        logger.info("Cleaned %d/%d records", len(cleaned), len(records))
        return cleaned

    def clean_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """Clean and normalize a single trade record.

        Returns None if the record should be discarded (e.g., missing critical data).
        """
        notes: list[str] = []

        reporter = record.get("reporter_code")
        partner = record.get("partner_code")
        commodity = record.get("commodity_code")
        flow = record.get("flow_code")
        period = record.get("period")

        # Discard records with missing essential fields
        if any(v is None for v in (reporter, partner, commodity, flow, period)):
            logger.debug("Skipping record with missing essential fields: %s", record)
            return None

        # Flag World/NES/EU aggregate partners (keep but mark for exclusion from mirror)
        if partner in (WORLD_CODE, AREAS_NES_CODE, EU_AGGREGATE_CODE):
            notes.append(f"Aggregate partner (code={partner}), excluded from mirror analysis")

        # Detect confidential suppression: zero or null value for a commodity
        # known to be frequently suppressed, OR explicitly marked confidential
        trade_value = self._clean_value(record.get("trade_value_usd"))
        is_confidential = record.get("is_confidential", 0)
        commodity_str = str(commodity) if commodity else ""
        hs4 = commodity_str[:4] if len(commodity_str) >= 4 else commodity_str

        if (trade_value is None or trade_value == 0) and hs4 in KNOWN_CONFIDENTIAL_HS:
            is_confidential = 1
            notes.append(f"Likely confidential suppression (HS {hs4}, value=0/null)")

        # Normalize monetary values
        cif_value = self._clean_value(record.get("cif_value_usd"))
        fob_value = self._clean_value(record.get("fob_value_usd"))

        # Derive FOB value for imports if not provided
        fob_adjusted = fob_value
        if flow in (1, 4):  # Import or re-import
            if fob_value is None and cif_value is not None:
                fob_adjusted = cif_value / self.cif_fob_ratio
                notes.append(f"FOB derived from CIF (ratio={self.cif_fob_ratio})")
            elif fob_value is None and trade_value is not None:
                fob_adjusted = trade_value / self.cif_fob_ratio
                notes.append(f"FOB derived from trade_value (ratio={self.cif_fob_ratio})")
        else:  # Export
            if fob_value is None and trade_value is not None:
                fob_adjusted = trade_value
                notes.append("FOB set to trade_value for export")

        # Normalize quantities
        weight = self._clean_value(record.get("net_weight_kg"))
        qty = self._clean_value(record.get("qty"))
        qty_unit = record.get("qty_unit_code")
        qty_normalized, unit_normalized = self._normalize_quantity(qty, qty_unit)

        has_quantity = qty_normalized is not None
        has_weight = weight is not None

        # Calculate unit price
        unit_price = None
        if trade_value is not None and trade_value > 0:
            if weight is not None and weight > 0:
                unit_price = trade_value / weight
            elif qty_normalized is not None and qty_normalized > 0:
                unit_price = trade_value / qty_normalized

        # Quality score: simple heuristic based on data completeness
        quality_score = self._compute_quality_score(
            trade_value, fob_adjusted, weight, qty_normalized,
            is_confidential,
        )

        # Flag re-exports
        is_re_export = record.get("is_re_export", 0)
        if flow in (3, 4):
            is_re_export = 1
            notes.append("Flagged as re-export/re-import")

        return {
            "reporter_code": reporter,
            "partner_code": partner,
            "commodity_code": str(commodity),
            "flow_code": flow,
            "period": str(period),
            "frequency": record.get("frequency", "A"),
            "trade_value_usd": trade_value,
            "fob_value_usd": fob_adjusted,
            "net_weight_kg": weight,
            "qty_normalized": qty_normalized,
            "qty_unit_normalized": unit_normalized,
            "unit_price_usd": unit_price,
            "is_re_export": is_re_export,
            "is_confidential": is_confidential,
            "has_quantity": 1 if has_quantity else 0,
            "has_weight": 1 if has_weight else 0,
            "quality_score": quality_score,
            "cleaning_notes": "; ".join(notes) if notes else None,
        }

    def _normalize_quantity(
        self, qty: float | None, unit_code: int | None
    ) -> tuple[float | None, str | None]:
        """Normalize quantity to a standard unit where possible."""
        if qty is None or unit_code is None:
            return None, None
        mapping = WEIGHT_UNITS.get(unit_code)
        if mapping is None:
            return qty, f"unit_{unit_code}"
        unit_name, multiplier = mapping
        return qty * multiplier, unit_name

    @staticmethod
    def _clean_value(value: Any) -> float | None:
        """Clean a numeric value, returning None for invalid/missing data."""
        if value is None:
            return None
        try:
            v = float(value)
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _compute_quality_score(
        trade_value: float | None,
        fob_value: float | None,
        weight: float | None,
        qty: float | None,
        is_confidential: int,
    ) -> float:
        """Compute a data quality score from 0.0 (poor) to 1.0 (excellent)."""
        score = 0.0
        max_points = 5.0

        if trade_value is not None and trade_value > 0:
            score += 1.0
        if fob_value is not None and fob_value > 0:
            score += 1.0
        if weight is not None and weight > 0:
            score += 1.0
        if qty is not None and qty > 0:
            score += 1.0
        if not is_confidential:
            score += 1.0

        return round(score / max_points, 2)
