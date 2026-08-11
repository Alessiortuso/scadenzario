from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db, get_local_db
from ..schemas import ImportMapping, ImportPreview, ImportResult
from ..services import importers

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _read_table(file: UploadFile) -> importers.SourceTable:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File troppo grande (max 10 MB)")
    try:
        adapter = importers.adapter_for(file.filename or "")
        return adapter.read(content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # pragma: no cover - file corrotti
        raise HTTPException(status_code=400, detail=f"File non leggibile: {exc}") from None


def _parse_mapping(raw: str | None) -> ImportMapping | None:
    if not raw:
        return None
    try:
        return ImportMapping.model_validate(json.loads(raw))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Mappatura non valida: {exc}") from None


@router.post("/preview", response_model=ImportPreview)
async def preview_file(
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
) -> ImportPreview:
    table = await _read_table(file)
    if not table.columns:
        raise HTTPException(status_code=400, detail="Il file non contiene intestazioni di colonna")
    return importers.preview(table, _parse_mapping(mapping))


@router.post("/apply", response_model=ImportResult)
async def apply_file(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> ImportResult:
    table = await _read_table(file)
    parsed = _parse_mapping(mapping)
    if parsed is None:
        raise HTTPException(status_code=422, detail="Mappatura obbligatoria")
    missing = [c for c in (parsed.title, parsed.due_date) if c not in table.columns]
    if missing:
        raise HTTPException(status_code=422, detail=f"Colonne non presenti nel file: {', '.join(missing)}")
    return importers.apply_import(db, local_db, table, parsed)
