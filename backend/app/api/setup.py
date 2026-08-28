from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from .. import runtime_config
from .. import db as db_module
from ..db import configure_shared, is_shared_configured

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/setup", tags=["configurazione"])


class SetupStatus(BaseModel):
    configured: bool
    database_url_masked: str | None
    source: str
    device_name: str
    email_sender_device: bool
    #: Perché la postazione non è collegata pur avendo una configurazione: si
    #: mostra in cima alla schermata, così l'utente sa se il rimedio è
    #: riscrivere la stringa o aggiornare l'applicazione.
    last_error: str | None = None
    #: Lo stesso guasto in forma confrontabile. Vale `schema_piu_recente`
    #: quando la postazione è semplicemente indietro di una versione: è il caso
    #: in cui la schermata mostra il pulsante che aggiorna sul posto.
    last_error_code: str | None = None


class ConnectionTest(BaseModel):
    database_url: str = Field(min_length=10)


class SetupPayload(ConnectionTest):
    device_name: str | None = None
    email_sender_device: bool = False


class TestResult(BaseModel):
    ok: bool
    detail: str


def _normalize(url: str) -> str:
    """Accetta la stringa così come la fornisce Neon e la rende utilizzabile.

    Neon consegna `postgresql://...`; SQLAlchemy ha bisogno del driver
    esplicito, quindi si aggiunge `+psycopg` se manca.
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _try_connect(url: str) -> TestResult:
    from sqlalchemy import create_engine

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            version = connection.execute(text("select version()")).scalar() or ""
        return TestResult(ok=True, detail=version.split(" on ")[0])
    except Exception as exc:
        message = str(exc).splitlines()[0][:300]
        return TestResult(ok=False, detail=message)
    finally:
        engine.dispose()


@router.get("/status", response_model=SetupStatus)
def status() -> SetupStatus:
    url = runtime_config.database_url()
    return SetupStatus(
        configured=is_shared_configured(),
        database_url_masked=runtime_config.mask(url) if url else None,
        source=runtime_config.source(),
        device_name=runtime_config.device_name(),
        email_sender_device=runtime_config.email_sender_device(),
        last_error=None if is_shared_configured() else db_module.shared_error,
        last_error_code=None if is_shared_configured() else db_module.shared_error_code,
    )


@router.post("/test", response_model=TestResult)
def test_connection(payload: ConnectionTest) -> TestResult:
    return _try_connect(_normalize(payload.database_url))


@router.post("", response_model=SetupStatus)
def save_setup(payload: SetupPayload) -> SetupStatus:
    url = _normalize(payload.database_url)
    result = _try_connect(url)
    if not result.ok:
        raise HTTPException(status_code=400, detail=f"Connessione non riuscita: {result.detail}")

    runtime_config.save(
        {
            "database_url": url,
            "device_name": payload.device_name or None,
            "email_sender_device": payload.email_sender_device,
        }
    )

    try:
        configure_shared(url, migrate=True)
    except Exception as exc:
        # La connessione funziona ma lo schema non si lascia preparare: capita
        # con un utente senza permessi di creare tabelle. Va detto qui, non
        # lasciato emergere come errore generico al primo uso.
        logger.exception("Preparazione dello schema condiviso fallita")
        raise HTTPException(
            status_code=500,
            detail=f"Connessione riuscita, ma la preparazione dello schema è fallita: {str(exc).splitlines()[0][:300]}",
        ) from exc

    logger.info("Database condiviso configurato su questa postazione")
    return status()
