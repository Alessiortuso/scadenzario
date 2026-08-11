from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import runtime_config
from ..db import get_db, get_local_db
from ..schemas import AppSettings, SettingsRead
from ..services import alerts, dispatcher, settings_service
from ..services.scheduler import scheduler

router = APIRouter(prefix="/api", tags=["impostazioni"])


@router.get("/settings", response_model=SettingsRead)
def read_settings(db: Session = Depends(get_db)) -> SettingsRead:
    return settings_service.to_read(settings_service.get_settings(db))


@router.put("/settings", response_model=SettingsRead)
def write_settings(
    payload: AppSettings,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> SettingsRead:
    saved = settings_service.save_settings(db, payload)
    # I preavvisi/orari cambiati vanno riflessi sugli avvisi non ancora consegnati.
    alerts.sync_all(db, local_db)
    return settings_service.to_read(saved)


@router.post("/scheduler/run")
def run_now(db: Session = Depends(get_db), local_db: Session = Depends(get_local_db)) -> dict:
    """Esegue subito un ciclo di generazione + consegna (utile per test o cron esterno)."""
    return dispatcher.run_cycle(db, local_db)


@router.get("/scheduler/status")
def scheduler_status() -> dict:
    return {
        "interval_seconds": scheduler.interval,
        "last_result": scheduler.last_result,
        "device_name": runtime_config.device_name(),
        "email_sender_device": runtime_config.email_sender_device(),
    }
