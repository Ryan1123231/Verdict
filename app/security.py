import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from itsdangerous import BadSignature, URLSafeSerializer

SECRET_KEY = os.environ["SECRET_KEY"]
SESSION_COOKIE = "session"

_hasher = PasswordHasher()
_serializer = URLSafeSerializer(SECRET_KEY, salt="session")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def sign_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session(cookie_value: str) -> int | None:
    try:
        data = _serializer.loads(cookie_value)
    except BadSignature:
        return None
    uid = data.get("uid")
    return uid if isinstance(uid, int) else None
