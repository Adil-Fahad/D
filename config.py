"""
HALAL SCAN AI PRO ULTIMATE
config.py — Central configuration. Edit here, changes propagate everywhere.
"""

import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
DATA_DIR        = BASE_DIR / "data"
LOGS_DIR        = BASE_DIR / "logs"
MODELS_DIR      = BASE_DIR / "models"

BLACKLIST_PATH  = BASE_DIR / "halal_blacklist.json"
MODEL_PATH      = BASE_DIR / "halal_ai_production.pkl"
FEATURES_PATH   = BASE_DIR / "features_production.pkl"
SIGNALS_PATH    = BASE_DIR / "live_signals.csv"
HISTORY_PATH    = DATA_DIR / "signal_history.csv"
BACKTEST_PATH   = DATA_DIR / "backtest_results.csv"
ALERTS_PATH     = DATA_DIR / "alerts.json"
TELEGRAM_SENT_PATH = DATA_DIR / "telegram_sent.json"

# ─── Data Collection ──────────────────────────────────────────────────────────
EXCHANGE_ID     = "binance"
TIMEFRAME       = "1h"
CANDLES         = int(os.getenv("CANDLES", "500"))          # candles per symbol
QUOTE_CURRENCY  = "USDT"
FETCH_DELAY_S   = float(os.getenv("FETCH_DELAY_S", "0.1"))          # seconds between symbol fetches (rate limit)
MAX_RETRIES     = 3
RETRY_BACKOFF_BASE_S = 1.5
HTTP_TIMEOUT_S  = 10

# ─── Feature Engineering ──────────────────────────────────────────────────────
RSI_PERIOD      = 14
EMA_SHORT       = 20
EMA_MID         = 50
EMA_LONG        = 200
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9
ADX_PERIOD      = 14
ATR_PERIOD      = 14
VOL_RATIO_WIN   = 20            # window for volume ratio
ROLL_Z_WIN      = 90            # rolling z-score normalisation window
ROLL_Z_CLIP     = 4.0           # sigma clip for z-scores

# ─── Target ───────────────────────────────────────────────────────────────────
TARGET_HORIZON  = 72            # hours ahead
TARGET_RETURN   = 0.05          # 5% minimum gain

# ─── Model Training ───────────────────────────────────────────────────────────
TRAIN_RATIO     = 0.80          # temporal split
EARLY_STOP_RND  = 50

XGB_PARAMS = {
    "n_estimators":     500,
    "max_depth":        5,
    "learning_rate":    0.05,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 10,
    "gamma":            1.0,
    "reg_alpha":        0.1,
    "reg_lambda":       1.0,
    "eval_metric":      "aucpr",
    "use_label_encoder": False,
    "random_state":     42,
    "n_jobs":           -1,
    "tree_method":      "hist",
}

LGBM_PARAMS = {
    "n_estimators":     500,
    "max_depth":        -1,
    "learning_rate":    0.04,
    "num_leaves":       31,
    "subsample":        0.85,
    "colsample_bytree": 0.85,
    "reg_alpha":        0.1,
    "reg_lambda":       1.0,
    "random_state":     42,
    "n_jobs":           -1,
    "objective":        "binary",
    "verbosity":        -1,
}

# GO/NO-GO gates (must pass before backtesting is run)
MIN_PROB_RANGE  = 0.30          # max_prob - min_prob must exceed this
MIN_CLASS_SEP   = 0.02          # mean(prob|y=1) - mean(prob|y=0) must exceed this

# ─── Scanner ──────────────────────────────────────────────────────────────────
SCAN_TOP_N      = 50            # top N coins to rank in live output
PROB_THRESHOLD  = 0.65          # default display threshold

# ─── Signal Verdicts ──────────────────────────────────────────────────────────
VERDICT_RULES = {
    "STRONG BUY": 0.85,
    "BUY":        0.70,
    "WATCH":      0.50,
    "AVOID":      0.00,
}

# ─── Flask ────────────────────────────────────────────────────────────────────
FLASK_HOST      = "0.0.0.0"
FLASK_PORT      = 5000
FLASK_DEBUG     = False
CACHE_TTL_S     = 300           # seconds before scanner re-runs

# Binance derivatives features
DERIVATIVE_FEATURES_ENABLED = os.getenv("DERIVATIVE_FEATURES_ENABLED", "1") == "1"
DERIVATIVE_FEATURE_CACHE_TTL_S = int(os.getenv("DERIVATIVE_FEATURE_CACHE_TTL_S", "900"))
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"

# Order flow
ORDER_FLOW_CACHE_TTL_S = int(os.getenv("ORDER_FLOW_CACHE_TTL_S", "120"))
LARGE_TRADE_THRESHOLD_USDT = float(os.getenv("LARGE_TRADE_THRESHOLD_USDT", "50000"))
ORDER_BOOK_DEPTH = int(os.getenv("ORDER_BOOK_DEPTH", "20"))
RECENT_TRADES_LIMIT = int(os.getenv("RECENT_TRADES_LIMIT", "500"))

# Background scanning
AUTO_SCAN_ENABLED = os.getenv("AUTO_SCAN_ENABLED", "1") == "1"
AUTO_SCAN_INTERVAL_HOURS = float(os.getenv("AUTO_SCAN_INTERVAL_HOURS", "4"))
AUTO_SCAN_MIN_PROB = float(os.getenv("AUTO_SCAN_MIN_PROB", str(PROB_THRESHOLD)))
AUTO_SCAN_TOP_N = int(os.getenv("AUTO_SCAN_TOP_N", str(SCAN_TOP_N)))

# Telegram alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
