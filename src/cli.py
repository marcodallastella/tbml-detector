"""CLI for UN Comtrade mirror analysis data pipeline.

Data source: UN Comtrade (https://comtrade.un.org/).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import sys

from dotenv import load_dotenv

# Ensure project root is on sys.path so src.* imports resolve
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Load .env from project root before any API client initialization
load_dotenv(_project_root / ".env")

from src.pipeline import ComtradeAPI, TradeCleaner, TradeStorage
from src.pipeline.country_codes import resolve_code
from src.analysis.mirror import MirrorAnalyzer
from src.analysis.anomaly import AnomalyDetector
from src.analysis.scoring import SeverityScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch data for specific country pairs and commodity codes."""
    api = ComtradeAPI()
    cleaner = TradeCleaner()
    storage = TradeStorage(args.db)
    storage.initialize()

    reporters = [resolve_code(c) for c in args.reporter.split(",")]
    partners = [resolve_code(c) for c in args.partner.split(",")]
    commodities = args.commodity.split(",") if args.commodity else None
    periods = args.period.split(",") if args.period else None

    for reporter in reporters:
        for partner in partners:
            if args.skip_fetched and storage.is_fetched(
                reporter, periods[0] if periods else "", partner
            ):
                logger.info("Skipping %d->%d (already fetched)", reporter, partner)
                continue

            logger.info("Fetching bilateral pair: %d <-> %d", reporter, partner)
            try:
                raw_records = api.fetch_bilateral_pair(
                    country_a=reporter,
                    country_b=partner,
                    commodity_code=commodities,
                    period=periods,
                    frequency=args.frequency,
                )

                # Normalize and store raw records
                normalized = [api.normalize_record(r) for r in raw_records]
                raw_count = storage.insert_raw_records(normalized, raw_records)

                # Clean and store
                cleaned = cleaner.clean_records(normalized)
                clean_count = storage.insert_cleaned_records(cleaned)

                # Log the fetch
                for p in (periods or [""]):
                    storage.log_fetch(
                        reporter_code=reporter,
                        partner_code=partner,
                        commodity_code=args.commodity,
                        period=p,
                        frequency=args.frequency,
                        record_count=raw_count,
                    )

                logger.info(
                    "Pair %d<->%d: %d raw, %d cleaned records stored",
                    reporter, partner, raw_count, clean_count,
                )

            except Exception as e:
                logger.error("Error fetching %d<->%d: %s", reporter, partner, e)
                for p in (periods or [""]):
                    storage.log_fetch(
                        reporter_code=reporter,
                        partner_code=partner,
                        period=p,
                        frequency=args.frequency,
                        status="error",
                        error_message=str(e),
                    )

    storage.close()


