"""Signed licence keys and the licence state.

Key format: "MW1." + base64url(JSON payload) + "." + base64url(Ed25519 signature of the
payload bytes), without "=" padding. Payload (compact JSON, sorted keys):
{"expires": "YYYY-MM-DD" | null, "holder": str, "issued": "YYYY-MM-DD", "modules": [...]}.
Keys are verified with the public key in licence_public_key.pem; only the software owner
holds the private key (see tools/licence/).
"""

import base64
import binascii
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.errors import ApiError

Module = Literal["course", "study", "job", "visa"]

MODULES: tuple[Module, ...] = ("course", "study", "job", "visa")
MODULE_LABELS: dict[Module, str] = {
    "course": "Training",
    "study": "Student Consultancy",
    "job": "Job Processing",
    "visa": "Immigration Processing",
}
KEY_PREFIX = "MW1"
MAX_KEY_LENGTH = 4096
INVALID_KEY = "This key is not valid."
PUBLIC_KEY_PATH = Path(__file__).resolve().parent / "licence_public_key.pem"
DHAKA = ZoneInfo("Asia/Dhaka")

_B64URL = re.compile(r"[A-Za-z0-9_-]+")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PAYLOAD_FIELDS = {"holder", "modules", "issued", "expires"}


@dataclass(frozen=True)
class LicencePayload:
    holder: str
    modules: tuple[Module, ...]
    issued: date
    expires: date | None


def today_dhaka() -> date:
    return datetime.now(DHAKA).date()


@lru_cache
def load_public_key() -> Ed25519PublicKey:
    try:
        data = PUBLIC_KEY_PATH.read_bytes()
    except FileNotFoundError:
        raise RuntimeError("licence public key missing") from None
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("licence public key is not an Ed25519 key")
    return key


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def make_key(
    private_key: Ed25519PrivateKey,
    holder: str,
    modules: Sequence[str],
    issued: date,
    expires: date | None,
) -> str:
    payload = json.dumps(
        {
            "expires": expires.isoformat() if expires else None,
            "holder": holder,
            "issued": issued.isoformat(),
            "modules": list(modules),
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return f"{KEY_PREFIX}.{b64url_encode(payload)}.{b64url_encode(private_key.sign(payload))}"


def _invalid() -> ApiError:
    return ApiError("VALIDATION", 422, INVALID_KEY)


def _decode_part(part: str) -> bytes:
    try:
        raw = b64url_decode(part)
    except (binascii.Error, ValueError):
        raise _invalid() from None
    # Only the canonical encoding is accepted, so no two key strings decode to the same bytes.
    if b64url_encode(raw) != part:
        raise _invalid()
    return raw


def _parse_date(value: Any) -> date:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise _invalid()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _invalid() from None


def _parse_payload(raw: bytes) -> LicencePayload:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _invalid() from None
    if not isinstance(data, dict) or set(data) != _PAYLOAD_FIELDS:
        raise _invalid()

    holder = data["holder"]
    if not isinstance(holder, str) or not 1 <= len(holder.strip()) <= 200:
        raise _invalid()

    modules = data["modules"]
    if (
        not isinstance(modules, list)
        or not modules
        or not all(isinstance(m, str) and m in MODULES for m in modules)
        or len(set(modules)) != len(modules)
    ):
        raise _invalid()

    issued = _parse_date(data["issued"])
    expires = None if data["expires"] is None else _parse_date(data["expires"])
    if expires is not None and expires < issued:
        raise _invalid()

    return LicencePayload(
        holder=holder.strip(),
        modules=tuple(m for m in MODULES if m in modules),
        issued=issued,
        expires=expires,
    )


def verify_key(key: str, today: date | None = None) -> LicencePayload:
    """Return the payload of a valid key. Any problem is VALIDATION "This key is not valid."."""
    if len(key) > MAX_KEY_LENGTH:
        raise _invalid()
    parts = key.strip().split(".")
    if len(parts) != 3 or parts[0] != KEY_PREFIX or not all(_B64URL.fullmatch(p) for p in parts[1:]):
        raise _invalid()
    payload_bytes = _decode_part(parts[1])
    signature = _decode_part(parts[2])
    try:
        load_public_key().verify(signature, payload_bytes)
    except InvalidSignature:
        raise _invalid() from None
    payload = _parse_payload(payload_bytes)
    if payload.expires is not None and payload.expires < (today or today_dhaka()):
        raise _invalid()
    return payload


@dataclass(frozen=True)
class LicenceState:
    key: str | None
    holder: str | None
    modules: dict[Module, bool]
    expires_at: date | None

    @property
    def active(self) -> bool:
        return self.key is not None and (self.expires_at is None or today_dhaka() <= self.expires_at)

    def licensed(self, module: Module) -> bool:
        return self.active and self.modules[module]


_SELECT_LICENCE = text(
    "SELECT key, holder, module_course, module_study, module_job, module_visa, expires_at "
    "FROM licence WHERE singleton = 'licence'"
)


def read_licence(conn: Connection) -> LicenceState:
    row = conn.execute(_SELECT_LICENCE).mappings().one_or_none()
    if row is None:
        raise RuntimeError("licence row missing")
    return LicenceState(
        key=row["key"],
        holder=row["holder"],
        modules={m: bool(row[f"module_{m}"]) for m in MODULES},
        expires_at=row["expires_at"],
    )


def modules_text(modules: dict[Module, bool]) -> str:
    return ", ".join(m for m in MODULES if modules[m]) or "none"


def public_view(state: LicenceState) -> dict[str, Any]:
    """What everyone may see. Modules show as off while the licence is not active."""
    return {
        "holder": state.holder,
        "modules": {m: state.licensed(m) for m in MODULES},
        "expires_at": state.expires_at.isoformat() if state.expires_at else None,
        "active": state.active,
    }


def mask_key(key: str) -> str:
    return f"{key[:8]}...{key[-6:]}"
