# Detection Logic Specification

Technical specification for the mirror trade analysis engine. This document defines
the formulas, normalization rules, statistical methods, scoring rubric, and data
quality considerations that the analytics module must implement.

---

## 1. Core Discrepancy Metrics

All metrics operate on a **bilateral corridor** defined by:
- Reporter country (ISO 3166-1 alpha-3)
- Partner country (ISO 3166-1 alpha-3)
- Commodity code (HS 2-digit, 4-digit, or 6-digit)
- Year (Comtrade annual data) or Year+Month (monthly data)
- Trade flow direction

### 1.1 Mirror Pair Construction

For every corridor, the engine must locate the **mirror pair**:

| Side A (Exporter report) | Side B (Importer report) |
|---|---|
| Country X reports **exports** to Country Y | Country Y reports **imports** from Country X |

Both values are in **current USD** as reported to UN Comtrade.

Let:
- `V_exp` = value reported by the exporting country
- `V_imp` = value reported by the importing country
- `Q_exp` = quantity (kg or supplementary unit) reported by the exporter
- `Q_imp` = quantity reported by the importer

### 1.2 Absolute Discrepancy

```
D_abs = V_imp - V_exp
```

Positive values mean the importer reports more than the exporter (potential
over-invoicing on the import side or under-invoicing on the export side).

### 1.3 Relative Discrepancy (Normalized)

```
D_rel = (V_imp - V_exp) / ((V_imp + V_exp) / 2)
```

This is the percentage discrepancy normalized by the midpoint of the two reported
values. Range: `(-2, +2)`. A value of 0 means perfect agreement.

**Why midpoint normalization**: Dividing by only one side biases the metric when one
side reports zero or near-zero. The midpoint formula is symmetric and bounded.

### 1.4 Log Ratio

```
D_log = ln(V_imp / V_exp)
```

Only valid when both values are strictly positive. Symmetric around 0 (i.e.,
`ln(2) = -ln(0.5)`). Useful for multiplicative comparisons and for inputs to
z-score calculations where the distribution of discrepancies is log-normal.

### 1.5 Quantity Discrepancy

```
Q_rel = (Q_imp - Q_exp) / ((Q_imp + Q_exp) / 2)
```

Same formula as value discrepancy but applied to physical quantities. Comparing
value and quantity discrepancies can distinguish price manipulation from
reporting errors: if quantities match but values diverge, price manipulation is
more likely.

### 1.6 Unit Price Discrepancy

```
UP_exp = V_exp / Q_exp
UP_imp = V_imp / Q_imp
UP_rel = (UP_imp - UP_exp) / ((UP_imp + UP_exp) / 2)
```

Unit price discrepancy isolates the price dimension from volume effects.

---

## 2. Normalization Rules

Raw mirror discrepancies contain systematic biases that must be corrected before
flagging anomalies. The normalization pipeline applies corrections in this order:

### 2.1 CIF/FOB Adjustment

**Problem**: Exporters typically report FOB (Free on Board) values. Importers
typically report CIF (Cost, Insurance, Freight) values. CIF > FOB by the cost of
shipping and insurance, creating a systematic positive discrepancy even for
legitimate trade.

**Adjustment factors by transport mode**:

| Transport Mode | Typical CIF/FOB Ratio | Range |
|---|---|---|
| Maritime (bulk commodities) | 1.05 - 1.10 | 1.02 - 1.15 |
| Maritime (containerized) | 1.06 - 1.12 | 1.03 - 1.18 |
| Air freight | 1.10 - 1.25 | 1.05 - 1.40 |
| Land (adjacent countries) | 1.02 - 1.05 | 1.01 - 1.08 |
| Pipeline (oil/gas) | 1.01 - 1.03 | 1.005 - 1.05 |

**Implementation**:

```python
def adjust_cif_fob(
    v_imp: float,
    v_exp: float,
    transport_mode: str,
    distance_km: float | None = None,
) -> tuple[float, float]:
    """
    Adjust importer value downward by estimated CIF/FOB ratio.

    Returns (v_imp_adjusted, cif_fob_ratio_used).
    """
    # Default ratios by transport mode
    BASE_RATIOS: dict[str, float] = {
        "maritime_bulk": 1.07,
        "maritime_container": 1.09,
        "air": 1.15,
        "land": 1.03,
        "pipeline": 1.02,
    }
    ratio = BASE_RATIOS.get(transport_mode, 1.07)  # default to maritime bulk

    # Optional: scale by distance for maritime/air
    if distance_km is not None and transport_mode in ("maritime_bulk", "maritime_container", "air"):
        # Linear interpolation: short routes get lower adjustment
        distance_factor = min(distance_km / 20000, 1.0)  # cap at 20,000 km
        ratio = 1.0 + (ratio - 1.0) * (0.5 + 0.5 * distance_factor)

    v_imp_adjusted = v_imp / ratio
    return v_imp_adjusted, ratio
```

When transport mode is unknown (the common case with Comtrade data), use a
**corridor-level default** based on the geographic relationship:
- Same continent, land border: 1.03
- Same continent, no land border: 1.07
- Intercontinental: 1.10
- Unknown: 1.07

**After adjustment**, recalculate `D_rel` using `V_imp_adjusted` in place of `V_imp`.

### 2.2 Reporting Lag Correction

**Problem**: Country A may report 2024 exports in its 2024 submission, but Country B
may not report the corresponding 2024 imports until its 2025 submission. Goods
shipped in December may clear customs in January. Monthly data is more affected
than annual data.

**Lag windows**:

| Data frequency | Typical lag | Maximum lag to check |
|---|---|---|
| Annual | 0 years | 1 year |
| Monthly | 0-2 months | 3 months |

**Implementation**:

For annual data, when a mirror pair shows a large discrepancy for year `t`:
1. Check if the discrepancy reverses or compensates in year `t+1`
2. Compute a **2-year rolling average** of both sides and compare
3. Flag only if the discrepancy persists across the rolling window

For monthly data:
1. Apply a **3-month rolling sum** to both sides before computing discrepancies
2. This smooths out timing differences in customs processing

