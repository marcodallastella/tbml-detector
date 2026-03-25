# No-Reporting Country Case

## Scenario

North Korea (DPRK) does not report trade data to UN Comtrade. All bilateral flow
data involving North Korea is one-sided — only the partner country's reported
exports/imports are available.

This fixture includes:
- China's reported petroleum and cement exports to North Korea
- UAE's reported zero petroleum exports to North Korea
- South Korea's reported zero corn exports to North Korea

North Korea's import records are entirely absent from Comtrade.

## Data Structure

- **China -> North Korea**: China reports $62M-$85M/yr in refined petroleum (HS 2710)
  and $8M-$12M/yr in cement (HS 2523). No DPRK import data exists.
- **UAE -> North Korea**: UAE reports zero petroleum exports. No DPRK data exists.
- **South Korea -> North Korea**: South Korea reports zero corn exports. No DPRK data.

## Key Characteristics

- **One-sided data only**: Mirror analysis is impossible in the traditional sense
- **Sanctioned destination**: North Korea is under comprehensive UN/US/EU sanctions
- **Petroleum trade is capped**: UN Security Council Resolution 2397 caps refined
  petroleum exports to DPRK at 500,000 barrels/year
- **Declining trend**: China's reported exports decrease over time, possibly
  reflecting sanctions enforcement or re-routing

## Expected Detection Output

- Mirror discrepancy: **CANNOT COMPUTE** (partner data unavailable)
- The tool should flag: no_partner_data, sanctioned_destination
- It should NOT interpret missing partner data as "zero trade" or compute a 100%
  discrepancy — the correct handling is to flag that mirror analysis is not possible
  for this corridor and note the data limitation
- Severity: **MEDIUM** (data limitation, not a confirmed anomaly) with a note that
  the corridor involves a non-reporting sanctioned country
- China's petroleum export volumes could be cross-checked against UNSC cap
