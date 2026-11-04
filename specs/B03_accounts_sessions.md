Spec B03 - Accounts, sessions, email codes, password reset, roles and team

Purpose
Let admins and applicants sign up and sign in securely, prove their email, reset a forgotten
password, keep separate sessions per module, and let the Super Admin control the team. This
replaces the placeholder get_current_actor from B02, so every later endpoint knows who is calling
and what they may do. Endpoints follow the auth, team and profile parts of
specs/F02_api_contract_mock.md, F04 and F10.

Scope
In scope:
- db/migrations/0003_accounts.sql:
  - admin_users: id, name, email, password_hash, role CHECK ('super_admin','admin','finance'),
    approved, active, sections text[] (each value 'course','study','job'), last_login_at,
    created_at, updated_at. Unique on lower(email).
  - applicant_accounts: id, public_id (CRS-/STU-/JOB- + 6 characters, unique), module CHECK,
    name, email, phone, country, education, password_hash, email_verified, created_at,
    updated_at. Unique on (module, lower(email)).
  - sessions: id (sha256 of the token, never the token itself), kind ('admin','applicant'),
    admin_id or applicant_id (exactly one set, CHECK), module (for applicants), created_at,
    last_seen_at, expires_at, ip, user_agent. DELETE is allowed on this table (sign-out).
  - email_codes: id, purpose ('verify','reset'), applicant_id, code_hash, expires_at, tries,
    used_at. Codes are marked used, never deleted.
  - signin_failures: email, kind, ip, at (for rate limiting). Old rows are ignored, not deleted.
  - notifications (outbox for now; B08 adds real sending): the Notification fields from F02
    (channel, to, to_name, module, event, subject, body, status 'queued'|'sent'|'failed', tries).
- app/auth/: password hashing (argon2), session create / read / end, cookies, rate limit,
  code create / check, and the real get_current_actor plus these dependencies:
  require_admin(), require_super_admin(), require_finance_or_super(),
  require_section(module) (super_admin, or admin with that module in sections - never finance),
  require_applicant(module).
- Endpoints below. APP_ENV setting ('development' | 'production'), default 'development'.
Out of scope: real email or WhatsApp sending (B08), catalog, applications, payments, the frontend
switch (B10), social login, two-factor sign-in.

Contract (all under /api; P public, A applicant of that module, S admin, SA super admin)
- POST /auth/admin/signup {name,email,password}                     P
- POST /auth/admin/signin {email,password}                          P
- POST /auth/applicant/{module}/signup {name,email,password}        P   module licensed
- POST /auth/applicant/{module}/signin {email,password}             P   module licensed
- POST /auth/applicant/{module}/send-code {email}                   P   module licensed
- POST /auth/applicant/{module}/verify {email,code}                 P   module licensed
- POST /auth/applicant/{module}/reset-request {email}               P   module licensed
- POST /auth/applicant/{module}/reset {email,code,new_password}     P   module licensed
- POST /auth/signout {target: "admin" | "course" | "study" | "job" | "all"}   P
- GET  /auth/session -> {admin: AdminUser|null, applicants: {course?,study?,job?}}   P
- PATCH /me/{module}/profile {name,phone,country,education}         A
- POST /me/{module}/password {current_password,new_password}        A
- GET  /admin/team                                                  SA
- POST /admin/team/{id}/approve | /deactivate | /reactivate         SA
- PUT  /admin/team/{id}/role {role}  |  PUT /admin/team/{id}/sections {sections}   SA
- Responses never contain password_hash, code_hash, tokens or session ids.
- Cookies: mw_admin, and mw_app_course / mw_app_study / mw_app_job. Each holds a random
  32-byte token. HttpOnly, SameSite=Lax, Path=/api, Secure when APP_ENV is production.
- Every request that changes data (not GET) must have an Origin header equal to FRONTEND_ORIGIN,
  otherwise 403 FORBIDDEN (protection against cross-site requests).

Functional rules
- Passwords: 6 to 128 characters; hashed with argon2; never logged or returned.
- Admin sign-up: the very first admin becomes super_admin, approved and active, and is signed in.
  This must be safe when two sign-ups arrive at the same moment (only one can be first). Later
  sign-ups are admin, not approved, not signed in.
- Admin sign-in fails with "Wrong email or password." for a wrong email or password, and with
  FORBIDDEN "Your account is waiting for approval." or "This account is deactivated." when true.
- Applicant sign-up: CONFLICT if the email already has an account in that module; otherwise
  creates an unverified account and a verify code. Not signed in until verified.
