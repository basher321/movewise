"""Document files on disk (spec B06).

Files are stored under STORAGE_DIR as <year>/<month>/<random uuid hex>, with no extension.
The original name lives only in the database. The type is decided by the first bytes of the
file, never by its name or the browser's content type.
"""

import hashlib
import logging
import os
import re
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.errors import ApiError
from app.licence import DHAKA

logger = logging.getLogger("app")

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_NAME = 200

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
_STORED_NAME = re.compile(r"\d{4}/\d{2}/[0-9a-f]{32}")


@dataclass(frozen=True)
class SavedFile:
    stored_name: str
    path: Path
    mime: str
    size_bytes: int
    sha256: str


def storage_root() -> Path:
    return get_settings().storage_path


def detect_mime(data: bytes) -> str | None:
    for magic, mime in _SIGNATURES:
        if data.startswith(magic):
            return mime
    return None


def clean_name(name: str) -> str:
    """Path parts removed, control characters removed, only the last 200 characters kept."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip()
    base = base[-MAX_NAME:]
    return base or "document"


def check_file(data: bytes, max_bytes: int = MAX_FILE_BYTES) -> str:
    if not 1 <= len(data) <= max_bytes:
        raise ApiError("VALIDATION", 422, f"The file must be from 1 byte to {max_bytes // (1024 * 1024)} MB.")
    mime = detect_mime(data)
    if mime is None:
        raise ApiError("VALIDATION", 422, "Only PDF, JPG or PNG files.")
    return mime


def save_file(data: bytes, mime: str) -> SavedFile:
    """Write to a temporary file in the target folder, then rename it into place."""
    now = datetime.now(DHAKA)
    folder_name = f"{now:%Y}/{now:%m}"
    folder = storage_root() / now.strftime("%Y") / now.strftime("%m")
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    final = folder / name
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
    except BaseException:
        _unlink(Path(tmp))
        raise
    return SavedFile(
        stored_name=f"{folder_name}/{name}",
        path=final,
        mime=mime,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not remove the file %s", path.name)


def remove_saved(saved: SavedFile) -> None:
    _unlink(saved.path)


def path_of(stored_name: str) -> Path:
    if not _STORED_NAME.fullmatch(stored_name):
        raise ValueError("bad stored name")
    return storage_root() / stored_name


def read_file(stored_name: str, document_id: object) -> bytes:
    try:
        return path_of(stored_name).read_bytes()
    except (FileNotFoundError, ValueError):
        logger.error("Document file is missing: document %s", document_id)
        raise ApiError("INTERNAL", 500, "File is missing") from None
