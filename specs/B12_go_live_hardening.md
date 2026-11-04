Spec B12 - Go-live hardening: limited database user, production mode, setup code, security
headers, separate notification service, backups, deployment and installation guide

Purpose
Make the software safe to run on a public server for a buyer: the running app can no longer
damage the database, production mode switches on every protection, nobody can take over a fresh
installation, messages keep flowing, data is backed up every day, and a buyer can install and
update it by following one guide.

Scope
In scope:
- db/migrations/0010_app_role.sql: if the role movewise_app exists, grant it USAGE on the schema,
  SELECT, INSERT, UPDATE on all tables, USAGE on sequences, DELETE only on sessions, and the same
  defaults for future tables; revoke everything else. If the role does not exist, print a notice
  and do nothing (so test databases still work).
- Config: new MIGRATE_DATABASE_URL (owner account, used only by the migration runner; falls back
  to DATABASE_URL in development), SETUP_TOKEN, NOTIFY_WORKER already exists.
- Production mode (APP_ENV=production) - start-up refuses to run, naming the problem, unless:
  SECRET_KEY has at least 32 characters; PUBLIC_SITE_URL and PUBLIC_API_URL start with https://;
  SETUP_TOKEN is set while no admin exists; and the DATABASE_URL user is NOT a superuser and does
  not own the tables (checked with a query at start-up). In production also: cookies are Secure;
  /docs, /redoc and /openapi.json are switched off; codes are never printed to the console;
  error logs never include request bodies.
- Setup code: GET /api/auth/setup-status -> {needs_setup: true|false}. In production, the first
  admin sign-up must include setup_token equal to SETUP_TOKEN (FORBIDDEN otherwise, compared in
  constant time). After the first admin exists, setup_token is ignored. In development no token is
  needed. Frontend admin sign-up shows a "Setup code" field only while needs_setup is true.
- Separate notification service: python -m app.notify.run runs only the B08 worker; production
  runs the web app with NOTIFY_WORKER=off and this service separately.
- Frontend security headers (next.config): Content-Security-Policy (self, plus Google Fonts if
  used; images self and data:), X-Frame-Options DENY, X-Content-Type-Options nosniff,
  Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy (camera, microphone,
  geolocation off), Strict-Transport-Security in production.
- deploy/ folder for Ubuntu 24.04 LTS:
  - nginx.conf: one domain; / goes to the Next.js server (port 3000), /api/ to uvicorn (port 8000);
    client_max_body_size 3m; request rate limits on /api/auth/ and /api/enquiries; HTTP redirected
    to HTTPS; certificates from Certbot.
  - systemd units: movewise-api (uvicorn, 2 workers, NOTIFY_WORKER=off), movewise-notify,
    movewise-web (next start), each restarting on failure, running as a non-root user "movewise".
  - backup.sh: pg_dump -Fc of movewise plus a tar.gz of the storage folder into
    /var/backups/movewise/<date-time>/, then keeps the last 14 daily and 8 weekly backup folders
    and removes only older folders inside /var/backups/movewise whose names match the date pattern.
    A systemd timer runs it daily at 02:30 Asia/Dhaka.
  - restore.md: how to restore a backup into a new empty database and check it, step by step.
- docs/INSTALL.md (for buyers): server size (2 CPU, 4 GB RAM, 40 GB disk), what to install
  (PostgreSQL 16, Python 3.12, Node 20, Nginx, Certbot), creating the database and the two users,
  backend/.env for production (every variable explained, no real values), migrations, building the
  frontend, starting the services, getting HTTPS, opening the site, entering the setup code,
  applying the licence key, filling Settings, sending test email and WhatsApp, turning off
  Sandbox for gateways, and a final checklist.
- docs/UPDATE.md: take a backup, pull the new version, run migrations, rebuild, restart; how to
  go back using the backup if something fails.
Out of scope: Docker, Windows production servers, load balancers, automatic off-site backup
upload (INSTALL.md tells the buyer to copy backups to another place), monitoring dashboards.

Contract
- No changes to existing endpoints except the setup_token field on admin sign-up and the new
  setup-status endpoint.
- The app connects with DATABASE_URL (movewise_app in production). Only the migration runner uses
  MIGRATE_DATABASE_URL.

Functional rules
- As movewise_app: SELECT, INSERT and UPDATE work; DELETE works only on sessions; DROP, TRUNCATE,
  ALTER and CREATE fail.
- backup.sh stops with an error (and does not remove any old backup) if pg_dump or tar fails.
  It never removes anything outside /var/backups/movewise and never the newest backup.
- Health (B01) stays public but in production shows only {"status","database"} (no migration name).
- Development keeps working exactly as before (no setup code, docs on, console codes on).

Edge cases
- Production start with a superuser DATABASE_URL: refuses with "Database user must not be a
  superuser in production."
- Setup code wrong 10 times from one IP: TOO_MANY_TRIES for 15 minutes (B03 rate limit).
- Disk full during backup: the partial folder is left with a FAILED marker file and an error is
  logged; older backups are not touched.
- Migration 0010 run again: no error.

Non-functional rules
- No new packages.
- Claude Code never runs backup.sh against real folders; it is tested only with a temporary
  folder and a test database.
- pytest, npm test, npm run build, npm run lint and the B11 E2E test pass.

Acceptance criteria
- g01 Production start-up refuses: short SECRET_KEY, http:// URLs, missing SETUP_TOKEN with no
  admin, and a superuser DATABASE_URL - each with a message naming the problem.
- g02 In production, /docs and /openapi.json return 404 and cookies have the Secure flag.
- g03 setup-status is true on an empty database; first admin sign-up without or with a wrong
  setup_token is FORBIDDEN in production and works with the right one; afterwards setup-status
  is false.
- g04 With movewise_app on movewise_test (if the role exists; otherwise SKIPPED with a message):
  DELETE on sessions works; DELETE on payments, DROP and TRUNCATE fail.
- g05 The frontend sends all the security headers listed (checked on the built app).
- g06 backup.sh in a temporary folder against movewise_test makes a .dump and a .tar.gz, keeps 14
  daily and 8 weekly folders when given 30 fake older folders, never removes a folder that does
  not match the date pattern, and removes nothing when pg_dump fails.
- g07 python -m app.notify.run sends queued messages while the web app runs with NOTIFY_WORKER=off.
- g08 docs/INSTALL.md and docs/UPDATE.md exist and contain no real password, key or token.
- All earlier tests and the E2E test pass.

Assumptions
- Specs B01-B11 are complete and committed.
- The role movewise_app was created by hand (Step 0).
