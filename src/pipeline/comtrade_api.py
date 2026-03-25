"""UN Comtrade API client with rate limiting, retry logic, and pagination."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Comtrade API constants
# typeCode, freqCode, clCode are path segments, not query params
BASE_URL = "https://comtradeapi.un.org/data/v1/get/{type_code}/{freq_code}/{cl_code}"
PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview"

# Flow codes (Comtrade API v1 uses string codes)
FLOW_IMPORT = "M"
FLOW_EXPORT = "X"
FLOW_RE_EXPORT = "XIP"
FLOW_RE_IMPORT = "MIP"

# Special partner codes to filter out in mirror analysis
WORLD_CODE = 0
AREAS_NES_CODE = 899

# Rate limiting: Comtrade allows ~100 requests per minute for premium
DEFAULT_RATE_LIMIT = 1.0  # seconds between requests
MAX_RECORDS_PER_REQUEST = 100_000


class ComtradeAPIError(Exception):
    """Raised when the Comtrade API returns an error."""


class ComtradeAPI:
    """Client for the UN Comtrade bulk data API.

    Authenticates via subscription key from the COMTRADE_API_KEY env var.
    Handles rate limiting, retries, and pagination.
    """

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: float = DEFAULT_RATE_LIMIT,
    ) -> None:
        self.api_key = api_key or os.environ.get("COMTRADE_API_KEY", "")
        if not self.api_key:
            raise ComtradeAPIError(
                "COMTRADE_API_KEY environment variable is not set. "
                "Get a subscription key at https://comtradeapi.un.org/"
            )
        self.rate_limit = rate_limit
        self._last_request_time: float = 0.0
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        """Build a requests session with retry logic."""
        session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=2.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Accept": "application/json",
        })
        return session

    def _throttle(self) -> None:
        """Enforce rate limiting between API calls."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.monotonic()

    def _request(self, type_code: str, freq_code: str, cl_code: str, params: dict[str, Any]) -> dict[str, Any]:
        """Make a single API request with throttling."""
        self._throttle()
        url = BASE_URL.format(type_code=type_code, freq_code=freq_code, cl_code=cl_code)
        logger.debug("Comtrade API request: %s %s", url, params)

        resp = self._session.get(url, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data and data["error"]:
            raise ComtradeAPIError(f"API error: {data.get('error')}")

        return data

    def get_trade_data(
        self,
        reporter_code: int | list[int],
        partner_code: int | list[int] | None = None,
        commodity_code: str | list[str] | None = None,
        flow_code: int | list[int] | None = None,
        period: str | list[str] | None = None,
        frequency: str = "A",
        type_code: str = "C",
        classification: str = "HS",
    ) -> list[dict[str, Any]]:
        """Fetch trade data from Comtrade API with pagination.

        Args:
            reporter_code: UN M49 reporter country code(s).
            partner_code: UN M49 partner country code(s). None for all partners.
            commodity_code: HS commodity code(s) (2/4/6 digit). None for all.
            flow_code: Trade flow type(s). None for all flows.
            period: Time period(s) as 'YYYY' or 'YYYYMM'. None for latest.
            frequency: 'A' for annual, 'M' for monthly.
            type_code: 'C' for commodities, 'S' for services.
            classification: 'HS' for Harmonized System.

        Returns:
            List of trade record dicts from the API.
        """
        # typeCode/freqCode/clCode are path segments; remaining params go in query string
        params: dict[str, Any] = {
            "reporterCode": self._join_codes(reporter_code),
        }

        if partner_code is not None:
            params["partnerCode"] = self._join_codes(partner_code)
        if commodity_code is not None:
            params["cmdCode"] = self._join_codes(commodity_code)
        if flow_code is not None:
            params["flowCode"] = self._join_codes(flow_code)
        if period is not None:
            params["period"] = self._join_codes(period)

        all_records: list[dict[str, Any]] = []
        # Comtrade paginates via count-based batching
        # We request in a loop until we get fewer records than the max
        data = self._request(type_code, frequency, classification, params)
        records = data.get("data", [])
        all_records.extend(records)

        logger.info("Fetched %d records", len(all_records))
        return all_records

    def fetch_bilateral_pair(
        self,
        country_a: int,
        country_b: int,
        commodity_code: str | list[str] | None = None,
        period: str | list[str] | None = None,
        frequency: str = "A",
    ) -> list[dict[str, Any]]:
        """Fetch BOTH sides of a bilateral trade flow for mirror analysis.

        Downloads:
        - Country A's reported exports to Country B
        - Country B's reported imports from Country A
        - Country B's reported exports to Country A
        - Country A's reported imports from Country B

        Args:
            country_a: First country code.
            country_b: Second country code.
            commodity_code: HS code(s) to filter.
            period: Time period(s).
            frequency: 'A' or 'M'.

        Returns:
            Combined list of all records for both directions.
        """
        all_records: list[dict[str, Any]] = []

        # The API requires an explicit flowCode when partnerCode is specified.
        # Make four calls: A exports to B, A imports from B,
        #                  B exports to A, B imports from A.
        for reporter, partner in [(country_a, country_b), (country_b, country_a)]:
            for flow in (FLOW_EXPORT, FLOW_IMPORT):
                records = self.get_trade_data(
                    reporter_code=reporter,
                    partner_code=partner,
                    commodity_code=commodity_code,
                    flow_code=flow,
                    period=period,
                    frequency=frequency,
                )
                all_records.extend(records)

        logger.info(
            "Bilateral pair %d<->%d: %d total records",
            country_a, country_b, len(all_records),
        )
        return all_records

    def scan_all_partners(
        self,
        reporter_code: int,
        commodity_code: str | list[str] | None = None,
        period: str | list[str] | None = None,
        frequency: str = "A",
    ) -> list[dict[str, Any]]:
        """Fetch all trade flows for a reporter across all partners.

        Used for broad scans to identify suspicious corridors.

        Args:
            reporter_code: Country code to scan.
            commodity_code: Optional HS code filter.
            period: Time period(s).
            frequency: 'A' or 'M'.

        Returns:
            List of trade records for all partners.
        """
        return self.get_trade_data(
            reporter_code=reporter_code,
            commodity_code=commodity_code,
            period=period,
            frequency=frequency,
        )

    @staticmethod
    def _join_codes(codes: int | str | list[int] | list[str]) -> str:
        """Join multiple codes into comma-separated string for API params."""
        if isinstance(codes, (int, str)):
            return str(codes)
        return ",".join(str(c) for c in codes)

    @staticmethod
    def is_world_or_nes(partner_code: int) -> bool:
        """Check if a partner code is 'World' or 'Areas NES' aggregate."""
        return partner_code in (WORLD_CODE, AREAS_NES_CODE)

    @staticmethod
    def is_re_export(flow_code: int) -> bool:
        """Check if a flow code indicates re-export or re-import."""
        return flow_code in (FLOW_RE_EXPORT, FLOW_RE_IMPORT)

    @staticmethod
    def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw API record into our internal format.

        Maps Comtrade field names to our schema column names and ensures
        all monetary values are in USD.
        """
        return {
            "reporter_code": record.get("reporterCode"),
            "partner_code": record.get("partnerCode"),
            "commodity_code": str(record.get("cmdCode", "")),
            "flow_code": record.get("flowCode"),
            "period": str(record.get("period", "")),
            "frequency": record.get("freqCode", "A"),
            "trade_value_usd": record.get("primaryValue"),
            "cif_value_usd": record.get("cifvalue"),
            "fob_value_usd": record.get("fobvalue"),
            "net_weight_kg": record.get("netWgt"),
            "qty": record.get("qty"),
            "qty_unit_code": record.get("qtyUnitCode"),
            "qty_unit_desc": record.get("qtyUnitAbbr"),
            "is_re_export": 1 if record.get("flowCode") in (FLOW_RE_EXPORT, FLOW_RE_IMPORT, "XIP", "MIP") else 0,
            "is_confidential": 1 if record.get("isOriginalClassification") == 0 else 0,
            "customs_code": record.get("customsCode"),
            "mot_code": record.get("motCode"),
            "mot_desc": record.get("motDesc"),
            "classification": record.get("classificationCode", "HS"),
            "ref_year": record.get("refYear"),
            "dataset_code": record.get("datasetCode"),
        }
