Spec B15 - "Forgot password?" for everyone: email reset link, and Super Admin resets staff

Purpose
Every sign-in (applicants in each module, staff on /admin, the Super Admin on /super-admin) gets
a working "Forgot password?". Owner decision 2026-11-02 ("Both"):
- When email sending is set up (Settings, B08), a reset link is emailed; it works once, for
  30 minutes.
- When email is not set up, the page says who can help. A Super Admin can give any other staff
  member (Admin, Finance or another Super Admin) a new temporary password from the Team tab.
  Applicants keep the B03 staff reset (temporary password) as well.
This changes the B03 decision of 2026-11-01 ("no email codes, reset only by staff") for the
case where email is set up; nothing is sent when it is not.

Scope
In scope:
- db/migrations/0012_password_resets.sql: table password_resets.
- backend/app/routers/password_reset.py (new) with the three public endpoints below.
- backend/app/routers/team.py: POST /admin/team/{id}/reset-password.
- backend/app/notify/outbox.py: the reset link is masked in the Notifications list (like codes).
- backend/tests/test_password_reset.py (new).
- frontend/src/lib/api: getPasswordOptions(), forgotPassword(), resetPassword(),
  resetStaffPassword().
- frontend: ForgotPasswordDialog for /admin and /super-admin (AdminAuth), the email form in
  the applicant "Forgot password?" step (AuthDialog), the /reset-password page, and a
  "Reset password" button per staff row in the Team tab.
Out of scope: SMS/WhatsApp reset, security questions, changing B13 My account.

Database (0012_password_resets.sql)
- password_resets: id uuid PK, created_at, updated_at (trigger), kind text CHECK IN
  ('admin','course','study','job'), admin_id uuid NULL FK admin_users ON DELETE RESTRICT,
  applicant_id uuid NULL FK applicant_accounts ON DELETE RESTRICT, token_hash bytea NOT NULL
  UNIQUE (sha256 of the token; the token itself is never stored), expires_at timestamptz NOT
  NULL, used_at timestamptz NULL, ip text NULL.
  CHECK exactly one of admin_id / applicant_id, and kind = 'admin' exactly when admin_id is set.
  Indexes on admin_id, applicant_id, created_at. No DELETE anywhere; old rows are ignored.

Contract (all under /api; P = public, SA = super admin)
- GET  /auth/password/options  P  -> { email: boolean }   (email sending is set up)
- POST /auth/password/forgot   P  { kind, login } -> { ok: true }
  - kind "admin": login is the staff email (any role, active and approved).
    kind course/study/job: module licensed first (MODULE_NOT_LICENSED); login is the username
    or email of that module's account, and the account must have an email.
  - Email not set up -> CONFLICT 409 "Email is not set up, so a reset link cannot be sent."
  - Otherwise always { ok: true }, whether or not an account matched (never tells).
  - When an account matched: a new token (32 random bytes, URL-safe), a password_resets row
    (expires in 30 minutes), one email (event "password_reset_link") with the link
    <site>/reset-password?token=<token>, and one audit row "password.reset_requested".
  - Limits: at most 3 links per account in 15 minutes (more are silently not sent); 20
    requests that made a link from one IP in 15 minutes -> TOO_MANY_TRIES.
- POST /auth/password/reset  P  { token, new_password } -> { ok: true, kind }
  - Unknown token -> VALIDATION "This reset link is not valid."; used or older than 30 minutes
    -> EXPIRED 410 "This reset link has expired. Please ask for a new one."
  - Bad new password -> VALIDATION (6 to 128 characters).
  - Sets the password, marks this and every other unused link of the account used, ends every
    session of the account, writes one audit row "password.reset_by_link".
- POST /admin/team/{id}/reset-password  SA  -> { temporary_password }
  - Any staff account except yourself (FORBIDDEN "Use My account to change your own
    password."); unknown id -> NOT_FOUND.
  - A 10-character temporary password (same alphabet as the applicant reset), shown once,
    stored only as a hash; ends that person's sessions; audit "team.password_reset".

Rules
- The Notifications list masks the token in the link of "password_reset_link" messages, so no
  staff member can read or use another person's link. The email itself has the real link.
- No response or audit row contains a token or a password.

Frontend
- /admin and /super-admin sign-in cards: a "Forgot password?" link under the Sign in button.
  It opens a dialog:
  - email set up: "Enter your email" -> "If this email has an account, we have sent a link to
    reset the password. It works for 30 minutes."
  - email not set up: staff page "Ask a Super Admin to reset your password in the Team tab.";
    Super Admin page "Ask another Super Admin to reset it in the Team tab, or the person who
    runs the server (tools/admin/set_password.py)."
- Applicant "Forgot password?" step: when email is set up, a form "Your username or email" ->
  same answer as above; the office contact stays below as the other way.
- /reset-password?token=...: new password and again (both with the eye button) -> "Your
  password was changed." and a link to the right sign-in (admin -> /admin, else the module
  page). Expired / invalid links show the API message and how to ask for a new one.
- Team tab: a "Reset password" link on every staff row except your own; confirm, then a
  dialog shows the temporary password once (like the applicant reset).
- Works at 390px and in light and dark mode.

Acceptance criteria
- b124 With email not set up, options says email false and forgot is CONFLICT; nothing queued.
- b125 With email set up, forgot for a real staff email queues one email with a link, writes one
  reset row and one audit row; an unknown email answers the same and writes nothing.
- b126 The link resets the password once: sign-in works with the new password only, the old
  sessions are ended, the same link then gives EXPIRED; a 31-minute-old link gives EXPIRED; a
  wrong token gives VALIDATION.
- b127 Applicant forgot works by username or email in a licensed module; an account without
  email gets nothing; an unlicensed module is MODULE_NOT_LICENSED.
- b128 A fourth request for one account within 15 minutes queues nothing more; 21 link-making
  requests from one IP give TOO_MANY_TRIES.
- b129 The Notifications list shows the reset email with the token masked.
- b130 Team reset: super admin resets an admin and another super admin (temporary password
  works, their sessions end, audit row); own account -> FORBIDDEN; an admin caller -> FORBIDDEN.
- b131 No response or audit detail contains a token, password or password_hash.

Assumptions
- B08 email sending works when Settings has SMTP host, sender email and SMTP password.
