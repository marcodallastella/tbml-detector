"""Mirror Trade Analysis Dashboard.

Main Streamlit entry point. Connects views and navigation for the
investigative journalist interface.

Run with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports resolve
# when Streamlit runs this file directly as a script.
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from src.dashboard.components.filters import get_db_connection
from src.dashboard.views import (
    alert_table,
    country_profile,
    heatmap,
    mirror_comparison,
    sankey,
    time_series,
)

# Page configuration
st.set_page_config(
    page_title="Mirror Trade Analysis",
    page_icon="\U0001f50d",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a clean, professional look
st.markdown("""
<style>
    /* Clean header styling */
    .stApp header {
        background-color: transparent;
    }
    /* Tighter metric spacing */
    [data-testid="stMetricValue"] {
        font-size: 1.4rem;
    }
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
    }
    /* Data table styling */
    .stDataFrame {
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


def main() -> None:
    """Main dashboard application."""
    # Sidebar navigation
    st.sidebar.title("Mirror Trade Analysis")
    st.sidebar.caption(
        "Investigating trade discrepancies between bilateral partners "
        "to surface potential trade-based money laundering indicators."
    )

    # Database path configuration
    default_db = Path(__file__).resolve().parent.parent.parent / "data" / "comtrade.db"
    db_path = st.sidebar.text_input(
        "Database path",
        value=str(default_db),
        help="Path to the SQLite database with analysis results.",
    )

    # Check database exists
    if not Path(db_path).exists():
        st.error(
            f"Database not found at `{db_path}`. "
            "Run the data pipeline first to fetch and analyze trade data. "
            "See the README for instructions."
        )
        return

    conn = get_db_connection(db_path)

    # Verify analysis_results table exists
    try:
        conn.execute("SELECT COUNT(*) FROM analysis_results").fetchone()
    except sqlite3.OperationalError:
        st.error(
            "The analysis_results table does not exist in the database. "
            "Run the analysis engine first to generate results."
        )
        return

    st.sidebar.divider()

    # Navigation
    pages = {
        "Alert Table": ("Ranked list of flagged trade flows", alert_table),
        "Mirror Comparison": ("Side-by-side export vs. import values", mirror_comparison),
        "Time Series": ("Discrepancy trends over time", time_series),
        "Heatmap": ("Country-pair severity matrix", heatmap),
        "Flow Diagram": ("Sankey diagram of trade flows", sankey),
        "Country Profile": ("All anomalies for a selected country", country_profile),
    }

    selected_page = st.sidebar.radio(
        "View",
        list(pages.keys()),
        format_func=lambda p: f"{p}",
        key="nav",
    )

    page_desc, page_module = pages[selected_page]

    st.sidebar.divider()

    # Quick stats in sidebar
    try:
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN priority_tier = 'critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN priority_tier = 'high' THEN 1 ELSE 0 END) as high,
                COUNT(DISTINCT reporter_code || '-' || partner_code) as corridors,
                COUNT(DISTINCT commodity_code) as commodities
            FROM analysis_results
            WHERE severity_score >= 20
        """).fetchone()

        st.sidebar.markdown("**Quick Stats** (severity >= 20)")
        st.sidebar.markdown(
            f"- {stats[0]} flagged flows\n"
            f"- {stats[1]} critical, {stats[2]} high\n"
            f"- {stats[3]} corridors\n"
            f"- {stats[4]} commodities"
        )
    except sqlite3.OperationalError:
        pass

    st.sidebar.divider()
    st.sidebar.caption(
        "This tool surfaces statistical anomalies in officially reported "
        "trade data. Discrepancies may have legitimate explanations. "
        "Use these findings as a starting point for investigation, "
        "not as proof of wrongdoing."
    )

    # Render selected page
    page_module.render(conn)


if __name__ == "__main__":
    main()
