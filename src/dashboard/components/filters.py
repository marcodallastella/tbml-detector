"""Shared filter components for the dashboard.

Provides sidebar filter widgets that are reused across multiple views.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

# Ensure src is on path when loaded by Streamlit
_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
from src.pipeline.country_codes import get_country_name as _name, label as _label

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "comtrade.db"


def get_db_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Get a cached SQLite connection.

    Uses Streamlit's session state to reuse the connection across reruns.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path = str(db_path)

    if "db_conn" not in st.session_state or st.session_state.get("db_path") != db_path:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        st.session_state["db_conn"] = conn
        st.session_state["db_path"] = db_path

    return st.session_state["db_conn"]


def _query_distinct(conn: sqlite3.Connection, column: str, table: str) -> list[Any]:
    """Query distinct values from a column."""
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}"  # noqa: S608
    ).fetchall()
    return [row[0] for row in rows]


def severity_tier_filter(key: str = "tier_filter") -> str | None:
    """Severity tier dropdown. Returns selected tier or None for all."""
    tiers = ["All", "critical", "high", "medium", "low", "noise"]
    labels = {
        "All": "All tiers",
        "critical": "Critical (80-100)",
        "high": "High (60-79)",
        "medium": "Medium (40-59)",
        "low": "Low (20-39)",
        "noise": "Noise (0-19)",
    }
    selected = st.selectbox(
        "Severity tier",
        tiers,
        format_func=lambda t: labels.get(t, t),
        key=key,
        help="Filter results by investigative priority. Critical means the "
             "discrepancy is large, persistent, and involves risky corridors.",
    )
    return None if selected == "All" else selected


def min_severity_slider(key: str = "min_severity") -> int:
    """Minimum severity score slider."""
    return st.slider(
        "Minimum severity score",
        min_value=0,
        max_value=100,
        value=20,
        key=key,
        help="Severity combines discrepancy size, statistical unusualness, "
             "how long it has persisted, and risk profiles of the countries "
             "and commodities involved. Higher = more suspicious.",
    )


def country_filter(
    conn: sqlite3.Connection,
    label: str = "Country",
    key: str = "country_filter",
    table: str = "analysis_results",
    column: str = "reporter_code",
) -> int | None:
    """Country selector. Returns country code or None for all."""
    codes = _query_distinct(conn, column, table)
    name_map = {c: _label(c) for c in codes}

    options = [None] + codes
    selected = st.selectbox(
        label,
        options,
        format_func=lambda c: "All countries" if c is None else name_map.get(c, str(c)),
        key=key,
    )
    return selected


def commodity_filter(
    conn: sqlite3.Connection,
    key: str = "commodity_filter",
) -> str | None:
    """Commodity code selector. Returns HS code or None for all."""
    rows = conn.execute(
        "SELECT DISTINCT commodity_code, commodity_description "
        "FROM analysis_results ORDER BY commodity_code"
    ).fetchall()

    if not rows:
        st.info("No analysis results available yet.")
        return None

    options: list[str | None] = [None] + [row["commodity_code"] for row in rows]
    desc_map = {row["commodity_code"]: row["commodity_description"] or "" for row in rows}

    selected = st.selectbox(
        "Commodity (HS code)",
        options,
        format_func=lambda c: "All commodities" if c is None else f"{c} — {desc_map.get(c, '')}",
        key=key,
        help="HS (Harmonized System) codes classify traded goods. "
             "2-digit = broad category, 6-digit = specific product.",
    )
    return selected


def period_filter(
    conn: sqlite3.Connection,
    key: str = "period_filter",
) -> str | None:
    """Period selector. Returns period string or None for all."""
    periods = _query_distinct(conn, "period", "analysis_results")
    options: list[str | None] = [None] + periods
    selected = st.selectbox(
        "Time period",
        options,
        format_func=lambda p: "All periods" if p is None else str(p),
        key=key,
    )
    return selected


def corridor_filter(
    conn: sqlite3.Connection,
    key_prefix: str = "corridor",
) -> tuple[int | None, int | None]:
    """Reporter + partner corridor filter. Returns (reporter, partner) codes."""
    col1, col2 = st.columns(2)
    with col1:
        reporter = country_filter(
            conn,
            label="Reporting country (exporter)",
            key=f"{key_prefix}_reporter",
            column="reporter_code",
        )
    with col2:
        partner = country_filter(
            conn,
            label="Partner country (importer)",
            key=f"{key_prefix}_partner",
            column="partner_code",
        )
    return reporter, partner


def get_country_name(conn: sqlite3.Connection, code: int) -> str:
    """Look up a human-readable country name from its code."""
    return _name(code, default=str(code))
