"""Alert table view: ranked list of flagged trade flows.

Sortable by severity, discrepancy, commodity, and country. Each row is
expandable to show triggered typology flags and scoring detail.
"""

from __future__ import annotations

import json
import sqlite3

import pandas as pd
import streamlit as st

from src.dashboard.components.export import csv_download_button
from src.dashboard.components.filters import (
    commodity_filter,
    country_filter,
    get_country_name,
    min_severity_slider,
    severity_tier_filter,
)
from src.dashboard.components.tooltips import TOOLTIPS


def render(conn: sqlite3.Connection) -> None:
    """Render the alert table view."""
    st.header("Flagged Trade Flows")
    st.caption(
        "Ranked list of trade flows where the exporter's reported value "
        "differs significantly from the importer's reported value. "
        "Higher severity scores indicate more suspicious patterns."
    )

    # Sidebar filters
    with st.sidebar:
        st.subheader("Filters")
        tier = severity_tier_filter(key="alert_tier")
        min_sev = min_severity_slider(key="alert_min_sev")
        reporter = country_filter(conn, label="Exporting country", key="alert_reporter")
        partner = country_filter(
            conn, label="Importing country", key="alert_partner", column="partner_code"
        )
        commodity = commodity_filter(conn, key="alert_commodity")

    # Build query
    query = "SELECT * FROM analysis_results WHERE severity_score >= ?"
    params: list = [min_sev]

    if tier:
        query += " AND priority_tier = ?"
        params.append(tier)
    if reporter:
        query += " AND reporter_code = ?"
        params.append(reporter)
    if partner:
        query += " AND partner_code = ?"
        params.append(partner)
    if commodity:
        query += " AND commodity_code = ?"
        params.append(commodity)

    query += " ORDER BY severity_score DESC"

    rows = conn.execute(query, params).fetchall()

    if not rows:
        st.info("No flagged flows match your filters. Try lowering the severity threshold.")
        return

    st.metric("Flagged flows", len(rows))

    # Convert to DataFrame for display
    columns = [desc[0] for desc in conn.execute(query, params).description]
    df = pd.DataFrame([tuple(row) for row in rows], columns=columns)

    # Display columns
    display_cols = [
        "priority_tier", "severity_score", "reporter_code", "partner_code",
        "commodity_code", "commodity_description", "period",
        "reported_value", "mirror_value", "discrepancy_pct",
    ]
    display_df = df[display_cols].copy()
    display_df.columns = [
        "Tier", "Severity", "Exporter", "Importer",
        "HS Code", "Commodity", "Period",
        "Reported (USD)", "Mirror (USD)", "Discrepancy %",
    ]

    # Format country names
    for col_label, col_code in [("Exporter", "reporter_code"), ("Importer", "partner_code")]:
        display_df[col_label] = df[col_code].apply(
            lambda c: get_country_name(conn, c)
        )

    # Format currency
    for col in ["Reported (USD)", "Mirror (USD)"]:
        display_df[col] = display_df[col].apply(
            lambda v: f"${v:,.0f}" if pd.notna(v) else "N/A"
        )
    display_df["Discrepancy %"] = display_df["Discrepancy %"].apply(
        lambda v: f"{v:+.1f}%" if pd.notna(v) else "N/A"
    )

    # Color tiers
    def tier_color(tier_val: str) -> str:
        colors = {
            "critical": "background-color: #ff4b4b33",
            "high": "background-color: #ffa50033",
            "medium": "background-color: #ffff0022",
            "low": "background-color: #90ee9022",
            "noise": "",
        }
        return colors.get(tier_val, "")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    # Expandable detail for each row
    st.subheader("Detail View")
    st.caption("Select a row number to see full analysis detail.")

    row_idx = st.number_input(
        "Row number (1-based)",
        min_value=1,
        max_value=len(df),
        value=1,
        key="alert_detail_row",
    )

    record = df.iloc[row_idx - 1]
    reporter_name = get_country_name(conn, int(record["reporter_code"]))
    partner_name = get_country_name(conn, int(record["partner_code"]))

    with st.expander(
        f"Detail: {reporter_name} -> {partner_name} | "
        f"HS {record['commodity_code']} | Period {record['period']}",
        expanded=True,
    ):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Severity Score",
                int(record["severity_score"]),
                help=TOOLTIPS["severity_score"],
            )
        with col2:
            st.metric(
                "Priority Tier",
                str(record["priority_tier"]).upper(),
                help=TOOLTIPS["priority_tier"],
            )
        with col3:
            disc = record["discrepancy_pct"]
            st.metric(
                "Discrepancy",
                f"{disc:+.1f}%" if pd.notna(disc) else "N/A",
                help=TOOLTIPS["discrepancy_pct"],
            )

        st.markdown("**Scoring Breakdown**")
        score_cols = st.columns(5)
        components = [
            ("Magnitude", "severity_magnitude"),
            ("Statistical", "severity_statistical"),
            ("Persistence", "severity_persistence"),
            ("Corridor Risk", "severity_corridor_risk"),
            ("Commodity Risk", "severity_commodity_risk"),
        ]
        for col, (label, field) in zip(score_cols, components):
            with col:
                val = record.get(field, 0)
                st.metric(label, f"{val}/20" if pd.notna(val) else "N/A")

        adj = record.get("severity_adjustments", 0)
        if adj and adj != 0:
            st.caption(f"Adjustments applied: {adj:+d} points (e.g., re-export or rounding corrections)")

        # Flags
        flags_raw = record.get("flags", "[]")
        try:
            flags = json.loads(flags_raw) if isinstance(flags_raw, str) else flags_raw
        except (json.JSONDecodeError, TypeError):
            flags = []

        if flags:
            st.markdown("**Triggered Flags**", help=TOOLTIPS["flags"])
            flag_descriptions = {
                "z_score_elevated": "Discrepancy is statistically elevated compared to this corridor's history (z-score > 2)",
                "z_score_high": "Discrepancy is statistically high (z-score > 3) -- very unusual for this corridor",
                "z_score_extreme": "Discrepancy is extreme (z-score > 5) -- almost never seen in this corridor's history",
                "benford_violation": "The distribution of trade values does not follow Benford's Law, which can indicate fabricated numbers",
                "asymmetry_detected": "There is a persistent directional bias in reporting -- one side consistently reports higher",
                "rolling_deviation": "Recent discrepancies deviate from the rolling average trend",
                "re_export_involved": "One or both sides of this flow involve re-exports, which complicates comparison",
                "confidential_flow": "Some values are suppressed for confidentiality, limiting analysis",
                "no_quantity_data": "No quantity or weight data available for unit price analysis",
                "rounding_artifact": "The discrepancy may be a rounding artifact rather than a real gap",
                "unit_price_deviation": "The declared price per unit differs significantly from global commodity benchmarks",
            }
            for flag_name in flags:
                desc = flag_descriptions.get(
                    flag_name,
                    "Anomaly pattern detected by the analysis engine"
                )
                st.markdown(f"- **{flag_name}**: {desc}")

        # Notes
        notes = record.get("notes", "")
        if notes:
            st.markdown(f"**Notes:** {notes}")

        # Trade values
        st.markdown("**Trade Values**")
        val_col1, val_col2, val_col3 = st.columns(3)
        with val_col1:
            rep_val = record["reported_value"]
            st.metric(
                "Exporter reported",
                f"${rep_val:,.0f}" if pd.notna(rep_val) else "N/A",
                help=TOOLTIPS["reported_value"],
            )
        with val_col2:
            mir_val = record["mirror_value"]
            st.metric(
                "Importer reported",
                f"${mir_val:,.0f}" if pd.notna(mir_val) else "N/A",
                help=TOOLTIPS["mirror_value"],
            )
        with val_col3:
            abs_gap = record.get("discrepancy_abs", 0)
            st.metric(
                "Absolute gap",
                f"${abs_gap:,.0f}" if pd.notna(abs_gap) else "N/A",
            )

    # Export
    st.divider()
    csv_download_button(df, filename="flagged_flows.csv", key="alert_csv")
