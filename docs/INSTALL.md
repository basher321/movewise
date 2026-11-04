# Installing Agency Suite

This guide installs the software on one Ubuntu 24.04 LTS server for one company and one domain.
Follow the steps in order. Commands are typed in the server's terminal as a user that can use
`sudo`. Wherever you see `<...>`, put in your own value; never copy a value from this guide.

## 1. The server

- 2 CPU, 4 GB RAM, 40 GB disk, Ubuntu 24.04 LTS.
- A domain name (below: `example.com`) whose DNS A record points to the server's IP address.
- Ports 80 and 443 open to the internet; port 22 for your own SSH access. Nothing else.

```bash
sudo apt update && sudo apt upgrade -y
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

## 2. Install the programs

PostgreSQL 16, Python 3.12, Nginx and Certbot come with Ubuntu 24.04:

```bash
sudo apt install -y postgresql-16 python3.12 python3.12-venv nginx certbot python3-certbot-nginx git
```

Node 20 (LTS) from NodeSource:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x -o nodesource_setup.sh
less nodesource_setup.sh          # read it before running it
sudo bash nodesource_setup.sh
sudo apt install -y nodejs
node --version                    # must start with v20
```

## 3. The system user and the program folder

The services run as a normal user called `movewise`, never as root.

```bash
sudo adduser --system --group --home /opt/movewise movewise
sudo -u movewise git clone <your repository address> /opt/movewise
sudo -u movewise mkdir -p /opt/movewise/storage
sudo chmod 750 /opt/movewise/storage
```

After this, `/opt/movewise/` holds `backend/`, `frontend/`, `db/`, `deploy/` and `docs/`.

## 4. The database and its two users

The database has two users:

| User | Used by | Can do |
|---|---|---|
| `movewise_owner` | the migration runner only (`MIGRATE_DATABASE_URL`) | owns the tables, changes the structure |
| `movewise_app` | the running website (`DATABASE_URL`) | read, add and change rows; delete only sign-in sessions |

Neither is a superuser. The website refuses to start in production if its user is a superuser or
owns the tables.

```bash
sudo -u postgres createuser --no-superuser --no-createdb --no-createrole --pwprompt movewise_owner
sudo -u postgres createuser --no-superuser --no-createdb --no-createrole --pwprompt movewise_app
sudo -u postgres createdb --owner=movewise_owner movewise
sudo -u postgres psql -d movewise -c "REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT ALL ON SCHEMA public TO movewise_owner;"
```

`--pwprompt` asks for each password. Use two different long random passwords, for example from
`openssl rand -base64 24`, and keep them in a password manager. They go only into `backend/.env`.

The `movewise_app` user must exist **before** the first migration: migration `0010_app_role.sql`
gives it exactly the rights in the table above. If you ever create it later, see "If something
goes wrong" at the end.

## 5. backend/.env for production

Create the file as the `movewise` user and make it readable only by that user:

```bash
sudo -u movewise cp /opt/movewise/backend/.env.example /opt/movewise/backend/.env
sudo chmod 600 /opt/movewise/backend/.env
sudo -u movewise nano /opt/movewise/backend/.env
```

Fill in every line. Each value is your own; this guide never shows a real one.

| Variable | What to put in |
|---|---|
| `APP_ENV` | `production`. Switches on every protection: Secure cookies, no API docs, no codes in the console, and the start-up checks below. |
| `DATABASE_URL` | `postgresql+psycopg://movewise_app:<app password>@localhost:5432/movewise` |
| `MIGRATE_DATABASE_URL` | `postgresql+psycopg://movewise_owner:<owner password>@localhost:5432/movewise`. Used only by the migration command. Required in production. |
| `TEST_DATABASE_URL` | Leave empty on the server. Tests are never run here. |
| `FRONTEND_ORIGIN` | `https://example.com` (your domain). Requests that change data from any other site are refused. |
| `SECRET_KEY` | At least 32 random characters: `openssl rand -base64 48`. Never share it; changing it later signs everybody out. |
| `SETUP_TOKEN` | A one-time setup code you choose: `openssl rand -hex 16`. Needed once, to create the first admin (step 10). |
| `PUBLIC_SITE_URL` | `https://example.com`. Where payers return after paying. Must start with `https://`. |
| `PUBLIC_API_URL` | `https://example.com`. The address the payment gateways call back. Must start with `https://`. |
| `STORAGE_DIR` | `/opt/movewise/storage`. Uploaded documents are kept here. |
| `NOTIFY_WORKER` | Leave empty. The services below set it: the website runs with `off` and the separate notification service sends the messages. |

Email (SMTP), WhatsApp and payment gateway keys are **not** put in this file. You enter them in
the admin panel under Settings (step 12); they are stored encrypted.

In production the API refuses to start, and names the problem, if: `SECRET_KEY` is shorter than
32 characters; `PUBLIC_SITE_URL` or `PUBLIC_API_URL` does not start with `https://`;
`SETUP_TOKEN` is empty while no admin exists; or the `DATABASE_URL` user is a superuser or owns
the tables. See the messages with `sudo journalctl -u movewise-api -n 50`.

## 6. Backend: install and migrate

```bash
cd /opt/movewise/backend
sudo -u movewise python3.12 -m venv .venv
sudo -u movewise .venv/bin/python -m pip install -r requirements.txt
sudo -u movewise .venv/bin/python -m app.db.migrate
```

