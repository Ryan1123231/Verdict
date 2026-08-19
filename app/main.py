from fastapi import Depends, FastAPI

from app import auth
from app.auth import get_current_user
from app.models import User

app = FastAPI()
app.include_router(auth.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def index(user: User | None = Depends(get_current_user)):
    if user is None:
        return {"logged_in": False}
    return {"logged_in": True, "username": user.username}
