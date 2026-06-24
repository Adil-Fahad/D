"""
Background scan scheduler.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from config import (
    AUTO_SCAN_ENABLED,
    AUTO_SCAN_INTERVAL_HOURS,
    AUTO_SCAN_MIN_PROB,
    AUTO_SCAN_TOP_N,
    SIGNALS_PATH,
)

logger = logging.getLogger(__name__)

_scan_lock = threading.Lock()
_state_lock = threading.Lock()
_thread: threading.Thread | None = None

_state = {
    "enabled": AUTO_SCAN_ENABLED,
    "interval_hours": AUTO_SCAN_INTERVAL_HOURS,
    "in_progress": False,
    "last_scan_time": None,
    "last_scan_count": None,
    "last_error": None,
    "next_scan_time": None,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _initial_last_scan_time() -> datetime | None:
    if not SIGNALS_PATH.exists():
        return None
    try:
        return datetime.fromtimestamp(SIGNALS_PATH.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def get_scheduler_state() -> dict:
    with _state_lock:
        state = dict(_state)

    now = _now()
    next_dt = state.get("next_scan_time")
    seconds = None
    if isinstance(next_dt, datetime):
        seconds = max(0, int((next_dt - now).total_seconds()))

    return {
        "enabled": state["enabled"],
        "interval_hours": state["interval_hours"],
        "in_progress": state["in_progress"],
        "last_scan_time": _iso(state.get("last_scan_time")),
        "last_scan_count": state.get("last_scan_count"),
        "last_error": state.get("last_error"),
        "next_scan_time": _iso(next_dt),
        "next_scan_in_seconds": seconds,
    }


def execute_scan(
    min_prob: float = AUTO_SCAN_MIN_PROB,
    top_n: int = AUTO_SCAN_TOP_N,
    source: str = "manual",
) -> list[dict]:
    if not _scan_lock.acquire(blocking=False):
        raise RuntimeError("A scan is already running.")

    from scanner import run_scan

    _set_state(in_progress=True, last_error=None)
    try:
        results = run_scan(min_prob=min_prob, top_n=top_n, save_csv=True)
        _set_state(
            in_progress=False,
            last_scan_time=_now(),
            last_scan_count=len(results),
            next_scan_time=_now() + timedelta(hours=AUTO_SCAN_INTERVAL_HOURS),
        )
        logger.info("%s scan complete: %s signals.", source.capitalize(), len(results))
        return results
    except Exception as exc:
        _set_state(in_progress=False, last_error=str(exc))
        raise
    finally:
        _scan_lock.release()


def _scheduler_loop() -> None:
    logger.info("Auto scan scheduler started; interval %.2fh.", AUTO_SCAN_INTERVAL_HOURS)
    while True:
        state = get_scheduler_state()
        if not state["enabled"]:
            time.sleep(60)
            continue

        next_scan = state.get("next_scan_time")
        if not next_scan:
            _set_state(next_scan_time=_now() + timedelta(hours=AUTO_SCAN_INTERVAL_HOURS))
            time.sleep(5)
            continue

        try:
            next_dt = datetime.fromisoformat(next_scan)
        except Exception:
            next_dt = _now() + timedelta(hours=AUTO_SCAN_INTERVAL_HOURS)
            _set_state(next_scan_time=next_dt)

        wait_s = (next_dt - _now()).total_seconds()
        if wait_s > 0:
            time.sleep(min(wait_s, 60))
            continue

        try:
            execute_scan(source="scheduled")
        except Exception as exc:
            logger.exception("Scheduled scan failed: %s", exc)
            _set_state(next_scan_time=_now() + timedelta(hours=AUTO_SCAN_INTERVAL_HOURS))


def start_scheduler() -> bool:
    global _thread
    if not AUTO_SCAN_ENABLED:
        _set_state(enabled=False)
        return False

    if _state["last_scan_time"] is None:
        _set_state(last_scan_time=_initial_last_scan_time())
    if _state["next_scan_time"] is None:
        _set_state(next_scan_time=_now() + timedelta(hours=AUTO_SCAN_INTERVAL_HOURS))

    if _thread and _thread.is_alive():
        return True

    _thread = threading.Thread(target=_scheduler_loop, name="auto-scan", daemon=True)
    _thread.start()
    return True
