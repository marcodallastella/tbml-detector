# TBML Typologies Reference

A comprehensive catalogue of trade-based money laundering schemes and how they
manifest in UN Comtrade mirror trade data. For each typology: the pattern
signature, detection thresholds, and expected false positive sources.

---

## 1. Over-Invoicing of Imports

### Scheme Description

The importer arranges to pay more than the true market value for goods. The excess
payment transfers value from the importing country to the exporting country,
where the surplus is diverted to a third party or laundered entity. The exporter
invoices at an inflated price; the importer submits customs declarations matching
the inflated invoice.

**Money flow direction**: From importing country to exporting country.

**Typical actors**: The importer and exporter are often related parties or
co-conspirators. The scheme may involve shell companies in the exporting country.

### Mirror Data Signature

```
V_imp >> V_exp   (importer declares much higher value than exporter)
D_rel > 0        (positive discrepancy after CIF/FOB adjustment)
Q_rel ≈ 0        (quantities roughly match — same goods, different declared value)
UP_imp >> UP_exp  (unit price discrepancy drives the value gap)
```

The key distinguishing feature is that **quantities agree but values diverge**,
indicating price manipulation rather than a reporting error about physical goods.

### Detection Thresholds

- `D_rel > 0.25` after CIF/FOB adjustment (25% overstatement of import value)
- `UP_rel > 0.30` (unit price divergence exceeds 30%)
- `|Q_rel| < 0.10` (quantities agree within 10%, isolating the price dimension)
- Persistent in the same direction across 3+ consecutive periods

### False Positive Sources

- **CIF/FOB gap**: Legitimate CIF values exceed FOB by 5-15% (shipping/insurance).
  Mitigated by applying CIF/FOB adjustment factors before flagging.
- **Currency fluctuation timing**: If exporter and importer convert to USD at
  different exchange rates (e.g., contract date vs. customs date), a temporary
  discrepancy can arise. Usually < 5%.
- **Quality/grade differences**: The exporter ships "standard grade" but the
  importer declares a higher grade for domestic tax or subsidy reasons. Not
  necessarily TBML but still suspicious.
- **Transfer pricing**: Legitimate multinational corporations may use transfer
  pricing that creates mirror discrepancies. Intra-firm trade accounts for an
  estimated 30-40% of global trade. Transfer prices within OECD arm's-length
  ranges are legal and indistinguishable from TBML in aggregate data. However,
  extreme transfer pricing (outside comparable uncontrolled price ranges) may
  itself be a TBML variant. This is a fundamental false positive source that
  cannot be fully eliminated through mirror analysis alone.

---

## 2. Under-Invoicing of Exports

### Scheme Description

The exporter declares goods at below market value. The importer pays the true
market value, but only the under-invoiced amount is reported to the exporter's
customs authority. The difference is retained offshore or diverted. This scheme
also facilitates capital flight from the exporting country.

**Money flow direction**: Value leaks from exporting country (unreported foreign
earnings remain abroad).

### Mirror Data Signature

```
V_imp >> V_exp   (same direction as over-invoicing of imports)
D_rel > 0        (positive discrepancy)
UP_imp >> UP_exp
```

Under-invoicing of exports and over-invoicing of imports produce the **same mirror
signature** (V_imp > V_exp). Distinguishing them requires contextual analysis:
- If the exporting country has capital controls or currency restrictions, under-
  invoicing of exports is more likely.
- If the importing country has high tariffs on the commodity, over-invoicing of
  imports is less likely (importer would pay more duty).

### Detection Thresholds

Same as over-invoicing of imports. The statistical signature is identical in mirror
data.

### False Positive Sources

Same as over-invoicing of imports, plus:
- **Export subsidies**: Some countries subsidize exports, creating incentive to
  over-declare export values (the opposite of under-invoicing). Discrepancies
  involving subsidized goods may run in the reverse direction.

---

## 3. Over-Invoicing of Exports

### Scheme Description

The exporter inflates the declared value of exports to claim larger export
subsidies, tax rebates (e.g., VAT refund fraud), or to justify receiving larger
foreign payments. The importer may report the true (lower) value.

**Money flow direction**: Fraudulent subsidy/rebate extraction in the exporting
country.

### Mirror Data Signature

```
V_exp >> V_imp   (exporter declares more than importer reports)
D_rel < 0        (negative discrepancy)
UP_exp >> UP_imp
```

### Detection Thresholds

