from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Friendship, User

router = APIRouter()


def friend_ids(db: Session, user_id: int) -> list[int]:
    rows = db.execute(
        select(Friendship.requester_id, Friendship.addressee_id).where(
            Friendship.status == "accepted",
            or_(
                Friendship.requester_id == user_id,
                Friendship.addressee_id == user_id,
            ),
        )
    ).all()
    return [r.addressee_id if r.requester_id == user_id else r.requester_id for r in rows]


@router.post("/api/friends/request")
def send_request(
    username: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = db.scalar(select(User).where(User.username == username.strip()))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot friend yourself")

    existing = db.scalar(
        select(Friendship).where(
            or_(
                (Friendship.requester_id == user.id)
                & (Friendship.addressee_id == target.id),
                (Friendship.requester_id == target.id)
                & (Friendship.addressee_id == user.id),
            )
        )
    )

    if existing is not None:
        if existing.status == "accepted":
            return {"status": "already_friends"}
        if existing.requester_id == target.id and existing.status == "pending":
            existing.status = "accepted"
            db.commit()
            return {"status": "accepted"}
        return {"status": "already_pending"}

    friendship = Friendship(
        requester_id=user.id, addressee_id=target.id, status="pending"
    )
    db.add(friendship)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "already_pending"}

    return {"status": "pending"}


@router.post("/api/friends/{friendship_id}/accept")
def accept_request(
    friendship_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    friendship = db.scalar(
        select(Friendship).where(
            Friendship.id == friendship_id,
            Friendship.addressee_id == user.id,
            Friendship.status == "pending",
        )
    )
    if friendship is None:
        raise HTTPException(status_code=404, detail="Request not found")

    friendship.status = "accepted"
    db.commit()
    return {"status": "accepted"}


@router.post("/api/friends/{friendship_id}/reject")
def reject_request(
    friendship_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    friendship = db.scalar(
        select(Friendship).where(
            Friendship.id == friendship_id,
            Friendship.addressee_id == user.id,
            Friendship.status == "pending",
        )
    )
    if friendship is None:
        raise HTTPException(status_code=404, detail="Request not found")

    db.delete(friendship)
    db.commit()
    return {"status": "rejected"}


@router.delete("/api/friends/{username}")
def unfriend(
    username: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = db.scalar(select(User).where(User.username == username.strip()))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    friendship = db.scalar(
        select(Friendship).where(
            Friendship.status == "accepted",
            or_(
                (Friendship.requester_id == user.id)
                & (Friendship.addressee_id == target.id),
                (Friendship.requester_id == target.id)
                & (Friendship.addressee_id == user.id),
            ),
        )
    )
    if friendship is None:
        raise HTTPException(status_code=404, detail="Not friends with that user")

    db.delete(friendship)
    db.commit()
    return {"unfriended": target.username}
