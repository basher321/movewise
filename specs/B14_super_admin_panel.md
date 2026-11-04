Spec B14 - Separate Super Admin sign-in, sign-up and panel

Purpose
The Super Admin gets their own page, /super-admin, with their own sign-in and (first-time
setup only) sign-up. Staff sign-up on /admin never makes a Super Admin any more. Requested by
the owner on 2026-11-02: "first user becomes Super Admin" is not a good rule.
This replaces, for the Super Admin only, the B03 rule "the very first admin becomes
super_admin" and moves the B12 setup code from the first admin sign-up to the Super Admin
sign-up. Staff (admin, finance) and applicants are otherwise unchanged.

Scope
In scope:
- backend/app/auth/accounts.py: create_admin() no longer decides "first"; it takes the role.
  New create_super_admin(): under the same advisory lock, refuses with CONFLICT when an
  active super_admin already exists, otherwise inserts an approved super_admin.
- backend/app/routers/auth.py:
  - POST /auth/admin/signup always makes role admin, approved false, not signed in. It no
    longer takes or checks a setup code.
  - New POST /auth/super/signup and POST /auth/super/signin (below).
  - GET /auth/setup-status gains super_admin_exists.
- backend/app/production.py: SETUP_TOKEN is required while no active super_admin exists
  (was: while no admin exists).
- backend tests: tests that made the first super admin through /auth/admin/signup now use
  /auth/super/signup; the setup-code tests move to the Super Admin sign-up; new
  tests/test_super_admin.py for the acceptance criteria below.
- frontend/src/lib/api: superAdminSignUp(), superAdminSignIn(); SetupStatus gains
  super_admin_exists.
- frontend/src/app/super-admin/page.tsx and components/admin/SuperAdminApp.tsx +
  SuperAdminAuth.tsx (new). The panel after sign-in is the existing admin panel (all tabs).
- frontend/src/components/admin/AdminAuth.tsx: the sign-up text no longer says the first
  account becomes Super Admin; the setup code box is removed; a line "Super Admin? Use the
  Super Admin page." links to /super-admin.
- The page title "Super Admin" for /super-admin.
Out of scope: no migration, no change to roles, sections, Team tab, applicant accounts,
My account (B13), or sessions (the Super Admin uses the same mw_admin session cookie).

Contract (all under /api; P = public)
- GET  /auth/setup-status  P  -> { needs_setup, super_admin_exists }
  - super_admin_exists: an active super_admin account exists.
  - needs_setup: production and no active super_admin (the Super Admin sign-up needs
    SETUP_TOKEN). Always false in development.
- POST /auth/super/signup  P  { name, email, password, setup_token }  -> AdminUser
  - Allowed only while no active super_admin exists; otherwise CONFLICT 409
    "A Super Admin already exists. Please sign in."
  - Production while needs_setup: the setup code is checked exactly as B12 did for the first
    admin sign-up (wrong code -> FORBIDDEN "The setup code is wrong.", saved as a failed
    sign-in; ten wrong codes from one IP -> TOO_MANY_TRIES).
  - Makes role super_admin, approved, active, and signs the person in (mw_admin cookie).
  - Email already used by any staff account -> CONFLICT (as the admin sign-up).
  - Audit "admin.signed_up" with detail "<email> (super_admin)".
- POST /auth/super/signin  P  { email, password }  -> AdminUser
  - Same checks, rate limits and messages as /auth/admin/signin, and in addition: an account
    that is not super_admin gets UNAUTHENTICATED "Wrong email or password." (it does not say
    the account exists), recorded as a failed sign-in.
  - Audit "admin.signed_in".
- POST /auth/admin/signup  P  { name, email, password }  -> AdminUser (always pending admin).
  A setup_token field, if sent, is ignored.
- /auth/admin/signin is unchanged (a Super Admin may still sign in there).

Frontend
- /super-admin: while loading nothing; signed in as super_admin -> the admin panel with all
  tabs (same as /admin); otherwise the "Super Admin sign in" card in the admin card style:
  - Sign in tab: email, password (with the eye button), Sign in.
  - Sign up tab: shown only while no Super Admin exists: name, email, password, and the
    setup code box when needs_setup. Text: "First-time setup: create the Super Admin account."
  - When a staff (non super admin) session is open, the card says "You are signed in as
    staff. Sign in with the Super Admin account to open the Super Admin panel."
- /admin sign-up text: "Staff accounts need approval from the Super Admin before they can
  sign in." No setup code box.
- Works at 390px width and in light and dark mode. Accent colour as /admin (#7C3AED).

Acceptance criteria
- b116 With no super admin, POST /auth/super/signup makes an approved super_admin, signs in,
  writes one audit row; a second call is CONFLICT and makes nothing.
- b117 POST /auth/admin/signup with no admins at all makes a pending admin (never
  super_admin) and sets no cookie.
- b118 /auth/super/signin: super admin with right password -> 200 and session; admin or
  finance with right password -> UNAUTHENTICATED; wrong password -> UNAUTHENTICATED.
- b119 setup-status: super_admin_exists false then true after the Super Admin sign-up;
  needs_setup false in development.
- b120 Production: Super Admin sign-up needs the setup code (wrong/missing -> FORBIDDEN and
  saved as failure; ten wrong -> TOO_MANY_TRIES); staff sign-up needs no code.
- b121 check_production refuses an empty SETUP_TOKEN while no active super_admin exists, even
  if other (admin) accounts exist.
- b122 Two parallel Super Admin sign-ups make exactly one super_admin.
- All earlier tests still pass (updated only where they relied on "first admin is super admin").

Assumptions
- The installation already has its Super Admin (nazmul.basher15@gmail.com); nothing changes
  for that account.

Addendum (2026-11-02, owner): several Super Admins
- The Team tab role select offers Admin, Finance Officer and Super Admin (this replaces the
  F10 rule "Super Admin shown as a badge"). Choosing Super Admin asks for confirmation.
- Other Super Admins can be changed back to Admin or Finance. The first Super Admin and the
  signed-in person stay locked on this screen, and the backend still refuses to deactivate or
  demote the last active Super Admin (CONFLICT), as before. No backend change.
- Every extra Super Admin signs in on /super-admin and has the full panel.