def cmd_scan(args: argparse.Namespace) -> None:
    """Broad scan across all partners for a given country and commodity.

    Fetches data in two passes to collect both sides of every mirror pair:
    1. Reporter's own view of all its trade flows (all partners).
    2. Each partner's view of its trade with the reporter.

    Both sides are required for mirror analysis. Without pass 2, only flows
    where the partner happens to be the reporter of another record can be
    compared.
    """
    from src.pipeline.comtrade_api import WORLD_CODE, AREAS_NES_CODE

    api = ComtradeAPI()
    cleaner = TradeCleaner()
    storage = TradeStorage(args.db)
    storage.initialize()

    commodities = args.commodity.split(",") if args.commodity else None
    periods = args.period.split(",") if args.period else None

    # --- Pass 1: reporter's own view, one period at a time ---
    # Iterating per period avoids the API returning nothing when one requested
    # period has no data yet (e.g. the current year before data is published).
    logger.info("Pass 1: scanning all partners as reported by %d", args.reporter)
    normalized: list[dict] = []
    pass1_raw = pass1_clean = 0

    for period in (periods or [None]):
        try:
            raw_records = api.scan_all_partners(
                reporter_code=args.reporter,
                commodity_code=commodities,
                period=period,
                frequency=args.frequency,
            )

            if not raw_records:
                logger.info("  Period %s: no data available, skipping", period)
                continue

            period_normalized = [api.normalize_record(r) for r in raw_records]
            normalized.extend(period_normalized)
            pass1_raw += storage.insert_raw_records(period_normalized, raw_records)
            pass1_clean += storage.insert_cleaned_records(cleaner.clean_records(period_normalized))

            storage.log_fetch(
                reporter_code=args.reporter,
                period=period or "",
                frequency=args.frequency,
                record_count=len(raw_records),
            )
            logger.info("  Period %s: %d records", period, len(raw_records))

        except Exception as e:
            logger.error("  Period %s scan error: %s", period, e)

    if not normalized:
        logger.warning("Pass 1 returned no data for any period — aborting")
        storage.close()
        return

    logger.info("Pass 1 complete: %d raw, %d cleaned records", pass1_raw, pass1_clean)

    # --- Pass 2: mirror side — each partner reports its trade with the reporter ---
    # Collect the unique real partner codes seen in pass 1 (skip world/NES aggregates)
    partner_codes = {
        r["partner_code"] for r in normalized
        if r.get("partner_code") not in (WORLD_CODE, AREAS_NES_CODE, None)
    }

    if not partner_codes:
        logger.warning("No individual partners found in pass 1 — skipping mirror fetch")
        storage.close()
        return

    logger.info(
        "Pass 2: fetching mirror data from %d partner countries as reporters",
        len(partner_codes),
    )

    total_raw = total_clean = 0
    for partner in sorted(partner_codes):
        partner_raw = partner_clean = 0
        for period in (periods or [None]):
            try:
                partner_records = api.get_trade_data(
                    reporter_code=partner,
                    partner_code=args.reporter,
                    commodity_code=commodities,
                    period=period,
                    frequency=args.frequency,
                )

                if not partner_records:
                    continue

                p_normalized = [api.normalize_record(r) for r in partner_records]
                partner_raw += storage.insert_raw_records(p_normalized, partner_records)
                partner_clean += storage.insert_cleaned_records(cleaner.clean_records(p_normalized))

                storage.log_fetch(
                    reporter_code=partner,
                    partner_code=args.reporter,
                    commodity_code=args.commodity,
                    period=period or "",
                    frequency=args.frequency,
                    record_count=len(partner_records),
                )

            except Exception as e:
                logger.error("  Partner %d period %s error: %s", partner, period, e)

        if partner_raw:
            logger.info("  Partner %d: %d raw, %d cleaned", partner, partner_raw, partner_clean)
        total_raw += partner_raw
        total_clean += partner_clean

    logger.info("Pass 2 complete: %d raw, %d cleaned records stored", total_raw, total_clean)
    storage.close()


def cmd_update(args: argparse.Namespace) -> None:
    """Update database with the latest available period."""
    api = ComtradeAPI()
    cleaner = TradeCleaner()
    storage = TradeStorage(args.db)
    storage.initialize()

    # Get previously fetched reporters from fetch_log
    rows = storage.conn.execute(
        "SELECT DISTINCT reporter_code, partner_code, commodity_code, frequency "
        "FROM fetch_log WHERE status = 'success'"
    ).fetchall()

    if not rows:
        logger.warning("No previous fetches found. Use 'fetch' or 'scan' first.")
        storage.close()
        return

    for row in rows:
        reporter = row["reporter_code"]
        partner = row["partner_code"]
        commodity = row["commodity_code"]
        freq = row["frequency"]

        logger.info("Updating reporter=%s partner=%s commodity=%s", reporter, partner, commodity)
        try:
            if partner is not None:
                raw_records = api.fetch_bilateral_pair(
                    country_a=reporter,
                    country_b=partner,
                    commodity_code=commodity,
                    frequency=freq,
                )
            else:
                raw_records = api.scan_all_partners(
                    reporter_code=reporter,
                    commodity_code=commodity,
                    frequency=freq,
                )

            normalized = [api.normalize_record(r) for r in raw_records]
            raw_count = storage.insert_raw_records(normalized, raw_records)
            cleaned = cleaner.clean_records(normalized)
            clean_count = storage.insert_cleaned_records(cleaned)

            logger.info("Updated: %d raw, %d cleaned", raw_count, clean_count)

        except Exception as e:
            logger.error("Update error for reporter=%s: %s", reporter, e)

    storage.close()


