from fastapi import FastAPI

from app import auth, friends, items, ratings, views

app = FastAPI()
app.include_router(auth.router)
app.include_router(items.router, prefix="/api")
app.include_router(ratings.router)
app.include_router(friends.router)
app.include_router(views.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
