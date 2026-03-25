# Jurisdictional Risk Indicators

Risk profiles for countries and territories relevant to trade-based money laundering
detection. This document informs the corridor risk component of the severity scoring
rubric (see `detection-spec.md` Section 4.1, Component 4).

---

## 1. Free Trade Zones and Freeports

Free trade zones (FTZs) reduce or eliminate customs reporting requirements, creating
opacity that can be exploited for TBML. The following FTZs are particularly
significant due to their scale, strategic location, or history of misuse.

### High-Risk FTZs

**Jebel Ali Free Zone (JAFZA), UAE**
- The world's largest FTZ by trade volume. Located in Dubai.
- Rationale: Hub for gold, electronics, and commodity re-exports. Multiple FATF
  and US Treasury investigations have linked JAFZA entities to sanctions evasion
  and trade misinvoicing. UAE's federal customs data does not fully capture intra-
  FTZ transactions.
- Commodities of concern: Gold (HS 71), electronics (HS 84-85), petroleum products
  (HS 27), precious stones.

**Colon Free Zone, Panama**
- Second-largest FTZ globally. Major re-export hub for the Americas.
- Rationale: Documented role in BMPE schemes. Goods enter duty-free and are
  re-exported to Latin American markets, often with altered invoicing. Panama's
  overall AML framework has been repeatedly flagged by FATF (grey-listed 2014,
  2019-2023).
- Commodities of concern: Consumer electronics, pharmaceuticals, textiles, auto
  parts.

**Hong Kong SAR**
- Functions as a de facto FTZ for the entire territory (zero tariffs on nearly all
  goods).
- Rationale: The world's largest re-export economy. Re-exports account for ~98% of
  total exports. Creates massive mirror discrepancies in Comtrade because partner
  countries may report origin-based or last-shipped-from-based trade differently.
  Also a documented conduit for mainland China capital flight.
- Commodities of concern: Electronics, gold, jewelry, watches, commodities in
  transit.

**Singapore Free Trade Zones (Jurong, Changi, etc.)**
- Major transshipment hub for Southeast Asia.
- Rationale: High volume of in-transit goods that may not appear in Singapore's
  import/export statistics. Documented role in commodity trade misinvoicing
  (particularly petroleum and palm oil). Strong AML framework but high throughput
  creates monitoring challenges.
- Commodities of concern: Petroleum (HS 27), palm oil (HS 1511), electronics,
  chemicals.

**Labuan, Malaysia**
- Offshore financial center and FTZ.
- Rationale: Combination of FTZ status with offshore financial services. Used for
  commodity trade financing with limited transparency. Malaysian authorities have
  identified Labuan-linked TBML schemes in palm oil and timber.
- Commodities of concern: Palm oil, timber (HS 44), petroleum.

### Moderate-Risk FTZs

| Jurisdiction | Key FTZ | Concern |
|---|---|---|
| Turkey | Various (22 FTZs) | Gold re-exports, textile misinvoicing |
| Uruguay | Zona Franca de Montevideo | Regional re-export hub, financial opacity |
| Paraguay | Ciudad del Este | Consumer goods smuggling, triple border area |
| Philippines | Various (Subic, Clark) | Electronics re-export, garment misinvoicing |
| Jordan | Aqaba SEZ | Re-export to Iraq, sanctions circumvention risk |
| Bahrain | Various | Gold and jewelry re-export |
| Mauritius | Freeport | Commodity transit, Africa-Asia trade |

### European Freeports

European freeports deserve special mention due to their role in high-value goods
storage:

| Freeport | Concern |
|---|---|
| Geneva Freeport (Switzerland) | Art, gold, precious stones storage with minimal reporting |
| Luxembourg Freeport | Art and luxury goods |
| Delaware FTZ (United States) | Shell company formation, limited beneficial ownership disclosure |

These facilities allow goods to be stored indefinitely without import declarations,
enabling value transformation and re-invoicing.

---

## 2. Secrecy Jurisdictions

Countries and territories with strong financial secrecy laws that facilitate the
concealment of beneficial ownership, making it difficult to trace TBML proceeds.

### Tier 1: Highest Secrecy Concern

**British Virgin Islands (BVI)**
- Rationale: Estimated 400,000+ active companies, many shell entities with no
  public beneficial ownership register. Frequently used as the registered
  jurisdiction for trading companies involved in commodity misinvoicing. Limited
  customs reporting to Comtrade.
- TBML relevance: BVI-registered entities frequently appear as intermediaries in
  trade chains, particularly for precious metals, oil, and mining commodities.

**Panama**
- Rationale: Despite reforms post-Panama Papers, bearer shares were only recently
  abolished. Large FTZ (Colon). Financial secrecy combined with trade opacity.
  Grey-listed by FATF multiple times.
