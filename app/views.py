from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import tmdb
from app.auth import _set_session, get_current_user, require_user
from app.db import get_db
from app.friends import friend_ids
from app.models import Friendship, Item, Rating, User
from app.security import SESSION_COOKIE, hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"user": None})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "register.html", {"user": None})


@router.post("/ui/register")
def ui_register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(password) < 12:
        return templates.TemplateResponse(
            request, "register.html",
            {"user": None, "error": "Password must be at least 12 characters"},
            status_code=400,
        )

    new_user = User(
        username=username.strip(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request, "register.html",
            {"user": None, "error": "Username or email already taken"},
            status_code=400,
        )

    response = RedirectResponse(url="/", status_code=303)
    _set_session(response, new_user.id)
    return response


@router.post("/ui/login")
def ui_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    found = db.scalar(select(User).where(User.email == email.strip().lower()))
    if found is None or not verify_password(found.password_hash, password):
        return templates.TemplateResponse(
            request, "login.html",
            {"user": None, "error": "Invalid email or password"},
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=303)
    _set_session(response, found.id)
    return response


@router.get("/", response_class=HTMLResponse)
def feed_page(
    request: Request,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    ids = friend_ids(db, user.id)
    rows = []
    if ids:
        rows = db.execute(
            select(
                Rating.score, Rating.review, User.username,
                Item.title, Item.year, Item.image_url, Item.type,
            )
            .join(User, User.id == Rating.user_id)
            .join(Item, Item.id == Rating.item_id)
            .where(Rating.user_id.in_(ids))
            .order_by(Rating.updated_at.desc())
            .limit(50)
        ).all()

    pending = db.scalar(
        select(Friendship).where(
            Friendship.addressee_id == user.id, Friendship.status == "pending"
        )
    )

    return templates.TemplateResponse(
        request, "feed.html",
        {"user": user, "feed": rows, "has_requests": pending is not None},
    )


@router.get("/friends", response_class=HTMLResponse)
def friends_page(
    request: Request,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    incoming = db.execute(
        select(Friendship.id, User.username)
        .join(User, User.id == Friendship.requester_id)
        .where(Friendship.addressee_id == user.id, Friendship.status == "pending")
    ).all()

    outgoing = db.execute(
        select(Friendship.id, User.username)
        .join(User, User.id == Friendship.addressee_id)
        .where(Friendship.requester_id == user.id, Friendship.status == "pending")
    ).all()

    ids = friend_ids(db, user.id)
    friends = []
    if ids:
        friends = db.execute(
            select(User.username).where(User.id.in_(ids)).order_by(User.username)
        ).all()

    return templates.TemplateResponse(
        request, "friends.html",
        {"user": user, "incoming": incoming, "outgoing": outgoing, "friends": friends},
    )


@router.post("/ui/friends/request")
def ui_friend_request(
    username: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = db.scalar(select(User).where(User.username == username.strip()))
    if target is None or target.id == user.id:
        return RedirectResponse(url="/friends", status_code=303)

    existing = db.scalar(
        select(Friendship).where(
            or_(
                (Friendship.requester_id == user.id) & (Friendship.addressee_id == target.id),
                (Friendship.requester_id == target.id) & (Friendship.addressee_id == user.id),
            )
        )
    )
    if existing is not None:
        if existing.requester_id == target.id and existing.status == "pending":
            existing.status = "accepted"
            db.commit()
        return RedirectResponse(url="/friends", status_code=303)

    db.add(Friendship(requester_id=user.id, addressee_id=target.id, status="pending"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/ui/friends/{friendship_id}/accept")
def ui_accept(
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
    if friendship is not None:
        friendship.status = "accepted"
        db.commit()
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/ui/friends/{friendship_id}/reject")
def ui_reject(
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
    if friendship is not None:
        db.delete(friendship)
        db.commit()
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/ui/friends/{username}/remove")
def ui_unfriend(
    username: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = db.scalar(select(User).where(User.username == username.strip()))
    if target is not None:
        friendship = db.scalar(
            select(Friendship).where(
                Friendship.status == "accepted",
                or_(
                    (Friendship.requester_id == user.id) & (Friendship.addressee_id == target.id),
                    (Friendship.requester_id == target.id) & (Friendship.addressee_id == user.id),
                ),
            )
        )
        if friendship is not None:
            db.delete(friendship)
            db.commit()
    return RedirectResponse(url="/friends", status_code=303)


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = "",
    user: User | None = Depends(get_current_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    results = tmdb.search(q[:100]) if q.strip() else []
    return templates.TemplateResponse(
        request, "search.html", {"user": user, "q": q, "results": results}
    )


@router.post("/rate")
def ui_rate(
    media_type: str = Form(...),
    source_id: str = Form(...),
    score: int = Form(...),
    review: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if score < 1 or score > 10:
        return RedirectResponse(url="/search", status_code=303)

    review = (review or "").strip()[:2000] or None

    item = db.scalar(
        select(Item).where(Item.source == "tmdb", Item.source_id == source_id)
    )
    if item is None:
        data = tmdb.fetch_one(media_type, source_id)
        if data is None:
            return RedirectResponse(url="/search", status_code=303)
        item = Item(**data)
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            item = db.scalar(
                select(Item).where(Item.source == "tmdb", Item.source_id == source_id)
            )

    existing = db.scalar(
        select(Rating).where(Rating.user_id == user.id, Rating.item_id == item.id)
    )
    if existing is not None:
        existing.score = score
        existing.review = review
    else:
        db.add(Rating(user_id=user.id, item_id=item.id, score=score, review=review))
    db.commit()

    return RedirectResponse(url="/me", status_code=303)


@router.get("/me", response_class=HTMLResponse)
def my_ratings_page(
    request: Request,
    type: str = "all",
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if type not in ("all", "movie", "tv", "game"):
        type = "all"

    counts_rows = db.execute(
        select(Item.type, func.count(Rating.id))
        .join(Item, Item.id == Rating.item_id)
        .where(Rating.user_id == user.id)
        .group_by(Item.type)
    ).all()
    counts = {t: c for t, c in counts_rows}
    counts["all"] = sum(counts.values())

    q = (
        select(
            Rating.id.label("rating_id"), Rating.score, Rating.review,
            Item.title, Item.year, Item.image_url, Item.type,
        )
        .join(Item, Item.id == Rating.item_id)
        .where(Rating.user_id == user.id)
    )
    if type != "all":
        q = q.where(Item.type == type)

    rows = db.execute(q.order_by(Rating.updated_at.desc())).all()

    return templates.TemplateResponse(
        request, "me.html",
        {"user": user, "ratings": rows, "active": type, "counts": counts},
    )


@router.post("/ratings/{rating_id}/delete")
def ui_delete_rating(
    rating_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rating = db.scalar(
        select(Rating).where(Rating.id == rating_id, Rating.user_id == user.id)
    )
    if rating is not None:
        db.delete(rating)
        db.commit()
    return RedirectResponse(url="/me", status_code=303)


@router.post("/ui/logout")
def ui_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/ui/logout")
def ui_logout_get():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
