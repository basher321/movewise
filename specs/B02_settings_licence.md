Spec B02 - Settings, licence (signed keys) and the module lock

Purpose
Store the company Settings and the licence in the database, protect secrets, serve the logo and
home picture, and add the module lock that every later endpoint uses. Licence keys are signed by
the software owner, so a buyer cannot make or change a key. Endpoints follow the settings and
licence parts of the contract in specs/F02_api_contract_mock.md and F03 / F11.

Scope
In scope:
- db/migrations/0002_settings_licence.sql:
  - settings: exactly one row (singleton, CHECK on a fixed key). Columns for every Settings field
    in the F02 contract (name, tagline, brand_color, hero_title, hero_text, stats jsonb,
    about_title, about_text, address, phone, email, hours, facebook, website, invoice_prefix,
    invoice_footer, vat_bin, default_fee_study_poisha, default_fee_job_poisha, gateway on/off and
    sandbox flags, manual payment on/off and instructions, mail sender name and email,
    whatsapp number, logo_image_id, hero_image_id, updated_at).
  - settings_secrets: one row per secret (name, ciphertext, updated_at) for SSLCommerz store id and
    password, bKash app key, app secret, username and password, Nagad merchant id and private
    key, mail API key, WhatsApp token. Values are encrypted, never stored in plain text.
  - branding_images: id, kind ('logo' | 'hero'), mime, size_bytes, sha256, bytes (bytea).
  - licence: exactly one row: key text (nullable), holder, modules (course, study, job booleans),
    issued_at, expires_at (nullable), applied_at, applied_by.
  - The migration inserts the single settings row with neutral defaults (name "Company name",
    brand colour #4F46E5, invoice prefix INV, default fees 100000 poisha for study and job,
    manual payment on, all gateways off) and the single licence row with no key and all modules
    off. No company, sample or demo data.
- app/licence.py: verify a signed key with the public key in backend/app/licence_public_key.pem.
- tools/licence/new_keypair.py: makes a new Ed25519 key pair; writes the private key to a path
  given on the command line that must be outside the project folder (refuse otherwise) and the
  public key to backend/app/licence_public_key.pem.
- tools/licence/make_key.py: makes a licence key from --private-key <path> --holder "<company>"
  --modules course,study,job [--expires YYYY-MM-DD]. Prints the key only.
- app/crypto.py: encrypt / decrypt secrets with a key derived from SECRET_KEY.
- app/auth/deps.py: get_current_actor() placeholder that always raises UNAUTHENTICATED until
  B03 replaces it; require_super_admin(); require_module(module) - all as FastAPI dependencies.
- Routers: settings and licence endpoints (below).
Out of scope: sign-in and sessions (B03 - tests override get_current_actor), any catalog,
application or payment endpoint, changing the frontend (B10).

Contract
- GET  /api/settings/public          P   -> PublicSettings (F02) + logo_url, hero_url (or null).
- GET  /api/settings                 SA  -> Settings without secret values; each secret field is
                                            returned as {"saved": true|false} only.
- PUT  /api/settings                 SA  -> same validation as F03. A secret field sent as empty
                                            or missing keeps the stored value; a non-empty value
                                            replaces it.
- PUT  /api/settings/logo, /hero     SA  multipart file; logo max 500 KB, hero max 1.5 MB.
- POST /api/settings/logo/clear, /hero/clear  SA  -> back to default (no picture).
- GET  /api/branding/logo, /hero     P   -> the image bytes with its mime type and a cache header
                                            based on sha256; 404 if none.
- GET  /api/licence                  P   -> { holder, modules, expires_at, active } (never the key).
- GET  /api/licence/full             SA  -> the above + key (masked: first 8 and last 6 characters).
- PUT  /api/licence                  SA  { key } -> verifies and stores; returns the public view.
- Licence key format: "MW1." + base64url(JSON payload) + "." + base64url(Ed25519 signature of
  the payload bytes). Payload: { "holder": str, "modules": ["course","study","job" subset, at
  least one], "issued": "YYYY-MM-DD", "expires": "YYYY-MM-DD" | null }.
- require_module(m): reads the licence row on every request; refuses with 403 MODULE_NOT_LICENSED
  if the module is not in the licence or the licence has expired. Applies to every role,
  including super_admin.

Functional rules
- Validation of PUT /api/settings exactly as F03: name and invoice prefix required, valid
  emails, at least one payment method on, an enabled gateway needs all its secret fields saved
  (either already stored or sent now), brand colour is #RRGGBB, stats are exactly 3 pairs,
  default fees are whole poisha above 0.
- Images: accept only PNG, JPEG and WebP, checked by the file's first bytes, not by its name.
  SVG and anything else is VALIDATION. Clearing an image keeps the old row in branding_images
  (nothing is deleted).
- Licence: a key with a bad signature, a bad format, no modules, or an expiry in the past is
  VALIDATION "This key is not valid." (no detail about why). The holder name shown everywhere
  comes from the key, not from Settings.
- When the licence expires, every module becomes locked; Core keeps working so the admin can
  sign in and apply a new key.
- Every successful PUT/POST writes one audit row: "Settings saved" (with the changed field names,
  never secret values), "Logo changed", "Home picture changed", "Licence changed" (old modules
  -> new modules).
- Secret values never appear in any response, log line or audit row.

Edge cases
- Settings row missing (should never happen): GET /api/settings/public returns 500 INTERNAL and
  logs "settings row missing"; nothing recreates it silently.
- SECRET_KEY changed after secrets were saved: decrypting fails; GET /api/settings shows those
  secrets as {"saved": false, "unreadable": true} and the admin must enter them again.
- The same valid key applied twice: accepted, audit row written, nothing else changes.
- A huge or malformed key string (over 4 KB): VALIDATION without trying to decode it.

Non-functional rules
- One new package: cryptography (pinned) - for Ed25519 and encryption. Nothing else.
- The private key never enters the project folder, git, a log or a test. Tests make their own
  temporary key pair and patch the public key.
- pytest passes, including all B01 tests.

Acceptance criteria
- b09 Migration 0002 applies to movewise_test; there is exactly one settings row and one
  licence row, with all modules off.
- b10 GET /api/settings/public contains no secret field; GET /api/settings shows secrets only as
  {"saved": ...}.
- b11 PUT /api/settings with bKash on and no bKash secrets is VALIDATION; with them it saves; the
  stored ciphertext differs from the plain value; a later PUT with empty bKash secrets keeps them.
- b12 PUT /api/settings without a super admin actor is UNAUTHENTICATED; with an admin actor is
  FORBIDDEN (tests override get_current_actor).
- b13 Uploading a PNG logo works and GET /api/branding/logo returns it; an SVG, a 600 KB logo, and
  a .png file that is really text are VALIDATION.
- b14 A key made by make_key.py for modules study,job is accepted; GET /api/licence shows
  study and job; a test route protected by require_module("course") returns 403
  MODULE_NOT_LICENSED, also for a super admin actor.
- b15 A key with one changed character, a key signed by another private key, and an expired key
  are all VALIDATION "This key is not valid."
- b16 An expired licence stored earlier makes require_module refuse every module.
- b17 Each successful change writes exactly one audit row, and no audit row contains a secret value.
- b18 new_keypair.py refuses an output path inside the project folder.

Assumptions
- Spec B01 is complete and committed.
- Sign-in comes in B03; until then only tests can act as an admin.