- `D_rel < -0.25` after CIF/FOB adjustment
- Persistent negative discrepancy across multiple periods
- Particularly suspicious when the exporting country offers VAT export rebates
  (e.g., China's VAT rebate system on manufactured exports)

### False Positive Sources

- **Importer undervaluation for tariff avoidance**: The importer may under-declare
  to pay lower import duties. This is customs fraud by the importer, not
  necessarily TBML by the exporter.
- **Free-alongside-ship vs. FOB differences**: Minor valuation basis differences.
- **Confidential import data**: If the importer's country suppresses the flow, the
  import side may appear artificially low.

---

## 4. Under-Invoicing of Imports

### Scheme Description

The importer declares goods at below market value to reduce customs duties and
taxes. The exporter invoices at the true value. The duty savings are a form of
illicit financial benefit, and the scheme may be combined with cash payments for
the difference outside the banking system.

**Money flow direction**: Duty evasion in the importing country; undeclared cash
payments may flow through informal channels.

### Mirror Data Signature

```
V_exp >> V_imp   (same direction as over-invoicing of exports)
D_rel < 0
```

### Detection Thresholds

- `D_rel < -0.25` after CIF/FOB adjustment
- Higher suspicion for high-tariff commodities (tariff rate > 15%)
- `UP_imp` significantly below global benchmark prices for the commodity

### False Positive Sources

- **Legitimate valuation differences**: Customs authorities may apply different
  valuation methods (transaction value, deductive value, computed value per WTO
  Customs Valuation Agreement).
- **Damaged or defective goods**: Importer may legitimately declare lower value.
- **Old inventory / obsolete stock**: Market value may have declined since export.

---

## 5. Multiple Invoicing / Duplicate Billing

### Scheme Description

The same shipment of goods is invoiced multiple times (e.g., different invoices to
different banks), allowing multiple payments to be made for a single physical
delivery. Each payment appears to be backed by a legitimate trade transaction, but
only one shipment occurred.

**Money flow direction**: Multiple payments flow from importer to exporter for a
single delivery, creating excess value transfer.

### Mirror Data Signature

```
V_imp >> V_exp       (if multiple import declarations for one export declaration)
  or
V_exp >> V_imp       (if multiple export declarations for one import clearance)

Q_imp >> Q_exp       (reported quantity on one side is a multiple of the other)
  or
V_imp / V_exp ≈ integer > 1  (value ratio is close to a whole number)
```

At the aggregate Comtrade level, multiple invoicing inflates one side's reported
total relative to the other.

### Detection Thresholds

- Value ratio `V_imp / V_exp` close to an integer (2x, 3x) — compute
  `abs(V_imp/V_exp - round(V_imp/V_exp))` and flag when < 0.05
- Large absolute discrepancy (`D_abs > USD 1M`) combined with integer-ratio pattern
- Sudden year-over-year jump in corridor volume on one side but not the other

### False Positive Sources

- **Aggregation artifacts**: Comtrade aggregates all transactions in a corridor.
  Multiple legitimate shipments naturally produce non-integer ratios. The
  integer-ratio test is most useful on disaggregated (tariff-line or monthly) data.
- **Partial shipments**: A single order split across multiple shipments may be
  reported differently by each side.
- **Different reporting periods**: Shipments spanning period boundaries may be
  counted in different months.

---

## 6. Phantom Shipments

### Scheme Description

Trade is reported by one side (typically the side paying), but no goods actually
move. The "exporter" provides fraudulent shipping documents. The importer makes
payment for non-existent goods, transferring value internationally under the guise
of trade.

Alternatively, an exporter fabricates export declarations to claim subsidies or
tax rebates, while no corresponding import is ever declared.

### Mirror Data Signature

```
V_exp > 0, V_imp = 0    (export reported, no matching import)
  or
V_imp > 0, V_exp = 0    (import reported, no matching export)
```

In Comtrade, this appears as a **one-sided flow**: one country reports a bilateral
trade flow, but the partner has no corresponding record for that corridor and
commodity in the same period.

### Detection Thresholds

- Any flow where one side reports > USD 100,000 and the other reports zero or has
  no record for that corridor-commodity-period combination
- Particularly suspicious when the reporting side is a known TBML-risk jurisdiction
- One-sided flows that appear suddenly (no prior trade history in that corridor)

### False Positive Sources

- **Non-reporting countries**: If the partner simply does not report to Comtrade,
  the missing mirror is a data gap, not a phantom shipment. Cross-reference against
  the list of non-reporting countries (see detection-spec.md Section 5.1).
- **Confidential trade suppression**: The partner may suppress the flow for
  confidentiality (see detection-spec.md Section 5.2).
- **Re-exports through third countries**: Country A exports to hub H, which re-
  exports to Country B. Country A reports exports to B (origin-destination), B
  reports imports from H (last-shipped-from). Neither A->B import nor H->B export
  shows the expected mirror.
- **Timing**: Goods shipped in December, customs cleared in January — one side
  records in the earlier period, the other in the later period. For annual data
  this effect is minor.
- **Below-threshold reporting**: Some countries do not report individual flows
  below a minimum value threshold. Small legitimate flows may appear as phantoms.

---

## 7. Carousel / Round-Tripping Schemes

### Scheme Description

Goods (or paper trails for non-existent goods) move in a circular pattern through
multiple jurisdictions, returning to the origin country or to a related entity.
Each leg of the circuit generates an apparently legitimate trade transaction. The
purpose is to generate multiple payment flows, to create the appearance of
business activity, or to exploit VAT/GST refund mechanisms.

**Variants**:
- **Classic VAT carousel**: Goods imported VAT-free into country A, sold
  domestically with VAT charged, then "exported" (VAT refund claimed) to country B,
  which re-exports back to A. The domestic seller disappears without remitting VAT.
- **Round-tripping for capital flight**: Goods exported from country A to shell
  companies in B, C, D, then "imported" back to A at inflated value. Capital has
  been moved through B, C, D.
- **Circular invoicing**: No goods move; only invoices circulate to create a paper
  trail of international trade.

### Mirror Data Signature

Carousel patterns do not produce a simple bilateral discrepancy. They require
**network analysis** across multiple corridors:

```
A -> B -> C -> A     (circular flow pattern)
```

Indicators in mirror data:
- Unusually high bilateral trade volumes between small economies or entities with
  no natural economic reason for the trade
- Near-identical values flowing in each leg of the circuit (minus small margins)
- Same commodity code in all legs (goods are not being transformed)
- Rapid turnover: short time between import and re-export in intermediate
  jurisdictions

### Detection Thresholds

- Identify cycles in the trade flow graph: for a given commodity and period, find
  closed loops A->B->C->...->A where trade volumes are within 20% across all legs
- Flag corridors where the same commodity is both imported and exported in
  significant volume (`min(V_imp, V_exp) / max(V_imp, V_exp) > 0.7`)
- Short holding period: monthly data shows import and export of the same commodity
  in the same month (re-export without processing)

### False Positive Sources

- **Legitimate re-export trade**: Entrepot economies (Singapore, Hong Kong,
  Netherlands) naturally import and re-export goods. High volumes are expected.
- **Intermediate processing**: Goods imported for assembly/processing and re-
  exported as a different product (different HS code) are not carousel fraud.
- **Seasonal patterns**: Agricultural commodities may flow in circular patterns
  due to harvest timing differences.
- **Return of defective goods**: Legitimate returns create apparent circular flows.

---

## 8. Commodity Misclassification

### Scheme Description

Goods are deliberately classified under incorrect HS codes to shift value between
categories. For example, high-value goods declared as low-value commodity codes
(to reduce duties) or low-value goods declared as high-value codes (to justify
larger payments).

**Variants**:
- **Value shifting**: Declaring gold jewelry (HS 7113, high value/kg) as costume
  jewelry (HS 7117, low value/kg)
- **Duty avoidance**: Declaring finished electronics under component codes with
  lower tariff rates
- **Sanction evasion**: Declaring sanctioned goods under non-sanctioned codes

### Mirror Data Signature

Misclassification creates discrepancies at the **HS code level** that may cancel
out at the aggregate level:

```
At HS 7113 (gold jewelry): V_exp >> V_imp  (exporter reports, importer under-reports)
At HS 7117 (costume jewelry): V_imp >> V_exp  (importer over-reports to compensate)
Sum across both codes: discrepancy may be small
```

Key indicator: **correlated opposite-sign discrepancies** in related HS codes for
the same corridor.

### Detection Thresholds

- For a corridor, compute discrepancies at 4-digit HS level. Flag when two or more
  related codes (same 2-digit chapter) show discrepancies > 25% in **opposite
  directions**
- Unit price anomaly: `UP_exp` or `UP_imp` deviates > 2 standard deviations from
  the global mean unit price for that HS code (across all corridors)
- Volume/value mismatch: large quantity of a "low-value" commodity with
  unexpectedly high total value, or vice versa

### False Positive Sources

- **Legitimate classification differences**: National tariff schedules may classify
  goods differently from the international HS standard at the 6+ digit level.
  Countries add national subheadings beyond the 6-digit international standard.
- **Product ambiguity**: Some products genuinely fall between categories (e.g., is a
  smartwatch HS 9102 [wristwatches] or HS 8517 [telecom equipment]?).
- **HS revision transitions**: When countries adopt new HS revisions at different
  times, the same product may be classified under different codes.
- **Parts vs. complete goods**: A machine imported as parts (HS 84xx.90) may be
  declared as a complete machine (HS 84xx.10) by the other side.

---

## 9. Concentration Anomalies

### Scheme Description

A single entity or a small group of related entities dominates a bilateral trade
corridor, accounting for an outsized share of total trade in a specific commodity.
While not inherently illegal, extreme concentration in TBML-risk corridors is a
red flag: it suggests that a small number of actors control the trade flow and
could manipulate prices or volumes without market competition revealing the
manipulation.

### Mirror Data Signature

Comtrade does not report entity-level data (it aggregates all traders in a
corridor). Concentration anomalies must be inferred from aggregate patterns:

- **Unusually small corridor with large value**: A bilateral flow of > USD 10M in
  a commodity where neither country is a major producer, consumer, or known
  transshipment point
- **Sudden appearance**: A corridor that had zero or minimal trade suddenly reports
  large volumes, suggesting a new (possibly single) actor
- **Unusual commodity-country pair**: A landlocked country with no coastline
  reporting large fish exports; a desert country exporting timber
- **Volatility**: Year-to-year variation > 50% in corridor value, suggesting
  dependence on a small number of transactions

### Detection Thresholds

- Flag corridors where bilateral trade in a 4-digit HS code exceeds 10% of one
  partner's total global trade in that code (suggesting domination by a small
  number of traders)
