from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Follow, Item, Rating, User

router = APIRouter()


@router.post("/follows")
def follow_user(
    username: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = db.scalar(select(User).where(User.username == username.strip()))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    follow = Follow(follower_id=user.id, followee_id=target.id)
    db.add(follow)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"following": target.username, "already": True}

    return {"following": target.username, "already": False}


@router.delete("/follows/{username}")
def unfollow_user(
    username: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = db.scalar(select(User).where(User.username == username.strip()))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    follow = db.scalar(
        select(Follow).where(
            Follow.follower_id == user.id, Follow.followee_id == target.id
        )
    )
    if follow is None:
        raise HTTPException(status_code=404, detail="Not following that user")

    db.delete(follow)
    db.commit()
    return {"unfollowed": target.username}


@router.get("/following")
def list_following(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(User.username)
        .join(Follow, Follow.followee_id == User.id)
        .where(Follow.follower_id == user.id)
        .order_by(User.username)
    ).all()
    return {"following": [r[0] for r in rows]}


@router.get("/feed")
def feed(
    limit: int = 50,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))

    rows = db.execute(
        select(
            Rating.id,
            Rating.score,
            Rating.review,
            Rating.updated_at,
            User.username,
            Item.title,
            Item.year,
            Item.type,
            Item.image_url,
        )
        .join(User, User.id == Rating.user_id)
        .join(Item, Item.id == Rating.item_id)
        .join(Follow, Follow.followee_id == Rating.user_id)
        .where(Follow.follower_id == user.id)
        .order_by(Rating.updated_at.desc())
        .limit(limit)
    ).all()

    return {
        "feed": [
            {
                "rating_id": r.id,
                "username": r.username,
                "title": r.title,
                "year": r.year,
                "type": r.type,
                "image_url": r.image_url,
                "score": r.score,
                "review": r.review,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }
