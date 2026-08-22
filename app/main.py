from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter

from app import auth, friends, items, ratings, views

app = FastAPI()
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return PlainTextResponse("Too many requests. Slow down.", status_code=429)

app.include_router(auth.router)
app.include_router(items.router, prefix="/api")
app.include_router(ratings.router)
app.include_router(friends.router)
app.include_router(views.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
