Spec F03 - Admin sign-in, admin panel frame, Settings, Licence and live branding

Purpose
Let the buyer company set itself up: the first admin signs up and becomes Super Admin, fills in
Settings (name, logo, pictures, text, contact, invoice, payment gateways, email and WhatsApp),
and applies a licence key. The public website then shows that company's branding and only the
modules it bought. Screens must look exactly like the Admin panel, Settings and Licence tabs in
reference/nextgen-learning-v2.html.

Scope
In scope:
- /admin page: admin Sign in / Sign up form (same look as the reference admin login), and after
  sign-in the admin panel frame: title "Admin panel", "Signed in as <name> · <role>", Sign out
  button, and the row of tab buttons.
- Tab row: shows only the tabs this person may open (rules below). In this spec only the
  Settings and Licence tabs have content; every other tab shows the card
  "This section is built in a later step."
- Settings tab (super_admin only): sections Company identity (name, tagline, brand colour,
  website, logo upload, home page picture upload), Website text (home headline, home text,
  3 stats, About headline, About text), Contact details, Invoices (prefix, VAT BIN, footer note),
  Payment gateways (SSLCommerz, bKash, Nagad, Offline payment), Email & WhatsApp.
  "Save settings" button at the top and the bottom.
- Licence tab (super_admin only): module cards (Core always included, then Courses, Student
  Consultancy, Job Processing with Licensed / Not licensed), current key, licensed-to name,
  activated date, "Apply key" form, "Demo keys" list, and the "Test the data-layer lock" card
  with three Call buttons that show the result (200 OK with a count, or 403 MODULE_NOT_LICENSED).
- Live branding on the public site: header logo and alt text, page title, footer name,
  home hero (tagline, headline, text, stats, picture), About headline and text, Contact card,
  brand colour as the accent on Home, Courses and Profile. All read from getPublicSettings().
- Licence on the public site: menu items, home "Three ways we help you" cards, "Popular right
  now" cards, About service cards and the footer "Verify certificate" link of unlicensed modules
  are hidden. Opening a page of an unlicensed module (/courses, /consultancy, /jobs, /verify and
  their sub-pages) shows a locked card: "403 MODULE_NOT_LICENSED - The <module> module is not
  licensed for this installation." with a Go home button.
- Remove frontend/src/config/company.ts; everything now comes from Settings.
Out of scope: applicant sign-in, other admin tabs, payments, catalog editing, team approval
screens, real file storage, real gateway calls.

Contract
- Uses only these actions from src/lib/api: adminSignUp, adminSignIn, signOut, getSession,
  getPublicSettings, getSettings, saveSettings, getLicence, applyLicenceKey,
  listCourses, listUniversities, listVacancies (for the lock test buttons).
- A React context SettingsProvider loads PublicSettings and Licence once at app start and
  exposes { settings, licence, reload() }. Saving Settings or applying a key calls reload()
  so the whole site updates without a page refresh.
- Tab visibility:
  super_admin: Courses, Student Consultancy, Job Processing (licensed ones only), Enquiries,
  Documents, Accounts, Catalog, Fees, Notifications, Team, Audit log, Settings, Licence.
  admin: only their assigned licensed modules, then Enquiries, Documents, Notifications.
  finance: Accounts, Notifications.
  Tab labels and icons are copied from the reference.

Functional rules
- Admin sign-up: name, email, password (6+). The first admin becomes Super Admin and is signed
  in. Later sign-ups show "Your account is waiting for approval by the Super Admin." and are
  not signed in.
- Admin sign-in errors are shown under the form: wrong email or password, waiting for approval.
- Logo upload: image only, max 500 KB. Home picture: image only, max 1.5 MB. Larger files show
  an error and are not saved. Each has a Remove / Use default button.
- If no logo is set, the original logo from F01 is used. If no home picture is set, the
  "tracking" card from the reference is shown in the hero.
- Settings validation: company name and invoice prefix are required; emails must be valid;
  at least one payment method must be on; an enabled gateway must have all its key fields
  (SSLCommerz: store id and password; bKash: app key, app secret, username, password;
  Nagad: merchant id and private key). Errors appear above the bottom Save button.
- Password and key fields are type="password". After saving, the page shows them as
  "Saved - leave empty to keep" instead of showing the stored value again.
- Apply key: an invalid key shows "This key is not valid." Clicking a demo key fills the box.
- If the current admin tab belongs to a module that becomes unlicensed, the panel switches to
  the first allowed tab.
- A non-super_admin who opens Settings or Licence (for example by an old link) sees FORBIDDEN in
  a red banner, not the form.

Edge cases
- Signed-in admin opens /admin after their account is removed: they are signed out and see
  the sign-in form.
- Browser storage full when uploading a picture: show "Picture is too big for browser storage"
  and keep the old picture.
- Licence with zero modules is not possible (the key format needs at least one letter).
- Very long company name: header shows it without breaking the layout at 390px.

Non-functional rules
- No new packages.
- Pages import only from src/lib/api/index.ts.
- Every screen matches the reference look and works at 390px width and in dark mode.
- npm run build, npm run lint and npm test pass (F02 tests must still pass).

Acceptance criteria
- First admin sign-up lands in the admin panel as Super Admin with the Settings and Licence tabs.
- A second sign-up shows the waiting message and cannot sign in.
- Changing the company name, headline and brand colour and saving updates the header alt
  text, page title, footer, home hero and accent colour without reloading the page.
- Uploading a logo shows it in the header; "Use default" brings back the original.
- A 2 MB logo is refused with an error message.
- Turning on bKash without its keys shows the gateway error and does not save.
- Turning off all payment methods shows "Turn on at least one payment method."
- Applying the "Student Consultancy only" demo key: Courses and Job Processing disappear from the
  menu, home cards and admin tabs; /courses and /jobs show the locked card; the lock test shows
  403 for courses and vacancies and 200 for universities.
- Applying the all-modules key brings everything back.
- After saving, secret fields are not shown back in the form or returned by getPublicSettings.
- Every screen in this spec has no sideways scroll at 390px and reads correctly in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01 and F02 are complete and committed.
- reference/nextgen-learning-v2.html is the design source for the admin login, tabs, Settings
  and Licence screens.
