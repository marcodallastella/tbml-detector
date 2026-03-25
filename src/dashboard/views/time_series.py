"""Time series view: discrepancy trends over time for a selected corridor.

Shows how the discrepancy between reported exports and imports evolves
over time, with severity scoring context.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.dashboard.components.export import corridor_brief_download, csv_download_button
from src.dashboard.components.filters import (
    commodity_filter,
    corridor_filter,
    get_country_name,
)
from src.dashboard.components.tooltips import TOOLTIPS


def render(conn: sqlite3.Connection) -> None:
    """Render the time series view."""
    st.header("Discrepancy Over Time")
    st.caption(
        "Track how the gap between reported exports and imports changes over "
        "time for a specific trade corridor. Persistent discrepancies in the "
        "same direction are more suspicious than one-off spikes."
    )

    # Filters
    with st.sidebar:
        st.subheader("Corridor Selection")
        reporter, partner = corridor_filter(conn, key_prefix="ts")
        commodity = commodity_filter(conn, key="ts_commodity")

    if not reporter or not partner:
        st.warning("Please select both an exporting and importing country.")
        return

    reporter_name = get_country_name(conn, reporter)
    partner_name = get_country_name(conn, partner)

    # Query
    query = """
        SELECT period, reported_value, mirror_value, discrepancy_abs,
               discrepancy_pct, z_score, severity_score, priority_tier,
               severity_magnitude, severity_statistical, severity_persistence,
               severity_corridor_risk, severity_commodity_risk,
               commodity_code, commodity_description, flags, notes
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

    # Multi-panel chart
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Trade Values (USD)",
            "Discrepancy (%)",
            "Severity Score",
        ),
        row_heights=[0.4, 0.3, 0.3],
    )

    # Panel 1: Trade values
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["reported_value"],
        name="Exporter reported",
        mode="lines+markers",
        line=dict(color="#2196F3", width=2),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df["period"], y=df["mirror_value"],
        name="Importer reported",
        mode="lines+markers",
        line=dict(color="#FF9800", width=2),
    ), row=1, col=1)

    # Panel 2: Discrepancy %
    disc_colors = [
        "#ff4b4b" if abs(v) > 25 else "#ffa500" if abs(v) > 10 else "#4CAF50"
        for v in df["discrepancy_pct"].fillna(0)
    ]
    fig.add_trace(go.Bar(
        x=df["period"], y=df["discrepancy_pct"],
        name="Discrepancy %",
        marker_color=disc_colors,
        showlegend=False,
    ), row=2, col=1)

    fig.add_hline(y=25, line_dash="dash", line_color="red", opacity=0.4, row=2, col=1)
    fig.add_hline(y=-25, line_dash="dash", line_color="red", opacity=0.4, row=2, col=1)
    fig.add_hline(y=0, line_color="gray", opacity=0.3, row=2, col=1)

    # Panel 3: Severity score
    tier_colors = {
        "critical": "#ff4b4b",
        "high": "#ff8c00",
        "medium": "#ffd700",
        "low": "#90ee90",
        "noise": "#d3d3d3",
    }
    sev_colors = [
        tier_colors.get(t, "#d3d3d3") for t in df["priority_tier"].fillna("noise")
    ]
    fig.add_trace(go.Bar(
        x=df["period"], y=df["severity_score"],
        name="Severity",
        marker_color=sev_colors,
        showlegend=False,
    ), row=3, col=1)

    # Tier threshold lines
    for threshold, label in [(80, "Critical"), (60, "High"), (40, "Medium")]:
        fig.add_hline(
            y=threshold, line_dash="dot", line_color="gray", opacity=0.3,
            annotation_text=label, annotation_position="bottom right",
            row=3, col=1,
        )

    fig.update_layout(
        title=f"Time Series: {reporter_name} -> {partner_name}",
        height=750,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Z-score chart (if available)
    if df["z_score"].notna().any():
        st.subheader("Statistical Context")
        st.caption(TOOLTIPS["z_score"])

        fig_z = go.Figure()
        fig_z.add_trace(go.Scatter(
            x=df["period"], y=df["z_score"],
            mode="lines+markers",
            name="Z-score",
            line=dict(color="#9C27B0", width=2),
        ))
        fig_z.add_hline(y=3, line_dash="dash", line_color="red", opacity=0.5,
                        annotation_text="High threshold (z=3)")
        fig_z.add_hline(y=-3, line_dash="dash", line_color="red", opacity=0.5)
        fig_z.add_hline(y=0, line_color="gray", opacity=0.3)

        fig_z.update_layout(
            title="Z-Score Over Time",
            xaxis_title="Period",
            yaxis_title="Z-Score",
            height=300,
            template="plotly_white",
        )
        st.plotly_chart(fig_z, use_container_width=True)

    # Data table
    with st.expander("View data table"):
        show_cols = ["period", "reported_value", "mirror_value", "discrepancy_pct",
                     "z_score", "severity_score", "priority_tier"]
        display_df = df[show_cols].copy()
        display_df.columns = ["Period", "Reported (USD)", "Mirror (USD)",
                              "Discrepancy %", "Z-Score", "Severity", "Tier"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Export
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        csv_download_button(df, filename=f"timeseries_{reporter}_{partner}.csv", key="ts_csv")
    with col2:
        corridor_brief_download(
            conn, reporter, partner, reporter_name, partner_name,
            commodity_code=commodity, key="ts_brief",
        )
