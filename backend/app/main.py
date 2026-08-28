from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import runtime_config
from .api import api_router
from .config import settings
from .db import NotConfigured, init_db
from .services.scheduler import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prima riga di ogni sessione: quale versione sta girando su questa
    # postazione. Diagnosticare a distanza senza saperlo è indovinare.
    logging.getLogger(__name__).info(
        "%s %s — postazione %s", settings.app_name, app.version, runtime_config.device_name()
    )
    try:
        init_db()
    except Exception:
        # Database condiviso non configurato o irraggiungibile: l'applicazione
        # deve partire lo stesso per poter mostrare la schermata di setup.
        logging.getLogger(__name__).warning(
            "Database condiviso non disponibile all'avvio: si attende la configurazione",
            exc_info=True,
        )
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    description="Scadenze, appuntamenti e note con avvisi e notifiche desktop.",
    version="1.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(NotConfigured)
async def _not_configured_handler(request: Request, exc: NotConfigured) -> JSONResponse:
    """Il frontend intercetta questo codice e porta alla schermata di configurazione."""
    return JSONResponse(
        status_code=503,
        content={"code": "not_configured", "detail": "Database condiviso non ancora configurato"},
    )


@app.get("/api/health", tags=["sistema"])
def health() -> dict:
    from . import db as db_module
    from .db import is_shared_configured
    from .migrations import SchemaPiuRecente

    return {
        "status": "ok",
        "timezone": settings.timezone,
        "device": runtime_config.device_name(),
        "database_configured": is_shared_configured(),
        # Questa postazione è rimasta indietro: il database condiviso è già
        # stato migrato da una versione più recente. Sta qui, e non solo in
        # `/api/setup/status`, perché il primo che deve saperlo è Electron —
        # che l'interfaccia non la legge, e all'avvio interroga già questa
        # rotta. Sapendolo, cerca l'aggiornamento subito invece di aspettare
        # il giro dell'ora, così il pulsante «Aggiorna adesso» trova il
        # pacchetto già pronto quando l'utente ci arriva.
        "schema_ahead": db_module.shared_error_code == SchemaPiuRecente.codice,
        "push_configured": settings.push_enabled,
        "email_configured": settings.email_enabled,
    }


class SpaStaticFiles(StaticFiles):
    """File statici con fallback su `index.html`.

    Le rotte dell'interfaccia (`/promemoria/12`, `/calendario`, ...) esistono
    solo lato browser: senza questo fallback un accesso diretto o un
    ricaricamento della pagina risponderebbe 404.

    Due accortezze, imparate da una schermata bianca dopo un aggiornamento:

    - il fallback vale **solo per le rotte**, non per i file. Un `.js` che non
      esiste più deve rispondere 404: rispondendo `index.html` il browser si
      ritrova dell'HTML dove si aspetta uno script, non esegue niente e mostra
      una pagina bianca senza un errore che aiuti;
    - `index.html` non si mette mai in cache. Ogni compilazione cambia il nome
      degli script (`main-VBIVJOH5.js`), e senza `Cache-Control` il browser
      applica la propria euristica: dopo un aggiornamento continuava a chiedere
      i file della versione precedente, che non esistono più.
    """

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
            servito = path
        except StarletteHTTPException as exc:
            # `PurePosixPath` e non `Path`: qui gli URL arrivano già normalizzati
            # con le barre in avanti, anche su Windows.
            if exc.status_code == 404 and not PurePosixPath(path).suffix:
                response = await super().get_response("index.html", scope)
                servito = "index.html"
            else:
                raise

        if servito in ("", ".", "index.html"):
            response.headers["Cache-Control"] = "no-store"
        else:
            # Il nome contiene già l'impronta del contenuto, ma una rivalidazione
            # su 127.0.0.1 non costa nulla e toglie di mezzo una classe di guai.
            response.headers["Cache-Control"] = "no-cache"
        return response


def _mount_frontend() -> None:
    """Serve il frontend compilato, se presente.

    In sviluppo si usa `ng serve` e questa cartella non esiste; nel pacchetto
    distribuito il backend serve anche l'interfaccia, così gira un processo solo.
    """
    candidates = [
        Path(__file__).resolve().parent / "static",  # copia inclusa nel pacchetto
        Path(__file__).resolve().parents[2] / "frontend" / "dist" / "frontend" / "browser",
    ]
    for path in candidates:
        if (path / "index.html").exists():
            app.mount("/", SpaStaticFiles(directory=path, html=True), name="frontend")
            logging.getLogger(__name__).info("Frontend servito da %s", path)
            return


_mount_frontend()
