# Pharmaceutical Over-Invoicing Case

## Scenario

Switzerland exports pharmaceutical products (HS 3004 — medicaments in measured
doses) to Nigeria at unit prices 5-10x the global benchmark. Germany also exports
the same commodity to Nigeria at elevated but less extreme unit prices.

Both sides of each corridor **agree** on the values — there is no significant mirror
discrepancy. The anomaly is in the unit prices themselves.

## Data Structure

- **Switzerland -> Nigeria (2019-2022)**: Unit prices of $500-$778/kg. Global
  benchmark for HS 3004 is approximately $80-$120/kg.
- **Germany -> Nigeria (2019-2020)**: Unit prices of $312-$317/kg. Also elevated
  but less extreme than Switzerland.

## Key Anomalies

- **No mirror discrepancy**: Both reporter and partner values agree within 1-2%
  (normal CIF/FOB spread)
- **Unit price anomaly**: Declared unit values are 5-10x the global benchmark
- **Benford's law**: Leading digit distribution of declared values may show
  irregularities
- **Increasing trend**: Swiss unit prices escalate year-over-year, suggesting
  a growing scheme

## Expected Detection Output

- Mirror discrepancy flags: **NONE** (both sides agree)
- Unit price flags: **HIGH** severity — unit prices far exceed commodity benchmarks
- Benford's law: May trigger depending on implementation
- This case tests that the tool can detect TBML even without mirror discrepancies,
  using unit price analysis as a complementary detection method
- Overall severity: **HIGH** (unit price anomaly alone)
