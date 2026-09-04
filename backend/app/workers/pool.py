"""A small in-process job runner: a ThreadPoolExecutor keyed by job id so the same job is never queued twice.

# ponytail: in-process threads are enough for a single-user desktop tool; swap for RQ/Celery if
# processing ever needs to survive restarts or run on more than one machine.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from ..config import settings

log = logging.getLogger(__name__)


class Pool:
    def __init__(self, workers: int) -> None:
        self._workers = max(1, workers)
        self._ex = ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="job")
        self._closed = False
        self._running: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, key: str, fn: Callable, *args) -> bool:
        """Queue fn(*args) under `key`. Returns False if a job with that key is still running."""
        with self._lock:
            fut = self._running.get(key)
            if fut is not None and not fut.done():
                return False
            if self._closed:  # the app lifespan closed us (e.g. a previous test client); start a fresh executor
                self._ex = ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="job")
                self._closed = False
            self._running[key] = self._ex.submit(self._run, key, fn, *args)
            return True

    def _run(self, key: str, fn: Callable, *args) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 - a job must never take the pool down
            log.exception("job %s failed", key)
        finally:
            with self._lock:
                self._running.pop(key, None)

    def is_running(self, key: str) -> bool:
        with self._lock:
            fut = self._running.get(key)
            return fut is not None and not fut.done()

    def running_keys(self) -> list[str]:
        with self._lock:
            return [k for k, f in self._running.items() if not f.done()]

    def wait_idle(self, timeout: float = 30) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.running_keys():
                return True
            time.sleep(0.05)
        return False

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            self._ex.shutdown(wait=False, cancel_futures=True)


pool = Pool(settings.workers)
