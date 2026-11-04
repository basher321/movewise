"""Company settings, encrypted secrets, and the logo / home picture.

Write endpoints read their body themselves, after require_super_admin, so the order of
checks is always: signed in -> role -> input valid -> do the work.
"""

import hashlib
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, RowMapping
from starlette.datastructures import UploadFile

from app.ai import providers as ai_providers
from app.ai.config import MAX_KEY, MODEL_RE, PROVIDER_LABELS, PROVIDERS, Provider, key_name, normalise
from app.audit import Actor, write_audit
from app.auth.deps import require_super_admin
from app.crypto import DecryptError, decrypt
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.secrets_store import read_secret, save_secret

logger = logging.getLogger("app")

router = APIRouter()

ImageKind = Literal["logo", "hero"]

GATEWAY_SECRETS: dict[str, tuple[str, ...]] = {
    "sslcommerz": ("store_id", "store_password"),
    "bkash": ("app_key", "app_secret", "username", "password"),
    "nagad": ("merchant_id", "private_key"),
}
# B08: the SMTP password replaces the old mail API key (that stored row is no longer used).
OTHER_SECRETS: dict[str, tuple[str, ...]] = {"mail": ("smtp_password",), "whatsapp": ("token",)}
SECRET_NAMES: tuple[str, ...] = tuple(
    f"{group}.{field}"
    for groups in (GATEWAY_SECRETS, OTHER_SECRETS)
    for group, fields in groups.items()
    for field in fields
)
GATEWAY_LABELS = {"sslcommerz": "SSLCommerz", "bkash": "bKash", "nagad": "Nagad"}
SECRET_LABELS = {
    "store_id": "store id",
    "store_password": "store password",
    "app_key": "app key",
    "app_secret": "app secret",
    "username": "username",
    "password": "password",
    "merchant_id": "merchant id",
    "private_key": "private key",
}

# settings column -> field path in the API, used to list changed fields in the audit row.
FIELD_PATHS: dict[str, str] = {
    "name": "name",
    "tagline": "tagline",
    "brand_color": "brand_color",
    "hero_title": "hero_title",
    "hero_text": "hero_text",
    "stats": "stats",
    "about_title": "about_title",
    "about_text": "about_text",
    "address": "address",
    "phone": "phone",
    "email": "email",
    "hours": "hours",
    "facebook": "facebook",
    "website": "website",
    "invoice_prefix": "invoice_prefix",
    "invoice_footer": "invoice_footer",
    "vat_bin": "vat_bin",
    "default_fee_study_poisha": "default_fee_poisha.study",
    "default_fee_job_poisha": "default_fee_poisha.job",
    "default_fee_visa_poisha": "default_fee_poisha.visa",
    "sslcommerz_enabled": "gateways.sslcommerz.enabled",
    "sslcommerz_sandbox": "gateways.sslcommerz.sandbox",
    "bkash_enabled": "gateways.bkash.enabled",
    "bkash_sandbox": "gateways.bkash.sandbox",
    "nagad_enabled": "gateways.nagad.enabled",
    "nagad_sandbox": "gateways.nagad.sandbox",
    "manual_enabled": "gateways.manual.enabled",
    "manual_instructions": "gateways.manual.instructions",
    "mail_sender_name": "mail.sender_name",
    "mail_sender_email": "mail.sender_email",
    "whatsapp_number": "whatsapp.number",
    "smtp_host": "mail.smtp_host",
    "smtp_port": "mail.smtp_port",
    "smtp_security": "mail.smtp_security",
    "smtp_username": "mail.smtp_username",
    "whatsapp_phone_number_id": "whatsapp.phone_number_id",
    "whatsapp_template_name": "whatsapp.template_name",
    "whatsapp_template_language": "whatsapp.template_language",
    "whatsapp_api_version": "whatsapp.api_version",
}
# B08: sending settings, shown only to the super admin (never in /settings/public).
PRIVATE_FIELDS = {
    "mail": ("smtp_host", "smtp_port", "smtp_security", "smtp_username"),
    "whatsapp": ("phone_number_id", "template_name", "template_language", "api_version"),
}
HOST_RE = re.compile(r"[A-Za-z0-9.-]{1,253}")
TEMPLATE_RE = re.compile(r"[a-z0-9_]{1,512}")
LANGUAGE_RE = re.compile(r"[a-z]{2,3}(_[A-Z]{2})?")
API_VERSION_RE = re.compile(r"v\d{1,3}\.\d{1,2}")
DIGITS_RE = re.compile(r"\d{5,30}")

EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
PREFIX_RE = re.compile(r"[A-Za-z0-9]{1,10}")

IMAGE_LIMITS: dict[ImageKind, int] = {"logo": 500 * 1024, "hero": 1536 * 1024}
IMAGE_TEXT: dict[ImageKind, tuple[str, str, str]] = {
    # label, size limit as shown, audit detail
    "logo": ("Logo", "500 KB", "Logo changed"),
    "hero": ("Home picture", "1.5 MB", "Home picture changed"),
}


# ---------- Request body ----------


class StatIn(BaseModel):
    number: str
    label: str


class SslcommerzIn(BaseModel):
    enabled: bool
    sandbox: bool
    store_id: str = ""
    store_password: str = ""


class BkashIn(BaseModel):
    enabled: bool
    sandbox: bool
    app_key: str = ""
    app_secret: str = ""
    username: str = ""
    password: str = ""


class NagadIn(BaseModel):
    enabled: bool
    sandbox: bool
    merchant_id: str = ""
    private_key: str = ""


class ManualIn(BaseModel):
    enabled: bool
    instructions: str = ""


class GatewaysIn(BaseModel):
    sslcommerz: SslcommerzIn
    bkash: BkashIn
    nagad: NagadIn
    manual: ManualIn


class MailIn(BaseModel):
    sender_name: str = ""
    sender_email: str = ""
    smtp_host: str = ""
    smtp_port: StrictInt = 587
    smtp_security: str = "starttls"
    smtp_username: str = ""
    smtp_password: str = ""


class WhatsappIn(BaseModel):
    number: str = ""
    token: str = ""
    phone_number_id: str = ""
    template_name: str = ""
    template_language: str = "en"
    api_version: str = "v21.0"


class FeesIn(BaseModel):
    study: StrictInt
    job: StrictInt
    # B19: optional, so a client that does not know Immigration yet keeps the saved fee.
    visa: StrictInt | None = None


class AiProviderIn(BaseModel):
    enabled: StrictBool
    model: str = Field(default="", max_length=1000)
    key: str = Field(default="", max_length=5000)


class AiIn(BaseModel):
    """B17: provider order, and each provider's switch, model and key ("" keeps the saved key)."""

    order: list[str] = Field(max_length=10)
    providers: dict[str, AiProviderIn]


class SettingsIn(BaseModel):
    """The F02 Settings shape. Fields such as logo, hero_image or logo_url are ignored:
    pictures change only through the upload endpoints."""

    name: str
    tagline: str = ""
    brand_color: str
    hero_title: str = ""
    hero_text: str = ""
    stats: list[StatIn]
    about_title: str = ""
    about_text: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    hours: str = ""
    facebook: str = ""
    website: str = ""
    invoice_prefix: str
    invoice_footer: str = ""
    vat_bin: str = ""
    default_fee_poisha: FeesIn
    gateways: GatewaysIn
    mail: MailIn
    whatsapp: WhatsappIn
    # B17: optional, so a body without it keeps the saved AI settings.
    ai: AiIn | None = None


def _columns(body: SettingsIn) -> dict[str, Any]:
    gw = body.gateways
    return {
        "name": body.name,
        "tagline": body.tagline,
        "brand_color": body.brand_color,
        "hero_title": body.hero_title,
        "hero_text": body.hero_text,
        "stats": [stat.model_dump() for stat in body.stats],
        "about_title": body.about_title,
        "about_text": body.about_text,
        "address": body.address,
        "phone": body.phone,
        "email": body.email,
        "hours": body.hours,
        "facebook": body.facebook,
        "website": body.website,
        "invoice_prefix": body.invoice_prefix,
        "invoice_footer": body.invoice_footer,
        "vat_bin": body.vat_bin,
        "default_fee_study_poisha": body.default_fee_poisha.study,
        "default_fee_job_poisha": body.default_fee_poisha.job,
        "default_fee_visa_poisha": body.default_fee_poisha.visa,
        "sslcommerz_enabled": gw.sslcommerz.enabled,
        "sslcommerz_sandbox": gw.sslcommerz.sandbox,
        "bkash_enabled": gw.bkash.enabled,
        "bkash_sandbox": gw.bkash.sandbox,
        "nagad_enabled": gw.nagad.enabled,
        "nagad_sandbox": gw.nagad.sandbox,
        "manual_enabled": gw.manual.enabled,
        "manual_instructions": gw.manual.instructions,
        "mail_sender_name": body.mail.sender_name,
        "mail_sender_email": body.mail.sender_email,
        "whatsapp_number": body.whatsapp.number,
        "smtp_host": body.mail.smtp_host.strip(),
        "smtp_port": body.mail.smtp_port,
        "smtp_security": body.mail.smtp_security,
        "smtp_username": body.mail.smtp_username.strip(),
        "whatsapp_phone_number_id": body.whatsapp.phone_number_id.strip(),
        "whatsapp_template_name": body.whatsapp.template_name.strip(),
        "whatsapp_template_language": body.whatsapp.template_language.strip(),
        "whatsapp_api_version": body.whatsapp.api_version.strip(),
    }


