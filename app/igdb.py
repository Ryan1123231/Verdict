import os
import threading
import time

import httpx

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
BASE_URL = "https://api.igdb.com/v4"

_lock = threading.Lock()
_token: str | None = None
_expires_at: float = 0.0


def _get_token() -> str:
    global _token, _expires_at

    with _lock:
        if _token is not None and time.time() < _expires_at - 300:
            return _token

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                TOKEN_URL,
                params={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            payload = resp.json()

        _token = payload["access_token"]
        _expires_at = time.time() + payload.get("expires_in", 3600)
        return _token


def _headers() -> dict:
    return {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/json",
    }


def _cover_url(cover: dict | None) -> str | None:
    if not cover or "url" not in cover:
        return None
    url = cover["url"]
    if url.startswith("//"):
        url = "https:" + url
    return url.replace("/t_thumb/", "/t_cover_big/")


def _year(ts: int | None) -> int | None:
    if not ts:
        return None
    try:
        return time.gmtime(ts).tm_year
    except (ValueError, OSError):
        return None


def _normalize(row: dict) -> dict | None:
    name = row.get("name")
    if not name:
        return None
    return {
        "source": "igdb",
        "source_id": str(row["id"]),
        "type": "game",
        "title": name,
        "year": _year(row.get("first_release_date")),
        "image_url": _cover_url(row.get("cover")),
    }


def search(query: str, limit: int = 10) -> list[dict]:
    query = query.strip().replace('"', "")
    if not query:
        return []

    body = (
        f'search "{query}"; '
        "fields name,first_release_date,cover.url; "
        "where version_parent = null; "
        f"limit {limit};"
    )

    with httpx.Client(timeout=8.0) as client:
        resp = client.post(f"{BASE_URL}/games", headers=_headers(), content=body)
        resp.raise_for_status()
        rows = resp.json()

    out = []
    for row in rows:
        item = _normalize(row)
        if item is not None:
            out.append(item)
    return out


def fetch_one(source_id: str) -> dict | None:
    try:
        game_id = int(source_id)
    except ValueError:
        return None

    body = f"fields name,first_release_date,cover.url; where id = {game_id};"

    with httpx.Client(timeout=8.0) as client:
        resp = client.post(f"{BASE_URL}/games", headers=_headers(), content=body)
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        return None
    return _normalize(rows[0])


def popular(limit: int = 6) -> list[dict]:
    cutoff = int(time.time()) - (400 * 24 * 3600)
    body = (
        "fields name,first_release_date,cover.url,total_rating,total_rating_count; "
        f"where first_release_date > {cutoff} "
        "& total_rating_count > 20 "
        "& version_parent = null; "
        "sort total_rating desc; "
        f"limit {limit};"
    )

    with httpx.Client(timeout=8.0) as client:
        resp = client.post(f"{BASE_URL}/games", headers=_headers(), content=body)
        resp.raise_for_status()
        rows = resp.json()

    out = []
    for row in rows:
        item = _normalize(row)
        if item is not None:
            out.append(item)
    return out


def browse(page: int = 1) -> list[dict]:
    page = max(1, min(page, 100))
    offset = (page - 1) * 20
    body = (
        "fields name,first_release_date,cover.url,total_rating_count; "
        "where total_rating_count > 30 & version_parent = null & cover != null; "
        "sort total_rating_count desc; "
        f"limit 20; offset {offset};"
    )

    with httpx.Client(timeout=8.0) as client:
        resp = client.post(f"{BASE_URL}/games", headers=_headers(), content=body)
        resp.raise_for_status()
        rows = resp.json()

    out = []
    for row in rows:
        item = _normalize(row)
        if item is not None:
            out.append(item)
    return out
