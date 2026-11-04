# Agency Suite backend

FastAPI + PostgreSQL. Every command below runs from the `backend/` folder.

## Before you start

- PostgreSQL with two databases: `movewise` (main) and `movewise_test` (tests only).
- Copy `.env.example` to `.env` and fill in every value. `.env` is never committed.
  - `DATABASE_URL` points to `movewise`.
  - `TEST_DATABASE_URL` points to `movewise_test`. Tests refuse to run unless its database name
    ends with `_test` and it is not the same database as `DATABASE_URL`.
- Optional settings (add them to `.env` by hand when you need them):
  - `STORAGE_DIR` - folder for uploaded documents (default `backend/storage`).
  - `PUBLIC_API_URL` - the address of this backend that SSLCommerz and bKash call back
    (default `http://localhost:8000`). Must be a public https address in production.
  - `PUBLIC_SITE_URL` - the website the payer returns to (default `FRONTEND_ORIGIN`).
  - `NOTIFY_WORKER=off` - stops the email / WhatsApp sending worker (tests always run with it off).
- Email (SMTP), WhatsApp, payment gateways, company details and fees are set by the super admin
  in the admin panel (Settings tab), not in `.env`. Secrets are stored encrypted.

## Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# Apply migrations to movewise
.venv\Scripts\python -m app.db.migrate

# Apply migrations to movewise_test
.venv\Scripts\python -m app.db.migrate --test

# Run the API on http://localhost:8000
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Run the tests (only movewise_test is used; every test is rolled back)
.venv\Scripts\python -m pytest
```

## Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python -m app.db.migrate
.venv/bin/python -m app.db.migrate --test
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
.venv/bin/python -m pytest
```

## Uploaded documents

- Files go to `STORAGE_DIR` (in `.env`); when it is empty, `backend/storage` is used. That folder
  is in `.gitignore` and is never served directly: files are only sent by the API after the
  owner or the right staff member is checked.
- **Back up the database AND the storage folder together.** A database without its files, or
  files without the database, cannot be restored on their own.

## Migrations

- One numbered file per change in `../db/migrations` (`0001_xxx.sql`, `0002_xxx.sql`, ...),
  applied in filename order, each in its own transaction, recorded in `schema_migrations`
  with a checksum.
- Never edit an applied file. If you do, migrate stops with
  "Applied migration <file> has changed. Add a new migration instead."

## Endpoints

- `GET /api/health` -> `{"status":"ok","database":"ok","migrations":"<last file>"}`,
  or 503 with `"database":"down"`.
