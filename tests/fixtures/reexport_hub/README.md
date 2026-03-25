# Re-Export Hub Legitimate Case

## Scenario

Singapore acts as a major re-export hub for electronic integrated circuits (HS 8542)
between Taiwan and Germany/EU. Taiwan manufactures chips, exports to Singapore, and
Singapore re-exports to Germany after aggregation, testing, or repackaging.

The Taiwan -> Singapore leg shows normal mirror alignment. The Singapore -> Germany
leg shows a large apparent discrepancy: Singapore reports much higher export values
than Germany reports as imports from Singapore. However, this is a **legitimate**
pattern explained by re-export accounting.

## Data Structure

- **Taiwan -> Singapore (2020-2022)**: Both sides agree within 2% — normal trade.
  Values: $2.8B-$3.4B/yr.
- **Singapore -> Germany (2020-2022)**: Singapore reports exports of $3.2B-$4.2B/yr.
  Germany reports imports of only $1.8B-$2.4B/yr. Apparent discrepancy: 43-44%.
- **Singapore -> World**: Included to show Singapore's total IC exports ($18.5B-$24B),
  providing context that the Germany corridor is a small fraction.

## Why This Is Legitimate

1. **Re-export accounting**: Singapore includes re-exported goods in its export
   statistics. Germany attributes imports to the country of origin (Taiwan), not the
   transit country (Singapore). This is standard practice under UN statistical
   recommendations.
2. **Value-added**: Singapore may add value through testing, packaging, or assembly,
   inflating the declared export value.
3. **Third-country attribution**: Germany may attribute some Singapore-shipped goods
   to Taiwan or other origins based on rules of origin.

## Expected Detection Output

- Mirror discrepancy on Singapore -> Germany: **HIGH** (~44% relative discrepancy)
- The tool should flag this corridor initially BUT:
  - Recognize Singapore as a known re-export hub
  - Note that the Taiwan -> Singapore leg is clean
  - Apply a re-export correction factor or flag as "likely re-export"
  - Downgrade severity from HIGH to **LOW** or **INFORMATIONAL**
- This tests the tool's ability to avoid false positives on legitimate trade patterns
