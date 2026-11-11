import hashlib
import hmac

from app.config import get_settings


def hash_user_id(channel: str, user_id: str) -> str:
    salt = get_settings().user_hash_salt.encode()
    return hmac.new(salt, f"{channel}:{user_id}".encode(), hashlib.sha256).hexdigest()


def secrets_match(given: str | None, expected: str) -> bool:
    return given is not None and hmac.compare_digest(given.encode(), expected.encode())
