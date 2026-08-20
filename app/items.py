from fastapi import APIRouter, Depends, Form, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import tmdb
from app.auth import require_user
from app.db import get_db
from app.models import Item, User

router = APIRouter()


@router.get("/search")
def search_items(
    q: str = Query(..., min_length=1, max_length=100),
    user: User = Depends(require_user),
):
    return {"results": tmdb.search(q)}


@router.post("/items")
def cache_item(
    media_type: str = Form(...),
    source_id: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Item).where(Item.source == "tmdb", Item.source_id == source_id)
    )
    if existing is not None:
        return {"id": existing.id, "title": existing.title, "cached": True}

    data = tmdb.fetch_one(media_type, source_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Item not found")

    item = Item(**data)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        item = db.scalar(
            select(Item).where(Item.source == "tmdb", Item.source_id == source_id)
        )
        return {"id": item.id, "title": item.title, "cached": True}

    return {"id": item.id, "title": item.title, "cached": False}
