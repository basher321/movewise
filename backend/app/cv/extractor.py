"""Extractor (spec B28 section 3.1): reads ONE uploaded document into the CV schema.

Every item gets the file it came from and the AI's confidence; low-confidence items and unsure
personal fields are marked "Please confirm". A passport is read only when the person ticked the
Passport chip, and only for the name and nationality (its number is never asked for or kept).
"""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection, RowMapping

from app.cv.ai_client import Caller, ask_json, prompt
from app.cv.reading import ReadDocument
from app.cv.schema import (
    Achievement,
    Certification,
    CvData,
    Education,
    Experience,
    Language,
    Personal,
    Reference,
    Skills,
    Training,
)

PERSONAL_FIELDS = (
    "full_name", "email", "phone", "city", "country", "linkedin", "website", "nationality", "date_of_birth",
    "gender", "marital_status",
)


class ExtractOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    personal: Personal = Field(default_factory=Personal)
    personal_unsure: list[str] = Field(default_factory=list)
    professional_summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    languages: list[Language] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    training: list[Training] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


class PassportOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: str = ""
    nationality: str = ""


def _user_message(doc_kind: str, file_name: str, document: ReadDocument) -> str:
    head = f"Document type chosen by the person: {doc_kind}. File name: {file_name}."
    if document.text:
        return f"{head}\n\nDOCUMENT TEXT:\n{document.text}"
    return f"{head}\n\nThe document is in the attached image(s)."


def extract(conn: Connection, caller: Caller, file_row: RowMapping, document: ReadDocument) -> CvData:
    name = str(file_row["file_name"])
    if file_row["doc_kind"] == "passport":
        found = ask_json(conn, caller, "extractor", prompt("passport"), "Read the name and nationality.", PassportOut,
                         images=document.images)
        personal = Personal(full_name=found.full_name, nationality=found.nationality)
        personal.sources = {f: name for f in ("full_name", "nationality") if getattr(personal, f)}
        return CvData(personal=personal)

    out = ask_json(conn, caller, "extractor", prompt("extractor"), _user_message(str(file_row["doc_kind"]), name, document),
                   ExtractOut, images=document.images if not document.text else None)
    data = CvData(
        personal=out.personal, professional_summary=out.professional_summary, experience=out.experience,
        education=out.education, skills=out.skills, languages=out.languages, certifications=out.certifications,
        training=out.training, achievements=out.achievements, references=out.references,
    )
    if data.personal.full_name.isupper() and len(data.personal.full_name) > 3:
        data.personal.full_name = " ".join(part.capitalize() for part in data.personal.full_name.split())
    data.personal.sources = {f: name for f in PERSONAL_FIELDS if getattr(data.personal, f)}
    data.personal.confirm_fields = [f for f in out.personal_unsure if f in PERSONAL_FIELDS and getattr(data.personal, f)]
    data.personal.show = []
    for section in ("experience", "education", "languages", "certifications", "training", "achievements", "references"):
        for item in getattr(data, section):
            item.source_file = name
            if item.confidence == "low":
                item.confirm = True
                item.note = "The document was unclear here. Please check it."
    return data
