"""
HALAL SCAN AI PRO ULTIMATE
scanner.py — Live scanner with smart filtering and order flow.

Key fixes:
  - Removed overly strict volume/ADX pre-filters that cut good signals
  - Order flow fetched on-demand only (not during bulk scan = much faster)
  - Better signal ranking using composite score
  - Watchlist data properly structured
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import joblib
import pandas as pd

from config import (
    MODEL_PATH, FEATURES_PATH, SIGNALS_PATH, HISTORY_PATH,
    SCAN_TOP_N, PROB_THRESHOLD, VERDICT_RULES,
)
from data_collector import collect_all, collect_one
from feature_engineer import engineer_features, FEATURE_NAMES
from order_flow import get_order_flow

logger = logging.getLogger(__name__)

_model    = None
_features = None


def load_model():
    global _model, _features
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. Run train_model.py first."
        )
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
    """
    Composite ranking score combining AI probability with quality indicators.
    RSI 30-60 = best zone, ADX > 20 = trending, Volume > 1.0 = active
    """
    if 30 <= rsi <= 60:
        rsi_score = 1.0
    elif rsi < 30:
        rsi_score = 0.8
    elif 60 < rsi <= 70:
        rsi_score = 0.7
    else:
        rsi_score = 0.4

    if adx >= 40:
        adx_score = 1.0
    elif adx >= 25:
        adx_score = 0.85
    elif adx >= 15:
        adx_score = 0.65
    else:
        adx_score = 0.4

    if vol_ratio >= 2.0:
        vol_score = 1.0
    elif vol_ratio >= 1.5:
        vol_score = 0.85
    elif vol_ratio >= 1.0:
        vol_score = 0.70
    else:
        vol_score = 0.50

    composite = (
        prob * 0.55 +
        rsi_score * 0.20 +
        adx_score * 0.15 +
        vol_score * 0.10
    )
    return round(composite, 4)


def analyze_symbol(symbol: str, include_order_flow: bool = True) -> Optional[Dict]:
    sym = symbol.upper().strip()
    if "/" not in sym:
        sym = f"{sym}/USDT"

    df = collect_one(sym)
    if df is None or df.empty:
        logger.warning(f"[{sym}] Could not fetch data.")
        return None

    feat_df = engineer_features(df, add_target=False)
    if feat_df.empty:
        logger.warning(f"[{sym}] Feature engineering failed.")
        return None

    latest = feat_df[FEATURE_NAMES].iloc[-1]
    model, _ = _get_model()
    X    = latest.values.reshape(1, -1)
    prob = float(model.predict_proba(X)[0, 1])
    price = float(df["close"].iloc[-1])
    base  = sym.replace("/USDT", "")

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

    return result


def run_scan(
    min_prob: float = PROB_THRESHOLD,
    top_n: int = SCAN_TOP_N,
    save_csv: bool = True,
) -> List[Dict]:
    logger.info(f"Starting scan (min_prob={min_prob:.0%}, top_n={top_n})...")
    model, _ = _get_model()
    scan_start = time.time()

    data = collect_all(apply_halal=True, verbose=True)
    results = []

    for symbol, df in data.items():
        try:
            feat_df = engineer_features(df, add_target=False)
            if feat_df.empty:
                continue

            latest = feat_df[FEATURE_NAMES].iloc[-1]
            X      = latest.values.reshape(1, -1)
            prob   = float(model.predict_proba(X)[0, 1])

            if prob < min_prob:
                continue

            rsi       = float(latest["rsi"])
            adx       = float(latest["adx"])
            vol_ratio = float(latest["volume_ratio"])
            price     = float(df["close"].iloc[-1])
            base      = symbol.replace("/USDT", "")

            # Only skip extremely overbought coins RSI > 80
            if rsi > 80:
                continue

            if price <= 0:
                continue

            composite = _composite_score(prob, rsi, adx, vol_ratio)

            entry = {
                "symbol":           base,
                "probability":      round(prob * 100, 2),
                "prob_raw":         round(prob, 4),
                "composite_score":  composite,
                "verdict":          get_verdict(prob),
                "combined_verdict": get_verdict(prob),
                "price":            price,
                "rsi":              round(rsi, 2),
                "adx":              round(adx, 2),
                "volume_ratio":     round(vol_ratio, 3),
                "return_24h":       round(float(latest["return_24h"]) * 100, 2),
                "return_72h":       round(float(latest["return_72h"]) * 100, 2),
                "scanned_at":       datetime.now(timezone.utc).isoformat(),
                "flow_score":       None,
                "flow_signal":      None,
                "taker_buy_ratio":  None,
                "whale_net":        None,
            }

            results.append(entry)

        except Exception as e:
            logger.debug(f"[{symbol}] Error: {e}")
            continue

    results.sort(key=lambda r: r["composite_score"], reverse=True)
    results = results[:top_n]

    elapsed = time.time() - scan_start
    logger.info(f"Scan complete: {len(results)} signals | {elapsed:.1f}s")

    if save_csv and results:
        _save_signals(results)
        _append_history(results)

    return results


def _save_signals(results: List[Dict]) -> None:
    pd.DataFrame(results).to_csv(SIGNALS_PATH, index=False)
    logger.info(f"Signals saved -> {SIGNALS_PATH}")


def _append_history(results: List[Dict]) -> None:
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    df = pd.DataFrame(results)
    if HISTORY_PATH.exists():
        existing = pd.read_csv(HISTORY_PATH)
        combined = pd.concat([existing, df], ignore_index=True).tail(10_000)
        combined.to_csv(HISTORY_PATH, index=False)
    else:
        df.to_csv(HISTORY_PATH, index=False)


def load_last_signals() -> List[Dict]:
    if not SIGNALS_PATH.exists():
        return []
    try:
        df = pd.read_csv(SIGNALS_PATH)
        sort_col = "composite_score" if "composite_score" in df.columns else "probability"
        df.sort_values(sort_col, ascending=False, inplace=True)
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Could not load signals: {e}")
        return []


def load_history(limit: int = 200) -> List[Dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        df = pd.read_csv(HISTORY_PATH)
        df.sort_values("scanned_at", ascending=False, inplace=True)
        return df.head(limit).to_dict(orient="records")
    except Exception as e:
        logger.error(f"Could not load history: {e}")
        return []
