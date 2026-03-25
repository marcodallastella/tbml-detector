"""UN Comtrade country code mappings: ISO 3166-1 alpha-3 ↔ Comtrade numeric IDs.

Sources:
- UN Comtrade Reporters reference:
  https://comtradeapi.un.org/files/v1/app/reference/Reporters.json
- UN Comtrade Partner Areas reference:
  https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json

The CLI accepts ISO 3166-1 alpha-3 codes (e.g. ``SAU``, ``PER``, ``GBR``).
Internally these are converted to Comtrade numeric IDs before API calls.
Numeric IDs are still accepted for backwards compatibility.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# ISO3 → Comtrade numeric reporter ID
# ---------------------------------------------------------------------------
# Based on Reporters.json. Where a country has both a historical entry (e.g.
# "India (...1974)", id=356) and a modern entry ("India", id=699), the modern
# id is used.  Numeric IDs are still accepted as input everywhere.
# ---------------------------------------------------------------------------

ISO3_TO_ID: dict[str, int] = {
    "ABW": 533,   # Aruba
    "AFG": 4,     # Afghanistan
    "AGO": 24,    # Angola
    "AIA": 660,   # Anguilla
    "ALB": 8,     # Albania
    "AND": 20,    # Andorra
    "ARE": 784,   # United Arab Emirates
    "ARG": 32,    # Argentina
    "ARM": 51,    # Armenia
    "ATG": 28,    # Antigua and Barbuda
    "AUS": 36,    # Australia
    "AUT": 40,    # Austria
    "AZE": 31,    # Azerbaijan
    "BDI": 108,   # Burundi
    "BEL": 56,    # Belgium
    "BEN": 204,   # Benin
    "BES": 535,   # Bonaire, Sint Eustatius and Saba
    "BFA": 854,   # Burkina Faso
    "BGD": 50,    # Bangladesh
    "BGR": 100,   # Bulgaria
    "BHR": 48,    # Bahrain
    "BHS": 44,    # Bahamas
    "BIH": 70,    # Bosnia Herzegovina
    "BLM": 652,   # Saint Barthélemy
    "BLR": 112,   # Belarus
    "BLZ": 84,    # Belize
    "BMU": 60,    # Bermuda
    "BOL": 68,    # Bolivia (Plurinational State of)
    "BRA": 76,    # Brazil
    "BRB": 52,    # Barbados
    "BRN": 96,    # Brunei Darussalam
    "BTN": 64,    # Bhutan
    "BWA": 72,    # Botswana
    "CAF": 140,   # Central African Republic
    "CAN": 124,   # Canada
    "CHE": 757,   # Switzerland (reporter code; partner code is 756)
    "CHL": 152,   # Chile
    "CHN": 156,   # China
    "CIV": 384,   # Côte d'Ivoire
    "CMR": 120,   # Cameroon
    "COD": 180,   # Democratic Republic of the Congo
    "COG": 178,   # Congo
    "COK": 184,   # Cook Islands
    "COL": 170,   # Colombia
    "COM": 174,   # Comoros
    "CPV": 132,   # Cabo Verde
    "CRI": 188,   # Costa Rica
    "CUB": 192,   # Cuba
    "CUW": 531,   # Curaçao
    "CYM": 136,   # Cayman Islands
    "CYP": 196,   # Cyprus
    "CZE": 203,   # Czechia
    "DEU": 276,   # Germany
    "DJI": 262,   # Djibouti
    "DMA": 212,   # Dominica
    "DNK": 208,   # Denmark
    "DOM": 214,   # Dominican Republic
    "DZA": 12,    # Algeria
    "ECU": 218,   # Ecuador
    "EGY": 818,   # Egypt
    "ERI": 232,   # Eritrea
    "ESP": 724,   # Spain
    "EST": 233,   # Estonia
    "ETH": 231,   # Ethiopia
    "EUR": 97,    # European Union
    "FIN": 246,   # Finland
    "FJI": 242,   # Fiji
    "FRA": 251,   # France
    "FRO": 234,   # Faroe Islands
    "FSM": 583,   # Micronesia (Federated States of)
    "GAB": 266,   # Gabon
    "GBR": 826,   # United Kingdom
    "GEO": 268,   # Georgia
    "GHA": 288,   # Ghana
    "GIB": 292,   # Gibraltar
    "GIN": 324,   # Guinea
    "GLP": 312,   # Guadeloupe
    "GMB": 270,   # Gambia
    "GNB": 624,   # Guinea-Bissau
    "GNQ": 226,   # Equatorial Guinea
    "GRC": 300,   # Greece
    "GRD": 308,   # Grenada
    "GRL": 304,   # Greenland
    "GTM": 320,   # Guatemala
    "GUF": 254,   # French Guiana
    "GUY": 328,   # Guyana
    "HKG": 344,   # China, Hong Kong SAR
    "HND": 340,   # Honduras
    "HRV": 191,   # Croatia
    "HTI": 332,   # Haiti
    "HUN": 348,   # Hungary
    "IDN": 360,   # Indonesia
    "IND": 699,   # India
    "IRL": 372,   # Ireland
    "IRN": 364,   # Iran
    "IRQ": 368,   # Iraq
    "ISL": 352,   # Iceland
    "ISR": 376,   # Israel
    "ITA": 380,   # Italy
    "JAM": 388,   # Jamaica
    "JOR": 400,   # Jordan
    "JPN": 392,   # Japan
    "KAZ": 398,   # Kazakhstan
    "KEN": 404,   # Kenya
    "KGZ": 417,   # Kyrgyzstan
    "KHM": 116,   # Cambodia
    "KIR": 296,   # Kiribati
    "KNA": 659,   # Saint Kitts and Nevis
    "KOR": 410,   # Republic of Korea
    "KWT": 414,   # Kuwait
    "LAO": 418,   # Lao People's Democratic Republic
    "LBN": 422,   # Lebanon
    "LBR": 430,   # Liberia
    "LBY": 434,   # Libya
    "LCA": 662,   # Saint Lucia
    "LKA": 144,   # Sri Lanka
    "LSO": 426,   # Lesotho
    "LTU": 440,   # Lithuania
    "LUX": 442,   # Luxembourg
    "LVA": 428,   # Latvia
    "MAC": 446,   # China, Macao SAR
    "MAR": 504,   # Morocco
    "MDA": 498,   # Republic of Moldova
    "MDG": 450,   # Madagascar
    "MDV": 462,   # Maldives
    "MEX": 484,   # Mexico
    "MHL": 584,   # Marshall Islands
    "MKD": 807,   # North Macedonia
    "MLI": 466,   # Mali
    "MLT": 470,   # Malta
    "MMR": 104,   # Myanmar
    "MNE": 499,   # Montenegro
    "MNG": 496,   # Mongolia
    "MNP": 580,   # Northern Mariana Islands
    "MOZ": 508,   # Mozambique
    "MRT": 478,   # Mauritania
    "MSR": 500,   # Montserrat
    "MTQ": 474,   # Martinique
    "MUS": 480,   # Mauritius
    "MWI": 454,   # Malawi
    "MYS": 458,   # Malaysia
    "MYT": 175,   # Mayotte
    "NAM": 516,   # Namibia
    "NER": 562,   # Niger
    "NGA": 566,   # Nigeria
    "NIC": 558,   # Nicaragua
    "NIU": 570,   # Niue
    "NLD": 528,   # Netherlands
    "NOR": 579,   # Norway
    "NPL": 524,   # Nepal
    "NRU": 520,   # Nauru
    "NZL": 554,   # New Zealand
    "OMN": 512,   # Oman
    "PAK": 586,   # Pakistan
    "PAN": 591,   # Panama
    "PER": 604,   # Peru
    "PHL": 608,   # Philippines
    "PLW": 585,   # Palau
    "PNG": 598,   # Papua New Guinea
    "POL": 616,   # Poland
    "PRK": 408,   # Democratic People's Republic of Korea
    "PRT": 620,   # Portugal
    "PRY": 600,   # Paraguay
    "PSE": 275,   # State of Palestine
    "PYF": 258,   # French Polynesia
    "QAT": 634,   # Qatar
    "REU": 638,   # Réunion
    "ROU": 642,   # Romania
    "RUS": 643,   # Russian Federation
    "RWA": 646,   # Rwanda
    "SAU": 682,   # Saudi Arabia
    "SDN": 729,   # Sudan
    "SEN": 686,   # Senegal
    "SGP": 702,   # Singapore
    "SHN": 654,   # Saint Helena
    "SLB": 90,    # Solomon Islands
    "SLE": 694,   # Sierra Leone
    "SLV": 222,   # El Salvador
    "SMR": 674,   # San Marino
    "SOM": 706,   # Somalia
    "SPM": 666,   # Saint Pierre and Miquelon
    "SRB": 688,   # Serbia
    "SSD": 728,   # South Sudan
    "STP": 678,   # Sao Tome and Principe
    "SUR": 740,   # Suriname
    "SVK": 703,   # Slovakia
    "SVN": 705,   # Slovenia
    "SWE": 752,   # Sweden
    "SWZ": 748,   # Eswatini
    "SXM": 534,   # Saint Maarten
    "SYC": 690,   # Seychelles
    "SYR": 760,   # Syria
    "TCA": 796,   # Turks and Caicos Islands
    "TCD": 148,   # Chad
    "TGO": 768,   # Togo
    "THA": 764,   # Thailand
    "TJK": 762,   # Tajikistan
    "TKL": 772,   # Tokelau
    "TKM": 795,   # Turkmenistan
    "TLS": 626,   # Timor-Leste
    "TON": 776,   # Tonga
    "TTO": 780,   # Trinidad and Tobago
    "TUN": 788,   # Tunisia
    "TUR": 792,   # Türkiye
    "TUV": 798,   # Tuvalu
    "TZA": 834,   # United Republic of Tanzania
    "UGA": 800,   # Uganda
    "UKR": 804,   # Ukraine
    "URY": 858,   # Uruguay
    "USA": 842,   # United States of America
    "UZB": 860,   # Uzbekistan
    "VAT": 336,   # Holy See (Vatican City State)
    "VCT": 670,   # Saint Vincent and the Grenadines
    "VEN": 862,   # Venezuela
    "VGB": 92,    # British Virgin Islands
    "VNM": 704,   # Viet Nam
    "VUT": 548,   # Vanuatu
    "WLF": 876,   # Wallis and Futuna Islands
    "WSM": 882,   # Samoa
    "YEM": 887,   # Yemen
    "ZAF": 710,   # South Africa
    "ZMB": 894,   # Zambia
    "ZWE": 716,   # Zimbabwe
}

# Reverse mapping: Comtrade numeric ID → ISO3
ID_TO_ISO3: dict[int, str] = {v: k for k, v in ISO3_TO_ID.items()}
# Also map the partner-side Switzerland code to CHE
ID_TO_ISO3.setdefault(756, "CHE")
# USA partner code
ID_TO_ISO3.setdefault(840, "USA")
# India historical reporter code
ID_TO_ISO3.setdefault(356, "IND")

# Numeric ID → country name
ID_TO_NAME: dict[int, str] = {
    0: "World",
    4: "Afghanistan",
    8: "Albania",
    12: "Algeria",
    16: "American Samoa",
    20: "Andorra",
    24: "Angola",
    28: "Antigua and Barbuda",
    31: "Azerbaijan",
    32: "Argentina",
    36: "Australia",
    40: "Austria",
    44: "Bahamas",
    48: "Bahrain",
    50: "Bangladesh",
    51: "Armenia",
    52: "Barbados",
    56: "Belgium",
    60: "Bermuda",
    64: "Bhutan",
    68: "Bolivia (Plurinational State of)",
    70: "Bosnia Herzegovina",
    72: "Botswana",
    76: "Brazil",
    84: "Belize",
    90: "Solomon Islands",
    92: "British Virgin Islands",
    96: "Brunei Darussalam",
    97: "European Union",
    100: "Bulgaria",
    104: "Myanmar",
    108: "Burundi",
    112: "Belarus",
    116: "Cambodia",
    120: "Cameroon",
    124: "Canada",
    132: "Cabo Verde",
    136: "Cayman Islands",
    140: "Central African Republic",
    144: "Sri Lanka",
    148: "Chad",
    152: "Chile",
    156: "China",
    158: "Taiwan, Province of China",
    170: "Colombia",
    174: "Comoros",
    175: "Mayotte",
    178: "Congo",
    180: "Democratic Republic of the Congo",
    184: "Cook Islands",
    188: "Costa Rica",
    191: "Croatia",
    192: "Cuba",
    196: "Cyprus",
    203: "Czechia",
    204: "Benin",
    208: "Denmark",
    212: "Dominica",
    214: "Dominican Republic",
    218: "Ecuador",
    222: "El Salvador",
    226: "Equatorial Guinea",
    231: "Ethiopia",
    232: "Eritrea",
    233: "Estonia",
    234: "Faroe Islands",
    242: "Fiji",
    246: "Finland",
    251: "France",
    254: "French Guiana",
    258: "French Polynesia",
    262: "Djibouti",
    266: "Gabon",
    268: "Georgia",
    270: "Gambia",
    275: "State of Palestine",
    276: "Germany",
    288: "Ghana",
    292: "Gibraltar",
    296: "Kiribati",
    300: "Greece",
    304: "Greenland",
    308: "Grenada",
    312: "Guadeloupe",
    320: "Guatemala",
    324: "Guinea",
    328: "Guyana",
    332: "Haiti",
    336: "Holy See",
    340: "Honduras",
    344: "China, Hong Kong SAR",
    348: "Hungary",
    352: "Iceland",
    356: "India",
    360: "Indonesia",
    364: "Iran",
    368: "Iraq",
    372: "Ireland",
    376: "Israel",
    380: "Italy",
    384: "Côte d'Ivoire",
    388: "Jamaica",
    392: "Japan",
    398: "Kazakhstan",
    400: "Jordan",
    404: "Kenya",
    408: "Democratic People's Republic of Korea",
    410: "Republic of Korea",
    414: "Kuwait",
    417: "Kyrgyzstan",
    418: "Lao People's Democratic Republic",
    422: "Lebanon",
    426: "Lesotho",
    428: "Latvia",
    430: "Liberia",
    434: "Libya",
    440: "Lithuania",
    442: "Luxembourg",
    446: "China, Macao SAR",
    450: "Madagascar",
    454: "Malawi",
    458: "Malaysia",
    462: "Maldives",
    466: "Mali",
    470: "Malta",
    474: "Martinique",
    478: "Mauritania",
    480: "Mauritius",
    484: "Mexico",
    496: "Mongolia",
    498: "Republic of Moldova",
    499: "Montenegro",
    500: "Montserrat",
    504: "Morocco",
    508: "Mozambique",
    512: "Oman",
    516: "Namibia",
    520: "Nauru",
    524: "Nepal",
    528: "Netherlands",
    531: "Curaçao",
    533: "Aruba",
    534: "Saint Maarten",
    535: "Bonaire, Sint Eustatius and Saba",
    540: "New Caledonia",
    548: "Vanuatu",
    554: "New Zealand",
    558: "Nicaragua",
    562: "Niger",
    566: "Nigeria",
    570: "Niue",
    579: "Norway",
    580: "Northern Mariana Islands",
    583: "Micronesia (Federated States of)",
    584: "Marshall Islands",
    585: "Palau",
    586: "Pakistan",
    591: "Panama",
    598: "Papua New Guinea",
    600: "Paraguay",
    604: "Peru",
    608: "Philippines",
    616: "Poland",
    620: "Portugal",
    624: "Guinea-Bissau",
    626: "Timor-Leste",
    634: "Qatar",
    638: "Réunion",
    642: "Romania",
    643: "Russian Federation",
    646: "Rwanda",
    652: "Saint Barthélemy",
    654: "Saint Helena",
    659: "Saint Kitts and Nevis",
    662: "Saint Lucia",
    666: "Saint Pierre and Miquelon",
    670: "Saint Vincent and the Grenadines",
    674: "San Marino",
    678: "Sao Tome and Principe",
    682: "Saudi Arabia",
    686: "Senegal",
    688: "Serbia",
    690: "Seychelles",
    694: "Sierra Leone",
    699: "India",
    702: "Singapore",
    703: "Slovakia",
    704: "Viet Nam",
    705: "Slovenia",
    706: "Somalia",
    710: "South Africa",
    716: "Zimbabwe",
    724: "Spain",
    728: "South Sudan",
    729: "Sudan",
    740: "Suriname",
    748: "Eswatini",
    752: "Sweden",
    756: "Switzerland",
    757: "Switzerland",
    760: "Syria",
    762: "Tajikistan",
    764: "Thailand",
    768: "Togo",
    772: "Tokelau",
    776: "Tonga",
    780: "Trinidad and Tobago",
    784: "United Arab Emirates",
    788: "Tunisia",
    792: "Türkiye",
    795: "Turkmenistan",
    796: "Turks and Caicos Islands",
    798: "Tuvalu",
    800: "Uganda",
    804: "Ukraine",
    807: "North Macedonia",
    818: "Egypt",
    826: "United Kingdom",
    834: "United Republic of Tanzania",
    840: "United States of America",
    842: "United States of America",
    854: "Burkina Faso",
    858: "Uruguay",
    860: "Uzbekistan",
    862: "Venezuela",
    876: "Wallis and Futuna Islands",
    882: "Samoa",
    887: "Yemen",
    894: "Zambia",
    899: "Areas, nes",
}

# Keep M49 as a backwards-compatible alias
M49 = ID_TO_NAME


def resolve_code(code: str | int) -> int:
    """Convert an ISO3 code or numeric string/int to a Comtrade numeric ID.

    Accepts:
    - ISO3 alpha-3 codes: ``'SAU'``, ``'PER'``, ``'USA'`` (case-insensitive)
    - Numeric strings: ``'682'``, ``'604'``
    - Integers: ``682``, ``604``

    Raises:
        ValueError: if the code is not a recognised ISO3 code and cannot be
                    parsed as an integer.
    """
    if isinstance(code, int):
        return code
    code_str = str(code).strip().upper()
    if code_str in ISO3_TO_ID:
        return ISO3_TO_ID[code_str]
    try:
        return int(code_str)
    except ValueError:
        raise ValueError(
            f"Unknown country code: {code!r}. "
            "Use ISO3 alpha-3 (e.g. 'SAU') or a numeric Comtrade ID (e.g. 682)."
        )


def get_country_name(code: int | str | None, default: str | None = None) -> str:
    """Return the country name for a Comtrade numeric ID or ISO3 code.

    Args:
        code: Numeric ID, ISO3 string, or numeric string.
        default: Fallback value when the code is not found.

    Returns:
        Country name string.
    """
    if code is None:
        return default or "Unknown"
    if isinstance(code, str):
        upper = code.strip().upper()
        if upper in ISO3_TO_ID:
            return ID_TO_NAME.get(ISO3_TO_ID[upper], default or upper)
    try:
        int_code = int(code)
    except (ValueError, TypeError):
        return default or str(code)
    return ID_TO_NAME.get(int_code, default or str(int_code))


def to_iso3(code: int | str | None) -> str | None:
    """Return the ISO3 alpha-3 code for a Comtrade numeric ID.

    Returns None if the code is not in the mapping.
    """
    if code is None:
        return None
    try:
        return ID_TO_ISO3.get(int(code))
    except (ValueError, TypeError):
        return None


def label(code: int | str | None) -> str:
    """Return a display label like ``'SAU – Saudi Arabia'``.

    Falls back to the numeric code if no ISO3 mapping is available.
    """
    if code is None:
        return "Unknown"
    try:
        num = resolve_code(code)
    except ValueError:
        return str(code)
    iso3 = ID_TO_ISO3.get(num, str(num))
    name = ID_TO_NAME.get(num, iso3)
    return f"{iso3} – {name}"
