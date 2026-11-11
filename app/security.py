import hashlib
import hmac
import os

from cryptography.fernet import Fernet

from app.config import get_settings

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_user_id(channel: str, user_id: str) -> str:
    salt = get_settings().user_hash_salt.encode()
    return hmac.new(salt, f"{channel}:{user_id}".encode(), hashlib.sha256).hexdigest()


def secrets_match(given: str | None, expected: str) -> bool:
    return given is not None and hmac.compare_digest(given.encode(), expected.encode())


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(candidate, bytes.fromhex(digest))


def _fernet() -> Fernet:
    return Fernet(get_settings().delivery_key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
