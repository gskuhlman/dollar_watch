"""In-process daily collector for the Streamlit server.

While the dashboard server is running, one daemon thread per process runs the headless
collector once a day at a configured America/New_York time and on startup when the newest
saved snapshot is stale. Open pages pick up the result through ``generation``: the app
keys its data cache on it and a polling fragment reruns the page when it advances.
"""
from __future__ import annotations

import re
import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

THREAD_NAME = "dollar_watch-daily-refresh"
DEFAULT_TIME = "18:30"  # after the U.S. close and the day's FRED/Treasury/NY Fed releases
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_START_LOCK = threading.Lock()


def parse_time(value: Any) -> tuple[int, int]:
    m = _TIME_RE.match(str(value or "").strip())
    if not m:
        m = _TIME_RE.match(DEFAULT_TIME)
    return int(m.group(1)), int(m.group(2))


def next_run_after(now: datetime, hhmm: Any, tz: str = "America/New_York") -> datetime:
    """Next wall-clock occurrence of ``hhmm`` in ``tz`` strictly after ``now`` (DST-aware)."""
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    hour, minute = parse_time(hhmm)
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local:
        target = (local + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target


class DailyRefresher:
    """Run ``run_fn`` daily. ``run_fn`` returns a dict with ``bundle`` and ``snapshot_id``."""

    def __init__(
        self,
        run_fn: Callable[[], dict],
        config_fn: Callable[[], dict],
        newest_snapshot_fn: Callable[[], str | None],
        *,
        tz: str = "America/New_York",
        stale_hours: float = 20.0,
        tick_seconds: float = 60.0,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.run_fn = run_fn
        self.config_fn = config_fn
        self.newest_snapshot_fn = newest_snapshot_fn
        self.tz = tz
        self.stale_hours = stale_hours
        self.tick_seconds = tick_seconds
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._run_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._bundle: dict | None = None
        self._next_run: datetime | None = None
        self._status: dict = {
            "generation": 0, "running": False, "last_reason": None, "last_started": None,
            "last_finished": None, "last_ok": None, "last_error": None, "last_snapshot_id": None,
        }

    # ---- configuration -------------------------------------------------
    def config(self) -> dict:
        try:
            cfg = dict(self.config_fn() or {})
        except Exception:
            cfg = {}
        hour, minute = parse_time(cfg.get("time"))
        return {"enabled": bool(cfg.get("enabled", True)), "time": f"{hour:02d}:{minute:02d}"}

    def snapshot_age_hours(self) -> float | None:
        try:
            newest = self.newest_snapshot_fn()
            if not newest:
                return None
            ts = datetime.fromisoformat(str(newest).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (self.now_fn() - ts).total_seconds() / 3600.0
        except Exception:
            return None

    def catchup_due(self) -> bool:
        age = self.snapshot_age_hours()
        return age is None or age > self.stale_hours

    # ---- running -------------------------------------------------------
    def run_now(self, reason: str = "manual") -> bool:
        """Run synchronously. Returns False without running when a run is already in progress."""
        if not self._run_lock.acquire(blocking=False):
            return False
        self._mark_running(reason)
        self._execute_locked()
        return True

    def _mark_running(self, reason: str) -> None:
        with self._state_lock:
            self._status.update(running=True, last_reason=reason, last_started=self.now_fn().isoformat())

    def _execute_locked(self) -> None:
        """Run ``run_fn``; the caller holds ``_run_lock`` and has marked the run started."""
        try:
            try:
                result = self.run_fn() or {}
                with self._state_lock:
                    self._bundle = result.get("bundle")
                    self._status.update(
                        last_ok=True, last_error=None, last_snapshot_id=result.get("snapshot_id"),
                        generation=self._status["generation"] + 1,
                    )
            except Exception as exc:
                with self._state_lock:
                    self._status.update(last_ok=False, last_error=f"{type(exc).__name__}: {exc}")
                traceback.print_exc()
            finally:
                with self._state_lock:
                    self._status.update(running=False, last_finished=self.now_fn().isoformat())
        finally:
            self._run_lock.release()

    def wait_idle(self, timeout: float) -> bool:
        """Block until no run is in progress (True) or ``timeout`` seconds pass (False)."""
        if not self._run_lock.acquire(timeout=timeout):
            return False
        self._run_lock.release()
        return True

    def trigger_async(self, reason: str = "manual") -> bool:
        if self._run_lock.locked():
            return False
        threading.Thread(target=self.run_now, args=(reason,), name=f"{THREAD_NAME}-manual", daemon=True).start()
        return True

    def tick(self) -> bool:
        """One scheduler step. Returns True when a scheduled run happened."""
        cfg = self.config()
        if not cfg["enabled"]:
            self._next_run = None
            return False
        now = self.now_fn()
        if self._next_run is None or self._next_run.strftime("%H:%M") != cfg["time"]:
            self._next_run = next_run_after(now, cfg["time"], self.tz)
        if now >= self._next_run:
            self._next_run = None  # recomputed (tomorrow) on the next tick
            self.run_now("scheduled")
            return True
        return False

    def _loop(self, catchup: bool = False) -> None:
        if catchup:
            self._execute_locked()
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                traceback.print_exc()
            self._stop.wait(self.tick_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        # Claim the startup catch-up run before returning, so a page loading right after start()
        # sees running=True and waits for it instead of collecting the same data in parallel.
        catchup = bool(self.config()["enabled"] and self.catchup_due() and self._run_lock.acquire(blocking=False))
        if catchup:
            self._mark_running("startup catch-up (newest snapshot stale)")
        self._thread = threading.Thread(target=self._loop, args=(catchup,), name=THREAD_NAME, daemon=True)
        self._thread.refresher = self  # type: ignore[attr-defined]
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ---- read side -----------------------------------------------------
    @property
    def generation(self) -> int:
        with self._state_lock:
            return int(self._status["generation"])

    def bundle_for(self, generation: int) -> dict | None:
        """The bundle produced by run ``generation``, or None if that is not the latest run."""
        with self._state_lock:
            if generation > 0 and generation == self._status["generation"]:
                return self._bundle
            return None

    def status(self) -> dict:
        cfg = self.config()
        if cfg["enabled"] and self._next_run is None:
            self._next_run = next_run_after(self.now_fn(), cfg["time"], self.tz)
        with self._state_lock:
            out = dict(self._status)
        out.update(enabled=cfg["enabled"], schedule_time=cfg["time"], tz=self.tz,
                   next_run=self._next_run.isoformat() if cfg["enabled"] and self._next_run else None,
                   thread_alive=bool(self._thread and self._thread.is_alive()))
        return out


def get_or_start(**kwargs) -> DailyRefresher:
    """Process-wide singleton that survives Streamlit script and module reloads."""
    with _START_LOCK:
        for t in threading.enumerate():
            existing = getattr(t, "refresher", None)
            if t.name == THREAD_NAME and t.is_alive() and existing is not None:
                return existing
        refresher = DailyRefresher(**kwargs)
        refresher.start()
        return refresher
