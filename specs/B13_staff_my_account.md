Spec B13 - Staff "My account": change own name, email and password

Purpose
Let every staff member (super admin, admin, finance) change their own display name, sign-in
email and password from the admin panel, without help from anyone. Staff sign in with their
email, so the email is their username. Requested by the owner on 2026-11-02: every user must be
able to change their own name, email and password. Applicants already can (B03: profile page
"Edit details" and "Change password"); this spec adds the same for staff.

Scope
In scope:
- backend/app/routers/admin_me.py (new): the two endpoints below, included in app/main.py.
- backend/app/auth/sessions.py: end_admin_sessions(conn, admin_id, keep=None) gains an optional
  keep (session hash to leave signed in), like end_applicant_sessions.
- backend/tests/test_admin_me.py (new): the acceptance tests below.
- frontend/src/lib/api: updateMyAdminAccount() and changeMyAdminPassword() in http/auth.ts,
  exported from index.ts.
- frontend/src/components/admin/MyAccountDialog.tsx (new) and a "My account" button next to
  "Sign out" in AdminApp.tsx.
- tools/admin/set_password.py (already added 2026-11-02, owner approved): sets a staff password
  from the command line for a person who cannot sign in; writes one audit row
  "admin.password_set". Kept as the recovery path.
Out of scope: no migration (admin_users already has name, email, password_hash and the
case-insensitive unique email index), no email verification, no change of role, sections,
approval or active state (those stay in the Team tab), no applicant changes.

Contract (all under /api; S = any signed-in staff: super_admin, admin or finance)
- PATCH /auth/admin/me  S  { name, email, current_password }  -> AdminUser
  - name: same rules as sign-up. email: same rules as sign-up.
  - current_password is required only when the email changes (may be "" otherwise).
  - Nothing changed -> returns the account and writes no audit row.
- POST /auth/admin/password  S  { current_password, new_password }  -> { ok: true }
  - new_password: same rules as sign-up (6 to 128 characters).
  - Ends every other session of this person; the current session stays signed in.

Errors (always {"code","message"})
- Not signed in, or signed in as an applicant only: UNAUTHENTICATED 401.
- Bad JSON, bad name, bad email, bad new password: VALIDATION 422.
- Wrong current password (email change or password change): FORBIDDEN 403
  "Your current password is not right."
- Email already used by another staff account (case-insensitive): CONFLICT 409
  "This email is already used by another staff account."
- The usual Origin check and rate limits for POST/PATCH apply.

Rules
- Order of checks: signed in -> input valid -> current password -> do the work.
- No module licence check: this is Core.
- Audit, in the same transaction as the change:
  - "admin.account_updated" with detail listing what changed, e.g.
    "name: Old -> New; email: old@x -> new@y". Never any password.
  - "admin.password_changed" with detail = the person's email.
- No response ever contains password_hash, a password or a session token.

Frontend
- AdminApp header: a ghost "My account" button before "Sign out" (same style).
- MyAccountDialog (uses the existing Modal style): two forms in one dialog.
  1. "Name and email": name, email (prefilled), current password (shown only when the email
     was edited). Save -> success toast "Your details were saved." and the header name updates.
  2. "Change password": current password, new password, new password again (must match,
     checked in the browser too). Each password box has the show/hide eye button used on the
     admin sign-in card. Save -> toast "Your password was changed." and the form clears.
- Error messages from the API are shown under the form, as on the sign-in card.
- Works at 390px width and in light and dark mode.

Acceptance criteria
- b109 PATCH /auth/admin/me with a new name returns the new name; one audit row
  admin.account_updated; GET /auth/session shows the new name.
- b110 Changing the email needs the right current password: wrong -> FORBIDDEN, no change, no
  audit row; right -> new email returned, and sign-in works with the new email, not the old.
- b111 Changing the email to another staff account's email (any letter case) -> CONFLICT.
- b112 POST /auth/admin/password with a wrong current password -> FORBIDDEN; with the right one
  -> ok, sign-in works with the new password only, the caller's session still works and the
  person's other session is ended; one audit row admin.password_changed.
- b113 New password of 5 characters -> VALIDATION; bad email -> VALIDATION.
- b114 Without an admin session -> UNAUTHENTICATED for both endpoints; works for super_admin,
  admin and finance alike.
- b115 No audit row and no response contains a password or password_hash.

Assumptions
- B03 and B13's predecessors are complete. pytest runs only against movewise_test.