def _sent_secrets(body: SettingsIn) -> dict[str, str]:
    """Secret values sent in this request. Empty or missing means keep the stored value."""
    values: dict[str, str] = {}
    for group, fields in GATEWAY_SECRETS.items():
        for field in fields:
            values[f"{group}.{field}"] = getattr(getattr(body.gateways, group), field)
    values["mail.smtp_password"] = body.mail.smtp_password
    values["whatsapp.token"] = body.whatsapp.token
    return {name: value for name, value in values.items() if value}


def _secret_path(name: str) -> str:
    group = name.split(".")[0]
    return f"gateways.{name}" if group in GATEWAY_SECRETS else name


# ---------- Validation (same rules as F03) ----------


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _validate(body: SettingsIn, available_secrets: set[str]) -> None:
    if not body.name.strip():
        raise _invalid("Please fill in: Company name.")
    if not COLOR_RE.fullmatch(body.brand_color):
        raise _invalid("Brand colour must look like #4F46E5.")
    if not PREFIX_RE.fullmatch(body.invoice_prefix):
        raise _invalid("Invoice prefix must be 1 to 10 letters or digits.")
    if len(body.stats) != 3:
        raise _invalid("There must be exactly 3 stats.")
    if body.email and not EMAIL_RE.fullmatch(body.email):
        raise _invalid("Please enter a valid email.")
    if body.mail.sender_email and not EMAIL_RE.fullmatch(body.mail.sender_email):
        raise _invalid("Please enter a valid sender email.")
    mail, wa = body.mail, body.whatsapp
    if mail.smtp_host.strip() and not HOST_RE.fullmatch(mail.smtp_host.strip()):
        raise _invalid("SMTP host must look like smtp.example.com.")
    if not 1 <= mail.smtp_port <= 65535:
        raise _invalid("SMTP port must be from 1 to 65535.")
    if mail.smtp_security not in ("starttls", "ssl", "none"):
        raise _invalid("Please choose the SMTP security: STARTTLS, SSL or none.")
    if len(mail.smtp_username) > 200:
        raise _invalid("SMTP username must be at most 200 characters.")
    if wa.phone_number_id.strip() and not DIGITS_RE.fullmatch(wa.phone_number_id.strip()):
        raise _invalid("WhatsApp phone number ID must be digits only.")
    if wa.template_name.strip() and not TEMPLATE_RE.fullmatch(wa.template_name.strip()):
        raise _invalid("WhatsApp template name may use lower-case letters, digits and _ only.")
    if not LANGUAGE_RE.fullmatch(wa.template_language.strip()):
        raise _invalid("WhatsApp template language must look like en or en_US.")
    if not API_VERSION_RE.fullmatch(wa.api_version.strip()):
        raise _invalid("WhatsApp API version must look like v21.0.")
    fees = body.default_fee_poisha
    if fees.study <= 0 or fees.job <= 0 or (fees.visa is not None and fees.visa <= 0):
        raise _invalid("Default fees must be whole numbers of poisha above 0.")
    gw = body.gateways
    if not (gw.sslcommerz.enabled or gw.bkash.enabled or gw.nagad.enabled or gw.manual.enabled):
        raise _invalid("Please turn on at least one payment method.")
    for group, fields in GATEWAY_SECRETS.items():
        if getattr(gw, group).enabled:
            missing = [SECRET_LABELS[f] for f in fields if f"{group}.{f}" not in available_secrets]
            if missing:
                raise _invalid(f"{GATEWAY_LABELS[group]} needs: {', '.join(missing)}.")


