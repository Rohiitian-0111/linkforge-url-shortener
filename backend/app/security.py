import secrets
import string
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings
from app.models import utcnow


password_hasher = PasswordHasher()
# Verify a hash even for unknown emails, avoiding the obvious timing distinction.
dummy_hash = password_hasher.hash("not-a-real-account-" + secrets.token_hex(16))
ALPHABET = string.ascii_letters + string.digits


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_short_code(length: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def create_access_token(user_id: str, settings: Settings) -> str:
    now = utcnow()
    return jwt.encode(
        {"sub": user_id, "iat": now, "nbf": now, "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
         "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "jti": secrets.token_hex(16)},
        settings.jwt_secret, algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"],
        issuer=settings.jwt_issuer, audience=settings.jwt_audience,
        options={"require": ["sub", "exp", "iat", "nbf", "iss", "aud", "jti"]},
    )
