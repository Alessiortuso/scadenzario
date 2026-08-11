from __future__ import annotations

import asyncio
import logging

from ..config import settings as env_settings
from ..db import LocalSession, SharedSession, is_shared_configured
from . import dispatcher

logger = logging.getLogger(__name__)


class AlertScheduler:
    """Loop asincrono che ogni N secondi rigenera e spedisce gli avvisi.

    Volutamente senza dipendenze esterne: un singolo task asyncio è sufficiente
    per questo carico. Per più repliche del backend, spostare il ciclo su un
    worker dedicato (o su un cron) chiamando POST /api/scheduler/run.
    """

    def __init__(self, interval_seconds: int | None = None) -> None:
        self.interval = interval_seconds or env_settings.scheduler_interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.last_result: dict | None = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.last_result = await asyncio.to_thread(self._run_once)
            except Exception:  # pragma: no cover - difensivo
                logger.exception("Ciclo scheduler fallito")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    @staticmethod
    def _run_once() -> dict:
        if not is_shared_configured():
            return {"skipped": "database condiviso non configurato"}

        shared_db = SharedSession()
        local_db = LocalSession()
        try:
            return dispatcher.run_cycle(shared_db, local_db)
        finally:
            local_db.close()
            shared_db.close()

    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduler avviato (intervallo %ss)", self.interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # pragma: no cover
                pass
            self._task = None


scheduler = AlertScheduler()
