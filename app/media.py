import io
import os
import secrets

from PIL import Image

MEDIA_DIR = "/media"
MAX_BYTES = 4 * 1024 * 1024
MAX_PIXELS = 40_000_000

Image.MAX_IMAGE_PIXELS = MAX_PIXELS

SIZES = {
    "avatar": (400, 400),
    "backdrop": (1600, 500),
}


def _ensure_dir() -> None:
    os.makedirs(MEDIA_DIR, exist_ok=True)


def save_image(raw: bytes, kind: str) -> str | None:
    if kind not in SIZES:
        return None
    if not raw or len(raw) > MAX_BYTES:
        return None

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
    except Exception:
        return None

    target_w, target_h = SIZES[kind]
    src_w, src_h = img.size
    if src_w < 1 or src_h < 1:
        return None

    scale = max(target_w / src_w, target_h / src_h)
    new_size = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    img = img.resize(new_size, Image.LANCZOS)

    left = (img.width - target_w) // 2
    top = (img.height - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    name = f"{kind}_{secrets.token_urlsafe(16)}.jpg"
    _ensure_dir()
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    with open(os.path.join(MEDIA_DIR, name), "wb") as f:
        f.write(out.getvalue())
    return name


def delete_image(name: str | None) -> None:
    if not name:
        return
    if "/" in name or "\\" in name or ".." in name:
        return
    path = os.path.join(MEDIA_DIR, name)
    try:
        os.remove(path)
    except OSError:
        pass
