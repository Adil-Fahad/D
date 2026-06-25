"""
HALAL SCAN AI PRO ULTIMATE
app.py — Simplified Flask backend. No watchlist. No history. Memory optimized.
"""

import gc
import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock

from flask import Flask, jsonify, request, render_template, abort
from flask_cors import CORS

from config import (
    CACHE_TTL_S, MODEL_PATH, FEATURES_PATH,
    BASE_DIR, LOGS_DIR,
)
from scanner import analyze_symbol, run_scan, load_model

LOGS_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# ── Simple in-memory cache ─────────────────────────────────────────────────
_cache: dict = {}
_cache_lock  = Lock()


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL_S:
            return entry["data"]
    return None


def _cache_set(key: str, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _cache_clear_signals():
    with _cache_lock:
        keys = [k for k in _cache if k.startswith("signals_")]
        for k in keys:
            del _cache[k]


# ── Cleanup after each request ─────────────────────────────────────────────
@app.after_request
def cleanup(response):
    gc.collect()
    return response


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    model_ready = MODEL_PATH.exists() and FEATURES_PATH.exists()
    return render_template("index.html", model_ready=model_ready)


@app.route("/static/sw.js")
def service_worker():
    return app.send_static_file("sw.js"), 200, {
        "Content-Type": "application/javascript",
        "Service-Worker-Allowed": "/"
    }


@app.route("/api/status")
def api_status():
    return jsonify({
        "status":      "ok",
        "model_ready": MODEL_PATH.exists() and FEATURES_PATH.exists(),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Run a fresh market scan. Returns top signals."""
    body     = request.get_json(silent=True) or {}
    min_prob = float(body.get("min_prob", 55)) / 100
    top_n    = int(body.get("top_n", 50))

    # Check cache first
    cache_key = f"signals_{min_prob:.2f}_{top_n}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("Serving scan from cache.")
        return jsonify({
            "success":    True,
            "count":      len(cached),
            "signals":    cached,
            "from_cache": True,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        })

    try:
        results = run_scan(min_prob=min_prob, top_n=top_n)
        _cache_set(cache_key, results)
        gc.collect()
        return jsonify({
            "success":    True,
            "count":      len(results),
            "signals":    results,
            "from_cache": False,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        })
    except FileNotFoundError as e:
        return jsonify({"error": str(e), "hint": "Run train_model.py first."}), 503
    except Exception as e:
        logger.exception("Scan failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze/<coin>")
def api_analyze(coin: str):
    """Deep analysis of one coin with order flow."""
    coin = coin.upper().strip()
    if not coin or len(coin) > 20:
        abort(400)

    cache_key = f"analyze_{coin}"
    hit = _cache_get(cache_key)
    if hit is not None:
        return jsonify({**hit, "from_cache": True})

    try:
        result = analyze_symbol(coin, include_order_flow=True)
        if result is None:
            return jsonify({
                "error":  f"Could not fetch or analyse {coin}",
                "symbol": coin,
                "hint":   "Check the symbol is a valid Binance USDT spot pair.",
            }), 404
        _cache_set(cache_key, result)
        gc.collect()
        return jsonify({**result, "from_cache": False})
    except FileNotFoundError as e:
        return jsonify({"error": str(e), "hint": "Run train_model.py first."}), 503
    except Exception as e:
        logger.exception(f"Analysis failed for {coin}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/signals")
def api_signals():
    """Return cached scan results if available."""
    min_prob = float(request.args.get("min_prob", 55)) / 100
    limit    = int(request.args.get("limit", 50))
    cache_key = f"signals_{min_prob:.2f}_{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify({
            "signals":    cached[:limit],
            "count":      len(cached[:limit]),
            "from_cache": True,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        })
    return jsonify({
        "signals":    [],
        "count":      0,
        "from_cache": False,
        "message":    "No scan data yet. Click Scan Now.",
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    })


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal(e):
    return jsonify({"error": "Internal server error"}), 500


# ── Startup ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  HALAL SCAN AI PRO ULTIMATE — Starting")
    logger.info("=" * 60)

    if MODEL_PATH.exists():
        try:
            load_model()
            logger.info("✅ Model pre-loaded successfully.")
        except Exception as e:
            logger.warning(f"Model pre-load failed: {e}")
    else:
        logger.warning("⚠️  No model found. Run train_model.py first.")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
