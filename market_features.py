"""
Binance futures-derived features.

Funding rate and open-interest change are used as optional model features. The
functions are cached and fail closed to zeroes so spot scanning keeps working
when a pair has no futures market or Binance rate-limits a request.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from config import (
    BINANCE_FUTURES_BASE_URL,
    DERIVATIVE_FEATURE_CACHE_TTL_S,
    DERIVATIVE_FEATURES_ENABLED,
    HTTP_TIMEOUT_S,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE_S,
)

logger = logging.getLogger(__name__)

DERIVATIVE_FEATURE_NAMES = ["funding_rate", "open_interest_change"]

_session: requests.Session | None = None
_session_lock = Lock()
_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


def _get_session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            session = requests.Session()
            adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64, max_retries=0)
            session.mount("https://", adapter)
            session.headers.update({"User-Agent": "HALAL-SCAN-AI/1.0"})
            _session = session
        return _session


def _cache_get(key: str) -> dict[str, float] | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < DERIVATIVE_FEATURE_CACHE_TTL_S:
            return entry["data"]
    return None


def _cache_set(key: str, data: dict[str, float]) -> None:
    with _cache_lock:
        _cache[key] = {"ts": time.time(), "data": data}


def _futures_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    if "/" in sym:
        base, quote = sym.split("/", 1)
        return f"{base}{quote}"
    if sym.endswith("USDT"):
        return sym
    return f"{sym}USDT"


def _request_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{BINANCE_FUTURES_BASE_URL}{path}"
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _get_session().get(url, params=params, timeout=HTTP_TIMEOUT_S)
            if response.status_code in {418, 429}:
                wait = RETRY_BACKOFF_BASE_S ** attempt
                logger.warning("Binance futures rate limit on %s. Retrying in %.1fs.", path, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            wait = RETRY_BACKOFF_BASE_S ** attempt
            logger.debug("Futures request failed for %s attempt %s/%s: %s", path, attempt, MAX_RETRIES, exc)
            time.sleep(wait)

    if last_error:
        raise last_error
    return None


def zero_derivative_features() -> dict[str, float]:
    return {name: 0.0 for name in DERIVATIVE_FEATURE_NAMES}


def get_latest_derivative_features(symbol: str) -> dict[str, float]:
    if not DERIVATIVE_FEATURES_ENABLED:
        return zero_derivative_features()

    fut_symbol = _futures_symbol(symbol)
    cached = _cache_get(fut_symbol)
    if cached is not None:
        return cached

    features = zero_derivative_features()

    try:
        premium = _request_json("/fapi/v1/premiumIndex", {"symbol": fut_symbol})
        if isinstance(premium, dict):
            features["funding_rate"] = float(premium.get("lastFundingRate") or 0.0)
    except Exception as exc:
        logger.debug("[%s] Funding-rate feature unavailable: %s", fut_symbol, exc)

    try:
        oi_rows = _request_json(
            "/futures/data/openInterestHist",
            {"symbol": fut_symbol, "period": "1h", "limit": 2},
        )
        if isinstance(oi_rows, list) and len(oi_rows) >= 2:
            prev = float(oi_rows[-2].get("sumOpenInterest") or 0.0)
            curr = float(oi_rows[-1].get("sumOpenInterest") or 0.0)
            if prev > 0:
                features["open_interest_change"] = (curr - prev) / prev
    except Exception as exc:
        logger.debug("[%s] Open-interest feature unavailable: %s", fut_symbol, exc)

    _cache_set(fut_symbol, features)
    return features


def add_derivative_features_to_ohlcv(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    out = df.copy()
    features = get_latest_derivative_features(symbol)
    for name in DERIVATIVE_FEATURE_NAMES:
        out[name] = float(features.get(name, 0.0))
    return out
