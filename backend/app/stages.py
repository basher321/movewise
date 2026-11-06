"""Stage names and required documents per module, copied from the reference (ST, JT, DOCS).
Immigration Processing (visa, spec B19) and Remote Jobs (remote) follow the same pattern.
Remote Jobs has no visa, medical or flight steps: the work is done from home."""

from typing import Literal

AppModule = Literal["study", "job", "visa", "remote"]

APP_MODULES: tuple[AppModule, ...] = ("study", "job", "visa", "remote")

STAGES: dict[AppModule, tuple[str, ...]] = {
    "study": (
        "Application started",
        "Documents submitted",
        "University review",
        "Offer letter received",
        "Tuition deposit & confirmation",
        "Visa application",
        "Visa interview / biometrics",
        "Visa decision",
        "Ready to fly ✈",
    ),
    "job": (
        "Application started",
        "Profile screening",
        "Employer interview",
        "Job offer & contract",
        "Medical & police clearance",
        "Work permit & visa",
        "Flight booked",
        "Ready to fly ✈",
    ),
    "visa": (
        "Application started",
        "Eligibility review",
        "Documents checked",
        "File prepared",
        "Visa application lodged",
        "Biometrics / interview",
        "Visa decision",
        "Ready to travel ✈",
    ),
    "remote": (
        "Application started",
        "Profile screening",
        "Skills test / interview",
        "Job offer & contract",
        "Onboarding",
        "Started work ✓",
    ),
}

DOCUMENT_TYPES: dict[AppModule, tuple[str, ...]] = {
    "study": (
        "Academic transcripts and certificates",
        "Valid passport",
        "IELTS (or equivalent) score report",
        "Statement of purpose",
        "Two recommendation letters",
        "CV",
        "Proof of funds",
    ),
    "job": (
        "Valid passport (18+ months)",
        "Education and experience certificates",
        "Updated CV",
        "Medical report",
        "Police clearance",
        "Passport-size photographs",
    ),
    "visa": (
        "Valid passport (all pages)",
        "Passport-size photographs",
        "Bank statement and proof of funds",
        "Employment or business documents",
        "Invitation, sponsor or family documents",
        "Previous visas and travel history",
        "Other supporting documents",
    ),
    "remote": (
        "Updated CV",
        "Education and experience certificates",
        "National ID or passport",
        "Portfolio or work samples",
    ),
}


def stage_count(module: AppModule) -> int:
    return len(STAGES[module])


def stage_name(module: AppModule, stage: int) -> str:
    return STAGES[module][stage]