- Year-over-year change > 100% in corridor value (sudden doubling)
- New corridor: zero trade in the previous 3 years, then > USD 1M
- Commodity-geography mismatch: commodity requires specific natural resources or
  climate that the exporting country does not possess (requires a lookup table of
  commodity-geography plausibility)

### False Positive Sources

- **Small economies**: For small countries, any single large order can dominate a
  corridor. Threshold should be scaled by country GDP or total trade volume.
- **Natural resource discoveries**: A new mine or oil field creates a new export
  corridor legitimately.
- **Trade agreement effects**: A new free trade agreement can redirect trade flows,
  creating sudden new corridors.
- **One-off capital goods**: A single large infrastructure purchase (e.g., aircraft,
  power plant equipment) can dominate a corridor for one year.

---

## 10. Free Trade Zone / Freeport Opacity

### Scheme Description

Free trade zones (FTZs), freeports, and special economic zones often have reduced
customs reporting requirements. Goods entering an FTZ may not be recorded as
imports by the host country until they leave the zone for domestic consumption.
This creates reporting gaps exploited for TBML.

**Exploitation patterns**:
- Goods enter FTZ, are re-invoiced at different prices, and re-exported
- Goods are stored indefinitely in freeport warehouses (no import declaration)
- Value transformation: raw materials enter, "finished products" leave at inflated
  prices, but no actual processing occurs
