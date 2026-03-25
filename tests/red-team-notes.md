# Red Team Notes

Adversarial analysis of the comtrade-mirror detection engine: patterns that could
evade detection, legitimate patterns that produce false positives, and recommended
improvements.

## TBML Patterns the Severity Rubric Might Miss

### 1. Carousel / Round-Tripping Through Multiple Intermediaries

The current mirror analysis examines bilateral pairs independently. A carousel
scheme routing goods A -> B -> C -> D -> A would show moderate discrepancies on
each leg but no single leg would score as critical. The tool lacks graph-based
analysis to detect circular flows.

**Risk**: High. Carousel schemes are among the most common TBML typologies.

**Recommendation**: Add network/graph analysis that computes total flow through
multi-hop paths for the same commodity and flags circular patterns.

### 2. Smurfing / Structured Trade Below Thresholds

If a money launderer splits a $50M phantom shipment into 50 transactions of $1M
each across slightly different HS codes or reporting periods, each individual
transaction falls below the `min_value_thresholds.annual_usd` of $10,000 and the
discrepancy on each is too small to trigger z-score alerts.

**Risk**: Medium. The tool's per-record approach cannot aggregate structuring.

**Recommendation**: Add aggregation analysis that sums flows by (reporter, partner,
HS chapter, year) before computing discrepancies, in addition to per-record analysis.

### 3. Commodity Code Shifting

A flow reported under HS 7108 (gold) by the exporter may be reported under
HS 7112 (gold waste and scrap) by the importer. The mirror join requires exact
commodity code match, so this pair would appear as two phantom shipments rather
than one discrepant mirror pair.

**Risk**: High. HS classification inconsistency is well-documented.

**Recommendation**: Implement fuzzy matching at the HS 4-digit or 2-digit level
and flag pairs where phantom flows on related codes could be the same shipment.

### 4. Value Manipulation Within CIF/FOB Tolerance

If a launderer sets the over-invoicing amount to fall within the 3-15% CIF/FOB
adjustment band (e.g., consistently invoicing at 12% above FOB), the CIF/FOB
normalization absorbs the manipulation and the residual discrepancy appears normal.

**Risk**: Medium. The fixed CIF/FOB ratio is a known weakness.

**Recommendation**: Use commodity- and route-specific CIF/FOB ratios derived from
historical data rather than fixed defaults. Flag corridors where the actual
CIF/FOB spread consistently exceeds the expected ratio for that transport mode.

### 5. Timing Manipulation

Report the same shipment in different fiscal periods. Exporter reports in December
2020; importer reports in January 2021. Annual data aggregation eliminates the
match. Monthly data may catch it with lag correction, but annual-only analysis
misses it entirely.

**Risk**: Medium. The tool has lag correction for monthly data but most Comtrade
data is annual.

**Recommendation**: When analyzing annual data, also check ±1 year windows for
potential matches before classifying as phantom.

### 6. Abuse of "Areas NES" Partner Code

Some countries report exports to "Areas NES" (code 899) rather than the true
destination. The mirror analysis excludes code 899 from mirror pairs. A launderer
could exploit this by routing through a country that reports to NES, making the
flow invisible to mirror analysis.

**Risk**: Low-Medium. Requires cooperation from a customs authority.

**Recommendation**: Flag countries that report unusually high proportions of trade
to "Areas NES" or "World" as data quality concerns.

### 7. Services Disguised as Goods

TBML often involves a parallel services invoice (e.g., "consulting fees") to
explain the monetary transfer. The goods flow may appear normal while the
over-payment happens outside the trade data entirely.

**Risk**: High, but out of scope for this tool (Comtrade covers goods, not services).

**Recommendation**: Document this limitation clearly. Suggest cross-referencing
with financial flow data when available.

## Legitimate Trade Patterns Producing False Positives

### 1. Re-Export Hub Discrepancies

Singapore, Hong Kong, Netherlands, Belgium, UAE, and Switzerland all act as major
re-export/entrepot hubs. They report re-exports as their own exports, but
destination countries often attribute imports to the country of origin, not the
transit country. This creates structural mirror discrepancies of 30-60% that are
entirely legitimate.

**Current mitigation**: The tool applies a -10 point re-export adjustment.

**Assessment**: Insufficient. Known re-export hubs for specific commodities (e.g.,
Singapore for electronics, Switzerland for gold, Belgium for diamonds) should
have higher adjustments or commodity-specific re-export factors.

### 2. CIF/FOB Variability

The fixed 7% default CIF/FOB ratio is a global average. Actual ratios vary:
- Australia -> China (iron ore, bulk maritime): 3-5%
- Colombia -> EU (flowers, perishable air freight): 15-25%
- Singapore -> Germany (electronics, container): 8-12%

Using a fixed ratio under-adjusts some corridors and over-adjusts others.

**Recommendation**: Build a lookup table of commodity-route-specific CIF/FOB
ratios from historical data.

### 3. Confidentiality Suppression

Major commodity exporters (Australia iron ore, US petroleum, Canada oil) suppress
bilateral values for confidentiality. A naive system treating these zeros as
phantom shipments would flag the world's largest trade corridors.

**Current mitigation**: The tool detects known-confidential HS codes and flags them.

