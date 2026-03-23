from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List

from .worker import TradingServiceWorker


@dataclass
class JobStatus:
    id: str
    interval_seconds: int
    next_run_time: str | None = None
    last_run_time: str | None = None


class _LoopJob:
    def __init__(self, job_id: str, interval_seconds: int, func: Callable[[], dict]):
        self.job_id = job_id
        self.interval_seconds = max(interval_seconds, 1)
        self.func = func
        self.status = JobStatus(id=job_id, interval_seconds=self.interval_seconds)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"job-{job_id}")

    def start(self):
        self.status.next_run_time = datetime.now(timezone.utc).isoformat()
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            now = datetime.now(timezone.utc)
            self.status.last_run_time = now.isoformat()
            try:
                self.func()
            except Exception:
                pass
            next_run = now + timedelta(seconds=self.interval_seconds)
            self.status.next_run_time = next_run.isoformat()
            self._stop.wait(self.interval_seconds)

    def stop(self):
        self._stop.set()


class WorkerScheduler:
    def __init__(self, worker: TradingServiceWorker):
        self.worker = worker
        self.jobs: List[_LoopJob] = []
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.jobs = [
            _LoopJob("trading_cycle", self.worker.settings.trading_interval_minutes * 60, self.worker.trading_cycle),
            _LoopJob("optimization_cycle", self.worker.settings.optimization_interval_hours * 3600, self.worker.optimization_cycle),
        ]
        for job in self.jobs:
            job.start()
        self._started = True

    def shutdown(self) -> None:
        if not self._started:
            return
        for job in self.jobs:
            job.stop()
        self._started = False

    def status(self) -> dict:
        return {
            "started": self._started,
            "jobs": [job.status.__dict__ for job in self.jobs],
        }
