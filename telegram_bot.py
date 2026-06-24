"""
Telegram alert delivery for STRONG BUY signals.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter

from config import (
    HTTP_TIMEOUT_S,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_SENT_PATH,
)

logger = logging.getLogger(__name__)

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
        session.mount("https://", adapter)
        _session = session
    return _session


def _load_sent() -> set[str]:
    if not TELEGRAM_SENT_PATH.exists():
        return set()
    try:
        return set(json.loads(TELEGRAM_SENT_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_sent(keys: set[str]) -> None:
    TELEGRAM_SENT_PATH.parent.mkdir(exist_ok=True)
    trimmed = sorted(keys)[-1000:]
    TELEGRAM_SENT_PATH.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


def _format_time(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return value


def format_signal_message(signal: dict) -> str:
    flow = signal.get("flow_signal") or "ON DEMAND"
    return "\n".join(
        [
            "\U0001F54C HALAL SCAN AI ALERT",
            f"Coin: {signal.get('symbol', '-')}",
            f"Probability: {float(signal.get('probability') or 0):.0f}%",
            f"Verdict: {signal.get('combined_verdict') or signal.get('verdict') or '-'}",
            f"Price: ${float(signal.get('price') or 0):,.6g}",
            f"RSI: {float(signal.get('rsi') or 0):.0f}",
            f"ADX: {float(signal.get('adx') or 0):.0f}",
            f"Flow: {flow}",
            f"Time: {_format_time(signal.get('scanned_at'))}",
        ]
    )


def send_signal_alert(signal: dict) -> bool:
    if not TELEGRAM_ENABLED:
        return False

    verdict = signal.get("combined_verdict") or signal.get("verdict")
    if verdict != "STRONG BUY":
        return False

    key = f"{signal.get('symbol')}|{signal.get('scanned_at')}|{signal.get('probability')}"
    sent = _load_sent()
    if key in sent:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": format_signal_message(signal),
        "disable_web_page_preview": True,
    }

    try:
        response = _get_session().post(url, json=payload, timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
        sent.add(key)
        _save_sent(sent)
        return True
    except Exception as exc:
        logger.warning("Telegram alert failed for %s: %s", signal.get("symbol"), exc)
        return False


def send_scan_alerts(signals: list[dict]) -> int:
    sent_count = 0
    for signal in signals:
        if send_signal_alert(signal):
            sent_count += 1
    return sent_count
