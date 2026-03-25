"""Sankey diagram view: trade flow visualization.

Shows volumes and discrepancies for a selected commodity flowing
from origin through transit hubs to destination.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.export import csv_download_button
from src.dashboard.components.filters import (
    commodity_filter,
    get_country_name,
    min_severity_slider,
    period_filter,
)
from src.dashboard.components.tooltips import TOOLTIPS


def render(conn: sqlite3.Connection) -> None:
    """Render the Sankey diagram view."""
    st.header("Trade Flow Diagram")
    st.caption(
        "This diagram shows how trade flows between countries for a selected "
        "commodity. The width of each link represents the trade volume. "
        "Red-tinted links indicate flows with significant discrepancies. "
        "Look for patterns where goods flow through intermediary countries "
        "(potential transit hubs used to obscure origin or manipulate values)."
    )

    # Filters
    with st.sidebar:
        st.subheader("Filters")
        commodity = commodity_filter(conn, key="sankey_commodity")
        period = period_filter(conn, key="sankey_period")
        min_sev = min_severity_slider(key="sankey_min_sev")
        max_flows = st.slider(
            "Maximum flows to display",
            min_value=5, max_value=100, value=30,
            key="sankey_max_flows",
            help="Limit the number of trade links shown to keep the diagram readable.",
        )

    if not commodity:
        st.warning("Please select a commodity in the sidebar to view the flow diagram.")
        return

    # Query flows
    query = """
        SELECT reporter_code, partner_code, reported_value, mirror_value,
               discrepancy_pct, severity_score, priority_tier
        FROM analysis_results
        WHERE commodity_code = ? AND severity_score >= ?
    """
    params: list = [commodity, min_sev]

    if period:
        query += " AND period = ?"
        params.append(period)

    query += " ORDER BY reported_value DESC LIMIT ?"
    params.append(max_flows)

    rows = conn.execute(query, params).fetchall()

    if not rows:
        st.info("No flows match your filters.")
        return

    columns = [desc[0] for desc in conn.execute(query, params).description]
    df = pd.DataFrame([tuple(row) for row in rows], columns=columns)

    # Build Sankey data
    # Collect unique countries and assign node indices
    countries: list[str] = []
    country_idx: dict[str, int] = {}

    def get_idx(code: int) -> int:
        name = get_country_name(conn, code)
        if name not in country_idx:
            country_idx[name] = len(countries)
            countries.append(name)
        return country_idx[name]

    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []
    colors: list[str] = []
    hover_texts: list[str] = []

    for _, row in df.iterrows():
        src = get_idx(int(row["reporter_code"]))
        tgt = get_idx(int(row["partner_code"]))
        val = max(row["reported_value"] or 0, 1)  # avoid zero-width links
        severity = row["severity_score"] or 0

        sources.append(src)
        targets.append(tgt)
        values.append(val)

        # Color by severity
        if severity >= 80:
            colors.append("rgba(255, 0, 0, 0.6)")
        elif severity >= 60:
            colors.append("rgba(255, 140, 0, 0.5)")
        elif severity >= 40:
            colors.append("rgba(255, 200, 0, 0.4)")
        else:
            colors.append("rgba(100, 149, 237, 0.3)")

        disc = row["discrepancy_pct"]
        disc_str = f"{disc:+.1f}%" if pd.notna(disc) else "N/A"
        hover_texts.append(
            f"Value: ${val:,.0f}<br>"
            f"Discrepancy: {disc_str}<br>"
            f"Severity: {severity}"
        )

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=countries,
            color="#4a90d9",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=colors,
            customdata=hover_texts,
            hovertemplate="%{customdata}<extra></extra>",
        ),
    )])

    fig.update_layout(
        title=f"Trade Flows for HS {commodity}",
        height=max(500, len(countries) * 30),
        template="plotly_white",
        font=dict(size=12),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Legend
    st.markdown(
        "**Color legend:** "
        ":red[Red] = Critical severity (80+) | "
        ":orange[Orange] = High (60-79) | "
        "\U0001f7e1 Yellow = Medium (40-59) | "
        "Blue = Low/Noise"
    )

    # Underlying data
    with st.expander("View underlying data"):
        display_df = df.copy()
        display_df["exporter"] = display_df["reporter_code"].apply(
            lambda c: get_country_name(conn, c)
        )
        display_df["importer"] = display_df["partner_code"].apply(
            lambda c: get_country_name(conn, c)
        )
        show_cols = ["exporter", "importer", "reported_value", "mirror_value",
                     "discrepancy_pct", "severity_score", "priority_tier"]
        st.dataframe(
            display_df[show_cols].rename(columns={
                "exporter": "Exporter", "importer": "Importer",
                "reported_value": "Reported (USD)", "mirror_value": "Mirror (USD)",
                "discrepancy_pct": "Discrepancy %", "severity_score": "Severity",
                "priority_tier": "Tier",
            }),
            use_container_width=True,
            hide_index=True,
        )
        csv_download_button(display_df, filename="sankey_data.csv", key="sankey_csv")
