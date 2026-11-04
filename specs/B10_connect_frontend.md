Spec B10 - Connect the frontend to the real backend; remove the mock and all demo data

Purpose
Make the website and admin panel read and write only the real database through the FastAPI
backend. Remove the browser mock store, the sample data and every demo-only feature, so what the
buyer sees is real. Pages keep their look; only src/lib/api/ and the screens whose data changed
are touched.

Scope
In scope:
- frontend/src/lib/api/http/: one module per contract group calling the backend with fetch
  (credentials "include", JSON, and multipart for uploads), turning {"code","message"} errors into
  ApiError with the same code and status. index.ts exports these instead of the mock.
- types.ts updated to match the backend exactly. First read the backend's /openapi.json and list
  every difference from the F02 contract (names, fields, ids vs slugs, money fields, answer keys,
  session shape, payment start answer, document file URLs); then update types and callers.
- Next.js rewrites: /api/* is forwarded to API_ORIGIN (frontend/.env.local, default
  http://localhost:8000), so the browser talks to one origin and cookies work.
- Delete with git rm: src/lib/api/mock/, seed.ts, storage.ts, the mock-only tests (t01-t47
  that test the mock), SHOW_DEMO_CODES and every "Demo only: your code is ..." line, the
  "Demo: simulate a failed payment" tick box, the Licence tab "Demo keys" list, any "Reset demo"
  link and any demo-accounts banner.
- Public pages: Home, About, Contact use Settings and the logo / hero image from
  /api/branding/*. Courses page builds its groups from GET /api/courses (course groups with their
  courses) instead of fixed groups. Course, university and job pages use slugs in their URLs.
  Agent forms take their choices from GET /api/catalog/options.
- Applicant flows: sign up, verify (code arrives by email now), sign in, reset, profile, apply,
  documents (upload as multipart; View opens the file URL), withdraw, invoices, refund request,
  course enrolment.
- Payments: choosing SSLCommerz or bKash sends the browser to the redirect_url from the backend.
  New page /payment/result?id=: asks GET /api/me/payments/{id} every 3 seconds for up to 60 seconds
  and shows Paid (with "View invoice" and a link back), Waiting for verification, Confirming...,
  or Failed / Cancelled (with "Try again"). The payment method list shows only SSLCommerz, bKash and
  Bank transfer / office (Nagad is paid inside SSLCommerz).
- Admin: every tab calls the backend. Settings tab: replace the email API key with SMTP host, port,
  security, username, password; WhatsApp gets phone number id, access token, template name,
  template language; remove the Nagad gateway section; secret fields show "Saved - leave empty to
  keep" from {"saved": true}. Licence tab: paste box for the signed key (MW1....), holder name and
  expiry from the key, masked key, no demo keys. Documents use the file URLs. Notifications show
  the masked text from the backend.
- Loading and error states on every page: "Loading..." while waiting, and a red banner
  "Cannot reach the server. Please try again." on network errors, with a Retry button.
- Empty database: every list shows a friendly empty message (no crash, no fake cards). The Home
  "Popular right now" and testimonials sections are hidden while there is nothing real to show.
Out of scope: course group and "Add course" admin screens, Settings test-email / test-WhatsApp
buttons, end-to-end browser tests (all B11); any backend change (if a backend change seems needed,
stop and tell me).

Contract
- Pages and components still import only from src/lib/api/index.ts.
- No page stores business data in localStorage or sessionStorage. Allowed browser storage: the
  agent form's last inputs (convenience only).
- Money arrives and is sent as poisha integers; pages show ৳ with thousands separators.
- The browser never sees gateway secrets, codes, password hashes or the full licence key.

Functional rules
- A 401 on any admin page shows the admin sign-in; on an applicant page it opens the auth dialog
  for that module. A 403 MODULE_NOT_LICENSED shows the locked card. Other errors show their message.
- After sign-in, sign-out, saving Settings or applying a licence, the Settings and Session
  contexts reload from the backend.
- Uploads show progress text "Uploading..." and the backend's error message on failure.
- The payment result page works after a full page reload and when opened from a gateway redirect.
- Dates and times are shown in Asia/Dhaka.

Edge cases
- Backend down when the site loads: the page shell still renders with the error banner.
- Session expired while filling a form: the form keeps its values; after signing in again the user
  can submit.
- Payment window closed by the user: the result page shows Cancelled or Confirming... and a
  "Try again" button that starts a new payment.
- Image endpoints return 404 (no logo set): the default logo is used; no broken image.

Non-functional rules
- No new packages.
- npm run build, npm run lint and npm test pass (new tests below). Backend pytest still passes.
- No string "demo", "mock", "sample" or "NextGen" remains in frontend/src except in comments
  explaining removal (a test checks this).

Acceptance criteria
- f01 src/lib/api/mock, seed.ts and storage.ts no longer exist; no file imports them.
- f02 Unit tests for the http layer: a {"code":"CONFLICT"} answer becomes ApiError CONFLICT 409;
  a network failure becomes the "Cannot reach the server" error.
- f03 The text check above passes, and no page writes business data to browser storage.
- Manual checks with backend and frontend running against the empty movewise database:
  - Home, Courses, Student Consultancy and Jobs pages load with empty messages, no fake data.
  - First admin sign-up becomes Super Admin; Settings save the company name, logo and SMTP fields;
    the header and footer show them.
  - Paste a signed licence key made with make_key.py; menus show only the licensed modules.
  - Add a university and a vacancy in Catalog; they appear on the website and in the agents.
  - A student signs up and receives the code by email (or sees it in the backend console in
    development), verifies, applies, uploads a PDF, and pays with the bKash sandbox; the result
    page shows Paid and the invoice.
  - A manual payment shows Waiting for verification until finance verifies it.
  - An admin moves the stage; the student sees it after reloading.
  - All screens: no sideways scroll at 390px, correct in dark mode.
- npm run build, npm run lint, npm test and backend pytest pass.

Assumptions
- Backend specs B01-B09 are complete and committed; the backend runs on http://localhost:8000.
- A licence key was made with tools/licence/make_key.py (B02 Step 6).
