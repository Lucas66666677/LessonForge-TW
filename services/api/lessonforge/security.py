from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import get_settings

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(*, user_id: str, organization_id: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org": organization_id,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "iss": "lessonforge-tw",
        "aud": "lessonforge-web",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token.decode("utf-8") if isinstance(token, bytes) else token


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        issuer="lessonforge-tw",
        audience="lessonforge-web",
    )
