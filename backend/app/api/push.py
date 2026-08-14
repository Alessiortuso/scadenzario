from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..db import get_local_db
from ..models import PushSubscription
from ..schemas import PublicKeyRead, PushSubscriptionCreate, PushSubscriptionRead
from ..services.notifiers import webpush

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/public-key", response_model=PublicKeyRead)
def public_key() -> PublicKeyRead:
    return PublicKeyRead(public_key=env_settings.vapid_public_key, enabled=env_settings.push_enabled)


@router.get("/subscriptions", response_model=list[PushSubscriptionRead])
def list_subscriptions(db: Session = Depends(get_local_db)) -> list[PushSubscription]:
    return list(db.scalars(select(PushSubscription).order_by(PushSubscription.created_at.desc())).all())


@router.post("/subscribe", response_model=PushSubscriptionRead, status_code=201)
def subscribe(payload: PushSubscriptionCreate, db: Session = Depends(get_local_db)) -> PushSubscription:
    if not env_settings.push_enabled:
        raise HTTPException(status_code=503, detail="Web Push non configurato (chiavi VAPID mancanti)")

    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=payload.endpoint)
        db.add(sub)
    sub.p256dh = payload.keys.p256dh
    sub.auth = payload.keys.auth
    sub.label = payload.label
    sub.active = True
    sub.last_error = None
    db.commit()
    return sub


@router.post("/unsubscribe", status_code=204)
def unsubscribe(endpoint: str = Body(..., embed=True), db: Session = Depends(get_local_db)) -> None:
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if sub is not None:
        db.delete(sub)
        db.commit()


@router.post("/test")
def send_test(db: Session = Depends(get_local_db)) -> dict:
    if not env_settings.push_enabled:
        raise HTTPException(status_code=503, detail="Web Push non configurato (chiavi VAPID mancanti)")

    payload = json.dumps(
        {
            "title": "Promemoria: notifica di prova",
            "body": "Se leggi questo messaggio le notifiche desktop funzionano.",
            "severity": "info",
            "url": "/",
            "tag": "test",
        },
        ensure_ascii=False,
    )
    sent, failed, details = webpush.send_raw(db, payload)
    if sent == 0 and failed == 0:
        raise HTTPException(status_code=404, detail="Nessun dispositivo registrato per le notifiche")
    return {"sent": sent, "failed": failed, "details": details}

