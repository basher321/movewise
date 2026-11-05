# B22 - Deploy on the cPanel server (nextglp.com)

Status: draft, waiting for the owner's approval.

## Goal

Run the website (Next.js) and the API (FastAPI) on the owner's cPanel account so the system
can go live on https://nextglp.com. The database is PostgreSQL; its location is decided by the
owner (the host is asked to enable PostgreSQL; hosted PostgreSQL is the fallback).

## What was checked on the server (2026-11-05, read only)

- Account nextglp on s13842.bom1.stableserver.net, CloudLinux + LiteSpeed, SSH on port 22.
- Main domain nextglp.com, no subdomains, public_html is empty (only default files).
- Python 3.12.16 (/opt/alt/python312), Node.js 20/22/24 (/opt/alt/alt-nodejs*), git,
  cloudlinux-selector (creates Python and Node.js apps, the same as "Setup Python/Node.js App").
- Disk limit 10 GB for the account.
- PostgreSQL: the cPanel feature is on, but cPanel answers "This server does not support this
  functionality", /var/run/postgres is missing and 127.0.0.1:5432 refuses connections.
  Outgoing connections to port 5432 (Neon, Supabase) are open.
- No root, no systemd, no Nginx: the files in deploy/ (systemd units, nginx.conf, backup.sh)
  cannot be used here as they are.

## Layout on the server

```
/home/nextglp/movewise/
  backend/      app/, requirements.txt, passenger_wsgi.py, .env (written on the server only)
  frontend/     the built site (Next.js standalone output), app.js
  storage/      uploaded documents (STORAGE_DIR), outside public_html
  releases/     the uploaded release archives
/home/nextglp/public_html   left as it is (cPanel/LiteSpeed serve the apps through it)
```

- Website: Node.js app (Node 22, production) on URL nextglp.com, root /home/nextglp/movewise/frontend.
- API: Python app (Python 3.12) on URL nextglp.com/api, root /home/nextglp/movewise/backend.
  The browser keeps one origin (https://nextglp.com), so session cookies stay first-party, the same
  as with Nginx. API_ORIGIN for the website points to https://nextglp.com.

## Changes in the project

1. backend/passenger_wsgi.py (new): the entry point cPanel's Python app calls. It wraps the
   FastAPI app with a2wsgi so it runs under Passenger/LiteSpeed (WSGI). If the app is mounted at
   /api, the entry point makes sure FastAPI still sees paths that start with /api.
2. backend/requirements.txt: add a2wsgi (one package, pinned to an exact version).
3. frontend/next.config.ts: add output: "standalone" so the built site runs from a small folder
   without the full node_modules (the build is made on the owner's PC; the server has too little
   memory for next build).
4. frontend/app.js (new): the startup file cPanel's Node.js app calls; it starts the standalone
   server on the port Passenger gives it.
5. deploy/cpanel.md (new): the steps below, written for the owner, plus how to update and how to
   roll back to the previous release.
6. deploy/cpanel_cron.txt (new): the cron lines below.

No change to endpoints, pages, the database schema or the API contract.

## Background work without systemd

- Notifications: the API runs with NOTIFY_WORKER=off. A cron job every minute runs
  `python -m app.notify.run --once` (sends what is queued and exits).
  If app.notify.run has no single-run mode, B22 adds a --once flag that runs one pass of the
  existing loop; nothing else in the worker changes.
- Backups: a cron job at 02:30 Asia/Dhaka runs pg_dump (from the PostgreSQL client in the
  Python virtualenv or the host's tool) into /home/nextglp/movewise/backups/, keeps 14 days, and
  archives storage/. If the host offers no pg_dump, the owner's PostgreSQL provider's daily backups
  are used and this is written in deploy/cpanel.md.

## Rate limits and upload size

- Nginx limit_req (sign-in, enquiries) is not available on shared hosting. The app's own
  sign-in limits stay as they are. LiteSpeed passes the real visitor IP to the app (REMOTE_ADDR).
- Upload size: the app already refuses bodies above 3 MB (11 MB for B21 documents).

## Steps (each server step is explained first and run only after the owner says yes)

1. On the PC: run the backend tests and the frontend tests and build; stop if anything fails.
2. On the PC: make a release archive (backend without .env, tests and __pycache__; frontend
   standalone build with static files and public/). Never include any .env file.
3. Upload the archive to /home/nextglp/movewise/releases/ with scp and unpack it.
4. Create the Python app (3.12, /api) and install requirements in its virtualenv.
5. Create the Node.js app (22, /), startup file app.js.
6. Owner writes backend/.env on the server (I give the list of names; I never see the values):
   DATABASE_URL, MIGRATE_DATABASE_URL, SECRET_KEY, SETUP_TOKEN, FRONTEND_ORIGIN=https://nextglp.com,
   PUBLIC_SITE_URL, PUBLIC_API_URL, APP_ENV=production, STORAGE_DIR, NOTIFY_WORKER=off.
7. When PostgreSQL is ready: create the owner and app database users, run backend/app/db/migrate.py
   with MIGRATE_DATABASE_URL, check "Nothing to apply." on a second run.
8. Start both apps, check /api/health, open the site at 390px and desktop, light and dark.
9. Add the cron jobs. Enable SSL (AutoSSL) and force https.
10. First Super Admin signs up with SETUP_TOKEN; owner installs the licence key.

Until step 7 is done the API cannot start (production start-up checks the database), so the site is
switched on for nextglp.com only after the database is ready. Steps 1 to 6 can be done before.

## Out of scope

- Moving the database later (host PostgreSQL <-> hosted PostgreSQL): a separate step with
  backup and restore (deploy/restore.md).
- Email/WhatsApp/payment gateway accounts: configured by the owner in Settings after go-live.
