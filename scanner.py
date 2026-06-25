"""
HALAL SCAN AI PRO ULTIMATE
scanner.py — Memory optimized. One symbol at a time. No CSV writing.
Upgraded to 9.5 Signal Quality Configuration for Python 3.11.
"""

import gc
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import ccxt
import joblib
import pandas as pd

from config import (
    MODEL_PATH, FEATURES_PATH, VERDICT_RULES,
    SCAN_TOP_N, PROB_THRESHOLD,
    EXCHANGE_ID, TIMEFRAME, CANDLES, QUOTE_CURRENCY, FETCH_DELAY_S, MAX_RETRIES,
)
from feature_engineer import engineer_features, FEATURE_NAMES
from halal_filter import filter_halal
from order_flow import get_order_flow

logger = logging.getLogger(__name__)

_model    = None
_features = None


def load_model():
    global _model, _features
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Run train_model.py first.")
    _model    = joblib.load(MODEL_PATH)
    _features = joblib.load(FEATURES_PATH)
    logger.info(f"Model loaded from {MODEL_PATH}")
    return _model, _features


def _get_model():
    if _model is None:
        load_model()
    return _model, _features


def get_verdict(prob: float) -> str:
    for verdict, threshold in VERDICT_RULES.items():
        if prob >= threshold:
            return verdict
    return "AVOID"


def get_signal_strength(prob: float) -> int:
    if prob >= 0.85: return 4
    if prob >= 0.70: return 3
    if prob >= 0.50: return 2
    return 1


def get_combined_verdict(prob: float, flow_score: float) -> str:
    verdict = get_verdict(prob)
    if verdict == "BUY" and flow_score >= 65:
        return "STRONG BUY"
    if verdict in ["STRONG BUY", "BUY"] and flow_score <= 35:
        return "WATCH"
    return verdict


def _composite_score(prob: float, rsi: float, adx: float, vol_ratio: float) -> float:
    if 30 <= rsi <= 60:   rsi_score = 1.0
    elif rsi < 30:         rsi_score = 0.8
    elif 60 < rsi <= 70:   rsi_score = 0.7
    else:                  rsi_score = 0.4

    if adx >= 40:          adx_score = 1.0
    elif adx >= 25:        adx_score = 0.85
    elif adx >= 15:        adx_score = 0.65
    else:                  adx_score = 0.4

    if vol_ratio >= 2.0:   vol_score = 1.0
    elif vol_ratio >= 1.5: vol_score = 0.85
    elif vol_ratio >= 1.0: vol_score = 0.70
    else:                  vol_score = 0.50

    return round(prob * 0.55 + rsi_score * 0.20 + adx_score * 0.15 + vol_score * 0.10, 4)


def _build_exchange() -> ccxt.Exchange:
    exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
    exchange.load_markets()
    return exchange


def _fetch_one(exchange, symbol: str) -> Optional[pd.DataFrame]:
    OHLCV_COLS = ["timestamp", "open", "high", "low", "close", "volume"]
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=CANDLES)
            if not raw or len(raw) < 100:
                return None
            df = pd.DataFrame(raw, columns=OHLCV_COLS)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            df = df.astype(float)
            df.sort_index(inplace=True)
            df.dropna(inplace=True)
            return df
        except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
            wait = 2 ** attempt
            logger.warning(f"[{symbol}] Retry {attempt}/{MAX_RETRIES} in {wait}s: {e}")
            time.sleep(wait)
        except ccxt.BadSymbol:
            return None
        except Exception as e:
            logger.debug(f"[{symbol}] Error: {e}")
            return None
    return None


def _get_halal_symbols(exchange) -> List[str]:
    symbols = [
        s for s, m in exchange.markets.items()
        if m.get("spot") and m.get("active")
        and m.get("quote") == QUOTE_CURRENCY
        and "/" in s and ":" not in s
    ]
    return filter_halal(symbols)