The last command prints `Applied ...` for each file. Every later migration must also run this
way, so that new tables belong to `movewise_owner` and `movewise_app` gets its rights on them
automatically.

## 7. Frontend: build

```bash
cd /opt/movewise/frontend
sudo -u movewise npm ci
sudo -u movewise npm run build
```

## 8. HTTPS

Get the certificate first, while Nginx still serves its default page on port 80:

```bash
sudo mkdir -p /var/www/certbot
sudo certbot certonly --nginx -d example.com
```

Give an email address for expiry warnings when Certbot asks. Then install the real site:

```bash
sudo cp /opt/movewise/deploy/nginx.conf /etc/nginx/sites-available/movewise
sudo sed -i 's/example\.com/<your domain>/g' /etc/nginx/sites-available/movewise
sudo ln -s /etc/nginx/sites-available/movewise /etc/nginx/sites-enabled/movewise
sudo unlink /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot renew --dry-run      # automatic renewal works
```

## 9. Start the services

```bash
sudo cp /opt/movewise/deploy/movewise-api.service /opt/movewise/deploy/movewise-notify.service \
        /opt/movewise/deploy/movewise-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now movewise-api movewise-notify movewise-web
systemctl status movewise-api movewise-notify movewise-web --no-pager
```

All three must show `active (running)`. Each restarts by itself if it stops.

## 10. Open the site and create the first admin

1. Open `https://example.com/admin`.
2. Choose **Sign up**. Because no admin exists yet, the form shows a **Setup code** field.
3. Enter your name, email, a strong password and the `SETUP_TOKEN` value from `backend/.env`.
4. This first account becomes the **Super Admin**. From now on the setup code is not needed or
   asked for; other admins sign up and wait for your approval.

Ten wrong setup codes from one address block further tries for 15 minutes.

## 11. Apply the licence key

In the admin panel open **Licence**, paste the licence key you received (it starts with `MW1.`)
and apply it. The holder name, the expiry date and the licensed modules appear. Only licensed
modules are shown on the website.

## 12. Fill in Settings

In **Settings** enter the company name, logo, colours, address, phone and email; the email
(SMTP) server; WhatsApp; and the payment methods. Save. Secret fields then show
"Saved - leave empty to keep".

- Press **Send test email** and **Send test WhatsApp**. Each must show "Sent ✓". If not, the
  message says what is wrong.
- **Payment gateways:** while you test, keep **Sandbox** on and make one small test payment.
  When it works, turn **Sandbox off** for SSLCommerz and bKash, enter the live keys from your
  gateway contract, save, and make one small real payment.

## 13. Backups

Backups run every day at 02:30 Bangladesh time and keep the last 14 days and 8 weeks.

```bash
sudo mkdir -p /var/backups/movewise
sudo chown postgres:postgres /var/backups/movewise
sudo chmod 700 /var/backups/movewise
sudo usermod -aG movewise postgres            # lets the backup read the storage folder
sudo cp /opt/movewise/deploy/movewise-backup.service /opt/movewise/deploy/movewise-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now movewise-backup.timer
sudo systemctl start movewise-backup.service   # one backup now, to check
sudo ls /var/backups/movewise/
```

The new folder must contain `movewise.dump`, `storage.tar.gz` and `OK`. A folder with `FAILED`
means that backup did not finish; see `sudo journalctl -u movewise-backup -n 50`.

**Copy the backups to another place.** A backup on the same server is lost with the server. At
least once a week, copy the newest folder to another computer or storage service, for example:

```bash
rsync -a <you>@<server>:/var/backups/movewise/ <a folder on another computer>/
```

How to restore a backup: `deploy/restore.md`.

## 14. Final checklist

- [ ] `https://example.com` opens with a padlock; `http://` goes to `https://`.
- [ ] `https://example.com/api/health` shows `{"status":"ok","database":"ok"}`.
- [ ] On the server, `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/docs` prints `404`
      (no API docs in production).
- [ ] You signed in as Super Admin; the setup code field no longer appears.
- [ ] The licence shows your company and the right modules.
- [ ] Company name and logo appear in the header and footer.
- [ ] Test email and test WhatsApp arrived.
- [ ] Gateways are out of Sandbox and one real payment worked.
- [ ] `systemctl list-timers movewise-backup.timer` shows the next run; one backup folder has `OK`.
- [ ] Backups are copied to another place.
- [ ] `backend/.env` is readable only by `movewise` (`ls -l` shows `-rw-------`).
- [ ] You keep the passwords, `SECRET_KEY` and `SETUP_TOKEN` in a password manager, not on paper
      or in email.

## If something goes wrong

- A service does not start: `sudo journalctl -u movewise-api -n 50` (or `movewise-web`,
  `movewise-notify`). In production the API names the setting that is wrong.
- `movewise_app` was created after the first migration: it has no rights yet. Grant them the same
  way as migration 0010:

  ```bash
  sudo -u postgres psql -d movewise -c "GRANT USAGE ON SCHEMA public TO movewise_app; \
    GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO movewise_app; \
    GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO movewise_app; \
    GRANT DELETE ON sessions TO movewise_app; \
    ALTER DEFAULT PRIVILEGES FOR ROLE movewise_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO movewise_app; \
    ALTER DEFAULT PRIVILEGES FOR ROLE movewise_owner IN SCHEMA public GRANT USAGE ON SEQUENCES TO movewise_app;"
  ```
- Updating to a new version: `docs/UPDATE.md`.