- TBML relevance: Combined FTZ + secrecy jurisdiction status makes Panama a
  critical node. Re-invoicing through Panama-registered entities is a documented
  TBML technique.

**Cayman Islands**
- Rationale: Major offshore financial center. Limited domestic trade but
  Cayman-registered entities are common in international trade finance structures.
- TBML relevance: Cayman SPVs used in commodity trade financing.

**Switzerland**
- Rationale: Banking secrecy (reduced but not eliminated post-CRS). Geneva freeport.
  World's largest commodity trading hub (Trafigura, Vitol, Glencore headquartered
  there). Customs data is reported but commodity trading through Swiss-based
  intermediaries creates complex ownership chains.
- TBML relevance: Swiss commodity traders handle an estimated 35% of global oil
  trade and 50% of global coffee trade. Misinvoicing through Swiss intermediaries
  is a documented pattern.

### Tier 2: Significant Secrecy Concern

| Jurisdiction | Key Concern |
|---|---|
| Liechtenstein | Private foundations, trust structures |
| Jersey, Guernsey, Isle of Man | UK Crown Dependencies with financial secrecy |
| Bermuda | Insurance and reinsurance structures used in trade |
| Luxembourg | Holding company structures, EU passporting |
| Seychelles | Easy company formation, limited oversight |
| Samoa | Offshore trusts, limited Comtrade reporting |
| Vanuatu | Citizenship-by-investment, offshore banking |
| Marshall Islands | Ship registration, shell companies |
| Belize | IBC formation, banking secrecy |

---

## 3. Weak Customs Reporting Jurisdictions

Countries with limited capacity to collect, validate, or report trade statistics.
Discrepancies involving these countries may reflect data quality issues rather than
TBML, but also create exploitable gaps.

### Chronically Non-Reporting to Comtrade

These countries have multi-year gaps in Comtrade data:

| Country | Last reliable report | Issue |
|---|---|---|
| North Korea (DPRK) | Never | Sanctions, no UN reporting |
| Somalia | Sporadic | State fragility, no functioning customs |
| South Sudan | Sporadic | Conflict, minimal customs infrastructure |
| Eritrea | Sporadic | Isolation, limited international reporting |
| Syria | ~2010 | Conflict disruption |
| Yemen | ~2014 | Conflict disruption |
| Libya | Sporadic | Post-2011 state fragmentation |
| Afghanistan | ~2019 | Government collapse, Taliban takeover |
| Turkmenistan | Sporadic | Authoritarian opacity, selective reporting |

### Intermittently Reporting

| Country | Issue |
|---|---|
| Iraq | Gaps during conflict years; improving post-2018 |
| Venezuela | Increasingly sporadic since 2016; sanctions effects |
| Myanmar | Disrupted since 2021 coup |
| Lebanon | Economic collapse since 2019 reduced reporting capacity |
| Zimbabwe | Periodic data gaps; hyperinflation distorts values |
| Cuba | Limited reporting; US sanctions complicate data |
| Equatorial Guinea | Oil exports poorly documented |
| Chad | Minimal customs infrastructure |
| Guinea-Bissau | State fragility |

### Weak Customs Capacity (Reports but with Known Quality Issues)

| Country | Issue |
|---|---|
| DRC (Congo) | Mining exports (coltan, cobalt, gold) significantly under-reported |
| Nigeria | Oil exports subject to discrepancies; artisanal gold unreported |
| Angola | Oil exports generally reported; diamond trade opacity |
| Papua New Guinea | Mining and forestry exports under-documented |
| Central African Republic | Gold and diamond exports significantly under-reported |
| Mozambique | Improving but gas/mineral exports have gaps |
| Laos | Timber and mineral exports poorly documented |
| Cambodia | Garment exports generally reported; other sectors less so |

---

## 4. Transit and Transshipment Hubs by Commodity

### Gold (HS 71)

| Hub | Role | Risk Level |
|---|---|---|
| UAE (Dubai) | Refining, re-export | Very High |
| Switzerland (Ticino, Geneva) | Refining, trading | Very High |
| Hong Kong SAR | Trading, re-export to China | High |
| United Kingdom (London) | LBMA trading hub | Moderate |
| India (Mumbai) | Import, processing | Moderate |
| South Africa (Johannesburg) | Mining, export | Moderate |
| Turkey (Istanbul) | Refining, transit to Europe | High |
| Togo | Transit for West African artisanal gold | High |
| Uganda | Transit for DRC/South Sudan gold | Very High |
| Rwanda | Transit for DRC conflict minerals | High |

**Specific concern**: Artisanal and small-scale mining (ASM) gold from conflict
zones (DRC, Sudan, Central African Republic, Venezuela) enters the formal supply
chain through transit hubs where it is mixed with legitimately sourced gold and
re-documented.

