Spec F04 - Applicant accounts: sign up, email verification, sign in, forgot password, My accounts, profile

Purpose
Let students, job seekers and learners create an account for the module they need, prove their
email, sign in, reset a forgotten password, switch between their module accounts, and see and
edit their profile. Screens must look and behave exactly like the Sign in / Sign up dialog,
"My accounts" menu and Profile page in reference/nextgen-learning-v2.html.

Scope
In scope:
- Auth dialog (opened by the header Sign in / Sign up buttons and by any "Sign in" link):
  module buttons (Courses, Student, Jobs - licensed ones only), Sign in / Sign up switch,
  fields Full name (sign-up only), Email, Password, error line, submit button,
  and a "Forgot password?" link under the form.
- Email verification dialog: shown after sign-up, and when an unverified account tries to sign in.
  6-digit code box, Verify button, "Send a new code" button.
- Forgot password dialog: step 1 email; step 2 code + new password.
- Header "My accounts (n)" menu, shown when at least one module account is signed in: one row per
  licensed module with the account name and ID, "Open profile" and "Sign out" - or "Not signed
  in" with Sign in / Sign up links.
- /profile and /profile/[module] page: module tabs (licensed only, a tick on signed-in ones).
  Not signed in: the reference card "<module> account - Each section has its own account and
  ID ... Sign in / Sign up". Signed in: avatar initials, name, account ID, details card (Email,
  Phone, Country, Education / work, Member since), "Edit details" and "Change password".
  Below it, one card "Your applications, courses and invoices appear here in a later step."
- Small contract change to F02 (listed in Contract): one session per module.
Out of scope: applications, enrolments, invoices and payments inside the profile; admin screens;
real email sending; social login.

Contract
- F02 change (update types.ts, the mock and the F02 tests that use sessions):
  getSession() returns { admin: AdminUser | null, applicants: { course?, study?, job?:
  ApplicantAccount } }. applicantSignIn adds or replaces only that module's session.
  signOut(target) where target is "admin" or a Module; signOut("all") clears everything.
- New actions: updateMyProfile(module, {name, phone, country, education}) -> ApplicantAccount
  (A, module licensed); changeMyPassword(module, currentPassword, newPassword) (A).
  HTTP later: PATCH /me/{module}/profile, POST /me/{module}/password.
- Uses existing actions: applicantSignUp, sendEmailCode, verifyEmail, applicantSignIn,
  requestPasswordReset, resetPassword, getSession, signOut, getLicence.
- A React context SessionProvider exposes { session, reload() } to the whole app; the header,
  profile and later pages read sessions only from it.
- The auth dialog can be opened from anywhere with openAuth({ mode: "in" | "up", module?,
  after?: () => void }). "after" runs once the person is signed in and verified (used later
  by Apply and Enrol buttons).

Functional rules
- The module chosen in the dialog defaults to: the module passed to openAuth, else the module of
  the current page (courses -> course, consultancy -> study, jobs -> job), else the first licensed one.
- Sign-up: name required; valid email; password 6+ characters. Success: account created,
  verification dialog opens, a code is "sent" (in the mock it is in the notification log).
- Demo helper: while the mock is in use, the verification and reset dialogs show
  "Demo only: your code is 123456" taken from the notification log. This line must be behind a
  single flag SHOW_DEMO_CODES in src/lib/api/index.ts, so it disappears when the backend is used.
- After a correct code: account verified, signed in to that module, dialog closes, "after" runs.
- Sign-in with an unverified account and correct password: verification dialog opens with a new code.
- Error messages (shown in the error line, never as a browser alert):
  wrong email or password -> "Wrong email or password."
  email already used in this module -> "This email already has a <module> account. Please sign in."
  wrong code -> "Wrong code. Please try again." / expired -> "This code has expired. Please request
  a new one." / too many tries -> "Too many wrong tries. Please request a new code."
- Forgot password: always shows "If this email has an account, we sent a code." (never reveals
  whether the email exists); after a correct code and a 6+ new password: "Password changed.
  Please sign in." and the Sign in dialog opens with the email filled.
- Sign out from the My accounts menu signs out only that module; if the person is on that
  module's profile page it re-renders as "not signed in".
- Edit details: name and phone required; phone must be a valid Bangladeshi mobile
  (01XXXXXXXXX, with optional +88) or an international number starting with +.
- Change password: current password must be right; new password 6+ characters.
- Unlicensed modules: their button is hidden in the dialog, their row is hidden in My accounts,
  their profile tab is hidden, and /profile/<module> shows the locked card from F03.

Edge cases
- Email typed with capitals or spaces is treated as the same email.
- Pressing Sign up twice quickly creates only one account.
- Closing the verification dialog leaves the account unverified; signing in later reopens it.
- A session for an account that no longer exists is removed silently on load.
- The dialog is fully usable with the keyboard; Escape closes it; focus returns to the button
  that opened it.

Non-functional rules
- No new packages. Pages import only from src/lib/api/index.ts.
- Looks exactly like the reference dialog, My accounts menu and Profile page; works at 390px and
  in dark mode.
- Passwords are never stored or logged in plain text, and never shown back.
- npm run build, npm run lint and npm test pass (all earlier tests updated for the session change
  and still passing).

Acceptance criteria
- New tests:
  t21 getSession holds study and job applicant sessions at the same time; signOut("study")
      removes only study.
  t22 updateMyProfile with an invalid phone is VALIDATION; with valid data it saves.
  t23 changeMyPassword with a wrong current password is FORBIDDEN; with the right one the new
      password works for sign-in and the old one does not.
- Manual checks (dev server):
  - Sign up in Student Consultancy -> verification dialog -> enter the demo code -> signed in;
    header shows "My accounts (1)" with the STU- ID.
  - Sign in to Jobs with another account -> "My accounts (2)"; signing out of Jobs leaves Student signed in.
  - Signing in to an unverified account opens the verification dialog.
  - Wrong code 6 times shows the too-many-tries message.
  - Forgot password: the reset flow changes the password; the old password no longer works.
  - Profile shows the details; editing name and phone saves and the header row updates.
  - With the "Student Consultancy only" licence, the dialog shows only the Student button and
    /profile/job shows the locked card.
  - Setting SHOW_DEMO_CODES to false hides the demo code line.
  - All screens: no sideways scroll at 390px, correct in dark mode, Escape closes dialogs.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01, F02 and F03 are complete and committed.
- Each module keeps its own account and ID, as in the reference.
