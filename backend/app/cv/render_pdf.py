"""CV and cover letter PDF with fpdf2 (spec B28; owner decision: fpdf2, not Playwright).

A4, single column, real selectable text in embedded open fonts (Carlito ~ Calibri metrics,
Tinos ~ Times metrics), no tables, pictures or icons in the body - so ATS systems read it. The
seven templates differ in font, heading style, accent colour and alignment only.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF

from app.cv.layout import CvLayout, Entry, Section

FONTS = Path(__file__).resolve().parent / "fonts"
FAMILIES = {
    "carlito": ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf"),
    "tinos": ("Tinos-Regular.ttf", "Tinos-Bold.ttf", "Tinos-Italic.ttf"),
}
# The font library notes tables it leaves out of the embedded font; not useful in the logs.
logging.getLogger("fontTools").setLevel(logging.ERROR)
TEXT = (25, 25, 25)
MUTED = (85, 85, 85)


@dataclass(frozen=True)
class Style:
    accent: tuple[int, int, int]
    name_size: float
    heading_size: float
    body_size: float
    upper: bool
    rule: bool
    center: bool
    margin: float = 16.0


STYLES: dict[str, Style] = {
    "modern": Style((31, 58, 95), 22, 11.5, 10.5, True, True, False),
    "corporate": Style((15, 23, 42), 21, 11.5, 10.5, True, True, True),
    "minimalist": Style((40, 40, 40), 20, 12, 10.5, False, False, False),
    "technical": Style((15, 92, 99), 21, 11.5, 10.5, True, True, False),
    "academic": Style((20, 20, 20), 20, 12, 11, False, True, True, 18.0),
    "europass": Style((0, 51, 153), 20, 11.5, 10.5, True, True, False),
    "international": Style((30, 41, 59), 21, 11.5, 10.5, True, True, True),
}


class CvPdf(FPDF):
    def __init__(self, font: str, style: Style, title: str) -> None:
        super().__init__(format="A4", unit="mm")
        regular, bold, italic = FAMILIES[font]
        self.add_font("cv", "", str(FONTS / regular))
        self.add_font("cv", "B", str(FONTS / bold))
        self.add_font("cv", "I", str(FONTS / italic))
        self.st = style
        self.set_margins(style.margin, 14, style.margin)
        self.set_auto_page_break(True, 14)
        self.set_title(title)
        self.set_creator("CV Agent")
        self.add_page()

    @property
    def width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def text_style(self, style: str = "", size: float | None = None, color: tuple[int, int, int] = TEXT) -> None:
        self.set_font("cv", style, size or self.st.body_size)
        self.set_text_color(*color)

    def header_block(self, name: str, contact: str, details: str) -> None:
        align = "C" if self.st.center else "L"
        self.text_style("B", self.st.name_size, self.st.accent)
        self.multi_cell(self.width, self.st.name_size * 0.45, name or " ", align=align, new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)
        for line in (contact, details):
            if line:
                self.text_style("", self.st.body_size - 0.5, MUTED)
                self.multi_cell(self.width, 5, line, align=align, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def heading(self, title: str) -> None:
        if self.get_y() > self.h - 32:
            self.add_page()
        self.ln(2.5)
        self.text_style("B", self.st.heading_size, self.st.accent)
        self.cell(self.width, 6.5, title.upper() if self.st.upper else title, new_x="LMARGIN", new_y="NEXT")
        if self.st.rule:
            self.set_draw_color(*self.st.accent)
            self.set_line_width(0.3)
            y = self.get_y() + 0.3
            self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(2)

    def paragraph(self, text: str) -> None:
        self.text_style()
        self.multi_cell(self.width, 5.2, text, new_x="LMARGIN", new_y="NEXT")

    def bullet(self, text: str, indent: float = 4.0) -> None:
        self.text_style()
        x = self.l_margin
        self.set_x(x)
        self.cell(indent, 5.2, "•")
        self.multi_cell(self.width - indent, 5.2, text, new_x="LMARGIN", new_y="NEXT")

    def entry(self, e: Entry) -> None:
        if self.get_y() > self.h - 26:
            self.add_page()
        y = self.get_y()
        date_w = 0.0
        if e.dates:
            self.text_style("", self.st.body_size - 0.5, MUTED)
            date_w = self.get_string_width(e.dates) + 2
            self.set_xy(self.w - self.r_margin - date_w, y)
            self.cell(date_w, 5.4, e.dates, align="R")
        self.set_xy(self.l_margin, y)
        self.text_style("B")
        self.multi_cell(self.width - date_w - 2, 5.4, e.title or " ", new_x="LMARGIN", new_y="NEXT")
        if e.subtitle:
            self.text_style("I", self.st.body_size - 0.5, MUTED)
            self.multi_cell(self.width, 5, e.subtitle, new_x="LMARGIN", new_y="NEXT")
        for b in e.bullets:
            self.bullet(b)
        self.ln(1.6)

    def section(self, s: Section) -> None:
        self.heading(s.title)
        if s.kind == "paragraph":
            self.paragraph(s.text)
        elif s.kind == "entries":
            for e in s.entries:
                self.entry(e)
        else:
            for line in s.lines:
                self.bullet(line)


def cv_pdf(layout: CvLayout, title: str) -> tuple[bytes, int]:
    """(PDF bytes, number of pages)."""
    pdf = CvPdf(layout.font, STYLES.get(layout.template, STYLES["modern"]), title)
    pdf.header_block(layout.name, layout.contact, layout.details)
    for s in layout.sections:
        pdf.section(s)
    return bytes(pdf.output()), pdf.pages_count


def letter_pdf(layout: CvLayout, body: str, title: str) -> bytes:
    pdf = CvPdf(layout.font, STYLES.get(layout.template, STYLES["modern"]), title)
    pdf.header_block(layout.name, layout.contact, "")
    pdf.ln(4)
    pdf.set_auto_page_break(True, 14)
    for paragraph in [p.strip() for p in body.split("\n\n") if p.strip()]:
        pdf.paragraph(paragraph)
        pdf.ln(3)
    return bytes(pdf.output())


def pdf_pages_png(pdf_bytes: bytes, dpi: int) -> list[bytes]:
    """The PDF pages as PNG pictures - the preview is the real PDF, so it matches exactly."""
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        return [page.get_pixmap(dpi=dpi).tobytes("png") for page in document]