- Multiple invoicing: goods in FTZ storage are invoiced multiple times to different
  buyers

### Mirror Data Signature

```
V_exp > 0 to FTZ jurisdiction, V_imp = 0 or minimal
  (goods enter FTZ but are not recorded as imports)
Subsequent V_exp from FTZ jurisdiction at different price level
```

The mirror discrepancy manifests as systematic under-reporting on the import side
for FTZ jurisdictions.

### Detection Thresholds

- Persistent positive `D_rel` (V_imp < V_exp) for corridors where the importer is
  an FTZ jurisdiction — the opposite of the normal CIF/FOB pattern
- High-value commodity flows into known FTZ jurisdictions with no corresponding
  domestic consumption data
- Large re-export margins: difference between import unit price and re-export unit
  price from FTZ jurisdiction exceeds 30%

### False Positive Sources

- **Legitimate warehousing and logistics**: FTZs serve valid commercial purposes
  (consolidation, light assembly, quality inspection). Not all FTZ flows are
  suspicious.
- **Delayed reporting**: FTZ goods may be reported when they leave the zone, not
  when they enter. Timing mismatch rather than suppression.
- **Different statistical territory**: Some FTZs are excluded from a country's
  statistical territory for Comtrade purposes (e.g., some Chinese SEZs report
  separately). Check Comtrade metadata for territory definitions.

