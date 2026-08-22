from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.limiter import limiter
from app.models import User
from app.security import (
    SESSION_COOKIE,
    hash_password,
    read_session,
    sign_session,
    verify_password,
)

router = APIRouter()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    user_id = read_session(cookie)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def _set_session(response: RedirectResponse, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user_id),
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 60 * 24 * 14,
    )


@router.post("/register")
@limiter.limit("4/hour")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")

    user = User(
        username=username.strip(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already taken")

    response = RedirectResponse(url="/", status_code=303)
    _set_session(response, user.id)
    return response


@router.post("/login")
@limiter.limit("8/minute")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))

    if user is None or not verify_password(user.password_hash, password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    response = RedirectResponse(url="/", status_code=303)
    _set_session(response, user.id)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
