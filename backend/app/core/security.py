import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

COOKIE_NAME = "intervai_session"
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
# Used for a real Argon2 verification when an email is unknown, limiting timing disclosure.
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def csrf_for(token: str) -> str:
    return hmac.new(
        get_settings().auth_secret.get_secret_value().encode(),
        f"csrf:{token}".encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False