---

## 11. Black Market Peso Exchange (BMPE) Patterns

### Scheme Description

The BMPE is a money laundering technique originating in narcotics trade between
Latin America and the United States. Drug proceeds in USD are sold to peso
brokers, who use them to purchase US goods on behalf of Latin American importers.
The goods are shipped to Latin America and sold for local currency. The effect is
that drug dollars are converted to pesos through trade transactions.

**Modern variants** extend beyond USD/COP to any currency pair and any trade
corridor where criminal proceeds in one currency need to be converted to another.

### Mirror Data Signature

BMPE is difficult to detect in Comtrade aggregate data because individual
transactions may appear legitimate. Aggregate indicators:

- **Over-invoicing of US exports** to specific Latin American countries: USD
  proceeds are used to buy goods at inflated prices, creating excess apparent
  demand
- **Commodity concentration**: BMPE tends to concentrate in consumer goods with
  liquid resale markets (electronics, appliances, textiles, auto parts)
- **Volume inconsistency**: Import volumes exceed the absorptive capacity of the
  destination market for that commodity

### Detection Thresholds

- `D_rel > 0.30` for consumer goods (HS 84-85, 61-62, 87) from the US to
  Colombia, Mexico, Venezuela, Peru, Ecuador, Brazil, Panama, Guatemala,
  Dominican Republic
- Unit price > 150% of global median for the same HS code
- Corridor volume growth > 30% year-over-year without corresponding GDP or
  population growth in the importing country

### False Positive Sources

- **Legitimate price premiums**: US-branded goods may command higher prices in
  Latin American markets (brand premium, warranty, local tax effects).
- **Exchange rate movements**: A depreciating local currency inflates USD-
  denominated import values relative to the prior year.
- **Economic growth**: Emerging markets may legitimately increase imports rapidly.
- **Different product mix**: Within an HS code, the US may export higher-end
  variants than the global average.

---

## 12. Abnormal Unit Price Deviations vs. Global Benchmarks

### Scheme Description

This is a cross-cutting detection method rather than a single scheme. Any TBML
typology that involves price manipulation (over/under-invoicing, misclassification)
will produce declared unit prices that deviate from global commodity benchmarks.

### Mirror Data Signature

```
UP_declared >> UP_benchmark   (over-invoicing)
UP_declared << UP_benchmark   (under-invoicing)
```

Where `UP_benchmark` is derived from:
- Global median unit price for the HS code across all Comtrade corridors
- Commodity exchange reference prices (LBMA for gold, Brent/WTI for crude, LME
  for base metals)
- Historical unit price for the same corridor

### Detection Thresholds

- Declared unit price deviates by more than 2 standard deviations from the global
  median for that HS code at the 4-digit or 6-digit level
- For exchange-traded commodities: declared unit price deviates by more than 15%
  from the reference price for the relevant period
- Sudden unit price change: year-over-year change in corridor unit price > 50%
  when the global benchmark has not moved proportionally

### False Positive Sources

- **Quality/grade variation**: Within an HS code, products vary enormously in
  quality and price (e.g., HS 7108 covers gold bars and gold powder at very
  different unit prices).
- **Aggregation effects**: Comtrade unit prices are averages across all
  transactions in a corridor. A change in product mix shifts the average without
  any individual transaction being anomalous.
- **Processing stage**: Raw vs. semi-processed vs. finished goods within the same
  HS code.
- **Volume discounts**: Large-volume purchases legitimately carry lower unit prices.
- **Incoterms differences**: DDP (delivered duty paid) includes more cost
  components than FOB, inflating the apparent unit price.

---

## 13. Smurfing / Structured Trade

### Scheme Description

A large illicit trade flow is broken into many smaller transactions to avoid
detection thresholds. Each individual transaction falls below minimum value or
discrepancy thresholds, but in aggregate they constitute a significant anomaly.
This is the trade analogue of financial "structuring" (breaking deposits into
sub-$10K amounts to avoid CTR filing).

**Variants**:
- **HS code splitting**: A $50M shipment of gold is declared across 10 different
  HS sub-codes (7108.11, 7108.12, 7108.13, etc.), each below threshold
- **Temporal splitting**: The same corridor-commodity flow is spread across
  multiple months so no single month triggers a flag
- **Partner splitting**: Trade is routed through multiple intermediary countries
  so no single bilateral corridor exceeds thresholds
