import os

import httpx

TMDB_TOKEN = os.environ["TMDB_TOKEN"]
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

_headers = {"Authorization": f"Bearer {TMDB_TOKEN}", "accept": "application/json"}


def _poster_url(path: str | None) -> str | None:
    return f"{IMAGE_BASE}{path}" if path else None


def _year(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


def search(query: str, limit: int = 10) -> list[dict]:
    query = query.strip()
    if not query:
        return []

    with httpx.Client(timeout=5.0) as client:
        resp = client.get(
            f"{BASE_URL}/search/multi",
            headers=_headers,
            params={"query": query, "include_adult": "false"},
        )
        resp.raise_for_status()
        payload = resp.json()

    results = []
    for row in payload.get("results", []):
        media_type = row.get("media_type")
        if media_type == "movie":
            title = row.get("title")
            date = row.get("release_date")
        elif media_type == "tv":
            title = row.get("name")
            date = row.get("first_air_date")
        else:
            continue

        if not title:
            continue

        results.append(
            {
                "source": "tmdb",
                "source_id": str(row["id"]),
                "type": media_type,
                "title": title,
                "year": _year(date),
                "image_url": _poster_url(row.get("poster_path")),
            }
        )
        if len(results) >= limit:
            break

    return results


def fetch_one(media_type: str, source_id: str) -> dict | None:
    if media_type not in ("movie", "tv"):
        return None

    with httpx.Client(timeout=5.0) as client:
        resp = client.get(f"{BASE_URL}/{media_type}/{source_id}", headers=_headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        row = resp.json()

    title = row.get("title") if media_type == "movie" else row.get("name")
    date = row.get("release_date") if media_type == "movie" else row.get("first_air_date")
    if not title:
        return None

    return {
        "source": "tmdb",
        "source_id": str(row["id"]),
        "type": media_type,
        "title": title,
        "year": _year(date),
        "image_url": _poster_url(row.get("poster_path")),
    }


def trending(media_type: str, limit: int = 6) -> list[dict]:
    if media_type not in ("movie", "tv"):
        return []

    with httpx.Client(timeout=6.0) as client:
        resp = client.get(
            f"{BASE_URL}/trending/{media_type}/week",
            headers=_headers,
            params={"language": "en-US"},
        )
        resp.raise_for_status()
        payload = resp.json()

    results = []
    for row in payload.get("results", []):
        title = row.get("title") if media_type == "movie" else row.get("name")
        date = row.get("release_date") if media_type == "movie" else row.get("first_air_date")
        if not title:
            continue
        results.append(
            {
                "source": "tmdb",
                "source_id": str(row["id"]),
                "type": media_type,
                "title": title,
                "year": _year(date),
                "image_url": _poster_url(row.get("poster_path")),
            }
        )
        if len(results) >= limit:
            break
    return results


def browse(media_type: str, page: int = 1) -> list[dict]:
    if media_type not in ("movie", "tv"):
        return []

    with httpx.Client(timeout=6.0) as client:
        resp = client.get(
            f"{BASE_URL}/{media_type}/popular",
            headers=_headers,
            params={"language": "en-US", "page": max(1, min(page, 100))},
        )
        resp.raise_for_status()
        payload = resp.json()

    results = []
    for row in payload.get("results", []):
        title = row.get("title") if media_type == "movie" else row.get("name")
        date = row.get("release_date") if media_type == "movie" else row.get("first_air_date")
        if not title:
            continue
        results.append(
            {
                "source": "tmdb",
                "source_id": str(row["id"]),
                "type": media_type,
                "title": title,
                "year": _year(date),
                "image_url": _poster_url(row.get("poster_path")),
            }
        )
    return results