### Petroleum and Mineral Fuels (HS 27)

| Hub | Role | Risk Level |
|---|---|---|
| Singapore | Trading, storage, bunkering | High |
| UAE (Fujairah) | Storage, blending, re-export | High |
| Netherlands (Rotterdam) | Trading, refining | Moderate |
| Malta | Ship-to-ship transfers | High |
| Malaysia (Johor) | Bunkering, re-export | Moderate |
| Nigeria (offshore) | Ship-to-ship transfers | Very High |
| Panama | Canal transit, bunkering | Moderate |
| Curacao | Venezuelan oil transit | High |

**Specific concern**: Ship-to-ship (STS) transfers at sea, particularly off the
coasts of West Africa, Southeast Asia, and in the Mediterranean. STS transfers
can disguise the origin of sanctioned oil (Iranian, Venezuelan, Russian) and
create Comtrade mirror gaps because neither the loading nor receiving country may
report the transaction.

### Electronics and Semiconductors (HS 84-85)

| Hub | Role | Risk Level |
|---|---|---|
| Hong Kong SAR | Re-export, value chain intermediary | High |
| Singapore | Re-export, distribution | Moderate |
| Taiwan | Manufacturing, re-export | Low |
| South Korea | Manufacturing | Low |
| Panama (Colon FTZ) | Re-export to Americas | High |
| UAE (Dubai) | Re-export to Middle East, Africa | High |
| Paraguay (Ciudad del Este) | Smuggling, informal re-export | Very High |
| Turkey | Re-export to Central Asia | Moderate |

**Specific concern**: Used electronics and e-waste trade. Declared as "used
electronics" but may be waste (illegal under Basel Convention) or may be used
to justify payments for non-existent goods.

### Precious and Semi-Precious Stones (HS 71)

| Hub | Role | Risk Level |
|---|---|---|
| Belgium (Antwerp) | Diamond trading, cutting | Moderate |
| India (Surat, Mumbai) | Diamond cutting, re-export | Moderate |
| UAE (Dubai) | Diamond and gemstone trading | High |
| Israel (Ramat Gan) | Diamond trading | Moderate |
| Thailand (Bangkok) | Gemstone trading, cutting | High |
| Sri Lanka (Colombo) | Gemstone export | Moderate |
| Hong Kong SAR | Jade, gemstone re-export | High |
| Tanzania (Arusha) | Tanzanite, gemstone export | High |

**Specific concern**: Valuation opacity. Unlike gold, most precious and semi-
precious stones have no standardized benchmark price. Valuation is subjective,
making price manipulation extremely difficult to detect and easy to justify.

### Chemicals and Pharmaceuticals (HS 28-30, 38)

| Hub | Role | Risk Level |
|---|---|---|
| India | Generic pharmaceutical manufacturing | Moderate |
| China | Bulk chemical and API manufacturing | Moderate |
| Singapore | Chemical trading | Moderate |
| Switzerland | Pharmaceutical trading | Moderate |
| Belgium | Chemical distribution | Low |
| Netherlands | Chemical distribution | Low |
| Pakistan | Pharmaceutical transit | High |
| Nigeria | Pharmaceutical import (counterfeit risk) | High |
| UAE | Pharmaceutical re-export | High |

**Specific concern**: Precursor chemicals for illicit drug production (ephedrine,
pseudoephedrine, acetic anhydride) are traded under legitimate HS codes. Diversion
through transit hubs creates TBML opportunities where the trade value discrepancy
masks the true nature of the transaction.

### Textiles and Apparel (HS 50-63)

| Hub | Role | Risk Level |
|---|---|---|
| Bangladesh | Manufacturing, export | Moderate |
| Vietnam | Manufacturing, export | Low |
| China | Manufacturing, export | Moderate |
| Turkey | Manufacturing, re-export | Moderate |
| UAE (Dubai) | Re-export to Africa | High |
| Hong Kong SAR | Trading, transit | High |
| Cambodia | Manufacturing | Moderate |
| Guatemala | Transit to US | High |

**Specific concern**: The high volume and low unit value of textile trade makes
it attractive for TBML. Small percentage price manipulations on large volumes
generate significant illicit financial flows without triggering per-transaction
alerts.

---

## 5. Country Risk Classification for Scoring

The following classification feeds into the severity scoring rubric
(detection-spec.md, Section 4.1, Component 4). Countries may appear in multiple
categories.

### Risk Factor: `secrecy_jurisdiction`

Jurisdictions where beneficial ownership opacity enables TBML:

