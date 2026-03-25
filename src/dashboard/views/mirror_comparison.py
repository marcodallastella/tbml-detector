"""Mirror comparison view: side-by-side exporter vs. importer values over time.

For a selected corridor, shows reporter exports alongside partner imports
with the discrepancy highlighted.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.export import corridor_brief_download, csv_download_button
from src.dashboard.components.filters import (
    commodity_filter,
    corridor_filter,
    get_country_name,
)
from src.dashboard.components.tooltips import TOOLTIPS


def render(conn: sqlite3.Connection) -> None:
    """Render the mirror comparison view."""
    st.header("Mirror Comparison")
    st.caption(
        "Compare what the exporting country reports sending with what the "
        "importing country reports receiving, over time. The gap between "
        "these two lines is the discrepancy."
    )
    st.info(TOOLTIPS["cif_fob"], icon="ℹ️")

    # Filters
    with st.sidebar:
        st.subheader("Corridor Selection")
        reporter, partner = corridor_filter(conn, key_prefix="mirror")
        commodity = commodity_filter(conn, key="mirror_commodity")

    if not reporter or not partner:
        st.warning("Please select both an exporting and importing country in the sidebar.")
        return

    reporter_name = get_country_name(conn, reporter)
    partner_name = get_country_name(conn, partner)

    # Query results for this corridor
    query = """
        SELECT period, reported_value, mirror_value, discrepancy_pct,
               discrepancy_abs, severity_score, priority_tier, flags, notes
        FROM analysis_results
        WHERE reporter_code = ? AND partner_code = ?
    """
    params: list = [reporter, partner]
    if commodity:
        query += " AND commodity_code = ?"
        params.append(commodity)
    query += " ORDER BY period ASC"

    rows = conn.execute(query, params).fetchall()

    if not rows:
        st.info(f"No analysis results for {reporter_name} -> {partner_name}.")
        return

    columns = [desc[0] for desc in conn.execute(query, params).description]
    df = pd.DataFrame([tuple(row) for row in rows], columns=columns)

    # Side-by-side chart
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["period"],
        y=df["reported_value"],
        name=f"{reporter_name} reported exports",
        marker_color="#2196F3",
        opacity=0.8,
    ))

    fig.add_trace(go.Bar(
        x=df["period"],
        y=df["mirror_value"],
        name=f"{partner_name} reported imports",
        marker_color="#FF9800",
        opacity=0.8,
    ))

    fig.update_layout(
        title=f"Trade Values: {reporter_name} -> {partner_name}",
        xaxis_title="Period",
        yaxis_title="Trade Value (USD)",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=450,
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Discrepancy line chart
    fig_disc = go.Figure()

    fig_disc.add_trace(go.Scatter(
        x=df["period"],
        y=df["discrepancy_pct"],
        mode="lines+markers",
        name="Discrepancy %",
        line=dict(color="#E91E63", width=2),
        fill="tozeroy",
        fillcolor="rgba(233, 30, 99, 0.1)",
    ))

    # Add threshold line
    fig_disc.add_hline(y=25, line_dash="dash", line_color="red", opacity=0.5,
                       annotation_text="25% threshold")
    fig_disc.add_hline(y=-25, line_dash="dash", line_color="red", opacity=0.5)
    fig_disc.add_hline(y=0, line_color="gray", opacity=0.3)

    fig_disc.update_layout(
        title="Discrepancy Over Time",
        xaxis_title="Period",
        yaxis_title="Discrepancy (%)",
        height=350,
        template="plotly_white",
    )

    st.plotly_chart(fig_disc, use_container_width=True)

    # Summary table
    st.subheader("Period Detail")
    display_df = df[["period", "reported_value", "mirror_value", "discrepancy_pct",
                      "severity_score", "priority_tier"]].copy()
    display_df.columns = ["Period", "Exporter Reported (USD)", "Importer Reported (USD)",
                          "Discrepancy %", "Severity", "Tier"]
    for col in ["Exporter Reported (USD)", "Importer Reported (USD)"]:
        display_df[col] = display_df[col].apply(
            lambda v: f"${v:,.0f}" if pd.notna(v) else "N/A"
        )
    display_df["Discrepancy %"] = display_df["Discrepancy %"].apply(
        lambda v: f"{v:+.1f}%" if pd.notna(v) else "N/A"
    )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Export
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        csv_download_button(df, filename=f"mirror_{reporter}_{partner}.csv", key="mirror_csv")
    with col2:
        corridor_brief_download(
            conn, reporter, partner, reporter_name, partner_name,
            commodity_code=commodity, key="mirror_brief",
        )
