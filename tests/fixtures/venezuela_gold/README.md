# Venezuelan Gold Case

## Scenario

Gold flows from Venezuela through Curacao to Switzerland, 2015-2019. This is based
on real investigative journalism findings (e.g., Reuters, OCCRP) documenting how
Venezuelan gold — much of it illegally mined — was laundered through Caribbean
intermediaries before reaching Swiss refiners.

## Data Structure

Three bilateral corridors, each with two sides (reporter exports vs partner imports):

1. **Venezuela -> Curacao**: Venezuela reports minimal gold exports ($0.15M-$1.2M/yr).
   Curacao reports massive gold imports from Venezuela ($180M-$420M/yr). Mirror
   discrepancy ratio: 99%+.

2. **Curacao -> Switzerland**: Curacao reports large gold exports ($165M-$400M/yr).
   Switzerland reports much smaller gold imports from Curacao ($22M-$42M/yr). Mirror
   discrepancy ratio: 85-90%.

3. Both discrepancies grow over time (2015-2019), indicating an escalating scheme.

## Key Anomalies

- **Massive bilateral mirror discrepancies** on both corridor legs
- **Volume discrepancy**: Curacao claims importing thousands of kg from Venezuela;
  Venezuela reports exporting single-digit kg
- **Implausible unit prices**: Some implied prices per kg deviate from the London
  gold fix (~$38,000-$42,000/kg in this period)
- **Persistence**: Pattern repeats every year for 5 years
- **Country risk**: Venezuela under sanctions, Curacao is a known transit hub

## Expected Detection Output

- Severity: **CRITICAL** (highest tier)
- Flags triggered: phantom_shipment (Venezuela side), mirror_discrepancy,
  volume_anomaly, unit_price_deviation, persistent_pattern, high_risk_corridor
- Both legs (VEN->CUW and CUW->CHE) should be flagged independently
- The corridor should rank among the highest-severity results in any broad scan
