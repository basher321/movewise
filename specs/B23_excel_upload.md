# B23 Excel upload of listings

Owner request (2026-11-09): upload an Excel file instead of typing every listing by hand, for
Student Consultancy, Job Processing and Immigration, with a template file, from the Super Admin
and Admin panels. Owner chose: listings only (no client records), and an item that already exists
is skipped, never changed.

## Scope

- Three upload types, one template each:

| Type (`kind`) | Module | Saved in |
|---|---|---|
| university | study | universities |
| vacancy | job | vacancies (remote = false) |
| visa | visa | visa_programs |

- Flow: choose the type -> download the template -> choose the filled file -> see the preview ->
  confirm -> see the result. Nothing is saved until the person confirms.
- Files: .xlsx only (the file's first bytes must be a zip), 1 byte to 5 MB, at most 1000 data rows.
- Out of scope: courses, remote jobs, client or application records, updating existing items, CSV,
  and the old .xls format. No new table and no migration.

## Who may upload

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.

- super_admin: every licensed type.
- admin: only the types of the sections assigned to them (`require_section(module)`).
- finance and applicants: never (FORBIDDEN 403). Unlicensed module: MODULE_NOT_LICENSED 403.
- Two columns are honoured for the super admin only, because admins cannot set them anywhere else:
  "Employer verified" (vacancy) and "Self Apply fee" (university). In an admin's upload they are
  ignored (employer not verified, Self Apply not offered) and the preview shows a warning on the row.

## Template

Generated on request with openpyxl. Sheet 1 holds only the header row, with dropdowns where a value
comes from a fixed list; required columns are marked with "*". Sheet 2, "Instructions", explains
each column. The templates contain no sample rows. Columns are found by header text, so their order
does not matter. Unknown columns are ignored. A missing required column rejects the whole file.

university: University name*, Country*, City, Levels*, Fields*, Tuition per year USD*, Minimum GPA*,
Minimum IELTS*, Intakes, Deadline, Scholarships, Work rights, Other conditions, Application link,
Self Apply fee taka, Admissions email, Hide from website.

vacancy: Job title*, Employer*, Country*, Occupation*, Minimum experience years*, Minimum education*,
Minimum English*, Salary USD per month*, Seats, Apply by, Contract, Benefits, Other conditions,
Employer licence, Employer HR email, Employer verified, Vacancy closed.

visa: Programme name*, Country*, Visa type*, Processing time, Validity, Government fee, Description,
Eligibility*, Required documents*, Other conditions, Official link, Embassy email, Hide from website.

Reading cells: Levels and Fields are comma separated. Eligibility and Required documents are
separated by a new line or ";". Yes/No columns accept Yes, No or empty (empty = No). Dates accept an
Excel date or YYYY-MM-DD. Education, English and Visa type use the same labels as the admin forms.
The taka fee is converted to whole poisha without floats. Formulas are read as their saved values.

## Row rules

Every row goes through the same validation as the admin forms (the existing `UniversityIn`,
`VacancyIn`, `VisaProgramIn` models and their value functions), so a row accepted here is exactly
what the form would accept. Fully empty rows are ignored.

Row status:
- `new`: valid, will be added.
- `skipped`: already in the system, or repeated earlier in the same file (never changed).
- `error`: not valid; the reason is shown and the row is not added. Other rows can still be added.

An item counts as the same when these match, ignoring upper/lower case and extra spaces:
university: name + country. vacancy: title + employer + country (on-site vacancies only).
visa: title + country + visa type.

## API

| Method | Path | Result |
|---|---|---|
| GET | /api/admin/import/{kind}/template | the .xlsx template (attachment, no-store) |
| POST | /api/admin/import/{kind}/preview | multipart `file` -> ImportPreview; saves nothing |
| POST | /api/admin/import/{kind}/commit | multipart `file` -> ImportResult |

ImportPreview: kind, total, new_count, skipped_count, error_count, rows[].
Row: row_number, label, status, message (reason, or "" when none), warnings[].
ImportResult: the same counts and rows, where new_count is the number actually added.

Commit reads and checks the file again on the server and trusts nothing from the preview. It runs
in one transaction under the catalog lock, and adding no rows is not an error.

Unknown `kind`: NOT_FOUND 404. Errors (VALIDATION 422): "Please choose a file.",
"Only .xlsx Excel files.", "The file must be from 1 byte to 5 MB.", "This file could not be read.",
"This file has no rows to import.", "At most 1000 rows in one file.",
"This does not look like the right template. Missing column: <name>."

Safety: read-only workbook mode, and a file that expands past 50 MB is refused ("This file could
not be read."). The uploaded file is never stored.

Request body limit: 3 MB everywhere, except POST to the preview and commit paths: 6 MB
("The file must be 5 MB or smaller."). deploy/nginx.conf allows 6m on those paths only.

Audit: one row per item added, in the same transaction, using the existing actions
catalog.university_saved, catalog.vacancy_saved, catalog.visa_program_saved with the detail
"<name>: added by Excel upload". A vacancy added as verified also writes "Employer verified".

## Frontend

- api layer: downloadImportTemplate, previewImport, commitImport (lib/api/http/imports.ts). Module
  licence and section are checked there too.
- New "Excel upload" tab in the shared admin panel (so on both /admin and /super-admin), shown when
  the person has at least one permitted type; in lib/admin/tabs. Plain CSS in the reference's style,
  admin accent colour, works at 390px and in light and dark mode.
- The preview shows the counts and a table of rows with Row, Item, Status and Message. The confirm
  button reads "Add n items" and is disabled when n is 0.

## Dependency

backend/requirements.txt gains openpyxl (pure Python). It must also be installed on the live server
when this is deployed.

## Tests

backend/tests/test_excel_import.py, on movewise_test only, with workbooks built inside the tests:
template columns for each type; preview saves nothing; commit adds valid rows and writes audit rows;
skipped and same-file repeats leave existing rows unchanged; error rows are reported and not added;
wrong file type, too large, too many rows and missing column; check order (not signed in, unlicensed,
finance, admin of another section); admin's owner-only columns are ignored with a warning.
Frontend: tab visibility per role and section.