def _ai_sent_keys(ai: AiIn | None) -> dict[str, str]:
    if ai is None:
        return {}
    return {key_name(p): ai.providers[p].key.strip() for p in PROVIDERS if p in ai.providers and ai.providers[p].key.strip()}


def _validate_ai(ai: AiIn, saved_keys: set[str]) -> dict[str, Any]:
    """The ai block to store (no keys in it). Same order of messages as the other settings."""
    if len(ai.order) != len(PROVIDERS) or set(ai.order) != set(PROVIDERS):
        raise _invalid("AI order must list Claude, ChatGPT, Gemini and Groq once each.")
    if set(ai.providers) != set(PROVIDERS):
        raise _invalid("AI settings must include Claude, ChatGPT, Gemini and Groq.")
    stored: dict[str, Any] = {"order": list(ai.order), "providers": {}}
    for p in PROVIDERS:
        item = ai.providers[p]
        model = item.model.strip()
        label = PROVIDER_LABELS[p]
        if model and not MODEL_RE.fullmatch(model):
            raise _invalid(f"{label} model may use letters, digits and . _ : / - only (at most 100).")
        if len(item.key.strip()) > MAX_KEY:
            raise _invalid(f"{label} API key is too long.")
        if item.enabled:
            if not model:
                raise _invalid(f"{label} needs a model name.")
            if key_name(p) not in saved_keys and not item.key.strip():
                raise _invalid(f"{label} needs an API key.")
        stored["providers"][p] = {"enabled": item.enabled, "model": model}
    return stored


# ---------- Database ----------

_SELECT_SETTINGS = text(
    "SELECT "
    + ", ".join(f"s.{column}" for column in FIELD_PATHS)
    + ", l.sha256 AS logo_sha256, h.sha256 AS hero_sha256 "
    "FROM settings s "
    "LEFT JOIN branding_images l ON l.id = s.logo_image_id "
    "LEFT JOIN branding_images h ON h.id = s.hero_image_id "
    "WHERE s.singleton = 'settings'"
)
_UPDATE_SETTINGS = text(
    "UPDATE settings SET "
    + ", ".join(f"{column} = :{column}" for column in FIELD_PATHS)
    + " WHERE singleton = 'settings'"
).bindparams(bindparam("stats", type_=JSONB))
_SELECT_SECRETS = text(
    "SELECT name, ciphertext FROM settings_secrets UNION ALL SELECT name, ciphertext FROM app_secrets"
)
_INSERT_IMAGE = text(
    "INSERT INTO branding_images (kind, mime, size_bytes, sha256, bytes) "
    "VALUES (:kind, :mime, :size_bytes, :sha256, :bytes) RETURNING id"
)
_SET_IMAGE: dict[ImageKind, Any] = {
    "logo": text("UPDATE settings SET logo_image_id = :image_id WHERE singleton = 'settings'"),
    "hero": text("UPDATE settings SET hero_image_id = :image_id WHERE singleton = 'settings'"),
}
_SELECT_IMAGE: dict[ImageKind, Any] = {
    "logo": text(
        "SELECT b.mime, b.sha256, b.bytes FROM settings s "
        "JOIN branding_images b ON b.id = s.logo_image_id WHERE s.singleton = 'settings'"
    ),
    "hero": text(
        "SELECT b.mime, b.sha256, b.bytes FROM settings s "
        "JOIN branding_images b ON b.id = s.hero_image_id WHERE s.singleton = 'settings'"
    ),
}


_UPDATE_AI = text("UPDATE settings SET ai = :ai WHERE singleton = 'settings'").bindparams(bindparam("ai", type_=JSONB))


def _saved_ai_keys(conn: Connection) -> set[str]:
    """AI key names whose stored value can be read."""
    stored = {name: ciphertext for name, ciphertext in conn.execute(_SELECT_SECRETS)}
    saved = set()
    for p in PROVIDERS:
        name = key_name(p)
        if name in stored:
            try:
                decrypt(name, stored[name])
                saved.add(name)
            except DecryptError:
                pass
    return saved


