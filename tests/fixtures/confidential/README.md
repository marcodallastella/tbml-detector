# Confidential Flows Case

## Scenario

Several major commodity corridors where one side's data is suppressed due to
confidentiality rules. Many countries suppress bilateral trade data for strategic
commodities (petroleum, minerals, defense-related goods) when a small number of
firms dominate the trade, to prevent disclosure of individual company activities.

This fixture covers three patterns of confidential suppression:

1. **US crude oil imports from Saudi Arabia**: US reports trade_value = 0 with
   empty quantities (confidential suppression). Saudi Arabia reports large exports.
2. **Australian iron ore exports to China**: Australia reports trade_value = 0 with
   empty quantities. China reports massive imports.
3. **Canadian crude oil exports to US**: Canada reports NULL/empty for all fields.
   US reports large imports.

## Data Structure

- **US <- Saudi Arabia (crude oil)**: Saudi reports $12.5B-$24.5B/yr exports.
  US reports 0 (suppressed). This is NOT zero trade — US imports massive amounts
  of Saudi crude oil. The 0 is a confidentiality marker.
- **Australia -> China (iron ore)**: Australia reports 0 (suppressed). China
  reports $68B-$95B/yr imports. Australia suppresses bilateral detail for iron ore
  to protect individual mining companies.
- **Canada -> US (crude oil)**: Canada reports NULL/empty fields (different
  suppression method). US reports $48B-$62B/yr imports.

## Key Characteristics

- **Zero vs NULL**: Two different suppression patterns exist:
  - Zero value with empty quantities (explicit suppression)
  - NULL/empty for all fields (row may or may not appear)
- **Major trade corridors**: These are some of the world's largest bilateral flows.
  A naive mirror analysis would flag them as 100% discrepancies.
- **Known confidential commodities**: Petroleum (HS 2709) and iron ore (HS 2601)
  are frequently suppressed by major exporters.

## Expected Detection Output

- The tool MUST NOT treat suppressed-zero or NULL values as actual zero trade
- It should detect the confidentiality pattern: large partner value + zero/null
  reporter value for known-confidential commodities
- Flag: confidential_suppression (informational, not suspicious)
- Severity: **NONE** — these are data quality artifacts, not anomalies
- The tool should exclude confidential flows from discrepancy statistics to avoid
  polluting baselines and z-scores
- This is a critical correctness test: misinterpreting confidential suppression as
  phantom shipments would produce massive false positives on the world's largest
  trade corridors
