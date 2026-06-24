"""
Historical signal outcome tracking.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from config import BACKTEST_PATH, HISTORY_PATH, TARGET_HORIZON, TARGET_RETURN
from data_collector import collect_one

logger = logging.getLogger(__name__)

RESULT_COLUMNS = [
    "signal_date",
    "coin",
    "probability",
    "actual_return_72h",
    "win",
    "entry_price",
    "exit_price",
    "verdict",
]


def _empty_result() -> dict:
    return {
        "rows": [],
        "summary": {
            "count": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "profit_factor": 0.0,
        },
    }


def _load_results_df() -> pd.DataFrame:
    if not BACKTEST_PATH.exists():
        return pd.DataFrame(columns=RESULT_COLUMNS)
    try:
        return pd.read_csv(BACKTEST_PATH)
    except Exception as exc:
        logger.error("Could not load backtest results: %s", exc)
        return pd.DataFrame(columns=RESULT_COLUMNS)


def _actual_return(symbol: str, scanned_at: str) -> tuple[float, float, float] | None:
    scan_time = pd.to_datetime(scanned_at, utc=True, errors="coerce")
    if pd.isna(scan_time):
        return None

    exit_time = scan_time + timedelta(hours=TARGET_HORIZON)
    if pd.Timestamp.utcnow() < exit_time:
        return None

    df = collect_one(symbol, include_derivatives=False)
    if df is None or df.empty:
        return None

    indexed = df.sort_index()
    entry_candidates = indexed[indexed.index >= scan_time]
    exit_candidates = indexed[indexed.index >= exit_time]
    if entry_candidates.empty or exit_candidates.empty:
        return None

    entry_price = float(entry_candidates["close"].iloc[0])
    exit_price = float(exit_candidates["close"].iloc[0])
    if entry_price <= 0:
        return None

    actual = (exit_price - entry_price) / entry_price * 100
    return actual, entry_price, exit_price


def refresh_backtest_results(limit: int = 250) -> dict:
    if not HISTORY_PATH.exists():
        return _empty_result()

    try:
        history = pd.read_csv(HISTORY_PATH).tail(limit)
    except Exception as exc:
        logger.error("Could not load signal history: %s", exc)
        return _empty_result()

    existing = _load_results_df()
    existing_keys = {
        f"{row.coin}|{row.signal_date}"
        for row in existing.itertuples(index=False)
        if hasattr(row, "coin") and hasattr(row, "signal_date")
    }
    new_rows = []

    for row in history.to_dict(orient="records"):
        symbol = str(row.get("symbol", "")).upper()
        scanned_at = row.get("scanned_at")
        if not symbol or not scanned_at:
            continue
        key = f"{symbol}|{scanned_at}"
        if key in existing_keys:
            continue

        outcome = _actual_return(symbol, scanned_at)
        if outcome is None:
            continue

        actual, entry_price, exit_price = outcome
        new_rows.append(
            {
                "signal_date": scanned_at,
                "coin": symbol,
                "probability": float(row.get("probability") or 0.0),
                "actual_return_72h": round(actual, 2),
                "win": actual >= (TARGET_RETURN * 100),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "verdict": row.get("combined_verdict") or row.get("verdict"),
            }
        )

    if new_rows:
        BACKTEST_PATH.parent.mkdir(exist_ok=True)
        combined = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
        combined.drop_duplicates(subset=["coin", "signal_date"], keep="last", inplace=True)
        combined.tail(10_000).to_csv(BACKTEST_PATH, index=False)

    return load_backtest_results(refresh=False)


def _summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return _empty_result()["summary"]

    returns = pd.to_numeric(df["actual_return_72h"], errors="coerce").dropna()
    wins = returns >= (TARGET_RETURN * 100)
    positive = returns[returns > 0].sum()
    negative = returns[returns < 0].sum()

    profit_factor = 0.0
    if negative < 0:
        profit_factor = float(positive / abs(negative))
    elif positive > 0:
        profit_factor = float("inf")

    return {
        "count": int(len(returns)),
        "win_rate": round(float(wins.mean() * 100), 2) if len(returns) else 0.0,
        "average_return": round(float(returns.mean()), 2) if len(returns) else 0.0,
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
    }


def load_backtest_results(refresh: bool = False) -> dict:
    if refresh:
        return refresh_backtest_results()

    df = _load_results_df()
    if not df.empty:
        df.sort_values("signal_date", ascending=False, inplace=True)

    return {
        "rows": df.to_dict(orient="records"),
        "summary": _summary(df),
    }
