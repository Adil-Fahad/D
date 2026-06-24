"""
Persistent probability alerts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from config import ALERTS_PATH

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_data_dir() -> None:
    ALERTS_PATH.parent.mkdir(exist_ok=True)


def load_alerts() -> list[dict]:
    if not ALERTS_PATH.exists():
        return []
    try:
        data = json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("Could not load alerts: %s", exc)
        return []


def save_alerts(alerts: list[dict]) -> None:
    _ensure_data_dir()
    ALERTS_PATH.write_text(json.dumps(alerts, indent=2), encoding="utf-8")


def add_alert(symbol: str, threshold: float) -> dict:
    symbol = symbol.upper().strip().replace("/USDT", "")
    threshold = max(1.0, min(float(threshold), 99.9))

    alerts = load_alerts()
    existing = next(
        (
            a for a in alerts
            if a.get("symbol") == symbol
            and float(a.get("threshold", 0)) == threshold
            and a.get("active", True)
        ),
        None,
    )
    if existing:
        return existing

    alert = {
        "id": uuid4().hex,
        "symbol": symbol,
        "threshold": round(threshold, 2),
        "active": True,
        "created_at": _now_iso(),
        "triggered_at": None,
        "last_probability": None,
        "last_verdict": None,
        "message": None,
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> bool:
    alerts = load_alerts()
    kept = [a for a in alerts if a.get("id") != alert_id]
    save_alerts(kept)
    return len(kept) != len(alerts)


def check_alerts(signals: list[dict]) -> list[dict]:
    alerts = load_alerts()
    if not alerts or not signals:
        return []

    signal_by_symbol = {
        str(s.get("symbol", "")).upper(): s
        for s in signals
        if s.get("symbol")
    }
    triggered: list[dict] = []

    for alert in alerts:
        if not alert.get("active", True):
            continue
        signal = signal_by_symbol.get(str(alert.get("symbol", "")).upper())
        if not signal:
            continue

        probability = float(signal.get("probability") or 0.0)
        threshold = float(alert.get("threshold") or 0.0)
        alert["last_probability"] = round(probability, 2)
        alert["last_verdict"] = signal.get("combined_verdict") or signal.get("verdict")

        if probability >= threshold:
            alert["active"] = False
            alert["triggered_at"] = _now_iso()
            alert["message"] = (
                f"{alert['symbol']} reached {probability:.1f}% AI probability "
                f"(alert {threshold:.1f}%)."
            )
            triggered.append({**alert, "signal": signal})

    save_alerts(alerts)
    return triggered


def recent_notifications(limit: int = 10) -> list[dict]:
    triggered = [a for a in load_alerts() if a.get("triggered_at")]
    triggered.sort(key=lambda a: a.get("triggered_at") or "", reverse=True)
    return triggered[:limit]