def run_scan(
    min_prob: float = PROB_THRESHOLD,
    top_n: int = SCAN_TOP_N,
) -> List[Dict]:
    """
    Memory-optimized scan — processes ONE symbol at a time.
    Enforces institutional trend filters and active volume thresholds.
    """
    logger.info(f"Starting upgraded scan (min_prob={min_prob:.0%}, top_n={top_n})...")
    model, _ = _get_model()
    scan_start = time.time()

    exchange = _build_exchange()
    symbols  = _get_halal_symbols(exchange)
    logger.info(f"Scanning {len(symbols)} halal symbols...")

    results = []
    failed  = 0

    for i, symbol in enumerate(symbols, 1):
        try:
            # Fetch one symbol
            df = _fetch_one(exchange, symbol)
            if df is None:
                failed += 1
                time.sleep(FETCH_DELAY_S)
                continue

            # Engineer features
            feat_df = engineer_features(df, add_target=False)
            
            if feat_df.empty:
                del df
                gc.collect()
                continue

            latest = feat_df[FEATURE_NAMES].iloc[-1].copy()
            
            # Keep tracks of latest pricing context safely
            current_close = float(df["close"].iloc[-1])
            del df
            del feat_df
            gc.collect()

            # Core Probability Score
            X    = latest.values.reshape(1, -1)
            prob = float(model.predict_proba(X)[0, 1])

            if prob < min_prob:
                time.sleep(FETCH_DELAY_S)
                continue

            rsi       = float(latest["rsi"])
            adx       = float(latest["adx"])
            vol_ratio = float(latest["volume_ratio"])
            ret_24h   = float(latest["return_24h"]) * 100
            ret_72h   = float(latest["return_72h"]) * 100

            # ── 9.5 SIGNAL FILTERS ──────────────────────────────────────────

            # 1. Skip strictly overbought conditions
            if rsi > 80:
                time.sleep(FETCH_DELAY_S)
                continue

            # 2. Institutional Volume Gate: Drop ghost-town drops
            if vol_ratio < 0.85:
                time.sleep(FETCH_DELAY_S)
                continue

            # 3. Macro Bleed-Out Rule: Exclude massive structural dumps
            if ret_72h < -15.0:
                time.sleep(FETCH_DELAY_S)
                continue

            # 4. Long-Term EMA Filter: Check macro health
            if "ema200" in latest:
                ema200_val = float(latest["ema200"])
                if current_close < (ema200_val * 0.90):
                    time.sleep(FETCH_DELAY_S)
                    continue

            # ────────────────────────────────────────────────────────────────

            composite = _composite_score(prob, rsi, adx, vol_ratio)
            base      = symbol.replace("/USDT", "")

            results.append({
                "symbol":           base,
                "probability":      round(prob * 100, 2),
                "prob_raw":         round(prob, 4),
                "composite_score":  composite,
                "verdict":          get_verdict(prob),
                "combined_verdict": get_verdict(prob),
                "rsi":              round(rsi, 2),
                "adx":              round(adx, 2),
                "volume_ratio":     round(vol_ratio, 3),
                "return_24h":       round(ret_24h, 2),
                "return_72h":       round(ret_72h, 2),
                "signal_strength":  get_signal_strength(prob),
                "scanned_at":       datetime.now(timezone.utc).isoformat(),
            })

            time.sleep(FETCH_DELAY_S)

            if i % 50 == 0:
                logger.info(f"Progress: {i}/{len(symbols)} | signals so far: {len(results)}")

        except Exception as e:
            logger.debug(f"[{symbol}] Error: {e}")
            failed += 1
            continue

    # Sort and slice limits
    results.sort(key=lambda r: r["composite_score"], reverse=True)
    results = results[:top_n]

    elapsed = time.time() - scan_start
    logger.info(f"Scan done: {len(results)} signals | {elapsed:.1f}s | {failed} failed")

    return results


def analyze_symbol(symbol: str, include_order_flow: bool = True) -> Optional[Dict]:
    """Single coin deep analysis with order flow."""
    sym = symbol.upper().strip()
    if "/" not in sym:
        sym = f"{sym}/USDT"

    exchange = _build_exchange()
    df = _fetch_one(exchange, sym)
    if df is None or df.empty:
        return None

    feat_df = engineer_features(df, add_target=False)
    del df
    gc.collect()

    if feat_df.empty:
        return None

    latest = feat_df[FEATURE_NAMES].iloc[-1].copy()
    del feat_df
    gc.collect()

    model, _ = _get_model()
    X    = latest.values.reshape(1, -1)
    prob = float(model.predict_proba(X)[0, 1])
    base = sym.replace("/USDT", "")

    try:
        ticker = exchange.fetch_ticker(sym)
        price  = float(ticker.get("last", 0))
    except Exception:
        price = 0.0

    result = {
        "symbol":           base,
        "full_symbol":      sym,
        "probability":      round(prob * 100, 2),
        "prob_raw":         round(prob, 4),
        "verdict":          get_verdict(prob),
        "combined_verdict": get_verdict(prob),
        "signal_strength":  get_signal_strength(prob),
        "price":            price,
        "rsi":              round(float(latest["rsi"]), 2),
        "adx":              round(float(latest["adx"]), 2),
        "volume_ratio":     round(float(latest["volume_ratio"]), 3),
        "ema20":            round(float(latest["ema20"]), 6),
        "ema50":            round(float(latest["ema50"]), 6),
        "macd":             round(float(latest["macd"]), 8),
        "macd_signal":      round(float(latest["macd_signal"]), 8),
        "return_24h":       round(float(latest["return_24h"]) * 100, 2),
        "return_72h":       round(float(latest["return_72h"]) * 100, 2),
        "scanned_at":       datetime.now(timezone.utc).isoformat(),
        "flow_score":       None,
        "flow_signal":      None,
        "taker_buy_ratio":  None,
        "ob_imbalance_pct": None,
        "whale_buys":       None,
        "whale_sells":      None,
        "whale_net":        None,
        "volume_delta_pct": None,
    }

    if include_order_flow:
        try:
            of = get_order_flow(sym)
            if of:
                result.update({
                    "flow_score":       of["flow_score"],
                    "flow_signal":      of["flow_signal"],
                    "taker_buy_ratio":  of["taker_buy_ratio"],
                    "ob_imbalance_pct": of["ob_imbalance_pct"],
                    "whale_buys":       of["whale_buys"],
                    "whale_sells":      of["whale_sells"],
                    "whale_net":        of["whale_net"],
                    "volume_delta_pct": of["volume_delta_pct"],
                    "combined_verdict": get_combined_verdict(prob, of["flow_score"]),
                })
        except Exception as e:
            logger.warning(f"[{sym}] Order flow failed: {e}")

    gc.collect()
    return result