# Agency Suite project conventions

These rules apply to every file you write in this project.

Product
- One installation per buyer company. There is no multi-company (tenant) logic and no tenant_id anywhere.
- The product has four modules: Core (always on), Training, Student Consultancy, Job Processing.
  Code names: core, course, study, job.
- The design reference is reference/nextgen-learning-v2.html. Every screen must look and behave like it.
  Never redesign. If something is missing in the reference, follow its existing style.

Folders
- frontend/  Next.js (App Router) + TypeScript (strict). Built first.
- backend/   FastAPI (Python). Built second.
- db/        PostgreSQL migrations and seed. Built third. The seed holds only real starting data
             (for example the first super admin and default settings), never fake or sample data.
- specs/     One spec file per step. Never edit a spec unless I ask.

Frontend rules
- No UI library (no Tailwind, no MUI, no Bootstrap). Plain CSS only, using the tokens from the reference
  (--bg, --surface, --text, --muted, --line, --navy, --on-navy, --a).
- Fonts: Sora for headings, DM Sans for text, loaded with next/font.
- Each page section keeps its own accent colour from the reference:
  home/courses/profile #4F46E5, consultancy #0EA5A4, jobs #D97706, about/admin #7C3AED, contact #0891B2.
- Pages never read or write data directly. All data goes through frontend/src/lib/api/.
- Module licence is checked in two places: the UI hides locked modules, and the api layer refuses them
  with error code MODULE_NOT_LICENSED (status 403).
- Company name, logo, colours and contact details always come from Settings, never hardcoded in pages.
- Every page must work at 390px width with no horizontal scroll, and in light and dark mode.

Backend rules
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 Core (no ORM models), psycopg 3, pytest.
- Every endpoint matches the contract in specs/F02_api_contract_mock.md and later F-specs:
  same names, same fields, same error codes. If a spec and the contract disagree, stop and ask.
- Errors are always JSON: {"code": "...", "message": "..."} with the HTTP status from the contract.
- Order of checks in every endpoint: signed in -> module licensed -> role and section -> input
  valid -> do the work. Never trust the frontend for any of these.
- Secrets come only from environment variables in backend/.env. Never read, print or log that
  file or its values, never hardcode them, never return them in a response.
  backend/.env.example lists the variable names with empty values.
- Every change of data writes one audit row in the same database transaction.
- No fake or sample data in migrations or in application code. Test data lives only inside tests.

Database rules
- PostgreSQL. Main database: movewise (DATABASE_URL). Test database: movewise_test
  (TEST_DATABASE_URL). Both use the postgres user for now.
- One numbered SQL file per change under db/migrations (0001_xxx.sql, ...), applied in filename
  order by backend/app/db/migrate.py and recorded in schema_migrations.
  Never edit or delete an applied migration; add a new one.
- Every table: primary key id uuid DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL
  DEFAULT now(); tables that change also have updated_at refreshed by a trigger.
- Money is BIGINT in poisha, column names end in _poisha, CHECK (... >= 0).
- Fixed value sets are TEXT columns with a CHECK list. Declare and index every foreign key;
  ON DELETE RESTRICT.
- Ledger, audit log, invoices and payments are append-only: triggers block DELETE on all four
  and block UPDATE on ledger_entries and audit_log.
- Never write DROP, TRUNCATE, or DELETE without WHERE in any migration, script or code.
- Tests run only against movewise_test. Each test runs inside a transaction that is rolled back.
  Tests never drop, truncate or delete anything.
- Never connect to the movewise database from tests, and never run tests against it.

Money and data
- Money is a whole number of poisha (1 taka = 100 poisha). Never use float for money.
  Field names for money end in _poisha. Show money to users as ৳ with thousands separators.
- Dates are stored in ISO format; times are shown in Asia/Dhaka.
- Fixed sets of values (status, stage, role) are string unions in TypeScript and CHECK lists in SQL.

Roles
- super_admin, admin, finance, applicant. An admin works only in the sections assigned to them.
  Finance sees Accounts and Notifications only.

Files
- Plain ASCII or UTF-8 text with no byte-order mark.
- Do only what the current spec says. Do not add features, pages or packages outside its Scope.

Safety rules (never break these, even if asked in a prompt)
- Never delete, drop or truncate a database, schema or table. Never run DROP, TRUNCATE or DELETE
  without a WHERE clause. If a task seems to need this, stop and ask me.
- Never delete folders or many files at once. Never run rm -rf, rmdir /s or Remove-Item -Recurse.
- Never run git push --force, git reset --hard or git clean -f.
- Never read, print or change .env files, passwords, API keys or payment gateway keys.
- Work only on the local development database. Never connect to a production server or database.
- Before any command that changes data, files outside this project, or installed software,
  explain what it will do and wait for my yes.
- A database change is made only by adding a new numbered migration file. Never edit or delete
  an old migration.
- Exception: deployment work on the live cPanel server nextglp@s13842.bom1.stableserver.net is
  allowed over SSH. I still explain each command that changes something and wait for a yes.