def _ai_view(conn: Connection) -> dict[str, Any]:
    ai = normalise(conn.execute(text("SELECT ai FROM settings WHERE singleton = 'settings'")).scalar_one())
    saved = _saved_ai_keys(conn)
    for p in PROVIDERS:
        ai["providers"][p]["key"] = {"saved": key_name(p) in saved}
    return ai


def _fetch_settings_row(conn: Connection) -> RowMapping | None:
    return conn.execute(_SELECT_SETTINGS).mappings().one_or_none()


def _settings_row(conn: Connection) -> RowMapping:
    row = _fetch_settings_row(conn)
    if row is None:
        # Never recreated silently: the migration inserts it and nothing deletes it.
        logger.error("settings row missing")
        raise RuntimeError("settings row missing")
    return row


def _secret_status(conn: Connection) -> dict[str, dict[str, bool]]:
    stored = {name: ciphertext for name, ciphertext in conn.execute(_SELECT_SECRETS)}
    status: dict[str, dict[str, bool]] = {}
    for name in SECRET_NAMES:
        if name not in stored:
            status[name] = {"saved": False}
            continue
        try:
            decrypt(name, stored[name])
            status[name] = {"saved": True}
        except DecryptError:
            status[name] = {"saved": False, "unreadable": True}
    return status


# ---------- Responses ----------


def _image_url(kind: ImageKind, sha256: str | None) -> str | None:
    return f"/api/branding/{kind}?v={sha256[:12]}" if sha256 else None


def _public_view(row: RowMapping) -> dict[str, Any]:
    logo_url = _image_url("logo", row["logo_sha256"])
    hero_url = _image_url("hero", row["hero_sha256"])
    return {
        "name": row["name"],
        "tagline": row["tagline"],
        "brand_color": row["brand_color"],
        "logo": logo_url or "",
        "hero_image": hero_url or "",
        "logo_url": logo_url,
        "hero_url": hero_url,
        "hero_title": row["hero_title"],
        "hero_text": row["hero_text"],
        "stats": row["stats"],
        "about_title": row["about_title"],
        "about_text": row["about_text"],
        "address": row["address"],
        "phone": row["phone"],
        "email": row["email"],
        "hours": row["hours"],
        "facebook": row["facebook"],
        "website": row["website"],
        "invoice_prefix": row["invoice_prefix"],
        "invoice_footer": row["invoice_footer"],
        "vat_bin": row["vat_bin"],
        "default_fee_poisha": {
            "study": row["default_fee_study_poisha"],
            "job": row["default_fee_job_poisha"],
            "visa": row["default_fee_visa_poisha"],
        },
        "gateways": {
            "sslcommerz": {"enabled": row["sslcommerz_enabled"], "sandbox": row["sslcommerz_sandbox"]},
            "bkash": {"enabled": row["bkash_enabled"], "sandbox": row["bkash_sandbox"]},
            "nagad": {"enabled": row["nagad_enabled"], "sandbox": row["nagad_sandbox"]},
            "manual": {"enabled": row["manual_enabled"], "instructions": row["manual_instructions"]},
        },
        "mail": {"sender_name": row["mail_sender_name"], "sender_email": row["mail_sender_email"]},
        "whatsapp": {"number": row["whatsapp_number"]},
    }


def _full_view(conn: Connection) -> dict[str, Any]:
    """Settings for the super admin: each secret field is only {"saved": ...}, never a value."""
    row = _settings_row(conn)
    view = _public_view(row)
    for group, fields in PRIVATE_FIELDS.items():
        prefix = "whatsapp_" if group == "whatsapp" else ""
        for field in fields:
            view[group][field] = row[prefix + field]
    for name, status in _secret_status(conn).items():
        group, field = name.split(".")
        target = view["gateways"][group] if group in GATEWAY_SECRETS else view[group]
        target[field] = status
    view["ai"] = _ai_view(conn)
    return view


