# Restoring a backup

A backup folder in `/var/backups/movewise/` is named by its date and time (Asia/Dhaka), for
example `2026-11-03_023000`. A good backup has three files: `movewise.dump`, `storage.tar.gz`
and `OK`. A folder with a `FAILED` file is incomplete: do not restore from it.

You always restore into a **new, empty** database and a **new** storage folder first, check them,
and only then switch the site over. The running database is never overwritten.

In the commands below, `OWNER` is the owner account of the database (the user in
`MIGRATE_DATABASE_URL`) and `BACKUP` is the folder you restore, for example:

```bash
OWNER=movewise_owner
BACKUP=/var/backups/movewise/2026-11-03_023000
```

## 1. Check the backup

```bash
sudo ls -l "$BACKUP"                       # movewise.dump, storage.tar.gz and OK must be there
sudo -u postgres pg_restore --list "$BACKUP/movewise.dump" | head    # the dump can be read
sudo tar -tzf "$BACKUP/storage.tar.gz" | head                        # the archive can be read
```

## 2. Create a new empty database

```bash
sudo -u postgres createdb --owner="$OWNER" movewise_restore
```

## 3. Restore the database

```bash
sudo -u postgres pg_restore --no-owner --role="$OWNER" --exit-on-error \
  --dbname=movewise_restore "$BACKUP/movewise.dump"
```

`--role` makes every table belong to the owner account again. The privileges of `movewise_app`
are stored in the dump and come back with it.

## 4. Check the restored database

```bash
sudo -u postgres psql -d movewise_restore -c "SELECT filename FROM schema_migrations ORDER BY filename DESC LIMIT 1;"
sudo -u postgres psql -d movewise_restore -c "SELECT count(*) FROM admin_users;"
sudo -u postgres psql -d movewise_restore -c "\dp sessions"
```

- The last migration must be the one you expect for this version.
- The number of admins (and of other important tables) must look right.
- `\dp sessions` must show `movewise_app` with `arwd` (select, insert, update, delete). Other
  tables show `arw`.

Then run the migrations against the restored copy; they must say `Nothing to apply.` for the same
version. Point `MIGRATE_DATABASE_URL` at `movewise_restore` only for this command, for example in
a separate shell, and set it back afterwards.

## 5. Restore the storage folder

```bash
sudo mkdir /opt/movewise/storage-restore
sudo tar -xzf "$BACKUP/storage.tar.gz" -C /opt/movewise/storage-restore --strip-components=1
sudo chown -R movewise:movewise /opt/movewise/storage-restore
sudo chmod -R g+rX /opt/movewise/storage-restore
```

## 6. Switch the site over

1. Stop the services: `sudo systemctl stop movewise-web movewise-api movewise-notify`
2. In `/opt/movewise/backend/.env`, change the database name in `DATABASE_URL` and
   `MIGRATE_DATABASE_URL` to `movewise_restore`, and set `STORAGE_DIR` to
   `/opt/movewise/storage-restore`. Change the backup service's `DB_NAME` and `STORAGE_DIR` too.
3. Start the services: `sudo systemctl start movewise-api movewise-notify movewise-web`
4. Check: `curl -s https://example.com/api/health` shows `"database":"ok"`; sign in as an admin
   and open a few applications and documents.

Keep the old database and storage folder until you are sure the restored copy is right. Remove
them later by hand, only after a fresh backup of the restored copy exists.