```python
def apply_lag_correction(
    corridor_timeseries: list[dict],
    frequency: str,  # "annual" or "monthly"
) -> list[dict]:
    """
    Apply rolling window smoothing to absorb reporting lags.

    Each dict in corridor_timeseries has keys:
        period, v_exp, v_imp, v_imp_adjusted (after CIF/FOB)

    Returns the same list with added keys:
        v_exp_smoothed, v_imp_smoothed, d_rel_smoothed
    """
    if frequency == "annual":
        window = 2
    else:
        window = 3

    for i in range(len(corridor_timeseries)):
        start = max(0, i - window + 1)
        chunk = corridor_timeseries[start : i + 1]
        v_exp_sum = sum(r["v_exp"] for r in chunk)
        v_imp_sum = sum(r["v_imp_adjusted"] for r in chunk)
        corridor_timeseries[i]["v_exp_smoothed"] = v_exp_sum / len(chunk)
        corridor_timeseries[i]["v_imp_smoothed"] = v_imp_sum / len(chunk)
        midpoint = (v_exp_sum + v_imp_sum) / 2
        if midpoint > 0:
            corridor_timeseries[i]["d_rel_smoothed"] = (v_imp_sum - v_exp_sum) / midpoint
        else:
            corridor_timeseries[i]["d_rel_smoothed"] = 0.0

    return corridor_timeseries
```

### 2.3 Re-export Correction

**Problem**: Country A exports goods to Country B, which re-exports to Country C.
Country A reports exports to B. Country C may report imports from A (origin-based)
or from B (last-shipped-from basis). This creates phantom discrepancies.

**Known re-export hubs**: Hong Kong SAR, Singapore, Netherlands, Belgium, UAE
(Dubai), Panama, Switzerland (for commodities).

**Heuristic corrections**:

1. **Flag, don't auto-correct**: Re-export patterns are complex. The engine should
   flag corridors involving known re-export hubs and reduce their severity score
   rather than attempt automatic correction.

2. **Triangulation check**: For a flagged corridor A->C, check whether:
   - A reports significant exports to hub H
   - H reports significant imports from A
   - H reports significant exports to C
   - C reports significant imports from H
   If all four conditions hold, the A->C discrepancy may be a re-export artifact.

3. **Adjustment**: When triangulation is confirmed, add a `re_export_flag: bool`
   and `re_export_hub: str | None` to the output. Reduce severity score by 1 tier
   (see Section 4).

### 2.4 Currency and Rounding

Comtrade values are in current USD. No currency conversion is needed. However:
- Some countries round to the nearest thousand USD. Check for suspiciously round
  numbers (all three trailing digits = 0) and flag minor discrepancies (<1%) as
  potential rounding artifacts.
- When reported values are below USD 1,000, percentage discrepancies become
  unreliable. Apply a **minimum value threshold** of USD 10,000 for annual data
  or USD 1,000 for monthly data. Exclude flows below this threshold from
  anomaly detection.

---

## 3. Statistical Methods

### 3.1 Z-Score Against Historical Corridor Baseline

For each corridor (reporter-partner-commodity triple), compute the historical
distribution of `D_rel` (after normalization) over all available years.

```
z_corridor = (D_rel_current - mean(D_rel_history)) / std(D_rel_history)
```

**Requirements**:
- Minimum 5 years of historical data to compute a reliable baseline
- If fewer years are available, fall back to the commodity-level global baseline
  (across all corridors for the same HS code)
- Use **robust statistics** when possible: median instead of mean, MAD (median
  absolute deviation) instead of standard deviation, to reduce sensitivity to
  outliers in the baseline itself

```python
import numpy as np

def z_score_corridor(
    d_rel_current: float,
    d_rel_history: list[float],
    min_history: int = 5,
) -> float | None:
    """
    Compute z-score of current discrepancy against corridor history.

    Returns None if insufficient history.
    """
    if len(d_rel_history) < min_history:
        return None

    arr = np.array(d_rel_history)
    median = np.median(arr)
    mad = np.median(np.abs(arr - median))
    # Scale MAD to be consistent with std for normal distributions
    mad_scaled = mad * 1.4826

    if mad_scaled < 1e-9:
        # No variation in history — any deviation is anomalous
        return float("inf") if abs(d_rel_current - median) > 1e-9 else 0.0

    return (d_rel_current - median) / mad_scaled
```

**Thresholds**:

| Z-score (absolute) | Interpretation |
|---|---|
| < 2.0 | Within normal variation |
| 2.0 - 3.0 | Elevated — warrants review |
| 3.0 - 5.0 | High — likely anomalous |
| > 5.0 | Extreme — strong investigative signal |

### 3.2 Rolling Window Deviation

For corridors with monthly data, compute a **12-month rolling z-score** to detect
regime changes (e.g., a corridor that was clean for years suddenly develops
persistent discrepancies).

```python
def rolling_zscore(
    d_rel_series: list[float],
    window: int = 12,
) -> list[float | None]:
    """
    Compute rolling z-score for each point using the preceding window.

    Returns list of z-scores (None for the first `window` entries).
    """
    results: list[float | None] = []
    for i in range(len(d_rel_series)):
        if i < window:
            results.append(None)
            continue
        history = d_rel_series[i - window : i]
        arr = np.array(history)
        median = np.median(arr)
        mad = np.median(np.abs(arr - median)) * 1.4826
        if mad < 1e-9:
            z = float("inf") if abs(d_rel_series[i] - median) > 1e-9 else 0.0
        else:
            z = (d_rel_series[i] - median) / mad
        results.append(z)
    return results
```

### 3.3 Benford's Law on Declared Values

Benford's Law predicts the frequency distribution of leading digits in naturally
occurring numerical datasets. Declared trade values that deviate from Benford's
expected distribution may indicate fabricated or manipulated invoices.

**Application**: For a given corridor-commodity pair, collect all individual
transaction values (where available from Comtrade Plus or tariff-line data) or
annual/monthly aggregates. Extract the first significant digit and compare to the
expected distribution.

