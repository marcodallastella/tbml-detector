# EU Aggregate vs. Member State Reporting

## Scenario

China reports textile exports (HS 6110 — jerseys, pullovers, cardigans) to the
"European Union" as an aggregate partner. Individual EU member states each report
their own imports from China separately. There is no single EU-level import record
to compare against China's aggregate export.

This creates an apparent mirror analysis problem: China's reported exports to "EU"
cannot be directly compared to any single partner's import record. The comparison
must be done by summing individual member state imports.

## Data Structure

- **China -> EU (aggregate)**: $8.5B (2021), $8.9B (2022)
- **Individual EU member states -> China (imports)**: 12 member states report imports
  summing to approximately $7.5B (2021) and $7.88B (2022)
- **Apparent gap**: ~$1.0B (2021), ~$1.02B (2022) — about 12%

## Why This Is NOT Suspicious

1. **Incomplete member state coverage**: Not all 27 EU member states are included in
   this fixture. The missing states account for the gap.
2. **Reporting methodology**: China may use different valuation methods (FOB) vs EU
   states (CIF), explaining some difference.
3. **Aggregate vs. granular reporting**: This is a well-known Comtrade data quality
   issue, not a TBML indicator.

## Expected Detection Output

- The tool should recognize "EU" (code 97) as an aggregate reporter
- It should attempt to sum member state imports and compare to the aggregate
- The ~12% gap should be flagged as **INFORMATIONAL** only, with a note explaining
  the aggregate reporting mismatch
- Severity: **NONE** or **INFORMATIONAL** — this is a data quality artifact, not
  a TBML indicator
- This tests the tool's handling of aggregate vs. granular reporting entities
