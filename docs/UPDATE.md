# Updating Agency Suite

Update when the site is quiet, for example early in the morning. The whole update takes about
ten minutes; the site is offline from step 3 to step 6.

## 1. Take a backup

```bash
sudo systemctl start movewise-backup.service
sudo ls /var/backups/movewise/ | tail -1          # the newest folder
sudo ls /var/backups/movewise/<newest folder>/     # must contain OK
```

Do not go on unless the newest folder contains `OK`. Note its name: you need it to go back.

Also note the version you have now:

```bash
cd /opt/movewise && sudo -u movewise git rev-parse HEAD
```

## 2. Read the release notes

Check whether the new version needs a new setting in `backend/.env`. Add it before you go on.

## 3. Stop the services

```bash
sudo systemctl stop movewise-web movewise-api movewise-notify
```

## 4. Get the new version

```bash
cd /opt/movewise
sudo -u movewise git pull
```

## 5. Install, migrate and build

```bash
cd /opt/movewise/backend
sudo -u movewise .venv/bin/python -m pip install -r requirements.txt
sudo -u movewise .venv/bin/python -m app.db.migrate

cd /opt/movewise/frontend
sudo -u movewise npm ci
sudo -u movewise npm run build
```

The migration command uses `MIGRATE_DATABASE_URL` (the owner account), prints `Applied ...` for
each new file, or `Nothing to apply.`. If any command fails, stop here and go to "Going back".

## 6. Start the services and check

```bash
sudo cp /opt/movewise/deploy/*.service /opt/movewise/deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start movewise-api movewise-notify movewise-web
systemctl status movewise-api movewise-notify movewise-web --no-pager
curl -s https://example.com/api/health
```

All three services must be `active (running)` and health must show `"database":"ok"`. Sign in as
an admin and open a few pages.

## Going back

If something fails after the migrations ran, go back to the old version **and** the backup from
step 1; the old version may not work with the new database structure.

1. Stop the services: `sudo systemctl stop movewise-web movewise-api movewise-notify`
2. Go back to the old version, using the number you noted in step 1:

   ```bash
   cd /opt/movewise
   sudo -u movewise git checkout <old version number>
   cd backend && sudo -u movewise .venv/bin/python -m pip install -r requirements.txt
   cd ../frontend && sudo -u movewise npm ci && sudo -u movewise npm run build
   ```

3. Restore the backup from step 1 into a new database and switch to it, following
   `deploy/restore.md`.
4. Start the services and check, as in step 6.

If the migrations did not run yet (the failure was in step 4 or in `pip install`), step 3 is not
needed: go back to the old version and start the services.

When you are back on the old version, ask for support before trying the update again.
