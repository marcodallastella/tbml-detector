"""Export functionality: CSV download and PDF brief generation."""

from __future__ import annotations

import io
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


def csv_download_button(
    df: pd.DataFrame,
    filename: str = "mirror_analysis_export.csv",
    label: str = "Download as CSV",
    key: str | None = None,
) -> None:
    """Render a CSV download button for a DataFrame."""
    if df.empty:
        st.info("No data to export.")
        return

    csv_buffer = df.to_csv(index=False)
    st.download_button(
        label=label,
        data=csv_buffer,
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def generate_corridor_brief(
    conn: sqlite3.Connection,
    reporter_code: int,
    partner_code: int,
    reporter_name: str,
    partner_name: str,
    commodity_code: str | None = None,
) -> str:
    """Generate a plain-text summary brief for a trade corridor.

    This produces a structured text report suitable for editorial
    presentations and source meetings.

    Args:
        conn: Database connection.
        reporter_code: Exporter country code.
        partner_code: Importer country code.
        reporter_name: Human-readable exporter name.
        partner_name: Human-readable importer name.
        commodity_code: Optional HS code filter.

    Returns:
        Formatted text brief.
    """
    query = """
        SELECT * FROM analysis_results
        WHERE reporter_code = ? AND partner_code = ?
    """
    params: list[Any] = [reporter_code, partner_code]
    if commodity_code:
        query += " AND commodity_code = ?"
        params.append(commodity_code)
    query += " ORDER BY severity_score DESC"

    rows = conn.execute(query, params).fetchall()
    if not rows:
        return "No analysis results found for this corridor."

    columns = [desc[0] for desc in conn.execute(query, params).description]
    results = [dict(zip(columns, tuple(row))) for row in rows]

    # Build brief
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("MIRROR TRADE ANALYSIS BRIEF")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Corridor: {reporter_name} -> {partner_name}")
    if commodity_code:
        desc = results[0].get("commodity_description", "")
        lines.append(f"Commodity: {commodity_code} ({desc})")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total flagged flows: {len(results)}")
    lines.append("")

    # Summary statistics
    severities = [r["severity_score"] for r in results]
    discrepancies = [r["discrepancy_pct"] for r in results if r["discrepancy_pct"] is not None]
    total_value = sum(r["reported_value"] or 0 for r in results)

    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Highest severity score: {max(severities)}")
    lines.append(f"  Average severity score: {sum(severities) / len(severities):.1f}")
    if discrepancies:
        lines.append(f"  Largest discrepancy: {max(discrepancies, key=abs):.1f}%")
        lines.append(f"  Average discrepancy: {sum(discrepancies) / len(discrepancies):.1f}%")
    lines.append(f"  Total reported trade value: ${total_value:,.0f}")
    lines.append("")

    # Tier breakdown
    tier_counts: dict[str, int] = {}
    for r in results:
        tier = r.get("priority_tier", "unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    lines.append("PRIORITY BREAKDOWN")
    lines.append("-" * 40)
    for tier in ["critical", "high", "medium", "low", "noise"]:
        count = tier_counts.get(tier, 0)
        if count > 0:
            lines.append(f"  {tier.upper()}: {count} flows")
    lines.append("")

    # Top flagged flows
    lines.append("TOP FLAGGED FLOWS (by severity)")
    lines.append("-" * 40)
    for i, r in enumerate(results[:10], 1):
        lines.append(
            f"  {i}. Period {r['period']} | "
            f"HS {r['commodity_code']} ({r.get('commodity_description', 'N/A')}) | "
            f"Severity: {r['severity_score']} ({r['priority_tier']})"
        )
        lines.append(
            f"     Reported: ${r['reported_value']:,.0f} | "
            f"Mirror: ${r['mirror_value']:,.0f} | "
            f"Gap: {r['discrepancy_pct']:.1f}%"
        )
        if r.get("flags"):
            lines.append(f"     Flags: {r['flags']}")
        if r.get("notes"):
            lines.append(f"     Notes: {r['notes']}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(
        "NOTE: This analysis is based on officially reported trade statistics "
        "and statistical anomaly detection. Discrepancies may have legitimate "
        "explanations (reporting lags, re-exports, confidential flows). "
        "This report is a starting point for investigation, not proof of "
        "wrongdoing."
    )
    lines.append("=" * 70)

    return "\n".join(lines)


def corridor_brief_download(
    conn: sqlite3.Connection,
    reporter_code: int,
    partner_code: int,
    reporter_name: str,
    partner_name: str,
    commodity_code: str | None = None,
    key: str = "brief_download",
) -> None:
    """Render a download button for a corridor summary brief."""
    brief = generate_corridor_brief(
        conn, reporter_code, partner_code,
        reporter_name, partner_name, commodity_code,
    )
    safe_reporter = reporter_name.replace(" ", "_")[:20]
    safe_partner = partner_name.replace(" ", "_")[:20]
    filename = f"brief_{safe_reporter}_to_{safe_partner}.txt"

    st.download_button(
        label="Download corridor brief",
        data=brief,
        file_name=filename,
        mime="text/plain",
        key=key,
        help="Download a text summary of this corridor's analysis results, "
             "suitable for editorial presentations and source meetings.",
    )