**Assessment**: Good coverage for petroleum and iron ore. Missing coverage for:
defense articles, rare earths, some agricultural commodities (e.g., Australia
wheat), and pharmaceutical active ingredients in some jurisdictions.

### 4. EU Aggregate Reporting

China, Russia, and some other countries report exports to "EU" as an aggregate.
Mirror analysis cannot match this against individual member state imports without
summing all 27 states.

**Current mitigation**: EU aggregate code (97) is excluded from mirror pairs.

**Assessment**: Adequate, but the tool should offer an optional aggregation mode
that sums EU member state imports for comparison.

### 5. Data Revision Lags

Comtrade data is revised. A preliminary report may differ significantly from the
final version. The tool may flag a corridor based on preliminary data that looks
fine after revision.

**Recommendation**: Track data vintage (fetched_at) and re-run analysis after
revision periods (typically 6-12 months).

### 6. Intra-Firm Transfer Pricing

Multinational corporations routinely price intra-firm trade at transfer prices
that differ from arm's-length market prices. This creates unit price anomalies
that are legal (within OECD guidelines) but indistinguishable from TBML
over/under-invoicing.

**Recommendation**: Note in the tool's output that unit price anomalies for
commodities dominated by a few multinationals (semiconductors, pharmaceuticals,
automotive parts) may reflect transfer pricing rather than TBML.

## Additional Edge Cases (from TBML Expert Review)

The following evasion techniques were identified by the tbml-expert from
FATF/Egmont case studies. They are lower-priority but worth documenting:

### 8. Barter / Countertrade Arrangements

Goods-for-goods trade where no monetary payment crosses borders. Creates
zero-value discrepancies or NES-reported flows. Documented in Iran-China and
Russia-India trade corridors. Rare but difficult to detect with monetary
value-based analysis.

### 9. Underweight / Overweight Manipulation

Physical goods match the declared HS code but actual weight or volume differs
from the customs declaration. Detectable when Q_rel (quantity discrepancy)
diverges significantly from zero while both sides report the same HS code and
similar monetary values.

### 10. Trade-Based Sanctions Evasion via Front Companies

Similar to TBML but motivated by sanctions circumvention rather than laundering.
The same detection methods apply. Partially covered under commodity
misclassification (sanctions evasion variant) in the typologies doc.

## Spec Updates Status

All 7 original evasion patterns and 6 false positive sources have been reviewed
by the tbml-expert and addressed in the detection spec and typologies documents:

- **Carousel detection**: detection-spec.md Section 8.1 — graph-based DFS cycle
  detection with severity bonuses (+5 to +15 by cycle length)
- **Smurfing**: detection-spec.md Section 8.3 + tbml-typologies.md Typology 13 —
  aggregate analysis across sub-threshold flows; clustering of D_rel values just
  below threshold is itself an anomaly signal
- **Commodity code shifting**: detection-spec.md Section 8.2 — fuzzy matching
  within same 2-digit HS chapter; second-pass match for unmatched phantoms
- **CIF/FOB band manipulation**: detection-spec.md Section 9.4 — confidence bands
  instead of single-point ratios (e.g., flowers by air: 1.15-1.30, bulk ore: 1.02-1.06)
- **Timing manipulation**: Covered by existing 2-year rolling average for annual data
- **Areas NES abuse**: detection-spec.md Section 8.4 + tbml-typologies.md Typology 14 —
  NES share analysis; >10% of total trade to NES triggers flag
- **Services limitation**: detection-spec.md Section 10 — documented as out-of-scope
- **Re-export adjustments**: detection-spec.md Section 9.3 — per-hub calibrated
  adjustments (Hong Kong -15, Singapore -10, Netherlands -12)
- **CIF/FOB variability**: Addressed via confidence bands in Section 9.4
- **Confidential suppression**: detection-spec.md Section 5.2 expanded — defense
  articles, rare earths, agricultural subsidies, Japan tech exports, India defense
- **EU aggregation**: detection-spec.md Section 8.6 — `aggregate_eu_flows()` function
- **Data revision**: detection-spec.md Section 8.5 — revision tracking
- **Transfer pricing**: tbml-typologies.md Section 1 — acknowledged as irreducible
  false positive source (30-40% of global trade is intra-firm)

## Recommended Improvements (Priority Order)

1. **Graph analysis for multi-hop flows** — Highest impact for carousel detection
   (now specified in detection-spec.md Section 8.1)
2. **Fuzzy HS code matching** — Critical for reducing false phantoms
   (now specified in detection-spec.md Section 8.2)
3. **Commodity-route-specific CIF/FOB ratios** — Reduces false positives
   (now specified in detection-spec.md Section 9.4)
4. **Aggregation mode** — Sum sub-threshold flows to detect structuring
   (now specified in detection-spec.md Section 8.3)
5. **Annual ±1 year lag window** — Catches timing manipulation
6. **Enhanced re-export scoring** — Per-hub calibrated adjustments
   (now specified in detection-spec.md Section 9.3)
7. **Data revision tracking** — Prevents premature alerts
   (now specified in detection-spec.md Section 8.5)
8. **NES/World concentration flagging** — Detects data quality evasion
   (now specified in detection-spec.md Section 8.4)
