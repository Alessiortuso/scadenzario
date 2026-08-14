import logging
import os
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

#: Nome della cartella dati in %LOCALAPPDATA%, e quello che aveva prima che
#: l'applicazione si chiamasse Promemoria.
DATA_DIR_NAME = "Promemoria"
LEGACY_DATA_DIR_NAME = "Scadenzario"


@lru_cache
def _resolve_data_dir() -> Path:
    """Trova la cartella dati della postazione, spostandola dal vecchio nome.

    Un aggiornamento da Scadenzario trova nella vecchia cartella la
    configurazione della postazione — comprese le credenziali del database
    condiviso — e il database locale degli avvisi: si sposta il contenuto
    invece di ripartire da una cartella vuota, che vorrebbe dire rifare il
    primo avvio su ogni PC.

    Se lo spostamento non riesce (cartella aperta da un'altra istanza,
    permessi) si continua a usare quella vecchia: nessun dato si perde e al
    riavvio successivo si riprova. Il risultato è memorizzato perché la
    decisione va presa una volta per processo, non a ogni lettura.
    """
    base = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))
    path = base / DATA_DIR_NAME
    legacy = base / LEGACY_DATA_DIR_NAME

    if not path.exists() and legacy.is_dir():
        try:
            legacy.rename(path)
            logger.info("Cartella dati spostata da %s a %s", legacy, path)
        except OSError as exc:
            logger.warning("Cartella dati ancora su %s (%s)", legacy, exc)
            return legacy

    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings(BaseSettings):
    """Configurazione applicativa, sovrascrivibile da .env o variabili d'ambiente."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Promemoria"
    #: Database condiviso fra le postazioni (PostgreSQL in produzione).
    #: Vuoto di proposito: senza configurazione l'applicazione deve chiedere la
    #: connessione all'utente, non creare in silenzio un database locale che
    #: farebbe divergere i dati fra le postazioni.
    database_url: str = ""
    #: Database locale alla postazione: stato di consegna delle notifiche.
    #: Vuoto = calcolato in %LOCALAPPDATA%\\Promemoria.
    local_database_url: str = ""
    #: Nome con cui questa postazione si identifica nei log e nelle notifiche.
    device_name: str = ""
    #: Solo la postazione designata invia le email, per non mandarne una copia
    #: per ogni PC su cui gira l'applicazione.
    email_sender_device: bool = False
    timezone: str = "Europe/Rome"
    #: Serve solo al dev server Angular, che gira sulla 4300 (la 4200 era
    #: occupata su questa macchina). Nel pacchetto distribuito il backend serve
    #: anche l'interfaccia, quindi non c'è nessuna origine esterna da ammettere.
    cors_origins: str = "http://localhost:4300"

    # Preavvisi di default (giorni prima) usati quando il promemoria non ne
    # definisce di propri.
    default_alert_offsets: str = "30,15,7,3,1,0"
    # Ogni quanti giorni ripetere l'avviso per una scadenza già scaduta (0 = mai).
    overdue_repeat_days: int = 3
    overdue_max_reminders: int = 5

    # Scheduler: ogni quanti secondi controllare le notifiche da inviare.
    scheduler_interval_seconds: int = 300
    # Orario (HH:MM) a cui inviare le notifiche generate per un dato giorno.
    daily_send_time: str = "08:00"

    # Web Push (VAPID). Generare le chiavi con: python -m app.tools.vapid_keys
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"

    # Email (SMTP). Se smtp_host è vuoto il canale email resta disattivo.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "promemoria@example.com"
    smtp_use_tls: bool = True

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def data_dir(self) -> Path:
        """Cartella per i dati locali della postazione (creata se assente)."""
        return _resolve_data_dir()

    @property
    def resolved_local_database_url(self) -> str:
        if self.local_database_url:
            return self.local_database_url
        return f"sqlite:///{(self.data_dir / 'locale.db').as_posix()}"

    @property
    def resolved_device_name(self) -> str:
        return self.device_name or os.environ.get("COMPUTERNAME") or "postazione"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def default_offsets(self) -> list[int]:
        return sorted({int(x) for x in self.default_alert_offsets.split(",") if x.strip()}, reverse=True)

    @property
    def send_hour_minute(self) -> tuple[int, int]:
        hh, _, mm = self.daily_send_time.partition(":")
        return int(hh), int(mm or 0)

    @property
    def push_enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
