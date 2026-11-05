"""One PDF layout for course certificates and completion letters (spec B20).

Drawn like drawCert() in the reference (frontend CertificateCanvas): a 1000 x 707 page (A4
landscape proportions, units are points), the gradient frame, the logo or the company name, the
heading, the person's name, what they completed, the two signature lines and the id line. Until
it is approved (or while it is not valid) a "VIEW ONLY" watermark covers the page, as in the
reference.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF

FONTS = Path(__file__).resolve().parent / "fonts"
W, H = 1000.0, 707.0
NAVY = (14, 27, 61)
MUTED = (85, 96, 122)
INDIGO = (79, 70, 229)
CYAN = (34, 211, 238)
LINE = (199, 204, 230)
MAX_TEXT_WIDTH = 820.0


@dataclass(frozen=True)
class CertDoc:
    heading: str  # "Certificate of Completion" or "Letter of Completion"
    intro: str  # "This is to certify that"
    name: str
    line: str  # "has successfully completed the course"
    title: str
    sub: str  # "12 weeks · Intermediate" or "Reference APP-... · Canada"
    issued: str  # already formatted for people
    id_line: str  # "Certificate ID CERT-... · Student CRS-..."
    company: str
    logo: bytes | None
    approved: bool
    watermark: str = "VIEW ONLY"


def _has_bengali(value: str) -> bool:
    return any("ঀ" <= ch <= "৿" for ch in value)


class _Pdf(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="L", unit="pt", format=(H, W))
        self.set_auto_page_break(False)
        self.set_margin(0)
        self.add_font("Sora", "B", str(FONTS / "Sora-Bold.ttf"))
        self.add_font("DMSans", "", str(FONTS / "DMSans-Regular.ttf"))
        self.add_font("NotoBengali", "", str(FONTS / "NotoSansBengali-Regular.ttf"))
        self.add_font("NotoBengali", "B", str(FONTS / "NotoSansBengali-Bold.ttf"))

    def centred(self, text: str, y: float, family: str, style: str, size: float, colour: tuple[int, int, int], x: float = W / 2) -> None:
        """Text centred on x with its baseline at y (like canvas fillText with textAlign centre).
        A line with Bangla characters uses Noto Sans Bengali (it also has Latin letters)."""
        if _has_bengali(text):
            family = "NotoBengali"
            style = "B" if style == "B" else ""
        self.set_font(family, style, size)
        # Shrink a long line until it fits inside the frame.
        while self.get_string_width(text) > MAX_TEXT_WIDTH and size > 12:
            size -= 1
            self.set_font(family, style, size)
        self.set_text_color(*colour)
        self.text(x - self.get_string_width(text) / 2, y, text)


def _frame(pdf: _Pdf) -> None:
    # The 14 pt gradient frame (indigo -> cyan), drawn as thin strips so it needs no pattern support.
    steps = 120
    for i in range(steps):
        t = i / (steps - 1)
        colour = tuple(round(a + (b - a) * t) for a, b in zip(INDIGO, CYAN, strict=True))
        pdf.set_fill_color(*colour)
        x = 17 + (W - 34) * i / steps
        width = (W - 34) / steps + 0.6
        pdf.rect(x, 17, width, 14, style="F")  # top
        pdf.rect(x, H - 31, width, 14, style="F")  # bottom
    pdf.set_fill_color(*INDIGO)
    pdf.rect(17, 17, 14, H - 34, style="F")  # left
    pdf.set_fill_color(*CYAN)
    pdf.rect(W - 31, 17, 14, H - 34, style="F")  # right
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(2)
    pdf.rect(46, 46, W - 92, H - 92)


def render(doc: CertDoc) -> bytes:
    pdf = _Pdf()
    pdf.set_title(f"{doc.heading} - {doc.name}")
    pdf.set_author(doc.company)
    pdf.add_page()
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, W, H, style="F")
    _frame(pdf)

    drawn_logo = False
    if doc.logo:
        try:
            info = pdf.image(io.BytesIO(doc.logo), h=94, x=-1000, y=-1000)  # measure first
            width = 94 * info.width / info.height if info.height else 94
            pdf.image(io.BytesIO(doc.logo), x=W / 2 - width / 2, y=56, h=94)
            drawn_logo = True
        except Exception:  # a logo that cannot be read: fall back to the company name
            drawn_logo = False
    if not drawn_logo:
        pdf.centred(doc.company.upper(), 118, "Sora", "B", 24, NAVY)

    pdf.centred(doc.heading, 196, "Sora", "B", 50, NAVY)
    pdf.centred(doc.intro, 258, "DMSans", "", 22, MUTED)
    pdf.centred(doc.name, 336, "Sora", "B", 36 if len(doc.name) > 22 else 48, INDIGO)
    pdf.centred(doc.line, 392, "DMSans", "", 22, MUTED)
    pdf.centred(doc.title, 454, "Sora", "B", 30 if len(doc.title) > 26 else 36, NAVY)
    if doc.sub:
        pdf.centred(doc.sub, 494, "DMSans", "", 19, MUTED)

    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(1.5)
    pdf.line(130, 598, 340, 598)
    pdf.line(660, 598, 870, 598)
    pdf.centred(doc.company, 624, "DMSans", "", 17, NAVY, x=235)
    pdf.centred(doc.issued, 624, "DMSans", "", 17, NAVY, x=765)
    pdf.centred(doc.id_line, 664, "DMSans", "", 15, NAVY)

    if not doc.approved:
        with pdf.local_context(fill_opacity=0.11, text_color=NAVY):
            pdf.set_font("Sora", "B", 64)
            with pdf.rotation(28.6, W / 2, H / 2):
                width = pdf.get_string_width(doc.watermark)
                for yy in range(-520, 521, 150):
                    for xx in range(-760, 761, 430):
                        pdf.text(W / 2 + xx - width / 2, H / 2 + yy, doc.watermark)

    return bytes(pdf.output())
