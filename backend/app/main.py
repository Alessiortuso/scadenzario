from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

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
    version="1.1.1",
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
    from .db import is_shared_configured

    return {
        "status": "ok",
        "timezone": settings.timezone,
        "device": runtime_config.device_name(),
        "database_configured": is_shared_configured(),
        "push_configured": settings.push_enabled,
        "email_configured": settings.email_enabled,
    }


class SpaStaticFiles(StaticFiles):
    """File statici con fallback su `index.html`.

    Le rotte dell'interfaccia (`/promemoria/12`, `/calendario`, ...) esistono
    solo lato browser: senza questo fallback un accesso diretto o un
    ricaricamento della pagina risponderebbe 404.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


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
