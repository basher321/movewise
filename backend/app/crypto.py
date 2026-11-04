"""Encrypt and decrypt settings secrets with a key derived from SECRET_KEY.

AES-256-GCM with a random 12-byte nonce per value. The secret's name is bound in as
associated data, so a ciphertext cannot be copied to another secret.
Stored form: "v1:" + base64(nonce + ciphertext).
"""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

_PREFIX = "v1:"
_INFO = b"movewise/settings-secrets/v1"
_NONCE_BYTES = 12


class DecryptError(Exception):
    """The value cannot be decrypted, for example because SECRET_KEY changed."""


def derive_key(secret_key: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
        secret_key.encode("utf-8")
    )


def _key() -> bytes:
    return derive_key(get_settings().secret_key)


def encrypt(name: str, plain: str) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(_key()).encrypt(nonce, plain.encode("utf-8"), name.encode("utf-8"))
    return _PREFIX + base64.b64encode(nonce + sealed).decode("ascii")


def decrypt(name: str, stored: str) -> str:
    if not stored.startswith(_PREFIX):
        raise DecryptError
    try:
        raw = base64.b64decode(stored[len(_PREFIX):], validate=True)
        plain = AESGCM(_key()).decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], name.encode("utf-8"))
        return plain.decode("utf-8")
    except (binascii.Error, ValueError, InvalidTag, UnicodeDecodeError):
        raise DecryptError from None
