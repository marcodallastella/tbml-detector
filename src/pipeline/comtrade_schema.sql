-- UN Comtrade Mirror Analysis Schema
-- Designed for bilateral mirror trade analysis: joining Country A's reported
-- exports with Country B's reported imports for the same commodity and period.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Reference Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS countries (
    country_code    INTEGER PRIMARY KEY,  -- UN M49 / Comtrade reporter code
    iso3            TEXT,                  -- ISO 3166-1 alpha-3
    name            TEXT NOT NULL,
    is_group        INTEGER DEFAULT 0,    -- 1 for aggregate areas (e.g. "World", "Areas NES")
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS commodities (
    commodity_code  TEXT PRIMARY KEY,      -- HS code (2/4/6 digit)
    description     TEXT NOT NULL,
    parent_code     TEXT,                  -- parent in HS hierarchy
    hs_level        INTEGER NOT NULL,      -- 2, 4, or 6
    section         TEXT                   -- HS section
);

-- ============================================================================
-- Core Trade Records
-- ============================================================================

-- Each row is one side of a bilateral trade flow as reported by one country.
-- Mirror analysis joins two rows: reporter A exporting to partner B,
-- vs. reporter B importing from partner A, for the same commodity and period.
CREATE TABLE IF NOT EXISTS trade_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identifiers
    reporter_code       INTEGER NOT NULL REFERENCES countries(country_code),
    partner_code        INTEGER NOT NULL REFERENCES countries(country_code),
    commodity_code      TEXT NOT NULL REFERENCES commodities(commodity_code),
    flow_code           TEXT NOT NULL,  -- X=Export, M=Import, XIP=Re-export, MIP=Re-import
    period              TEXT NOT NULL,      -- 'YYYY' (annual) or 'YYYYMM' (monthly)
    frequency           TEXT NOT NULL,      -- 'A' (annual) or 'M' (monthly)

    -- Values (all USD)
    trade_value_usd     REAL,              -- primary monetary value
    cif_value_usd       REAL,              -- CIF value (imports)
    fob_value_usd       REAL,              -- FOB value (exports)

    -- Quantities
    net_weight_kg       REAL,              -- net weight in kilograms
    qty                 REAL,              -- supplementary quantity
    qty_unit_code       INTEGER,           -- unit code for supplementary quantity
    qty_unit_desc       TEXT,              -- unit description

    -- Flags and metadata
    is_re_export        INTEGER DEFAULT 0, -- 1 if flow_code in (XIP, MIP) or flagged
    is_confidential     INTEGER DEFAULT 0, -- 1 if value suppressed for confidentiality
    customs_code        TEXT,              -- customs procedure code
    mot_code            INTEGER,           -- mode of transport code
    mot_desc            TEXT,              -- mode of transport description

    -- Data provenance
    classification      TEXT,              -- 'HS' or 'SITC', etc.
    ref_year            INTEGER,           -- reference year from API
    dataset_code        TEXT,              -- Comtrade dataset identifier
    raw_json            TEXT,              -- original API response row (JSON)

    -- Record management
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),

    -- Unique constraint: one record per reporter/partner/commodity/flow/period
    UNIQUE(reporter_code, partner_code, commodity_code, flow_code, period)
);

-- ============================================================================
-- Cleaned / Normalized Records
-- ============================================================================

-- Cleaned version of trade_records with normalization applied.
-- Links back to raw record for audit trail.
CREATE TABLE IF NOT EXISTS cleaned_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_record_id       INTEGER NOT NULL REFERENCES trade_records(id),

    reporter_code       INTEGER NOT NULL,
    partner_code        INTEGER NOT NULL,
    commodity_code      TEXT NOT NULL,
    flow_code           TEXT NOT NULL,  -- X=Export, M=Import, XIP=Re-export, MIP=Re-import
    period              TEXT NOT NULL,
    frequency           TEXT NOT NULL,

    -- Normalized values
    trade_value_usd     REAL,
    fob_value_usd       REAL,              -- FOB-adjusted value (CIF->FOB for imports)
    net_weight_kg       REAL,
    qty_normalized      REAL,              -- quantity in standardized unit
    qty_unit_normalized TEXT,              -- standardized unit label
    unit_price_usd      REAL,              -- trade_value_usd / qty or weight

    -- Quality flags
    is_re_export        INTEGER DEFAULT 0,
    is_confidential     INTEGER DEFAULT 0,
    has_quantity         INTEGER DEFAULT 1, -- 0 if qty data missing
    has_weight           INTEGER DEFAULT 1, -- 0 if weight data missing
    quality_score       REAL,              -- 0.0-1.0 data quality indicator
    cleaning_notes      TEXT,              -- what normalization was applied

    cleaned_at          TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(reporter_code, partner_code, commodity_code, flow_code, period)
);

-- ============================================================================
-- Mirror Pairs View
-- ============================================================================

