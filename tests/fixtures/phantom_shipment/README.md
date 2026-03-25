# Phantom Shipment Case

## Scenario

China reports $572M in heavy machinery exports (HS 8429, 8430) to Syria over
2019-2021. Syria has **zero** corresponding import records for these commodity codes
and time periods. Syria does not report to Comtrade for these years.

This is a classic phantom shipment scenario: one side reports trade that the other
side has no record of. While the absence of Syrian data could be due to
non-reporting, the combination of a sanctioned destination, high values, and
complete absence of partner data is a strong red flag.

## Data Structure

- **China -> Syria**: Reporter (China) exports are present with large values
  ($150M-$180M/yr for HS 8429, $20M-$25M/yr for HS 8430)
- **Syria -> China**: No import records exist (Syria is a non-reporter for this
  period)
- Total one-sided exports: ~$572M over 3 years

## Key Anomalies

- **Complete mirror gap**: 100% discrepancy — reporter data exists, partner data
  is entirely absent
- **Sanctioned destination**: Syria is under multiple international sanctions
  regimes
- **High value machinery**: Heavy machinery exports to a conflict zone
- **Consistent pattern**: Repeated over 3 consecutive years

## Expected Detection Output

- Mirror discrepancy: **100%** (phantom — no partner data)
- Severity: **CRITICAL** — phantom flow to sanctioned jurisdiction
- Flags: phantom_shipment, no_partner_data, high_risk_destination, persistent_pattern
- Note: The tool should distinguish between "partner didn't report" (data quality)
  and "partner reports zero" (true phantom). Both are concerning but have different
  confidence levels. Since Syria is a known non-reporter, the tool should flag this
  but note the data quality caveat.
