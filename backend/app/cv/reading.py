"""Turns an uploaded file into what the Extractor reads (spec B28): text, or page images.

- PDF: its text with PyMuPDF. A scanned PDF (almost no text) becomes page images instead.
- DOCX: paragraphs and table cells with python-docx.
- JPG / PNG: the picture, made smaller (longest side 1600 px) so it is quick to send.
- DOC (old Word): cannot be read on the server (spec B28 Decisions 6).
"""

import io
from dataclasses import dataclass, field

import docx
import pymupdf
from PIL import Image as PilImage

from app.cv import storage
from app.cv.ai_client import Image

MAX_TEXT = 30_000
MIN_PDF_TEXT = 200
MAX_PAGES_AS_IMAGES = 4
MAX_SIDE = 1600


class Unreadable(Exception):
    """The file cannot be read (damaged, password protected, or the old .doc format)."""


@dataclass
class ReadDocument:
    text: str = ""
    images: list[Image] = field(default_factory=list)


def _small_jpeg(data: bytes) -> Image:
    with PilImage.open(io.BytesIO(data)) as picture:
        picture = picture.convert("RGB")
        picture.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=85)
    return Image("image/jpeg", out.getvalue())


def read_pdf(data: bytes) -> ReadDocument:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise Unreadable("damaged PDF") from exc
    with document:
        if document.needs_pass:
            raise Unreadable("password protected")
        texts = [page.get_text() for page in document]
        joined = "\n".join(texts).strip()
        if len(joined) >= MIN_PDF_TEXT:
            return ReadDocument(text=joined[:MAX_TEXT])
        images = []
        for page in list(document)[:MAX_PAGES_AS_IMAGES]:
            pixmap = page.get_pixmap(dpi=110)
            images.append(_small_jpeg(pixmap.tobytes("png")))
        return ReadDocument(text=joined[:MAX_TEXT], images=images)


def read_docx(data: bytes) -> ReadDocument:
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise Unreadable("damaged DOCX") from exc
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(dict.fromkeys(cells)))
    return ReadDocument(text="\n".join(lines)[:MAX_TEXT])


def read_file(stored_name: str, mime: str) -> ReadDocument:
    data = storage.read(stored_name)
    if mime == storage.PDF:
        return read_pdf(data)
    if mime == storage.DOCX:
        return read_docx(data)
    if mime in (storage.JPEG, storage.PNG):
        try:
            return ReadDocument(images=[_small_jpeg(data)])
        except Exception as exc:
            raise Unreadable("damaged picture") from exc
    raise Unreadable("unsupported format")
