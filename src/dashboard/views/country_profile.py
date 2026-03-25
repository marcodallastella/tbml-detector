"""Country profile view: anomalous corridors and commodities for a country.

Select a country and see all its flagged trade corridors and commodities
ranked by severity.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.export import csv_download_button
from src.dashboard.components.filters import (
    country_filter,
    get_country_name,
    min_severity_slider,
)
from src.dashboard.components.tooltips import TOOLTIPS


def render(conn: sqlite3.Connection) -> None:
    """Render the country profile view."""
    st.header("Country Profile")
    st.caption(
        "Select a country to see a summary of all its flagged trade corridors "
        "and commodities, ranked by severity. Use this view to investigate "
        "a specific country's trade patterns."
    )

    # Filters
    with st.sidebar:
        st.subheader("Country Selection")
        selected_country = country_filter(
            conn, label="Select country", key="profile_country",
        )
        direction = st.radio(
            "View as",
            ["Exporter", "Importer", "Both"],
            key="profile_direction",
            help="View this country's flagged flows as exporter, importer, or both.",
        )
        min_sev = min_severity_slider(key="profile_min_sev")

    if not selected_country:
        st.info("Select a country in the sidebar to view its profile.")
        return

    country_name = get_country_name(conn, selected_country)
    st.subheader(country_name)

    # Query based on direction
    if direction == "Exporter":
        where_clause = "reporter_code = ?"
    elif direction == "Importer":
        where_clause = "partner_code = ?"
    else:
        where_clause = "(reporter_code = ? OR partner_code = ?)"

    query = f"""
        SELECT * FROM analysis_results
        WHERE {where_clause} AND severity_score >= ?
        ORDER BY severity_score DESC
    """
    params: list = [selected_country]
    if direction == "Both":
        params.append(selected_country)
    params.append(min_sev)

    rows = conn.execute(query, params).fetchall()

    if not rows:
        st.info(f"No flagged flows for {country_name} with severity >= {min_sev}.")
        return

    columns = [desc[0] for desc in conn.execute(query, params).description]
    df = pd.DataFrame([tuple(row) for row in rows], columns=columns)

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total flagged flows", len(df))
    with col2:
        critical_count = len(df[df["priority_tier"] == "critical"])
        st.metric("Critical", critical_count)
    with col3:
        high_count = len(df[df["priority_tier"] == "high"])
        st.metric("High", high_count)
    with col4:
        partner_cols = set(df["partner_code"].unique()) | set(df["reporter_code"].unique())
        partner_cols.discard(selected_country)
        unique_partners = len(partner_cols)
        st.metric("Partner countries", unique_partners)

    # Tier distribution
    tier_counts = df["priority_tier"].value_counts()
    tier_order = ["critical", "high", "medium", "low", "noise"]
    tier_colors = {
        "critical": "#ff4b4b", "high": "#ff8c00",
        "medium": "#ffd700", "low": "#90ee90", "noise": "#d3d3d3",
    }

    fig_tier = px.bar(
        x=[t for t in tier_order if t in tier_counts.index],
        y=[tier_counts.get(t, 0) for t in tier_order if t in tier_counts.index],
        color=[t for t in tier_order if t in tier_counts.index],
        color_discrete_map=tier_colors,
        labels={"x": "Priority Tier", "y": "Number of Flows"},
        title="Flows by Priority Tier",
    )
    fig_tier.update_layout(
        showlegend=False, height=300, template="plotly_white",
    )
    st.plotly_chart(fig_tier, use_container_width=True)

    # Top corridors
    st.subheader("Top Corridors by Severity")

    corridor_df = df.groupby(["reporter_code", "partner_code"]).agg(
        max_severity=("severity_score", "max"),
        avg_severity=("severity_score", "mean"),
        flow_count=("severity_score", "count"),
        avg_discrepancy=("discrepancy_pct", "mean"),
    ).reset_index().sort_values("max_severity", ascending=False)

    corridor_df["exporter"] = corridor_df["reporter_code"].apply(
        lambda c: get_country_name(conn, c)
    )
    corridor_df["importer"] = corridor_df["partner_code"].apply(
        lambda c: get_country_name(conn, c)
    )

    display_corridor = corridor_df[[
        "exporter", "importer", "max_severity", "avg_severity",
        "flow_count", "avg_discrepancy",
    ]].head(20).copy()
    display_corridor.columns = [
        "Exporter", "Importer", "Max Severity", "Avg Severity",
        "Flows", "Avg Discrepancy %",
    ]
    display_corridor["Avg Severity"] = display_corridor["Avg Severity"].apply(lambda v: f"{v:.0f}")
    display_corridor["Avg Discrepancy %"] = display_corridor["Avg Discrepancy %"].apply(
        lambda v: f"{v:+.1f}%" if pd.notna(v) else "N/A"
    )

    st.dataframe(display_corridor, use_container_width=True, hide_index=True)

    # Top commodities
    st.subheader("Top Commodities by Severity")

    commodity_df = df.groupby(["commodity_code", "commodity_description"]).agg(
        max_severity=("severity_score", "max"),
        avg_severity=("severity_score", "mean"),
        flow_count=("severity_score", "count"),
        total_value=("reported_value", "sum"),
    ).reset_index().sort_values("max_severity", ascending=False)

    fig_comm = px.bar(
        commodity_df.head(15),
        x="commodity_code",
        y="max_severity",
        color="max_severity",
        color_continuous_scale="YlOrRd",
        hover_data=["commodity_description", "flow_count", "total_value"],
        labels={
            "commodity_code": "HS Code",
            "max_severity": "Max Severity",
            "commodity_description": "Commodity",
        },
        title="Most Suspicious Commodities",
    )
    fig_comm.update_layout(height=350, template="plotly_white")
    st.plotly_chart(fig_comm, use_container_width=True)

    display_comm = commodity_df[[
        "commodity_code", "commodity_description", "max_severity",
        "flow_count", "total_value",
    ]].head(15).copy()
    display_comm.columns = ["HS Code", "Commodity", "Max Severity", "Flows", "Total Value (USD)"]
    display_comm["Total Value (USD)"] = display_comm["Total Value (USD)"].apply(
        lambda v: f"${v:,.0f}" if pd.notna(v) else "N/A"
    )
    st.dataframe(display_comm, use_container_width=True, hide_index=True)

    # Export
    st.divider()
    csv_download_button(df, filename=f"country_profile_{selected_country}.csv", key="profile_csv")
