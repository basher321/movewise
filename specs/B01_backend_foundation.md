Spec B01 - Backend foundation: project, database connection, migrations, errors, audit, health

Purpose
Create the FastAPI backend skeleton that every later backend spec builds on: configuration from
environment variables, the database connection to movewise, a migration runner, the shared error
format that matches the frontend ApiError, the audit-log writer, and a health check. Nothing
business-specific is built here.

Scope
In scope:
- backend/ project: requirements.txt (pinned versions), app/main.py, app/config.py,
  app/db/engine.py, app/db/migrate.py, app/errors.py, app/audit.py, app/routers/health.py,
  .env.example, README.md with run and test commands for Windows and Linux.
- db/migrations/0001_foundation.sql:
  - extension pgcrypto (for gen_random_uuid);
  - table schema_migrations (filename, checksum, applied_at);
  - function set_updated_at() and the pattern for updated_at triggers;
  - table audit_log (id, at, by_id, by_name, by_role, action, detail, ip) with a trigger that
    raises an error on UPDATE and on DELETE.
- Migration runner: python -m app.db.migrate applies new files to DATABASE_URL;
  python -m app.db.migrate --test applies them to TEST_DATABASE_URL. Files are applied in filename
  order, each in its own transaction, and recorded with a checksum. It refuses to run if an
  already applied file has changed.
- Error handling: ApiError(code, status, message) and handlers so every error, including
  validation errors and unexpected errors, returns {"code","message"} JSON. Unexpected errors
  return 500 INTERNAL with a generic message; details go to the server log only.
- GET /api/health -> {"status":"ok","database":"ok","migrations":"<last applied filename>"}.
- CORS allowing only FRONTEND_ORIGIN, with credentials.
- Request size limit 3 MB.
- pytest setup: a session fixture that runs migrations on the test database, and a per-test
  fixture that opens a transaction and rolls it back at the end.
Out of scope: users, sessions, settings, licence, any business table or endpoint (B02 onward).

Contract
- Error codes and statuses exactly as in specs/F02_api_contract_mock.md, plus INTERNAL 500.
- All endpoints live under /api.
- Config names: DATABASE_URL, TEST_DATABASE_URL, FRONTEND_ORIGIN, SECRET_KEY, read from
  backend/.env. A missing required variable stops start-up with a message that names the
  variable (never its value).
- write_audit(conn, actor, action, detail) inserts one audit row using the caller's connection,
  so it commits or rolls back together with the change it records.

Functional rules
- The application uses DATABASE_URL (database movewise). Tests use only TEST_DATABASE_URL.
- Safety checks:
  - The test fixtures refuse to run unless the test database name ends with "_test".
  - Start-up and tests refuse to run if DATABASE_URL and TEST_DATABASE_URL point to the same database.
- The migration runner prints each file it applies and stops at the first error, leaving earlier
  files applied and the failed one not recorded. It never drops, truncates or deletes anything.
- Health returns "database":"down" with status 503 if the database cannot be reached.
- The database password never appears in logs, error messages or health output.

Edge cases
- Running migrate twice applies nothing the second time.
- Editing 0001 after it was applied makes migrate stop with "Applied migration 0001_foundation.sql
  has changed. Add a new migration instead."
- An UPDATE or DELETE on audit_log raises an error.

Non-functional rules
- Only these packages: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, psycopg[binary],
  argon2-cffi, python-multipart, pytest, httpx. Pinned in requirements.txt.
- Type hints everywhere.
- backend/.env and backend/.venv are in .gitignore. No secret in any tracked file.

Acceptance criteria
- b01 python -m app.db.migrate --test applies 0001 to movewise_test; a second run applies nothing.
- b02 INSERT into audit_log works; UPDATE and DELETE on audit_log fail with an error.
- b03 GET /api/health returns 200 with database ok and the last migration name.
- b04 A request with bad JSON returns 422 {"code":"VALIDATION",...}; an unexpected error returns
  500 {"code":"INTERNAL",...} without any stack trace in the body.
- b05 A request from another origin gets no CORS permission.
- b06 write_audit inside a transaction that is rolled back leaves no audit row.
- b07 Starting without DATABASE_URL stops with a message naming DATABASE_URL.
- b08 Tests refuse to run when TEST_DATABASE_URL points to a database whose name does not end
  in "_test", or to the same database as DATABASE_URL.
- pytest passes; .gitignore contains backend/.env and backend/.venv.

Assumptions
- PostgreSQL is installed; databases movewise and movewise_test exist; backend/.env was created by hand.
- Frontend specs F01-F11 are complete and committed.
