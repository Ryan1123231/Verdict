from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Item, Rating, User

router = APIRouter()

MIN_SCORE = 1
MAX_SCORE = 10
MAX_REVIEW_LEN = 2000


def _serialize(rating: Rating) -> dict:
    return {
        "id": rating.id,
        "item_id": rating.item_id,
        "score": rating.score,
        "review": rating.review,
        "created_at": rating.created_at.isoformat(),
        "updated_at": rating.updated_at.isoformat(),
    }


def _validate(score: int, review: str | None) -> str | None:
    if score < MIN_SCORE or score > MAX_SCORE:
        raise HTTPException(
            status_code=400, detail=f"Score must be between {MIN_SCORE} and {MAX_SCORE}"
        )
    if review is not None:
        review = review.strip() or None
        if review is not None and len(review) > MAX_REVIEW_LEN:
            raise HTTPException(status_code=400, detail="Review is too long")
    return review


@router.post("/ratings")
def create_rating(
    item_id: int = Form(...),
    score: int = Form(...),
    review: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    review = _validate(score, review)

    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    existing = db.scalar(
        select(Rating).where(Rating.user_id == user.id, Rating.item_id == item_id)
    )
    if existing is not None:
        existing.score = score
        existing.review = review
        db.commit()
        return _serialize(existing)

    rating = Rating(user_id=user.id, item_id=item_id, score=score, review=review)
    db.add(rating)
    db.commit()
    return _serialize(rating)


@router.get("/ratings/me")
def list_my_ratings(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Rating).where(Rating.user_id == user.id).order_by(Rating.updated_at.desc())
    ).all()
    return {"ratings": [_serialize(r) for r in rows]}


@router.put("/ratings/{rating_id}")
def update_rating(
    rating_id: int,
    score: int = Form(...),
    review: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    review = _validate(score, review)

    rating = db.scalar(
        select(Rating).where(Rating.id == rating_id, Rating.user_id == user.id)
    )
    if rating is None:
        raise HTTPException(status_code=404, detail="Rating not found")

    rating.score = score
    rating.review = review
    db.commit()
    return _serialize(rating)


@router.delete("/ratings/{rating_id}")
def delete_rating(
    rating_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rating = db.scalar(
        select(Rating).where(Rating.id == rating_id, Rating.user_id == user.id)
    )
    if rating is None:
        raise HTTPException(status_code=404, detail="Rating not found")

    db.delete(rating)
    db.commit()
    return {"deleted": True}
