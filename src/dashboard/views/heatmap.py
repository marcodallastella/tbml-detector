"""Heatmap view: country-pair matrix colored by discrepancy severity.

Shows a matrix of exporter-importer pairs with cells colored by the
average or maximum severity score for a selected commodity and time period.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.components.export import csv_download_button
from src.dashboard.components.filters import (
    commodity_filter,
    get_country_name,
    min_severity_slider,
    period_filter,
)


def render(conn: sqlite3.Connection) -> None:
    """Render the heatmap view."""
    st.header("Discrepancy Heatmap")
    st.caption(
        "This matrix shows country pairs colored by how suspicious their "
        "trade discrepancies are. Darker cells indicate higher severity. "
        "Use this to spot which bilateral corridors deserve attention."
    )

    # Filters
    with st.sidebar:
        st.subheader("Filters")
        commodity = commodity_filter(conn, key="heatmap_commodity")
        period = period_filter(conn, key="heatmap_period")
        min_sev = min_severity_slider(key="heatmap_min_sev")
        agg_method = st.radio(
            "Aggregation",
            ["Maximum severity", "Average severity"],
            key="heatmap_agg",
            help="How to combine multiple flows between the same country pair: "
                 "maximum shows the worst case, average shows the overall pattern.",
        )

    # Build query
    agg_func = "MAX" if agg_method == "Maximum severity" else "AVG"
    query = f"""
        SELECT reporter_code, partner_code,
               {agg_func}(severity_score) as severity,
               COUNT(*) as flow_count,
               {agg_func}(discrepancy_pct) as avg_discrepancy
        FROM analysis_results
        WHERE severity_score >= ?
    """
    params: list = [min_sev]

    if commodity:
        query += " AND commodity_code = ?"
        params.append(commodity)
    if period:
        query += " AND period = ?"
        params.append(period)

    query += " GROUP BY reporter_code, partner_code ORDER BY severity DESC"

    rows = conn.execute(query, params).fetchall()

    if not rows:
        st.info("No data matches your filters. Try adjusting the commodity, period, or severity threshold.")
        return

    columns = [desc[0] for desc in conn.execute(query, params).description]
    df = pd.DataFrame([tuple(row) for row in rows], columns=columns)

    # Resolve country names
    df["exporter"] = df["reporter_code"].apply(lambda c: get_country_name(conn, c))
    df["importer"] = df["partner_code"].apply(lambda c: get_country_name(conn, c))

    # Pivot for heatmap
    # Limit to top N countries to keep the heatmap readable
    max_countries = st.slider(
        "Maximum countries to display",
        min_value=5, max_value=50, value=20,
        key="heatmap_max",
        help="Limit the matrix size to the most active countries.",
    )

    # Get top countries by number of appearances
    all_countries = pd.concat([df["exporter"], df["importer"]]).value_counts()
    top_countries = all_countries.head(max_countries).index.tolist()

    filtered = df[df["exporter"].isin(top_countries) & df["importer"].isin(top_countries)]

    if filtered.empty:
        st.info("Not enough data for a heatmap with current filters.")
        return

    pivot = filtered.pivot_table(
        values="severity",
        index="exporter",
        columns="importer",
        aggfunc="max",
        fill_value=0,
    )

    fig = px.imshow(
        pivot,
        color_continuous_scale="YlOrRd",
        aspect="auto",
        labels=dict(x="Importer", y="Exporter", color="Severity"),
        title="Discrepancy Severity by Country Pair",
    )

    fig.update_layout(
        height=max(400, len(pivot) * 25 + 150),
        template="plotly_white",
        xaxis=dict(tickangle=45),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Summary stats
    st.subheader("Top Corridors")
    top_df = df.head(20)[["exporter", "importer", "severity", "flow_count", "avg_discrepancy"]].copy()
    top_df.columns = ["Exporter", "Importer", "Severity", "Flows", "Avg Discrepancy %"]
    top_df["Severity"] = top_df["Severity"].apply(lambda v: f"{v:.0f}")
    top_df["Avg Discrepancy %"] = top_df["Avg Discrepancy %"].apply(
        lambda v: f"{v:+.1f}%" if pd.notna(v) else "N/A"
    )
    st.dataframe(top_df, use_container_width=True, hide_index=True)

    # Export
    st.divider()
    csv_download_button(df, filename="heatmap_data.csv", key="heatmap_csv")