- **Entity splitting**: Multiple related shell companies each handle a portion
  of the flow (invisible in aggregate Comtrade data, but detectable at
  tariff-line level if available)

### Mirror Data Signature

No single mirror pair shows a large discrepancy. Instead:

```
Many flows with D_rel clustered just below threshold (e.g., 0.08-0.09 when
  threshold is 0.10)
Same corridor, many HS codes, all with small positive (or negative) D_rel
Aggregate D_rel across all HS codes for the corridor exceeds threshold
```

Statistically, natural discrepancies should be distributed around zero with
variance. Clustering just below a threshold is itself an anomaly signal.

### Detection Thresholds

- Aggregate `D_rel` across all HS codes for a corridor exceeds 25% when
  individual codes are all below 10%
- Number of distinct 4-digit HS codes in a corridor doubles year-over-year
- Distribution of sub-threshold `D_rel` values fails a uniformity test (clusters
  near the threshold boundary)
- More than 10 individually sub-threshold flows in the same corridor-period

### False Positive Sources

- **Diversified legitimate trade**: Countries with broad trade relationships
  naturally have many small flows across many HS codes. The key distinguishing
  factor is whether the discrepancies are systematically directional.
- **Small trade volumes**: When total corridor value is low (< USD 1M), many
  sub-threshold flows may be normal noise.

---

## 14. Partner Code Opacity (Areas NES Abuse)

### Scheme Description

Some countries report a significant share of their trade with partner code 899
("Areas Not Elsewhere Specified") or other aggregate/unspecified partner codes.
These flows cannot be mirror-matched because no specific partner country claims
the corresponding side. Actors exploiting this report trade to NES to make flows
invisible to bilateral analysis.

### Mirror Data Signature

```
Reporter reports V_exp > 0 to partner "899" (Areas NES)
No mirror pair exists — no specific country claims the import
```

The flow is entirely opaque to mirror analysis. Detection relies on monitoring
the NES share rather than bilateral comparison.

### Detection Thresholds

- Country's NES-reported trade exceeds 10% of total trade value
- NES share increases by more than 5 percentage points year-over-year
- NES trade concentrated in high-risk commodities (HS 71, 27, 97)
- NES trade volume exceeds USD 100M

### False Positive Sources

- **Legitimate confidentiality**: Some countries use NES codes for genuine
  national security suppression (military equipment, nuclear materials).
- **Statistical rounding**: Very small trade flows may be grouped into NES to
  protect commercial confidentiality of individual traders.
- **Newly independent territories**: Trade with territories whose ISO codes are
  not yet in the reporter's customs system may temporarily appear as NES.

---

## Appendix A: Typology Interaction Matrix

Multiple TBML schemes often co-occur. The detection engine should look for
combinations:

| Primary Typology | Commonly Combined With |
|---|---|
| Over-invoicing imports | FTZ opacity, BMPE, transfer pricing |
| Under-invoicing exports | Capital flight corridors, concentration anomalies |
| Phantom shipments | Shell companies in secrecy jurisdictions, NES code abuse |
| Carousel/round-tripping | VAT fraud, misclassification, smurfing |
| Misclassification | Over/under-invoicing, sanction evasion |
| Multiple invoicing | Phantom shipments, FTZ opacity |
| Smurfing/structuring | All invoice manipulation types, misclassification |
| NES code opacity | Phantom shipments, under-invoicing exports |

When two or more typology indicators co-occur for the same corridor, increase the
severity score (see `detection-spec.md` Section 4).

---

## Appendix B: FATF/Egmont Group Reference

This typology catalogue aligns with the following FATF and Egmont Group
publications:

- FATF (2006), "Trade-Based Money Laundering" — foundational typology definitions
- FATF (2008), "Best Practices on Trade-Based Money Laundering" — detection
  guidance for financial institutions
- APG/FATF (2012), "APG Typologies Report: Trade-Based Money Laundering" — Asian
  regional patterns
- Egmont Group / FATF (2020), "Trade-Based Money Laundering: Trends and
  Developments" — updated typologies including digital trade
- FATF (2021), "Money Laundering from Environmental Crime" — commodity-specific
  TBML (timber, minerals, wildlife)

The HS code risk ratings in the severity scoring rubric (detection-spec.md Section
4.1, Component 5) are derived from these sources and from academic research on
TBML commodity patterns (Zdanowicz 2009, Ferwerda et al. 2013, Naheem 2016).
