"""The fixed choices of the CV Agent wizard (spec B28). Same lists as the CHECK rules of 0026."""

from typing import Literal

from app.countries import WORLD_COUNTRIES

CvType = Literal["new", "update", "overseas", "immigration", "student", "graduate", "professional", "academic", "europass"]
CV_TYPES: tuple[CvType, ...] = (
    "new", "update", "overseas", "immigration", "student", "graduate", "professional", "academic", "europass",
)

Category = Literal[
    "skilled_worker", "it", "healthcare", "engineering", "construction", "hospitality", "agriculture",
    "manufacturing", "driving", "administration", "business", "finance", "education", "research",
    "student_admission", "general",
]
CATEGORIES: tuple[Category, ...] = (
    "skilled_worker", "it", "healthcare", "engineering", "construction", "hospitality", "agriculture",
    "manufacturing", "driving", "administration", "business", "finance", "education", "research",
    "student_admission", "general",
)

DocKind = Literal["cv", "academic", "experience", "training", "licence", "language", "passport", "other"]
DOC_KINDS: tuple[DocKind, ...] = ("cv", "academic", "experience", "training", "licence", "language", "passport", "other")

Template = Literal["modern", "corporate", "minimalist", "technical", "academic", "europass", "international"]
TEMPLATES: tuple[Template, ...] = ("modern", "corporate", "minimalist", "technical", "academic", "europass", "international")

# The flag grid of Step 2; every other country comes from the full list ("Other").
FEATURED_COUNTRIES: tuple[str, ...] = (
    "Canada", "USA", "UK", "Australia", "New Zealand", "Germany", "France", "Italy", "Sweden", "Switzerland",
    "Finland", "Netherlands", "Denmark", "Ireland", "Malaysia", "Singapore", "Japan", "South Korea",
)
COUNTRIES: frozenset[str] = frozenset(WORLD_COUNTRIES)

MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UPLOADS_PER_HOUR = 30
MAX_PROJECTS = 50
MAX_ADVERT = 20000
MAX_TITLE = 120