BVI, Panama, Cayman Islands, Switzerland, Liechtenstein, Jersey, Guernsey, Isle of
Man, Bermuda, Luxembourg (for holding structures), Seychelles, Samoa, Vanuatu,
Marshall Islands, Belize, Bahamas, Antigua and Barbuda, Dominica (citizenship by
investment), St. Kitts and Nevis, Turks and Caicos.

### Risk Factor: `re_export_hub`

Jurisdictions where significant re-export activity creates mirror data complexity:

Hong Kong SAR, Singapore, Netherlands, Belgium, UAE, Panama, Switzerland (for
commodities), Malaysia (Labuan), Mauritius.

### Risk Factor: `free_trade_zone`

Jurisdictions with major FTZs that reduce customs reporting granularity:

UAE (JAFZA, multiple others), Panama (Colon), Hong Kong SAR (territory-wide),
Singapore, Labuan (Malaysia), Uruguay, Paraguay, Jordan (Aqaba), Bahrain, Turkey
(22 FTZs), Philippines (Subic, Clark), Switzerland (Geneva freeport).

### Risk Factor: `non_reporting`

Jurisdictions with absent or severely deficient Comtrade reporting (see Section 3
above for full list). Includes: DPRK, Somalia, South Sudan, Eritrea, Syria, Yemen,
Libya, Afghanistan, Turkmenistan, Iraq, Venezuela, Myanmar, Lebanon.

### Risk Factor: `narcotics_route`

Corridors associated with narcotics trafficking where trade flows may be linked
to drug money laundering:

- **Latin America - US**: Colombia, Mexico, Peru, Bolivia, Ecuador, Venezuela,
  Guatemala, Honduras, El Salvador, Dominican Republic
- **Afghanistan - Europe**: Afghanistan, Iran, Turkey, Balkans route (Bulgaria,
  Serbia, Kosovo, Albania)
- **Golden Triangle**: Myanmar, Laos, Thailand
- **West Africa transit**: Guinea-Bissau, Senegal, Gambia, Ghana, Nigeria, Benin,
  Togo

### Implementation Note

```python
JURISDICTION_RISK: dict[str, list[str]] = {
    "secrecy_jurisdiction": [
        "VGB", "PAN", "CYM", "CHE", "LIE", "JEY", "GGY", "IMN",
        "BMU", "LUX", "SYC", "WSM", "VUT", "MHL", "BLZ", "BHS",
        "ATG", "DMA", "KNA", "TCA",
    ],
    "re_export_hub": [
        "HKG", "SGP", "NLD", "BEL", "ARE", "PAN", "CHE", "MYS", "MUS",
    ],
    "free_trade_zone": [
        "ARE", "PAN", "HKG", "SGP", "MYS", "URY", "PRY", "JOR",
        "BHR", "TUR", "PHL", "CHE",
    ],
    "non_reporting": [
        "PRK", "SOM", "SSD", "ERI", "SYR", "YEM", "LBY", "AFG",
        "TKM", "IRQ", "VEN", "MMR", "LBN",
    ],
    "narcotics_route": [
        "COL", "MEX", "PER", "BOL", "ECU", "VEN", "GTM", "HND",
        "SLV", "DOM", "AFG", "IRN", "TUR", "BGR", "SRB", "XKX",
        "ALB", "MMR", "LAO", "THA", "GNB", "SEN", "GMB", "GHA",
        "NGA", "BEN", "TGO",
    ],
}


def get_corridor_risk_factors(
    reporter_iso3: str,
    partner_iso3: str,
) -> list[str]:
    """
    Return list of risk factor keys applicable to a bilateral corridor.
    A factor is triggered if either the reporter or partner is in the list.
    """
    factors: list[str] = []
    for factor, countries in JURISDICTION_RISK.items():
        if reporter_iso3 in countries or partner_iso3 in countries:
            factors.append(factor)
    return factors
```

---

## 6. Data Sources for Risk Updates

Jurisdictional risk profiles change over time. The following sources should be
monitored for updates:

| Source | What it provides | Update frequency |
|---|---|---|
| FATF Mutual Evaluations | AML/CFT compliance ratings | Per country (rolling) |
| FATF High-Risk / Grey List | Countries under increased monitoring | 3x per year (Feb, Jun, Oct) |
| EU List of Non-Cooperative Jurisdictions | Tax haven blacklist | Updated annually |
| US Treasury OFAC SDN List | Sanctioned entities and countries | Continuous |
| Tax Justice Network Financial Secrecy Index | Secrecy scoring by jurisdiction | Biennial |
| Basel AML Index | Country ML/TF risk scoring | Annual |
| Transparency International CPI | Corruption perception | Annual |
| UN Comtrade Reporter Metadata | Which countries report and when | Continuous |
| OECD CRS participation | Tax information exchange | Annual |
