# Comtrade Mirror

A trade-based money laundering (TBML) detection tool for investigative journalists.
Performs **mirror analysis** on UN Comtrade bilateral trade flow data: comparing
what Country A reports as exports to Country B against what Country B reports as
imports from Country A. Statistically significant discrepancies can indicate
over/under-invoicing, phantom shipments, and other TBML schemes.

## What is Mirror Analysis?

Every international trade transaction is reported twice: once by the exporter and
once by the importer. In legitimate trade, these two reports should broadly agree
(after adjusting for shipping costs and timing). When they diverge significantly,
it may indicate that someone is manipulating invoices to move money across borders
under the cover of trade.

This tool automates that comparison across thousands of bilateral trade corridors,
applies statistical tests to distinguish suspicious discrepancies from normal
noise, and ranks findings by investigative priority.

## Architecture

```
src/
  pipeline/               Data ingestion and storage
    comtrade_api.py        UN Comtrade API client (rate-limited, with retry)
    cleaning.py            Data cleaning and CIF/FOB normalization
    storage.py             SQLite storage layer with mirror pair views

  analysis/               Anomaly detection engine
    mirror.py              Core discrepancy computation (D_rel, D_abs, D_log)
    anomaly.py             Z-score, Benford's law, asymmetry, correlation tests
    scoring.py             Severity scoring rubric (0-100 composite score)
    unit_price.py          Unit price benchmark comparison

  dashboard/              Streamlit investigative dashboard
    app.py                 Main entry point (streamlit run src/dashboard/app.py)
    views/                 Dashboard pages
      alert_table.py       Ranked alert table with filtering
      mirror_comparison.py Side-by-side export vs. import comparison
      time_series.py       Temporal discrepancy trends
      heatmap.py           Country-pair severity matrix
      sankey.py            Flow diagrams for trade corridor visualization
      country_profile.py   All anomalies for a selected country
    components/            Shared UI components (filters, tooltips, export)

  cli.py                  Command-line interface

config/
  analysis.yaml           All detection thresholds and adjustment factors

data/
  comtrade.db             SQLite database (created on first fetch)

docs/
  detection-spec.md       Technical specification for the detection engine
  tbml-typologies.md      TBML scheme catalogue with mirror data signatures
  jurisdiction-risk.md    Country/territory risk profiles and classifications
```

## Prerequisites

