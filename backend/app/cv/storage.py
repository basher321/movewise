"""CV Agent files on disk (spec B28): encrypted at rest, type decided by the file's content.

Stored under STORAGE_DIR/cv/<year>/<month>/<random hex> with no extension. The content is sealed
with AES-256-GCM (key derived from SECRET_KEY with its own label), the file's id-free random
name bound in as associated data. The original name lives only in the database.
"""

import hashlib
import io
import logging
import os
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.errors import ApiError
from app.files import storage_root
from app.licence import DHAKA

logger = logging.getLogger("app")

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"
DOC = "application/msword"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_INFO = b"movewise/cv-files/v1"
_NONCE = 12
_STORED = re.compile(r"cv/\d{4}/\d{2}/[0-9a-f]{32}")
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class StoredCvFile:
    stored_name: str
    path: Path
    mime: str
    size_bytes: int
    sha256: str


def _key() -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
        get_settings().secret_key.encode("utf-8")
    )


def detect_mime(data: bytes) -> str | None:
    """PDF, JPG, PNG, DOCX (a zip with word/document.xml) or the old Word .doc (OLE file)."""
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(_OLE):
        return DOC
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return DOCX
        except zipfile.BadZipFile:
            return None
    return None


def check_upload(data: bytes, max_bytes: int) -> str:
    if not 1 <= len(data) <= max_bytes:
        raise ApiError("VALIDATION", 422, f"Each file must be from 1 byte to {max_bytes // (1024 * 1024)} MB.")
    mime = detect_mime(data)
    if mime is None:
        raise ApiError("VALIDATION", 422, "Only PDF, DOC, DOCX, JPG or PNG files.")
    return mime


def scan_for_viruses(data: bytes) -> bool:
    """Virus-scan hook (spec B28). Returns True when the file is clean. No scanner is set up yet,
    so every file passes; a real scanner plugs in here."""
    return True


def save(data: bytes, mime: str) -> StoredCvFile:
    now = datetime.now(DHAKA)
    folder = storage_root() / "cv" / now.strftime("%Y") / now.strftime("%m")
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    stored_name = f"cv/{now:%Y}/{now:%m}/{name}"
    nonce = os.urandom(_NONCE)
    sealed = nonce + AESGCM(_key()).encrypt(nonce, data, stored_name.encode("ascii"))
    final = folder / name
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(sealed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
    except BaseException:
        _unlink(Path(tmp))
        raise
    return StoredCvFile(stored_name, final, mime, len(data), hashlib.sha256(data).hexdigest())


def path_of(stored_name: str) -> Path:
    if not _STORED.fullmatch(stored_name):
        raise ValueError("bad stored name")
    return storage_root() / stored_name


def read(stored_name: str) -> bytes:
    """The decrypted content. Raises ApiError when the file is gone or cannot be opened."""
    try:
        raw = path_of(stored_name).read_bytes()
        return AESGCM(_key()).decrypt(raw[:_NONCE], raw[_NONCE:], stored_name.encode("ascii"))
    except (FileNotFoundError, ValueError, InvalidTag):
        logger.error("CV file cannot be read")
        raise ApiError("INTERNAL", 500, "The file cannot be read.") from None


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not remove a CV file")


def remove(stored_name: str) -> None:
    try:
        _unlink(path_of(stored_name))
    except ValueError:
        logger.error("Refused to remove a CV file outside the CV folder")
