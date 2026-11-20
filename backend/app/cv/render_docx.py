"""CV and cover letter DOCX with python-docx (spec B28): real text, real Word headings and
bullet lists, no text boxes, tables or pictures - so ATS systems read it. Same blocks as the PDF.
Fonts: Calibri for the Carlito templates, Times New Roman for the Tinos ones (Word has both)."""

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt, RGBColor

from app.cv.layout import CvLayout
from app.cv.render_pdf import STYLES

WORD_FONT = {"carlito": "Calibri", "tinos": "Times New Roman"}


def _document(layout: CvLayout) -> "Document":  # type: ignore[valid-type]
    doc = Document()
    style = STYLES.get(layout.template, STYLES["modern"])
    for section in doc.sections:
        section.page_height, section.page_width = Mm(297), Mm(210)
        section.left_margin = section.right_margin = Mm(style.margin)
        section.top_margin = section.bottom_margin = Mm(14)
    font = WORD_FONT.get(layout.font, "Calibri")
    normal = doc.styles["Normal"]
    normal.font.name = font
    normal.font.size = Pt(style.body_size)
    for name in ("Title", "Heading 1", "List Bullet"):
        doc.styles[name].font.name = font
    accent = RGBColor(*style.accent)
    title = doc.add_paragraph(style="Title")
    run = title.add_run(layout.name or " ")
    run.font.size, run.font.color.rgb, run.bold = Pt(style.name_size), accent, True
    if style.center:
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for line in (layout.contact, layout.details):
        if line:
            p = doc.add_paragraph(line)
            if style.center:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return doc


def _heading(doc: "Document", text: str, layout: CvLayout) -> None:  # type: ignore[valid-type]
    style = STYLES.get(layout.template, STYLES["modern"])
    h = doc.add_heading(text.upper() if style.upper else text, level=1)
    for run in h.runs:
        run.font.size = Pt(style.heading_size)
        run.font.color.rgb = RGBColor(*style.accent)


def cv_docx(layout: CvLayout) -> bytes:
    doc = _document(layout)
    for s in layout.sections:
        _heading(doc, s.title, layout)
        if s.kind == "paragraph":
            doc.add_paragraph(s.text)
        elif s.kind == "entries":
            for e in s.entries:
                p = doc.add_paragraph()
                p.add_run(e.title).bold = True
                if e.dates:
                    p.add_run(f"  ({e.dates})")
                if e.subtitle:
                    doc.add_paragraph().add_run(e.subtitle).italic = True
                for b in e.bullets:
                    doc.add_paragraph(b, style="List Bullet")
        else:
            for line in s.lines:
                doc.add_paragraph(line, style="List Bullet")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def letter_docx(layout: CvLayout, body: str) -> bytes:
    doc = _document(layout)
    for paragraph in [p.strip() for p in body.split("\n\n") if p.strip()]:
        doc.add_paragraph(paragraph)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