- Python 3.11 or later
- A UN Comtrade API subscription key (free tier available at
  https://comtradeapi.un.org/)

## Installation

```bash
git clone <repository-url>
cd comtrade-mirror
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your Comtrade API key in the `.env` file at the project root:

```bash
echo 'COMTRADE_API_KEY=your-subscription-key' > .env
```

The CLI loads `.env` automatically via `python-dotenv`. Alternatively, export the
variable directly:

```bash
export COMTRADE_API_KEY="your-subscription-key"
```

Get a free API key at https://comtradeapi.un.org/.

## Quick Start

```bash
# 1. Scan all gold exports from Peru across all partners, 2023-2025
#    (automatically fetches both sides of every corridor for mirror analysis)
python -m src.cli scan --reporter 604 --commodity 7108 --period 2023,2024,2025

# 2. Run the analysis engine to score discrepancies
python -m src.cli analyze --commodity 7108

# 3. Launch the dashboard to explore results
.venv/bin/streamlit run src/dashboard/app.py
```

`scan` collects both the reporter's view and every partner's mirror view in one
command, then `analyze` computes discrepancies and scores them. The dashboard
reads from the database (`data/comtrade.db`).

## CLI Reference

All commands are run from the project root via `python -m src.cli` or
`python src/cli.py`.

### `fetch` -- Fetch data for specific country pairs

```bash
python src/cli.py fetch \
  --reporter 842         \  # US (UN M49 code)
  --partner 170          \  # Colombia
  --commodity 7108       \  # Gold
  --period 2022,2023     \
  --frequency A          \  # A=annual, M=monthly
  --skip-fetched            # skip already-downloaded combinations
```

| Flag | Required | Description |
|---|---|---|
| `--reporter` | Yes | Reporter country code(s), comma-separated (UN M49) |
| `--partner` | Yes | Partner country code(s), comma-separated |
| `--commodity` | No | HS commodity code(s). Omit for all commodities |
| `--period` | No | Period(s) as YYYY or YYYYMM. Omit for latest available |
| `--frequency` | No | `A` (annual, default) or `M` (monthly) |
| `--skip-fetched` | No | Skip combinations already in the database |
| `--db` | No | Path to SQLite database (default: `data/comtrade.db`) |

### `scan` -- Broad scan across all partners for a country

The primary command for mirror analysis investigations. Collects **both sides**
of every trade corridor automatically:

1. **Pass 1** -- Fetches all trade flows reported by the target country across
   all its partners (the reporter's own view).
2. **Pass 2** -- For each partner identified in pass 1, fetches that partner's
   reported trade with the target country (the mirror side).

This two-pass approach means a single `scan` command gathers all the data needed
to compute mirror discrepancies without any manual follow-up fetches.

```bash
# All gold exports from Peru to all partners, 2023-2025
python -m src.cli scan --reporter 604 --commodity 7108 --period 2023,2024,2025

# All precious metals from UK, annual
python -m src.cli scan --reporter 826 --commodity 71 --period 2023
```

| Flag | Required | Description |
|---|---|---|
| `--reporter` | Yes | Reporter country code (single, UN M49) |
| `--commodity` | No | HS code(s) to filter, comma-separated |
| `--period` | No | Period(s) as YYYY or YYYYMM, comma-separated |
| `--frequency` | No | `A` (annual, default) or `M` (monthly) |
| `--db` | No | Path to SQLite database (default: `data/comtrade.db`) |

**Note:** Pass 2 makes one API call per partner country. For broad commodities
with many trade partners this can be hundreds of calls — the built-in rate
limiter handles this automatically but the scan may take several minutes.

### `update` -- Refresh all previously fetched corridors

```bash
python src/cli.py update
```

Re-fetches data for every reporter/partner/commodity combination previously
downloaded. Useful for periodic refresh to catch revised data.

### `export` -- Export data to CSV

```bash
# Export cleaned records
python src/cli.py export --output results.csv --table cleaned_records

# Export mirror pairs view
python src/cli.py export --output mirrors.csv --table mirror_pairs

# Export phantom shipments
python src/cli.py export --output phantoms.csv --table phantom_exports

# Custom SQL query
python src/cli.py export --output custom.csv \
  --query "SELECT * FROM mirror_pairs WHERE ABS(value_gap_usd) > 1000000"
```

| Flag | Required | Description |
|---|---|---|
| `--output` | Yes | Output CSV file path |
| `--table` | No | Table/view to export: `trade_records`, `cleaned_records`, `mirror_pairs`, `phantom_exports`, `phantom_imports` |
| `--query` | No | Custom SQL query (overrides `--table`) |

## Configuration

All detection parameters are in `config/analysis.yaml`. Key settings:

### CIF/FOB Adjustment

Controls the expected shipping cost markup applied before flagging discrepancies.
Default ratios by transport mode range from 1.02 (pipeline) to 1.15 (air freight).

```yaml
cif_fob:
  default_ratio: 1.07
  ratios:
    maritime_bulk: 1.07
    air: 1.15
    land: 1.03
```

### Detection Thresholds

```yaml
min_d_rel_to_flag: 0.10    # 10% minimum discrepancy to flag
z_score:
  thresholds:
    elevated: 2.0           # warrants review
    high: 3.0               # likely anomalous
    extreme: 5.0            # strong investigative signal
```

### Severity Scoring

Five components (0-20 each) sum to a 0-100 composite score:

1. **Magnitude** -- size of the discrepancy after normalization
2. **Statistical anomaly** -- z-score against historical corridor baseline
3. **Persistence** -- consecutive periods with significant discrepancy
4. **Corridor risk** -- jurisdiction risk factors (secrecy, FTZ, narcotics routes)
5. **Commodity risk** -- inherent TBML risk of the traded commodity

Priority tiers: Critical (80-100), High (60-79), Medium (40-59), Low (20-39),
Noise (0-19).

See `docs/detection-spec.md` for the complete specification.

## Dashboard

Launch the investigative dashboard:

```bash
streamlit run src/dashboard/app.py
```

The dashboard opens in your browser at `http://localhost:8501`. It reads from the
SQLite database (default: `data/comtrade.db`) and requires the analysis engine to
have been run first so that the `analysis_results` table is populated.

### Views

The dashboard provides six views, selectable from the sidebar:

**Alert Table** -- The primary investigation view. Shows a ranked list of all
flagged trade flows sorted by severity score. Filter by priority tier (critical,
high, medium), exporting/importing country, commodity, and time period. Each row
can be expanded to show the scoring breakdown and triggered typology flags. Use
this as your starting point to identify leads.

**Mirror Comparison** -- Side-by-side comparison of what the exporter reported
vs. what the importer reported for a specific corridor. Shows both value and
quantity discrepancies. Useful for drilling into a specific alert to understand
the nature and magnitude of the gap.

**Time Series** -- Plots discrepancy trends over time for a selected corridor.
Shows whether a discrepancy is a one-off or a persistent pattern. Overlays
z-score thresholds so you can see when a corridor shifted from normal to
anomalous. Critical for establishing the persistence component of the severity
score.

**Heatmap** -- A matrix of country pairs colored by average or maximum severity
score for a selected commodity and period. Useful for spotting geographic clusters
of suspicious activity -- e.g., identifying that gold exports from a particular
region all show elevated discrepancies.

**Flow Diagram** -- Sankey diagram showing trade flow volumes between countries for
a selected commodity. Visualizes the path from origin through transit hubs to
destination. Helps identify carousel/round-tripping patterns where goods flow in
circles through intermediary jurisdictions.

**Country Profile** -- Select a country and see all its flagged corridors and
commodities aggregated. View the country as exporter, importer, or both. Useful
when investigating a specific jurisdiction -- see all anomalies at a glance rather
than searching corridor by corridor.

### Exporting Results

Every view includes a **Download as CSV** button that exports the currently
filtered data. The Mirror Comparison and Country Profile views also offer a
**Corridor Brief** download -- a structured plain-text summary suitable for
editorial presentations and source meetings.

### Tips for Journalists

- Start with the **Alert Table** filtered to "critical" and "high" tiers. These
  are the flows where the statistical signal is strongest.
- Check the **Time Series** for persistence. A single year of discrepancy may be
  a data artifact; three or more consecutive years in the same direction is a much
  stronger signal.
- Cross-reference with the **Country Profile** to see if a flagged country shows
  anomalies across multiple commodities or just one.
- Watch for the `re-export corridor` and `confidential flow involved` notes in the
  alert details -- these are common legitimate explanations to rule out first.
- Use the corridor brief export to document your findings before reaching out to
  sources.
- Remember: these are statistical indicators, not proof. The sidebar displays a
  reminder that discrepancies may have legitimate explanations.

## Data Sources and Known Limitations

### Data Source

All trade data comes from the [UN Comtrade](https://comtradeapi.un.org/) database,
the most comprehensive source of international merchandise trade statistics. Data
is reported by national customs authorities and compiled by the UN Statistics
Division.

### Known Limitations

Mirror analysis is one investigative lens among several. The following patterns
are **not detectable** through Comtrade mirror analysis alone:

- **Services-based value transfer**: Parallel services invoices (consulting fees,
  IP licensing) that explain monetary transfers while goods flows appear normal.
  Comtrade covers goods trade only.
- **Intra-firm transfer pricing**: Multinational corporations may use transfer
  pricing that creates persistent mirror discrepancies but falls within OECD
  arm's-length guidelines.
- **Informal value transfer (hawala)**: Leaves no trade data footprint.
- **Physical smuggling**: Goods that bypass customs produce no records on either
  side.

### Data Quality Caveats

- **Non-reporting countries**: ~15 countries chronically do not report to Comtrade.
  Discrepancies involving these jurisdictions may simply reflect missing data.
  See `docs/jurisdiction-risk.md` for the full list.
- **Confidential trade suppression**: Many countries suppress specific commodity
  flows for commercial or national security confidentiality.
- **CIF/FOB asymmetry**: Exporters report FOB, importers report CIF. A 5-15%
  positive discrepancy is normal and expected. The tool adjusts for this, but the
  adjustment is an estimate.
- **Re-export hubs**: Hong Kong, Singapore, Netherlands, UAE, and other entrepot
  economies create structural discrepancies. The tool flags and down-weights these
  but cannot fully resolve them.
- **HS code classification differences**: The same product may be classified under
  different codes by different countries, creating apparent discrepancies.
- **EU aggregate reporting**: Some countries report trade with the EU as a single
  entity rather than individual member states.

For the complete list of data quality issues, see `docs/detection-spec.md`
Section 5.

## Documentation

| Document | Description |
|---|---|
| `docs/detection-spec.md` | Complete technical specification: formulas, normalization rules, statistical methods, scoring rubric, data quality issues, advanced detection methods |
| `docs/tbml-typologies.md` | TBML scheme catalogue: 14 typology patterns with mirror data signatures, detection thresholds, and false positive sources |
| `docs/jurisdiction-risk.md` | Country/territory risk profiles: FTZs, secrecy jurisdictions, weak customs reporters, commodity-specific transit hubs |

## Testing

```bash
pip install pytest pytest-cov
pytest tests/ -v
```

## Data Attribution

All trade data is sourced from [UN Comtrade](https://comtrade.un.org/). When
publishing findings based on this tool, always attribute the underlying data to
UN Comtrade. Do not redistribute raw trade data files. The pipeline's incremental
fetch design downloads only the data needed for your investigation.

## Disclaimer

This project is intended for use by investigative journalists and researchers.
Findings from this tool are statistical indicators, not evidence of wrongdoing.
Always corroborate with additional sources -- corporate registry data, shipping
records, financial disclosures, and local investigative reporting -- before
publication.
