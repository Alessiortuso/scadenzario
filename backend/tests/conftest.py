"""Impianto dei test.

I due database sono ricreati in memoria a ogni test **passando dalle
migrazioni**, non da `create_all`: così ogni esecuzione della suite verifica
anche che le migrazioni producano davvero lo schema che il codice si aspetta.

I servizi ricevono le sessioni come parametro, quindi non serve toccare lo stato
globale di `app.db` se non per gli endpoint HTTP (vedi `client`).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import migrations
from app.models import Reminder
from app.schemas import AppSettings


def _memory_session(target: str) -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # una sola connessione: il database vive finché vive l'engine
    )
    migrations.upgrade(engine, target)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


@pytest.fixture
def shared_db() -> Session:
    """Database condiviso: promemoria, categorie, impostazioni."""
    db = _memory_session("shared")
    yield db
    db.close()


@pytest.fixture
def local_db() -> Session:
    """Database della postazione: notifiche e iscrizioni push."""
    db = _memory_session("local")
    yield db
    db.close()


@pytest.fixture
def today() -> date:
    return date.today()


@pytest.fixture
def app_settings() -> AppSettings:
    """Impostazioni esplicite: i test non devono dipendere dal `.env` locale."""
    return AppSettings(
        channel_inapp=True,
        channel_push=False,
        channel_email=False,
        default_alert_offsets=[30, 15, 7, 3, 1, 0],
        overdue_repeat_days=3,
        overdue_max_reminders=5,
        daily_send_time="08:00",
        notify_emails=[],
    )


@pytest.fixture
def client(shared_db: Session, local_db: Session, monkeypatch):
    """Client HTTP con i due database di test al posto di quelli reali.

    `to-display` non passa dalle dipendenze per il database condiviso — lo apre
    da sé, proprio per non rispondere 503 quando manca — quindi va sostituita
    anche la sessione che usa.
    """
    from fastapi.testclient import TestClient

    from app.api import notifications as notifications_api
    from app.db import get_db, get_local_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: shared_db
    app.dependency_overrides[get_local_db] = lambda: local_db
    monkeypatch.setattr(notifications_api, "SharedSession", lambda: shared_db)
    monkeypatch.setattr(notifications_api, "is_shared_configured", lambda: True)

    # Senza `with`: il lifespan non parte, quindi i test non toccano il
    # database reale della postazione né il PostgreSQL condiviso.
    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def make_reminder(shared_db: Session):
    """Crea un promemoria aperto, con `created_at` regolabile.

    `created_at` conta: il motore degli avvisi lo usa per non sparare tutti i
    preavvisi arretrati di un promemoria inserito a ridosso.
    """

    def _make(
        due_in_days: int,
        *,
        title: str = "Promemoria di prova",
        created_days_ago: int = 0,
        alert_offsets: list[int] | None = None,
        **kwargs,
    ) -> Reminder:
        reminder = Reminder(
            title=title,
            due_date=date.today() + timedelta(days=due_in_days),
            created_at=datetime.now(timezone.utc) - timedelta(days=created_days_ago),
            alert_offsets=alert_offsets,
            **kwargs,
        )
        shared_db.add(reminder)
        shared_db.commit()
        return reminder

    return _make