**Expected first-digit frequencies (Benford's Law)**:

| Digit | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| Frequency | 0.301 | 0.176 | 0.125 | 0.097 | 0.079 | 0.067 | 0.058 | 0.051 | 0.046 |

**Test**: Chi-squared goodness-of-fit test or Kolmogorov-Smirnov test.

```python
from scipy import stats

def benford_test(
    values: list[float],
    min_samples: int = 50,
) -> dict[str, float] | None:
    """
    Test whether the distribution of first significant digits of `values`
    conforms to Benford's Law.

    Returns dict with chi2 statistic, p-value, and MAD (mean absolute
    deviation from Benford's expected frequencies).
    Returns None if fewer than min_samples values.
    """
    if len(values) < min_samples:
        return None

    benford_expected = {
        d: np.log10(1 + 1 / d) for d in range(1, 10)
    }

    # Extract first significant digit
    first_digits: list[int] = []
    for v in values:
        if v <= 0:
            continue
        s = f"{v:.10e}"
        for ch in s:
            if ch.isdigit() and ch != "0":
                first_digits.append(int(ch))
                break

    if len(first_digits) < min_samples:
        return None

    n = len(first_digits)
    observed = np.zeros(9)
    for d in first_digits:
        observed[d - 1] += 1

    expected = np.array([benford_expected[d] * n for d in range(1, 10)])

    chi2, p_value = stats.chisquare(observed, f_exp=expected)
    mad = np.mean(np.abs(observed / n - np.array([benford_expected[d] for d in range(1, 10)])))

    return {
        "chi2": float(chi2),
        "p_value": float(p_value),
        "mad": float(mad),
        "n_samples": n,
    }
```

**Interpretation**:
- p-value < 0.01: Strong evidence of non-conformity — flag for review
- p-value < 0.05: Moderate evidence — include in composite score
- MAD > 0.015: Significant deviation regardless of p-value

**Caveats**: Benford's Law works best on datasets spanning multiple orders of
magnitude. Narrowly distributed values (e.g., a single commodity at similar price
levels) may not conform even for legitimate trade. Always combine with other
indicators.

### 3.4 Correlation Analysis for Commodity Signatures

Some commodities have known geological, compositional, or seasonal signatures that
constrain plausible trade patterns. When metadata is available:

**Pearson correlation**: For continuous commodity attributes (e.g., gold purity
percentages, crude oil API gravity) that should correlate with declared origin.

**Spearman rank correlation**: For ordinal or non-linear relationships (e.g., HS
code complexity vs. declared value per kg — high-tech goods should have higher
unit values).

```python
def correlation_check(
    declared_values: list[float],
    reference_values: list[float],
    method: str = "spearman",  # or "pearson"
) -> dict[str, float]:
    """
    Check correlation between declared trade values and a reference series
    (e.g., global benchmark prices, expected seasonal pattern).
    """
    if method == "pearson":
        r, p = stats.pearsonr(declared_values, reference_values)
    else:
        r, p = stats.spearmanr(declared_values, reference_values)

    return {"correlation": float(r), "p_value": float(p), "method": method}
```

**Application examples**:
- Compare declared unit prices for gold (HS 7108) against London Bullion Market
  daily fix prices. Low correlation → suspicious.
- Compare declared crude oil volumes against seasonal refinery demand patterns.
- Check if declared electronics unit values correlate with known component cost
  indices.

### 3.5 Asymmetric Discrepancy Detection

TBML often creates **directional** discrepancies (consistently in one direction
over time). Legitimate noise is symmetric. Test for asymmetry using a one-sample
sign test or Wilcoxon signed-rank test on the series of `D_rel` values for a
corridor.

```python
def asymmetry_test(
    d_rel_series: list[float],
    min_samples: int = 5,
) -> dict[str, float] | None:
    """
    Test whether discrepancies are systematically biased in one direction.
    Uses Wilcoxon signed-rank test against zero.
    """
    if len(d_rel_series) < min_samples:
        return None

    arr = np.array(d_rel_series)
    # Remove exact zeros
    arr = arr[arr != 0]
    if len(arr) < min_samples:
        return None

    stat, p_value = stats.wilcoxon(arr, alternative="two-sided")
    direction = "import_over" if np.median(arr) > 0 else "export_over"

    return {
        "statistic": float(stat),
        "p_value": float(p_value),
        "direction": direction,
        "median_discrepancy": float(np.median(arr)),
    }
```

---

## 4. Severity Scoring Rubric

Each flagged flow receives a composite severity score from 0-100 that ranks it
by investigative priority. The score combines multiple dimensions.

### 4.1 Component Scores

Each component produces a score from 0 to 20. The total is the sum of all
components, capped at 100.

#### Component 1: Magnitude of Discrepancy (0-20)

Based on `D_rel` after CIF/FOB adjustment:

| |D_rel| (absolute) | Score |
|---|---|
| < 0.10 (< 10%) | 0 |
| 0.10 - 0.25 | 5 |
| 0.25 - 0.50 | 10 |
| 0.50 - 1.00 | 15 |
| > 1.00 (> 100%) | 20 |

#### Component 2: Statistical Anomaly (0-20)

Based on `z_corridor` (z-score against historical baseline):

| |z_corridor| | Score |
|---|---|
| < 2.0 | 0 |
| 2.0 - 3.0 | 5 |
| 3.0 - 4.0 | 10 |
| 4.0 - 5.0 | 15 |
| > 5.0 | 20 |

#### Component 3: Persistence Over Time (0-20)

Number of consecutive periods (years for annual, months for monthly) where the
discrepancy exceeds 10% in the same direction:

| Consecutive periods | Score |
|---|---|
| 1 | 0 |
| 2 | 5 |
| 3 | 10 |
| 4-5 | 15 |
| 6+ | 20 |

#### Component 4: Corridor Risk Profile (0-20)

Based on the jurisdiction risk indicators (see `docs/jurisdiction-risk.md`):

| Risk factor | Points |
|---|---|
| One partner is a secrecy jurisdiction | +5 |
| One partner is a known re-export hub | +3 |
| One partner is a free trade zone territory | +4 |
| One partner is a non-reporting or late-reporting country | +5 |
| Corridor has known narcotics trafficking routes | +5 |
| Both partners are FATF-compliant, low-risk | +0 |

Cap at 20. Sum all applicable risk factors.

#### Component 5: Commodity Risk Profile (0-20)

Based on commodity characteristics:

| Commodity category (HS chapter) | Risk score |
|---|---|
| Gold, precious metals (71) | 20 |
| Precious/semi-precious stones (71) | 18 |
| Art, antiques, collectibles (97) | 18 |
| Petroleum, crude oil (27) | 15 |
| Pharmaceuticals (30) | 15 |
| Electronics, semiconductors (84-85) | 12 |
| Chemicals (28-29) | 10 |
| Textiles, apparel (50-63) | 8 |
| Agricultural products (01-24) | 5 |
| Manufactured goods (general) | 3 |
| Other / unknown | 5 |

### 4.2 Composite Score Calculation

```python
@dataclass
class SeverityScore:
    magnitude: int          # 0-20
    statistical_anomaly: int  # 0-20
    persistence: int        # 0-20
    corridor_risk: int      # 0-20
    commodity_risk: int     # 0-20
    adjustments: int        # negative adjustments
    total: int              # 0-100

def compute_severity(
    d_rel: float,
    z_score: float | None,
    consecutive_periods: int,
    corridor_risk_factors: list[str],
    hs_chapter: int,
    re_export_flag: bool = False,
    rounding_flag: bool = False,
) -> SeverityScore:
    """Compute composite severity score."""

    # Component 1: Magnitude
    abs_d = abs(d_rel)
    if abs_d > 1.0:
        magnitude = 20
    elif abs_d > 0.50:
        magnitude = 15
    elif abs_d > 0.25:
        magnitude = 10
    elif abs_d > 0.10:
        magnitude = 5
    else:
        magnitude = 0

    # Component 2: Statistical anomaly
    if z_score is None:
        statistical_anomaly = 5  # Unknown = moderate baseline
    elif abs(z_score) > 5.0:
        statistical_anomaly = 20
    elif abs(z_score) > 4.0:
        statistical_anomaly = 15
    elif abs(z_score) > 3.0:
        statistical_anomaly = 10
    elif abs(z_score) > 2.0:
        statistical_anomaly = 5
    else:
        statistical_anomaly = 0

    # Component 3: Persistence
    if consecutive_periods >= 6:
        persistence = 20
    elif consecutive_periods >= 4:
        persistence = 15
    elif consecutive_periods >= 3:
        persistence = 10
    elif consecutive_periods >= 2:
        persistence = 5
    else:
        persistence = 0

    # Component 4: Corridor risk (from risk factors)
    RISK_POINTS: dict[str, int] = {
        "secrecy_jurisdiction": 5,
        "re_export_hub": 3,
        "free_trade_zone": 4,
        "non_reporting": 5,
        "narcotics_route": 5,
    }
    corridor_risk = min(20, sum(
        RISK_POINTS.get(f, 0) for f in corridor_risk_factors
    ))

    # Component 5: Commodity risk
    COMMODITY_RISK: dict[int, int] = {
        71: 20, 97: 18, 27: 15, 30: 15,
    }
    commodity_risk = COMMODITY_RISK.get(hs_chapter, 5)
    if 84 <= hs_chapter <= 85:
        commodity_risk = 12
    elif 28 <= hs_chapter <= 29:
        commodity_risk = 10
    elif 50 <= hs_chapter <= 63:
        commodity_risk = 8
    elif 1 <= hs_chapter <= 24:
        commodity_risk = 5

    # Adjustments (negative)
    adjustments = 0
    if re_export_flag:
        adjustments -= 10  # Reduce priority for likely re-export artifacts
    if rounding_flag:
        adjustments -= 5   # Reduce for rounding-only discrepancies

    total = max(0, min(100,
        magnitude + statistical_anomaly + persistence +
        corridor_risk + commodity_risk + adjustments
    ))

    return SeverityScore(
        magnitude=magnitude,
        statistical_anomaly=statistical_anomaly,
        persistence=persistence,
        corridor_risk=corridor_risk,
        commodity_risk=commodity_risk,
        adjustments=adjustments,
        total=total,
    )
```

### 4.3 Priority Tiers

| Score range | Tier | Action |
|---|---|---|
| 80-100 | Critical | Immediate investigative follow-up |
| 60-79 | High | Include in analyst review queue |
| 40-59 | Medium | Flag for periodic review |
| 20-39 | Low | Log for trend analysis only |
| 0-19 | Noise | Suppress from default view |

---

## 5. Known Comtrade Data Quality Issues

The engine must account for systematic data quality problems that create
false positives or blind spots.

### 5.1 Non-Reporting Countries

The following countries/territories have significant gaps in their Comtrade
reporting. Discrepancies involving these jurisdictions should be interpreted
with caution (the discrepancy may simply reflect missing data, not
manipulation):

**Chronically non-reporting or severely delayed** (as of 2024):
- Afghanistan
- Chad
- Democratic Republic of Congo
- Equatorial Guinea
- Eritrea
- Guinea-Bissau
- Libya
- North Korea (DPRK)
- Somalia
- South Sudan
- Syria
- Turkmenistan
- Yemen

**Intermittently reporting** (gaps of 1-3 years common):
- Iraq
- Lebanon
- Myanmar
- Venezuela
- Zimbabwe

**Implementation**: When one partner in a mirror pair is a non-reporting country,
mark the flow with `data_quality: "partner_non_reporting"` and exclude from
automated anomaly detection. Present these flows in a separate "data gap" report.

### 5.2 Confidential Trade Suppression

Many countries suppress trade data for specific commodities or partners
to protect commercial confidentiality or national security.

**Common suppression patterns**:
- **United States**: Suppresses flows for specific HS codes related to defense,
  nuclear materials, and some agricultural products. Confidential values appear
  as HS 9999 aggregate or are simply omitted.
- **Canada**: Uses "Country 0" partner code for suppressed bilateral flows.
  Suppresses low-valued trade to avoid disclosure of individual traders.
- **Australia**: Suppresses specific mineral exports (e.g., uranium, rare earths)
  at tariff-line level.
- **EU member states**: May suppress intra-EU flows for sensitive goods. Eurostat
  publishes aggregate EU trade but member-state-level data may be suppressed.
- **China**: Selective suppression of strategic commodity flows (rare earths,
  certain electronics). Increasing restrictions on sub-annual granularity.
- **Russia**: Post-2022, significant increase in suppressed flows across
  commodities and partners.
- **Multiple countries**: Defense articles (HS 93 and dual-use items under various
  chapters) are commonly suppressed. Rare earth elements (HS 2846, 2805) are
  increasingly treated as strategic by China, US, Australia, and others.
  Agricultural subsidies data (sugar, cotton, dairy in the US and EU) may be
  partially suppressed at tariff-line level to avoid WTO dispute exposure.
- **Japan**: Suppresses specific technology exports under catch-all controls.
- **India**: Intermittent suppression of defense imports and some mineral exports.

**Implementation**: The engine should maintain a `confidential_suppression` lookup
table mapping (country, HS code range) to known suppression policies. When a
mirror pair involves a suppressed flow, flag it as `data_quality: "likely_suppressed"`
rather than treating the missing side as a phantom shipment.

### 5.3 Commodity Code Inconsistencies

**HS code version mismatches**: Comtrade data spans HS revisions (HS 1992, 1996,
2002, 2007, 2012, 2017, 2022). The same physical good may be classified under
different codes across revisions. UN Comtrade provides concordance tables, but
edge cases persist.

**Known problematic HS chapters**:
- **HS 84-85** (machinery, electronics): Rapidly evolving product categories lead
  to classification ambiguity (e.g., smartphones classified as phones vs.
  computers).
- **HS 27** (mineral fuels): Blending and processing changes classification
  (crude vs. refined products).
- **HS 71** (precious metals/stones): High value density makes small classification
  shifts create large value discrepancies.
- **HS 30** (pharmaceuticals): Generic vs. branded, bulk vs. retail packaging
  creates classification ambiguity.
- **HS 38** (miscellaneous chemical products): Catch-all category with
  heterogeneous contents.

**Implementation**: For HS chapters with known classification issues, widen the
acceptable discrepancy threshold by a configurable factor (default: 1.5x the
normal threshold). Log the wider threshold in output metadata.

### 5.4 EU Aggregate vs. Member-State Reporting

**Problem**: Some partner countries report trade with "EU" as a single entity,
while individual EU member states report separately. This creates systematic
double-counting and missing mirror pairs.

**Specific issues**:
- Pre-2020 UK data: UK reported as both individual country and part of EU aggregate
- Intra-EU trade: Collected via Intrastat (sample-based for small traders), leading
  to undercount of low-value intra-EU flows
- EU28 vs EU27 transition: Data spanning the 2020 Brexit boundary requires careful
  handling of UK inclusion/exclusion
- Some non-EU countries report exports to "Areas NES" (Not Elsewhere Specified)
  which may include EU aggregate flows

**Implementation**:
1. When a partner reports trade with EU aggregate (partner code 97), do NOT attempt
   to match against individual member states.
2. Provide a configuration option to aggregate member-state data to EU level for
   comparison purposes.
3. Flag intra-EU flows with `data_quality: "intrastat_estimate"` and apply wider
   thresholds.

### 5.5 Quantity Unit Mismatches

Comtrade reports quantities in kilograms (net weight) and/or supplementary units
(e.g., number of items, liters, square meters). Not all countries report both.

**Common problems**:
- One side reports in kg, the other in supplementary units — makes quantity
  comparison impossible
- Unit conversion errors (e.g., metric tons reported in the kg field)
- Missing quantity data (value reported but quantity is zero or null)

**Implementation**: Only compute quantity-based metrics (`Q_rel`, `UP_rel`) when
both sides report in the same unit. When units differ, set quantity metrics to
`None` and note `data_quality: "unit_mismatch"`.

### 5.6 Time Period Alignment

**Problem**: Not all countries report on the same fiscal year basis. Most use
calendar year, but some have fiscal years starting in April (e.g., India), July
(e.g., Australia), or October (e.g., United States federal fiscal year, though
trade data is typically calendar year).

Comtrade normalizes to calendar year for annual data, but monthly data near
fiscal year boundaries may have alignment issues.

**Implementation**: Use calendar year as the standard reference period. For monthly
analysis, allow a configurable alignment window (default: +/- 1 month) when
comparing mirror pairs involving countries with non-calendar fiscal years.

---

## 6. Output Schema

Each detected anomaly produces a record with the following structure:

```python
from dataclasses import dataclass, field
from datetime import date

@dataclass
class AnomalyRecord:
    # Identifiers
    reporter_iso3: str
    partner_iso3: str
    hs_code: str              # 2, 4, or 6 digit HS code
    period: str               # "2024" or "2024-06"
    flow_direction: str       # "export" or "import"

    # Raw values
    v_exp: float
    v_imp: float
    q_exp: float | None
    q_imp: float | None

    # Normalized values
    v_imp_adjusted: float     # After CIF/FOB adjustment
    cif_fob_ratio: float      # Ratio used for adjustment

    # Discrepancy metrics
    d_abs: float
    d_rel: float              # After normalization
    d_rel_raw: float          # Before normalization
    d_log: float | None       # None if either value is zero
    q_rel: float | None       # None if quantity data unavailable
    up_rel: float | None      # None if unit price not computable

    # Statistical metrics
    z_score_corridor: float | None
    z_score_rolling: float | None
    benford_pvalue: float | None
    asymmetry_pvalue: float | None

    # Scoring
    severity: SeverityScore

    # Context
    data_quality_flags: list[str] = field(default_factory=list)
    re_export_flag: bool = False
    re_export_hub: str | None = None
    corridor_risk_factors: list[str] = field(default_factory=list)

    # Metadata
    analysis_date: date = field(default_factory=date.today)
    comtrade_data_revision: str | None = None
```

### 6.1 Filtering and Presentation

The engine should support filtering anomaly records by:
- Minimum severity score
- Priority tier
- Reporter or partner country
- HS code or chapter
- Time period range
- Specific data quality flags (include/exclude)
- Specific risk factors

Default output should be sorted by `severity.total` descending.

---

## 7. Processing Pipeline Summary

The analytics engine should process data in this order:

```
1. Data Ingestion
   └── Load Comtrade bilateral trade data for target corridors/periods

2. Mirror Pair Construction
   └── Match export records from Country A with import records from Country B

3. Raw Discrepancy Calculation
   └── Compute D_abs, D_rel, D_log, Q_rel, UP_rel for each mirror pair

4. Normalization
   ├── CIF/FOB adjustment (Section 2.1)
   ├── Reporting lag smoothing (Section 2.2)
   ├── Re-export triangulation check (Section 2.3)
   └── Rounding and minimum value filters (Section 2.4)

5. Statistical Analysis
   ├── Z-score against corridor history (Section 3.1)
   ├── Rolling window z-score (Section 3.2)
   ├── Benford's Law test (Section 3.3)
   ├── Correlation analysis where applicable (Section 3.4)
   └── Asymmetry test (Section 3.5)

6. Severity Scoring
   └── Compute composite score per Section 4

7. Output
   ├── Generate AnomalyRecord for each flagged flow
   ├── Filter by minimum severity threshold
   └── Sort by severity descending
```

Each stage should be implemented as a separate, testable module. The pipeline
should be idempotent: running it twice on the same input produces the same output.

---

## 8. Advanced Detection Methods

These methods address evasion techniques that bypass the bilateral mirror analysis
described in Sections 1-6. They are computationally more expensive and should be
run as a second pass after the primary pipeline.

### 8.1 Graph-Based Carousel / Multi-Hop Detection

**Problem**: Carousel and round-tripping schemes (see `tbml-typologies.md` Section
7) distribute value across multiple corridor legs. Each individual leg may show
only moderate discrepancies (below thresholds), but the circular pattern as a
whole is anomalous. Bilateral-only analysis misses this entirely.

**Method**: Build a directed trade flow graph per commodity per period, then search
for cycles.

```python
from collections import defaultdict

def detect_circular_flows(
    trade_flows: list[dict],
    hs_code: str,
    period: str,
    volume_tolerance: float = 0.20,
    min_value_usd: float = 100_000,
    max_cycle_length: int = 5,
) -> list[dict]:
    """
    Detect circular trade flows for a given commodity and period.

    Args:
        trade_flows: List of dicts with keys: exporter_iso3, importer_iso3, value
        hs_code: HS code being analyzed
        period: Time period
        volume_tolerance: Max allowed variation between leg values (0.20 = 20%)
        min_value_usd: Minimum leg value to consider
        max_cycle_length: Maximum number of hops in a cycle

    Returns:
        List of detected cycles, each with participants and values.
    """
    # Build adjacency list
    graph: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for flow in trade_flows:
        if flow["value"] >= min_value_usd:
            graph[flow["exporter_iso3"]].append(
                (flow["importer_iso3"], flow["value"])
            )

    cycles: list[dict] = []

    def dfs(
        start: str,
        current: str,
        path: list[tuple[str, str, float]],
        visited: set[str],
    ) -> None:
        if len(path) > max_cycle_length:
            return
        for neighbor, value in graph[current]:
            if neighbor == start and len(path) >= 2:
                # Found a cycle — check volume consistency
                values = [v for _, _, v in path]
                min_v, max_v = min(values), max(values)
                if max_v > 0 and (max_v - min_v) / max_v <= volume_tolerance:
                    cycles.append({
                        "participants": [s for s, _, _ in path],
                        "legs": path,
                        "hs_code": hs_code,
                        "period": period,
                        "mean_value": sum(values) / len(values),
                        "volume_spread": (max_v - min_v) / max_v,
                    })
            elif neighbor not in visited:
                visited.add(neighbor)
                path.append((current, neighbor, value))
                dfs(start, neighbor, path, visited)
                path.pop()
                visited.remove(neighbor)

    for node in graph:
        dfs(node, node, [], {node})

    return cycles
```

**Scoring**: Detected cycles add a bonus to severity for all participating
corridors:
- 2-hop cycle (A->B->A): +5 to severity (common in legitimate re-export)
- 3-hop cycle: +10
- 4+ hop cycle: +15
- All legs involve same HS code without processing: additional +5

### 8.2 Fuzzy HS Code Matching for Misclassification Detection

**Problem**: When the exporter reports HS 7108 (gold) and the importer reports HS
7112 (gold waste/scrap), the mirror join on exact HS code produces two phantom
shipment alerts instead of one misclassification alert. This is a critical gap.

**Method**: In addition to exact HS code matching, perform a fuzzy match within
the same 2-digit HS chapter, looking for complementary discrepancies.

```python
def fuzzy_hs_match(
    unmatched_exports: list[dict],
    unmatched_imports: list[dict],
    value_tolerance: float = 0.30,
) -> list[dict]:
    """
    Attempt to match unmatched one-sided flows within the same HS chapter.

    Each dict has keys: reporter_iso3, partner_iso3, hs_code, period, value

    Returns list of suspected misclassification pairs.
    """
    matches: list[dict] = []

    # Group by corridor and period
    export_groups: dict[tuple, list[dict]] = defaultdict(list)
    import_groups: dict[tuple, list[dict]] = defaultdict(list)

    for e in unmatched_exports:
        key = (e["reporter_iso3"], e["partner_iso3"], e["period"])
        export_groups[key].append(e)

    for i in unmatched_imports:
        # For imports, the "corridor" is reversed: importer reports, partner is exporter
        key = (i["partner_iso3"], i["reporter_iso3"], i["period"])
        import_groups[key].append(i)

    for corridor_key in export_groups:
        if corridor_key not in import_groups:
            continue

        exports = export_groups[corridor_key]
        imports = import_groups[corridor_key]

        for exp in exports:
            exp_chapter = exp["hs_code"][:2]
            for imp in imports:
                imp_chapter = imp["hs_code"][:2]
                if exp_chapter != imp_chapter:
                    continue
                if exp["hs_code"] == imp["hs_code"]:
                    continue  # Already matched exactly

                # Check value similarity
                mid = (exp["value"] + imp["value"]) / 2
                if mid > 0 and abs(exp["value"] - imp["value"]) / mid <= value_tolerance:
                    matches.append({
                        "export_record": exp,
                        "import_record": imp,
                        "hs_chapter": exp_chapter,
                        "export_hs": exp["hs_code"],
                        "import_hs": imp["hs_code"],
                        "value_discrepancy": abs(exp["value"] - imp["value"]),
                        "typology": "suspected_misclassification",
                    })

    return matches
```

**Pipeline integration**: Run fuzzy matching after Step 2 (Mirror Pair
Construction). Any flows matched by fuzzy HS should be:
1. Removed from the phantom shipment candidate list
2. Added to the misclassification candidate list with elevated severity
3. Flagged with `detection_method: "fuzzy_hs_match"`

### 8.3 Smurfing / Structured Trade Detection

**Problem**: A single large illicit flow (e.g., $50M phantom shipment) can be
split into many smaller flows across slightly different HS codes, time periods,
or intermediary countries, each falling below detection thresholds individually.

**Method**: Aggregate analysis at the corridor level (ignoring HS code
granularity) and at the entity cluster level (grouping related corridors).

```python
def detect_structuring(
    corridor_flows: list[dict],
    reporter_iso3: str,
    partner_iso3: str,
    period: str,
    individual_threshold: float = 0.10,  # 10% D_rel — below normal flag
    aggregate_threshold: float = 0.25,   # 25% D_rel — flagging level
) -> dict | None:
    """
    Check whether individually sub-threshold flows aggregate to an
    above-threshold discrepancy at the corridor level.

    Each dict in corridor_flows has: hs_code, v_exp, v_imp, d_rel
    """
    # Filter to flows that individually fall below the flag threshold
    sub_threshold = [f for f in corridor_flows if abs(f["d_rel"]) < individual_threshold]

    if not sub_threshold:
        return None

    total_v_exp = sum(f["v_exp"] for f in sub_threshold)
    total_v_imp = sum(f["v_imp"] for f in sub_threshold)
    mid = (total_v_exp + total_v_imp) / 2

    if mid <= 0:
        return None

    aggregate_d_rel = (total_v_imp - total_v_exp) / mid

    if abs(aggregate_d_rel) >= aggregate_threshold:
        return {
            "reporter_iso3": reporter_iso3,
            "partner_iso3": partner_iso3,
            "period": period,
            "n_sub_threshold_flows": len(sub_threshold),
            "n_hs_codes": len(set(f["hs_code"] for f in sub_threshold)),
            "aggregate_v_exp": total_v_exp,
            "aggregate_v_imp": total_v_imp,
            "aggregate_d_rel": aggregate_d_rel,
            "typology": "suspected_structuring",
        }
    return None
```

**Additional heuristics**:
- Many flows in the same corridor with `D_rel` clustered just below the flagging
  threshold (between 0.08 and 0.10 when threshold is 0.10): statistically unlikely
  in natural data
- Sudden proliferation of HS codes in a corridor: if the number of distinct 4-digit
  codes traded between A and B doubles year-over-year, check whether the new codes
  carry discrepancies in the same direction

### 8.4 Areas NES and Partner Code Opacity

**Problem**: Some countries report trade with partner code 899 ("Areas Not
Elsewhere Specified") or similar catch-all codes. These flows are invisible to
mirror analysis because no partner country claims the corresponding side.

**Method**: Track the share of each country's total trade reported to NES/unspecified
partners. A high or growing NES share is suspicious.

```python
NES_PARTNER_CODES: set[str] = {
    "899",  # Areas NES
    "636",  # Areas NES (alternate)
    "0",    # Unspecified (Canada-style)
    "97",   # EU aggregate (context-dependent)
    "290",  # Other Asia NES
    "490",  # Other Europe NES
    "890",  # Other Africa NES
}

def nes_share_analysis(
    country_flows: list[dict],
    reporter_iso3: str,
    period: str,
    nes_share_threshold: float = 0.10,
) -> dict | None:
    """
    Compute the share of a country's total trade reported to NES/unspecified partners.

    Flag if the share exceeds threshold or has increased significantly.
    """
    total_value = sum(f["value"] for f in country_flows)
    nes_value = sum(
        f["value"] for f in country_flows
        if f["partner_code"] in NES_PARTNER_CODES
    )

    if total_value <= 0:
        return None

    nes_share = nes_value / total_value

    if nes_share >= nes_share_threshold:
        return {
            "reporter_iso3": reporter_iso3,
            "period": period,
            "nes_value_usd": nes_value,
            "total_value_usd": total_value,
            "nes_share": nes_share,
            "flag": "high_nes_share",
        }
    return None
```

### 8.5 Preliminary vs. Revised Data Detection

**Problem**: Comtrade data undergoes revisions. Preliminary figures may differ
significantly from final figures. Analysts comparing data at different revision
stages may see discrepancies that are simply data quality evolution.

**Method**: Track the `data_revision` field in Comtrade metadata. When available:
1. Compare the same flow across data revisions
2. Flag corridors where preliminary-to-final revision changes exceed 10%
3. Exclude discrepancies that are attributable to revision timing from the anomaly
   list
4. Add `data_quality: "preliminary_data"` flag when the most recent revision is
   less than 12 months old

### 8.6 EU Member-State Aggregation Mode

**Problem**: When a non-EU country reports trade with individual EU member states,
but the corresponding mirror side is reported only at the EU aggregate level, no
bilateral match is possible.

**Implementation**: Provide an optional aggregation mode:

```python
EU27_MEMBERS: set[str] = {
    "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST",
    "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA",
    "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK",
    "SVN", "ESP", "SWE",
}

def aggregate_eu_flows(
    flows: list[dict],
    period: str,
) -> list[dict]:
    """
    Aggregate individual EU member state flows into a single EU27 entity.

    Use when the mirror partner reports to EU aggregate.
    Only aggregate flows where the reporter or partner is an EU member state.
    """
    aggregated: dict[tuple, dict] = {}

    for flow in flows:
        reporter = flow["reporter_iso3"]
        partner = flow["partner_iso3"]

        # Determine if aggregation applies
        if reporter in EU27_MEMBERS:
            agg_reporter = "EU27"
            agg_partner = partner
        elif partner in EU27_MEMBERS:
            agg_reporter = reporter
            agg_partner = "EU27"
        else:
            agg_reporter = reporter
            agg_partner = partner

        key = (agg_reporter, agg_partner, flow["hs_code"], flow["flow_direction"])

        if key not in aggregated:
            aggregated[key] = {
                "reporter_iso3": agg_reporter,
                "partner_iso3": agg_partner,
                "hs_code": flow["hs_code"],
                "period": period,
                "flow_direction": flow["flow_direction"],
                "value": 0.0,
                "quantity": 0.0,
                "member_states": [],
                "aggregated": True,
            }

        aggregated[key]["value"] += flow.get("value", 0.0)
        aggregated[key]["quantity"] += flow.get("quantity", 0.0)
        if reporter in EU27_MEMBERS:
            aggregated[key]["member_states"].append(reporter)
        elif partner in EU27_MEMBERS:
            aggregated[key]["member_states"].append(partner)

    return list(aggregated.values())
```

---

## 9. Evasion-Aware Severity Adjustments

The base severity scoring in Section 4 should be supplemented with bonuses when
advanced detection methods (Section 8) identify evasion-pattern indicators.

### 9.1 Multi-Typology Co-occurrence Bonus

When two or more distinct typology indicators fire for the same corridor in the
same period, apply a co-occurrence bonus:

| Number of co-occurring typologies | Bonus |
|---|---|
| 2 | +5 |
| 3 | +10 |
| 4+ | +15 |

### 9.2 Structuring Indicator Bonus

When the smurfing/structuring detector (Section 8.3) identifies aggregate
discrepancies composed of individually sub-threshold flows:

| Number of sub-threshold flows | Bonus |
|---|---|
| 5-10 | +5 |
| 11-20 | +10 |
| 20+ | +15 |

### 9.3 Re-export Hub Adjustment Calibration

The base -10 adjustment for re-export hubs (Section 4.2) is insufficient for some
corridors. Calibrate based on the hub's re-export ratio:

| Re-export hub | Typical re-export share | Adjustment |
|---|---|---|
| Hong Kong SAR | ~98% | -15 |
| Singapore | ~45% | -10 |
| Netherlands | ~55% | -12 |
| Belgium | ~35% | -8 |
| UAE | ~30% | -7 |
| Panama | ~25% | -5 |

### 9.4 CIF/FOB Confidence Band

Replace the single-point CIF/FOB ratio with a confidence band. Only flag
discrepancies that exceed the **upper bound** of the expected CIF/FOB range for
the transport mode:

```python
CIF_FOB_BANDS: dict[str, tuple[float, float]] = {
    "maritime_bulk": (1.02, 1.15),
    "maritime_container": (1.03, 1.18),
    "air": (1.05, 1.40),
    "land": (1.01, 1.08),
    "pipeline": (1.005, 1.05),
    "flowers_air": (1.15, 1.30),   # High-value perishables by air
    "bulk_ore": (1.02, 1.06),      # Low CIF/FOB for heavy bulk
}

def is_within_cif_fob_band(
    d_rel: float,
    transport_mode: str,
) -> bool:
    """
    Check if a positive discrepancy falls within the expected CIF/FOB band.
    Only applies to positive D_rel (import > export).
    """
    if d_rel <= 0:
        return False
    low, high = CIF_FOB_BANDS.get(transport_mode, (1.02, 1.15))
    # Convert band to D_rel equivalent
    # D_rel = (V_imp - V_exp) / midpoint ≈ 2*(ratio-1)/(ratio+1)
    d_rel_high = 2 * (high - 1) / (high + 1)
    return d_rel <= d_rel_high
```

---

## 10. Known Limitations and Out-of-Scope

The following patterns are documented for completeness but are **not detectable**
through Comtrade mirror analysis alone:

1. **Services-based value transfer**: Parallel services invoices (consulting fees,
   IP licensing, management fees) that explain monetary transfers while goods
   flows appear normal. Comtrade covers goods trade only; services data requires
   BOP/EBOPS datasets.

2. **Intra-firm transfer pricing within arm's-length bounds**: Multinational
   corporations may use transfer pricing that creates persistent mirror
   discrepancies. If pricing falls within OECD Transfer Pricing Guidelines
   ranges, it is indistinguishable from TBML in aggregate data.

3. **Hawala and informal value transfer**: Value transfer through informal banking
   channels leaves no trade data footprint whatsoever.

4. **Cryptocurrency-settled trade**: Payments settled outside the banking system
   may not be reflected in customs declarations.

5. **Physical smuggling**: Goods that physically bypass customs entirely produce
   no Comtrade records on either side.

Investigative journalists using this tool should be aware that mirror analysis is
one lens among several. Findings should be corroborated with corporate registry
data, shipping records, financial disclosures, and local investigative reporting.

---

## 11. Configuration Parameters

All thresholds and adjustment factors should be configurable. Default values are
specified throughout this document. The engine should accept a configuration
object:

```python
@dataclass
class DetectionConfig:
    # CIF/FOB
    cif_fob_default_ratio: float = 1.07
    cif_fob_ratios: dict[str, float] = field(default_factory=lambda: {
        "maritime_bulk": 1.07,
        "maritime_container": 1.09,
        "air": 1.15,
        "land": 1.03,
        "pipeline": 1.02,
    })

    # Lag correction
    annual_smoothing_window: int = 2
    monthly_smoothing_window: int = 3

    # Value thresholds
    min_annual_value_usd: float = 10_000
    min_monthly_value_usd: float = 1_000

    # Z-score
    min_history_years: int = 5
    z_score_elevated: float = 2.0
    z_score_high: float = 3.0
    z_score_extreme: float = 5.0

    # Benford
    benford_min_samples: int = 50
    benford_pvalue_threshold: float = 0.01

    # Severity
    severity_noise_max: int = 19
    severity_low_max: int = 39
    severity_medium_max: int = 59
    severity_high_max: int = 79

    # HS code classification tolerance
    problematic_hs_chapters: list[int] = field(default_factory=lambda: [
        27, 30, 38, 71, 84, 85,
    ])
    classification_tolerance_factor: float = 1.5

    # Minimum discrepancy to flag
    min_d_rel_to_flag: float = 0.10  # 10%
```
