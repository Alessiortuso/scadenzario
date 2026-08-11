from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Category
from ..schemas import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categorie"])


@router.get("", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)).all())


@router.post("", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> Category:
    category = Category(**payload.model_dump())
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Categoria già esistente") from None
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)) -> None:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    db.delete(category)
    db.commit()
