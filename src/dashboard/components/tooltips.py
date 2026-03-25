"""Contextual tooltips and plain-language explanations.

Every metric shown to the journalist user is accompanied by a tooltip
explaining what it means and why it matters, in plain language.
"""

TOOLTIPS: dict[str, str] = {
    "severity_score": (
        "A score from 0 to 100 that combines how large the trade discrepancy is, "
        "how statistically unusual it is, how long it has persisted, and how risky "
        "the countries and commodities involved are. Higher scores deserve closer "
        "investigation."
    ),
    "priority_tier": (
        "Critical (80-100): Strong evidence of irregularity across multiple dimensions. "
        "High (60-79): Significant anomaly worth investigating. "
        "Medium (40-59): Notable discrepancy, possibly explainable. "
        "Low (20-39): Minor discrepancy, likely normal trade variation. "
        "Noise (0-19): Within expected range."
    ),
    "discrepancy_pct": (
        "The percentage difference between what the exporting country reported "
        "sending and what the importing country reported receiving, after adjusting "
        "for shipping costs (CIF/FOB). A discrepancy above 25% after adjustment "
        "is unusual and may warrant investigation."
    ),
    "z_score": (
        "How many standard deviations this discrepancy is from the historical "
        "average for this trade corridor. A z-score above 3 means this is very "
        "unusual compared to past trade between these two countries."
    ),
    "cif_fob": (
        "CIF (Cost, Insurance, Freight) vs FOB (Free On Board): Importers typically "
        "report higher values than exporters because import values include shipping "
        "and insurance costs. A typical CIF/FOB ratio is 1.05-1.10. The system "
        "adjusts for this before flagging discrepancies."
    ),
    "mirror_analysis": (
        "Mirror analysis compares what Country A says it exported to Country B "
        "with what Country B says it imported from Country A. In legitimate trade, "
        "these should roughly match (after accounting for shipping costs and "
        "reporting lags). Large gaps can indicate invoice manipulation, phantom "
        "shipments, or other irregularities."
    ),
    "phantom_shipment": (
        "A trade flow reported by one country but not the other. For example, "
        "Country A reports exporting $10M in gold to Country B, but Country B "
        "has no record of importing it. This could indicate falsified trade "
        "documents used to move money."
    ),
    "flags": (
        "Specific patterns detected by the analysis engine: over/under-invoicing, "
        "phantom shipments, abnormal unit prices, Benford's law violations, etc. "
        "Each flag indicates a particular type of trade anomaly."
    ),
    "reported_value": (
        "The trade value in US dollars as reported by the exporting country."
    ),
    "mirror_value": (
        "The trade value in US dollars as reported by the importing country."
    ),
    "persistence": (
        "The number of consecutive time periods where this corridor has shown "
        "a significant discrepancy in the same direction. Persistent discrepancies "
        "are more suspicious than one-off spikes."
    ),
    "corridor_risk": (
        "A risk score based on the countries involved. Factors include: whether "
        "either country is a known secrecy jurisdiction, a re-export hub, a free "
        "trade zone, or has weak customs reporting."
    ),
    "commodity_risk": (
        "A risk score based on what is being traded. High-value, easy-to-misprice "
        "goods like gold, precious stones, art, and pharmaceuticals carry higher "
        "risk scores."
    ),
}


def get_tooltip(metric: str) -> str:
    """Get the plain-language tooltip for a metric."""
    return TOOLTIPS.get(metric, "")