-- This view is the core of mirror analysis. It joins export records from
-- reporter A with import records from reporter B for the same commodity
-- and period, producing one row per bilateral mirror pair.
CREATE VIEW IF NOT EXISTS mirror_pairs AS
SELECT
    e.id                AS export_record_id,
    i.id                AS import_record_id,
    e.reporter_code     AS exporter_code,
    e.partner_code      AS importer_code,
    e.commodity_code,
    e.period,
    e.frequency,

    -- Exporter-reported values
    e.trade_value_usd   AS export_value_usd,
    e.fob_value_usd     AS export_fob_usd,
    e.net_weight_kg      AS export_weight_kg,
    e.qty_normalized     AS export_qty,
    e.unit_price_usd     AS export_unit_price,

    -- Importer-reported values
    i.trade_value_usd    AS import_value_usd,
    i.fob_value_usd      AS import_fob_usd,
    i.net_weight_kg       AS import_weight_kg,
    i.qty_normalized      AS import_qty,
    i.unit_price_usd      AS import_unit_price,

    -- Discrepancy metrics (positive = importer reports more)
    i.trade_value_usd - e.trade_value_usd AS value_gap_usd,
    CASE
        WHEN e.trade_value_usd > 0 AND i.trade_value_usd > 0
        THEN (i.trade_value_usd - e.trade_value_usd) / e.trade_value_usd
        ELSE NULL
    END AS value_gap_ratio,
    CASE
        WHEN e.fob_value_usd > 0 AND i.fob_value_usd > 0
        THEN (i.fob_value_usd - e.fob_value_usd) / e.fob_value_usd
        ELSE NULL
    END AS fob_gap_ratio,
    CASE
        WHEN e.net_weight_kg > 0 AND i.net_weight_kg > 0
        THEN (i.net_weight_kg - e.net_weight_kg) / e.net_weight_kg
        ELSE NULL
    END AS weight_gap_ratio,

    -- Quality indicators
    e.is_re_export       AS export_is_re_export,
    i.is_re_export       AS import_is_re_export,
    e.is_confidential    AS export_is_confidential,
    i.is_confidential    AS import_is_confidential,
    e.quality_score      AS export_quality,
    i.quality_score      AS import_quality

FROM cleaned_records e
JOIN cleaned_records i
    ON  e.partner_code    = i.reporter_code
    AND e.reporter_code   = i.partner_code
    AND e.commodity_code  = i.commodity_code
    AND e.period          = i.period
    AND e.frequency       = i.frequency
WHERE e.flow_code IN ('X', 'XIP')   -- export or re-export
  AND i.flow_code IN ('M', 'MIP')   -- import or re-import
  AND e.partner_code NOT IN (0, 97, 899)   -- exclude World, EU aggregate, Areas NES
  AND i.partner_code NOT IN (0, 97, 899)
  AND e.is_confidential = 0   -- exclude confidential-suppressed records
  AND i.is_confidential = 0;

-- ============================================================================
-- Phantom Shipments View
-- ============================================================================

-- Exports reported by A to B with no matching import reported by B from A.
CREATE VIEW IF NOT EXISTS phantom_exports AS
SELECT
    e.id                AS record_id,
    e.reporter_code     AS exporter_code,
    e.partner_code      AS importer_code,
    e.commodity_code,
    e.period,
    e.trade_value_usd,
    e.net_weight_kg
FROM cleaned_records e
LEFT JOIN cleaned_records i
    ON  e.partner_code    = i.reporter_code
    AND e.reporter_code   = i.partner_code
    AND e.commodity_code  = i.commodity_code
    AND e.period          = i.period
    AND e.frequency       = i.frequency
    AND i.flow_code IN (1, 4)
WHERE e.flow_code IN ('X', 'XIP')
  AND e.partner_code NOT IN (0, 97, 899)
  AND e.is_confidential = 0
  AND i.id IS NULL;

-- Imports reported by B from A with no matching export reported by A to B.
CREATE VIEW IF NOT EXISTS phantom_imports AS
SELECT
    i.id                AS record_id,
    i.partner_code      AS exporter_code,
    i.reporter_code     AS importer_code,
    i.commodity_code,
    i.period,
    i.trade_value_usd,
    i.net_weight_kg
FROM cleaned_records i
LEFT JOIN cleaned_records e
    ON  i.partner_code    = e.reporter_code
    AND i.reporter_code   = e.partner_code
    AND i.commodity_code  = e.commodity_code
    AND i.period          = e.period
    AND i.frequency       = e.frequency
    AND e.flow_code IN ('X', 'XIP')
WHERE i.flow_code IN ('M', 'MIP')
  AND i.partner_code NOT IN (0, 97, 899)
  AND i.is_confidential = 0
  AND e.id IS NULL;

-- ============================================================================
-- Pipeline Tracking
-- ============================================================================

-- Track which data has been fetched so we can do incremental updates.
CREATE TABLE IF NOT EXISTS fetch_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_code   INTEGER NOT NULL,
    partner_code    INTEGER,           -- NULL = all partners
    commodity_code  TEXT,              -- NULL = all commodities
    flow_code       INTEGER,
    period          TEXT NOT NULL,
    frequency       TEXT NOT NULL,
    record_count    INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'success',  -- 'success', 'error', 'partial'
    error_message   TEXT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);

-- ============================================================================
-- Indexes for Mirror Analysis Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_trade_reporter_partner
    ON trade_records(reporter_code, partner_code);

CREATE INDEX IF NOT EXISTS idx_trade_commodity_period
    ON trade_records(commodity_code, period);

CREATE INDEX IF NOT EXISTS idx_trade_flow
    ON trade_records(flow_code);

CREATE INDEX IF NOT EXISTS idx_trade_period
    ON trade_records(period);

CREATE INDEX IF NOT EXISTS idx_cleaned_mirror
    ON cleaned_records(reporter_code, partner_code, commodity_code, flow_code, period);

CREATE INDEX IF NOT EXISTS idx_cleaned_flow_period
    ON cleaned_records(flow_code, period);

CREATE INDEX IF NOT EXISTS idx_fetch_log_lookup
    ON fetch_log(reporter_code, partner_code, commodity_code, period);