def _sniff_mime(data: bytes) -> str | None:
    """The picture type from the file's first bytes, never from its name."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ---------- Endpoints ----------


@router.get("/settings/public")
def get_public_settings(conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    return _public_view(_settings_row(conn))


@router.get("/settings")
def get_settings(
    actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return _full_view(conn)


@router.put("/settings")
async def save_settings(
    request: Request,
    actor: Actor = Depends(require_super_admin),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(SettingsIn, await request.body())
    old = _settings_row(conn)
    sent = _sent_secrets(body)
    available = {name for name, status in _secret_status(conn).items() if status["saved"]} | set(sent)
    _validate(body, available)
    ai_keys = _ai_sent_keys(body.ai)
    ai_value = None
    if body.ai is not None:
        ai_value = _validate_ai(body.ai, _saved_ai_keys(conn))

    columns = _columns(body)
    if columns["default_fee_visa_poisha"] is None:
        columns["default_fee_visa_poisha"] = old["default_fee_visa_poisha"]
    conn.execute(_UPDATE_SETTINGS, columns)
    for name, value in sent.items():
        save_secret(conn, name, value)
    changed = [FIELD_PATHS[column] for column, value in columns.items() if old[column] != value]
    changed += [_secret_path(name) for name in sent]
    if ai_value is not None:
        old_ai = normalise(conn.execute(text("SELECT ai FROM settings WHERE singleton = 'settings'")).scalar_one())
        if old_ai != ai_value:
            conn.execute(_UPDATE_AI, {"ai": ai_value})
            changed.append("ai")
        for name, value in ai_keys.items():
            save_secret(conn, name, value)
            changed.append(name)
    write_audit(conn, actor, "settings.saved", "Settings saved: " + (", ".join(changed) or "no changes"))
    return _full_view(conn)


@router.put("/settings/{kind}")
async def upload_image(
    kind: ImageKind,
    request: Request,
    actor: Actor = Depends(require_super_admin),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    label, limit_text, audit_detail = IMAGE_TEXT[kind]
    form = await request.form(max_files=1, max_fields=1)
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise _invalid("file: Please choose a picture.")
    data = await upload.read(IMAGE_LIMITS[kind] + 1)
    if len(data) > IMAGE_LIMITS[kind]:
        raise _invalid(f"{label} must be {limit_text} or smaller.")
    mime = _sniff_mime(data)
    if mime is None:
        raise _invalid(f"{label} must be a PNG, JPEG or WebP picture.")

    image_id = conn.execute(
        _INSERT_IMAGE,
        {
            "kind": kind,
            "mime": mime,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": data,
        },
    ).scalar_one()
    conn.execute(_SET_IMAGE[kind], {"image_id": image_id})
    write_audit(conn, actor, f"settings.{kind}", audit_detail)
    return _full_view(conn)


@router.post("/settings/{kind}/clear")
def clear_image(
    kind: ImageKind,
    actor: Actor = Depends(require_super_admin),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    # The old picture stays in branding_images; only the link is removed.
    conn.execute(_SET_IMAGE[kind], {"image_id": None})
    write_audit(conn, actor, f"settings.{kind}", f"{IMAGE_TEXT[kind][2]} (default)")
    return _full_view(conn)


@router.get("/branding/{kind}")
def get_branding_image(kind: ImageKind, request: Request, conn: Connection = Depends(get_conn)) -> Response:
    row = conn.execute(_SELECT_IMAGE[kind]).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Not found.")
    etag = f'"{row["sha256"]}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=bytes(row["bytes"]), media_type=row["mime"], headers=headers)


class TestAiIn(BaseModel):
    provider: str = Field(max_length=20)


@router.post("/admin/settings/test-ai")
async def test_ai(
    request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    """B17: one short test prompt to a provider with its saved key and model. Never shows the key."""
    name = parse_body(TestAiIn, await request.body()).provider
    if name not in PROVIDERS:
        raise _invalid("Please choose Claude, ChatGPT, Gemini or Groq.")
    provider: Provider = name  # type: ignore[assignment]
    label = PROVIDER_LABELS[provider]
    model = normalise(conn.execute(text("SELECT ai FROM settings WHERE singleton = 'settings'")).scalar_one())[
        "providers"
    ][provider]["model"]
    key = read_secret(conn, key_name(provider))
    if not key or not model:
        result = ai_providers.ProviderResult(ok=False, error=f"{label} needs a saved model and API key first")
    else:
        result = await run_in_threadpool(ai_providers.ask, provider, key, model, "Reply with the single word OK.", "Say OK.")
        if not result.ok:
            result = ai_providers.ProviderResult(ok=False, error=f"{label}: {result.error}")
    write_audit(conn, actor, "Test AI sent", f"{label} · {'ok' if result.ok else 'failed'}")
    return {"ok": True} if result.ok else {"ok": False, "error": result.error}
