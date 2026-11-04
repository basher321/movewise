Spec F11 - Catalog and Fees tabs

Purpose
Let the Super Admin keep the offer up to date without a developer: add and edit universities,
vacancies (with employer verification) and courses, hide or close them, and set the application
fee for each university and vacancy. Applicants always see the exact fee before paying, and fees
already paid never change. Screens must look and behave like the Catalog and Fees tabs of the
Admin panel in reference/nextgen-learning-v2.html.

Scope
In scope:
- "🗂 Catalog" tab (super_admin only), with a switch for the licensed parts:
  Universities / Employers & vacancies / Courses.
  - Universities table: University (+ country, city), Needs (GPA, IELTS, levels), Tuition,
    Deadline, Website (Published / Hidden), Edit. "+ Add university".
    Form: name, country, city, levels, fields, tuition per year (USD), minimum GPA, minimum IELTS,
    intakes, deadline (text), scholarships, work rights, other conditions, official application
    link, admissions email, "Hide from website".
  - Vacancies table: Job (+ employer, country), Needs (experience, education, English), Salary,
    Seats (applied / total), Website (Live / Closed / Employer not verified), Edit. "+ Add vacancy".
    Form: job title, employer, country, occupation, minimum experience, minimum education, minimum
    English, salary (USD/month), seats, apply by (date), contract, benefits, other conditions,
    employer licence / registration no., employer HR email, "Employer verified",
    "Vacancy closed".
  - Courses table: Course (+ category), Duration (+ level), Price, Website, Edit.
    Form: price (৳), duration, level, short description, "Hide from website".
    (New courses and course groups are out of scope.)
- "Fees" tab (super_admin only), as in the reference: text "Set the application fee for each job
  and university...", a Jobs card and a Universities card (licensed modules only) with Country,
  Name (+ city or employer and occupation), Default, and a Fee (৳) box per row; "Save fees" and
  "Reset all to default".
Out of scope: deleting any catalog item, adding new courses or course categories, bulk import,
images for universities or employers, employer logins.

Contract
- Uses: listUniversities, getUniversity, saveUniversity, listVacancies, getVacancy, saveVacancy,
  listCourses, getCourse, saveCourse, getSession. Admin calls return every item, including hidden,
  closed and unverified ones.
- F02 change (update types, mock and tests):
  - Settings gets default_fee_poisha { study, job } (seed values from the reference FEES).
  - University and Vacancy app_fee_poisha becomes fee_override_poisha (number or null). The fee
    an applicant pays = override if set, else the module default. Add effectiveFee(module, item).
  - New action saveFees({ study: {id: poisha | null}, job: {id: poisha | null} }) (SA) and
    resetFees(module | "all") (SA). HTTP later: PUT /admin/fees, POST /admin/fees/reset.
  - There is no delete function for universities, vacancies or courses. They are hidden or closed.
- Every save writes an audit entry naming the item and the fields that changed.

Functional rules
- Only super_admin can open these tabs or call these actions (FORBIDDEN otherwise).
- Only licensed modules appear in the Catalog switch and the Fees cards; calls for an unlicensed
  module are MODULE_NOT_LICENSED.
- University form: name, country, city, at least one level, at least one field, tuition, GPA
  (0-4), IELTS (0-9, steps of 0.5), intakes and deadline are required. The application link, if
  given, must start with https://. The admissions email, if given, must be valid. The id is made
  from the name and is never changed later.
- Vacancy form: title, employer, country, occupation, experience (0 or more), salary (above 0),
  contract are required. Seats, if given, must be 1 or more. "Apply by" must not be in the past
  when the vacancy is open. Changing "Employer verified" writes its own audit entry
  ("Employer verified" / "Employer unverified").
- Course form: price must be a whole number of taka above 0; saved as poisha.
- Public visibility (already in F02 and F06-F07): hidden universities, hidden courses, closed
  vacancies and unverified employers disappear from the website and the agents at once; people
  who already applied or enrolled still see their own item.
- Fees: every fee box must be a whole number above 0 ("Every fee must be above 0." and focus the
  first wrong box). A value equal to the default is saved as no override. "Fees saved." in green
  after saving. "Reset all to default" asks for confirmation and clears all overrides.
- Fee changes never touch existing payments: an application that already has a payment (any
  status) keeps its amount. An unpaid application with no payment yet uses the new fee.

Edge cases
- Two universities with the same name: the second gets a short suffix on its id; both work.
- Seats reached: the vacancy stays open (staff decide), and the Seats column shows e.g. "6 / 6".
- An item edited while an applicant has its page open: they see the new data on the next load.
- Very long names: tables wrap text and never scroll the page sideways at 390px (the table area
  itself may scroll sideways).

Non-functional rules
- No new packages. Pages import only from src/lib/api/index.ts.
- Looks exactly like the reference Catalog and Fees tabs; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass.

Acceptance criteria
- t43 effectiveFee uses the override when set and the module default when null.
- t44 After saveFees, an application that already has a payment keeps its old amount; a new
  application pays the new fee.
- t45 There is no delete function for universities, vacancies or courses; saving as an admin
  (role "admin") is FORBIDDEN.
- t46 saveUniversity with GPA 5, IELTS 6.3 or a link starting with http:// is VALIDATION.
- t47 Changing employer_verified writes the "Employer verified" / "Employer unverified" audit entry.
- Manual checks:
  - Add a university for Canada, Bachelor, Computer Science & AI -> it shows in the study agent
    results; tick "Hide from website" -> it disappears from the agent and /consultancy.
  - Add a vacancy with "Employer verified" off -> Website shows "Employer not verified" and it is
    not on /jobs; tick it -> it appears.
  - Close a vacancy someone applied to -> it leaves /jobs, but the applicant still sees their
    application page.
  - Change a course price -> the course page and Enrol dialog show the new price.
  - Fees tab: set a university fee to ৳1,500 -> its item page and fee dialog show ৳1,500; an
    application paid earlier still shows its old amount on the invoice.
  - "Reset all to default" brings back the default fees.
  - With the "Student Consultancy only" licence, the Catalog switch and Fees tab show only universities.
  - All screens: no sideways page scroll at 390px, correct in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01-F10 are complete and committed.
- Field lists, layouts and default fees are copied from the reference (aCat, UF, JF, showFees, FEES).
