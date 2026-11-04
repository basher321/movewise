"""argon2 password hashing. Plain passwords are never stored, logged or returned."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    """With no stored hash (no such account) a dummy hash is checked, so it takes as long."""
    global _dummy_hash
    real = stored is not None
    if stored is None:
        if _dummy_hash is None:
            _dummy_hash = _hasher.hash("no account has this password")
        stored = _dummy_hash
    try:
        _hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False
    return real