def cmd_analyze(args: argparse.Namespace) -> None:
    """Run the analysis engine against fetched data and populate analysis_results."""
    db = args.db or str(Path(__file__).resolve().parent.parent / "data" / "comtrade.db")
    analyzer = MirrorAnalyzer(db)
    detector = AnomalyDetector()
    scorer = SeverityScorer(db)
    scorer.initialize_results_table()

    logger.info("Computing mirror discrepancies...")
    discrepancies = analyzer.compute_discrepancies(
        commodity_code=args.commodity or None,
        period=args.period or None,
        min_value_usd=args.min_value,
    )

    if not discrepancies:
        logger.warning("No mirror pairs found. Run 'fetch' or 'scan' first.")
        analyzer.close()
        scorer.close()
        return

    logger.info("Scoring %d discrepancy pairs...", len(discrepancies))
    results = []
    for d in discrepancies:
        history = analyzer.get_corridor_history(
            d.exporter_code, d.importer_code, d.commodity_code
        )
        # Exclude current period from history for z-score baseline
        history_excl = [h for h in history if h.period != d.period]
        anomaly = detector.analyze_corridor(d, history_excl)
        scored = scorer.score_discrepancy(d, anomaly, history_excl)
        results.append(scored)

    count = scorer.store_results(results)
    logger.info("Analysis complete: %d results stored.", count)

    # Print a quick summary
    tiers: dict[str, int] = {}
    for r in results:
        tiers[r.severity.tier] = tiers.get(r.severity.tier, 0) + 1
    for tier in ("critical", "high", "medium", "low", "noise"):
        if tier in tiers:
            logger.info("  %s: %d", tier, tiers[tier])

    analyzer.close()
    scorer.close()


def cmd_export(args: argparse.Namespace) -> None:
    """Export raw or cleaned data to CSV."""
    storage = TradeStorage(args.db)

    table = args.table
    output = Path(args.output)

    if args.query:
        count = storage.export_to_csv(output, query=args.query)
    else:
        count = storage.export_to_csv(output, table=table)

    logger.info("Exported %d rows to %s", count, output)
    storage.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="comtrade-mirror",
        description="UN Comtrade bilateral mirror trade analysis pipeline",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to SQLite database (default: data/comtrade.db)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- fetch --
    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch data for specific country pairs",
    )
    fetch_parser.add_argument(
        "--reporter", required=True,
        help="Reporter country code(s), comma-separated. ISO3 (e.g. USA,GBR) or numeric Comtrade IDs",
    )
    fetch_parser.add_argument(
        "--partner", required=True,
        help="Partner country code(s), comma-separated. ISO3 (e.g. COL,PER) or numeric Comtrade IDs",
    )
    fetch_parser.add_argument(
        "--commodity", default=None,
        help="HS commodity code(s), comma-separated",
    )
    fetch_parser.add_argument(
        "--period", default=None,
        help="Period(s) YYYY or YYYYMM, comma-separated",
    )
    fetch_parser.add_argument(
        "--frequency", default="A", choices=["A", "M"],
        help="Frequency: A=annual, M=monthly (default: A)",
    )
    fetch_parser.add_argument(
        "--skip-fetched", action="store_true",
        help="Skip already-fetched combinations",
    )
    fetch_parser.set_defaults(func=cmd_fetch)

    # -- scan --
    scan_parser = subparsers.add_parser(
        "scan", help="Scan all partners for a country",
    )
    scan_parser.add_argument(
        "--reporter", required=True, type=resolve_code,
        help="Reporter country code: ISO3 (e.g. PER) or numeric Comtrade ID (e.g. 604)",
    )
    scan_parser.add_argument(
        "--commodity", default=None,
        help="HS commodity code(s), comma-separated",
    )
    scan_parser.add_argument(
        "--period", default=None,
        help="Period(s) YYYY or YYYYMM, comma-separated",
    )
    scan_parser.add_argument(
        "--frequency", default="A", choices=["A", "M"],
        help="Frequency: A=annual, M=monthly (default: A)",
    )
    scan_parser.set_defaults(func=cmd_scan)

    # -- analyze --
    analyze_parser = subparsers.add_parser(
        "analyze", help="Run analysis engine and populate analysis_results table",
    )
    analyze_parser.add_argument(
        "--commodity", default=None,
        help="Limit analysis to this HS commodity code",
    )
    analyze_parser.add_argument(
        "--period", default=None,
        help="Limit analysis to this period (YYYY or YYYYMM)",
    )
    analyze_parser.add_argument(
        "--min-value", type=float, default=10_000,
        dest="min_value",
        help="Minimum trade value in USD to include (default: 10000)",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # -- update --
    update_parser = subparsers.add_parser(
        "update", help="Update database with latest period",
    )
    update_parser.set_defaults(func=cmd_update)

    # -- export --
    export_parser = subparsers.add_parser(
        "export", help="Export data to CSV",
    )
    export_parser.add_argument(
        "--output", required=True,
        help="Output CSV file path",
    )
    export_parser.add_argument(
        "--table", default="cleaned_records",
        choices=["trade_records", "cleaned_records", "mirror_pairs",
                 "phantom_exports", "phantom_imports"],
        help="Table or view to export (default: cleaned_records)",
    )
    export_parser.add_argument(
        "--query", default=None,
        help="Custom SQL query to export (overrides --table)",
    )
    export_parser.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