- Applicant sign-in with the right password but unverified email: FORBIDDEN with message
  "EMAIL_NOT_VERIFIED" and a fresh code is sent.
- Codes: 6 digits from a secure random source, stored only as a hash, valid 15 minutes, 5 wrong
  tries then TOO_MANY_TRIES and the code is marked used. A new code makes older ones unusable.
  In development the code is also printed to the server console. A code never appears in any
  API response.
- reset-request always answers 200 "If this email has an account, we sent a code." whether or
  not the account exists.
- A successful reset or password change ends every other session of that account.
- Rate limit: more than 10 failed sign-ins for the same email and kind in 15 minutes, or more
  than 30 from the same IP, gives TOO_MANY_TRIES until the window passes.
- Sessions: admin sessions end after 8 hours without activity and after 7 days at most;
  applicant sessions after 30 days. An expired session counts as signed out. A session of a
  deactivated admin or an unapproved admin is refused.
- Team rules exactly as F10: approving gives role admin with all licensed sections; changing
  role to finance clears sections; the last active super_admin can never be deactivated or
  demoted (CONFLICT); an admin cannot change their own role or deactivate themselves (FORBIDDEN);
  deactivating ends all that admin's sessions. Nobody is ever deleted.
- Applicant ids: STU- for study, JOB- for job, CRS- for course; 6 characters from
  A-Z and 2-9 without O, I, 0, 1; retried if taken.
- Email matching ignores case and spaces at both ends.
- Audit rows: admin signed up, admin signed in, applicant signed up, email verified, password
  reset, password changed, profile updated, every team change. Failed sign-ins are counted in
  signin_failures, not audited.

Edge cases
- Sign-up for an unlicensed module: MODULE_NOT_LICENSED.
- Session cookie for an account that no longer matches (e.g. admin deactivated): treated as
  signed out and the cookie is cleared.
- Sign-out with no session: 200, nothing happens.
- Two quick sign-ups with the same email and module: one succeeds, the other gets CONFLICT.

Non-functional rules
- No new packages (argon2-cffi is already in B01).
- Constant-time comparison for tokens and codes.
- pytest passes, including all B01 and B02 tests (they now use real sessions where they used
  the override).

Acceptance criteria
- b19 First admin sign-up returns super_admin and sets mw_admin; second returns pending and no cookie;
  the pending admin cannot sign in until approved.
- b20 Two parallel first sign-ups produce exactly one super_admin.
- b21 Applicant signs up in study, cannot sign in before verifying, verifies with the code from
  the outbox, then signs in; GET /auth/session shows the STU- account.
- b22 The same email signs up in job too; both sessions exist; signout {target:"study"} leaves job.
- b23 Six wrong codes give TOO_MANY_TRIES; an expired code gives EXPIRED; no response contains a code.
- b24 reset-request gives the same answer for a real and an unknown email; reset with the right
  code changes the password and ends the other sessions.
- b25 Eleven failed sign-ins for one email give TOO_MANY_TRIES.
- b26 A POST with a wrong Origin header is FORBIDDEN.
- b27 require_section("job") refuses an admin with sections ["study"] and any finance user;
  a super_admin passes (if job is licensed).
- b28 Team: deactivating or demoting the last super_admin is CONFLICT; self role change is
  FORBIDDEN; a deactivated admin's session stops working at once; there is no delete endpoint.
- b29 The sessions table stores only token hashes; no response contains password_hash or tokens.
- b30 An admin session idle for more than 8 hours is refused.
- b31 Every successful change in this spec writes exactly one audit row.

Assumptions
- Specs B01 and B02 are complete and committed.
- Real email sending comes in B08; until then codes wait in the notifications outbox
  (and print to the console in development).

Decisions (2026-11-01, approved by the owner) - replaces the applicant email-code rules above
- Applicants sign up with full name, username (3-30 letters, numbers, . or _, one per module,
  case-insensitive) and password, plus optional email and mobile. They are signed in at once.
  No email code is sent; email is not verified.
- Applicants sign in with their username (or, for accounts made before usernames, their email)
  and password. The send-code, verify, reset-request and reset endpoints are removed.
- A forgotten password is reset by staff of that section (super admin or admin with the
  section, never finance): POST /admin/accounts/{id}/reset-password gives a temporary password
  once, ends the person's sessions and writes an audit row.
- Staff (super admin, admin, finance) keep signing in with email and password.
- Migration 0011 allows applicant email to be empty. The owner allowed its two DROP statements
  (DROP NOT NULL on applicant_accounts.email and replacing the "email not empty" check).
