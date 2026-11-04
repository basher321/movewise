#!/usr/bin/env bash
# Daily backup of the movewise database and storage folder (B12), run by movewise-backup.timer.
#
# Writes BACKUP_ROOT/<YYYY-MM-DD_HHMMSS>/ (Asia/Dhaka time) with movewise.dump (pg_dump -Fc) and
# storage.tar.gz, then an OK marker. If anything fails (pg_dump, tar, a full disk), the new folder
# gets a FAILED marker, the error is logged and the script stops before rotation, so no older
# backup is touched.
#
# Rotation (only after a successful backup) keeps the newest backup of each of the last 14 days,
# the newest of each of the last 8 ISO weeks, and always the newest backup. It looks only at
# folders directly inside BACKUP_ROOT that have the date-time name and an OK marker; it never
# follows a symlink and never touches anything else.
#
# Settings (environment): BACKUP_ROOT (default /var/backups/movewise), DB_NAME (default movewise),
# STORAGE_DIR (default /opt/movewise/storage), PG_DUMP (default pg_dump). The database connection
# comes from the usual PG* variables or the local postgres sign-in. BACKUP_ROOT may be another
# folder only with BACKUP_ALLOW_TEST_ROOT=1 (the tests use a temporary folder).

set -Eeuo pipefail
umask 077

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/movewise}"
DB_NAME="${DB_NAME:-movewise}"
STORAGE_DIR="${STORAGE_DIR:-/opt/movewise/storage}"
PG_DUMP="${PG_DUMP:-pg_dump}"
REAL_ROOT="/var/backups/movewise"
KEEP_DAILY=14
KEEP_WEEKLY=8
NAME_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}$'

log() { echo "backup: $*" >&2; }
fail() { log "ERROR: $*"; exit 1; }

# ---------- where to write ----------

case "$BACKUP_ROOT" in
  /*) ;;
  *) fail "BACKUP_ROOT must be an absolute path." ;;
esac
if [ -L "$BACKUP_ROOT" ] || [ ! -d "$BACKUP_ROOT" ]; then
  fail "BACKUP_ROOT must be an existing folder, not a symlink."
fi
root="$(cd "$BACKUP_ROOT" && pwd -P)"
[ "$root" != "/" ] || fail "BACKUP_ROOT must not be /."
if [ "$root" != "$REAL_ROOT" ] && [ "${BACKUP_ALLOW_TEST_ROOT:-}" != "1" ]; then
  fail "BACKUP_ROOT must be $REAL_ROOT."
fi
[ -d "$STORAGE_DIR" ] || fail "STORAGE_DIR does not exist."

# ---------- backup ----------

stamp="$(TZ=Asia/Dhaka date +%Y-%m-%d_%H%M%S)"
dest="$root/$stamp"
[ ! -e "$dest" ] || fail "$dest already exists."
mkdir "$dest"

on_error() {
  touch "$dest/FAILED" 2>/dev/null || true
  log "ERROR: backup failed; $dest is marked FAILED. Older backups were not touched."
}
trap on_error ERR

"$PG_DUMP" -Fc --file "$dest/movewise.dump" "$DB_NAME"
tar -czf "$dest/storage.tar.gz" -C "$(dirname "$STORAGE_DIR")" "$(basename "$STORAGE_DIR")"
touch "$dest/OK"
trap - ERR
log "wrote $dest"

# ---------- rotation ----------

names=()
while IFS= read -r name; do
  if [[ "$name" =~ $NAME_RE ]] && [ -d "$root/$name" ] && [ ! -L "$root/$name" ] && [ -f "$root/$name/OK" ]; then
    names+=("$name")
  fi
done < <(find "$root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)

declare -A keep=() days=() weeks=()
newest="${names[0]}"
keep["$newest"]=1
for name in "${names[@]}"; do
  day="${name%%_*}"
  week="$(date -d "$day" +%G-W%V)"
  # names are newest first, so the first one seen for a day or week is its newest backup.
  if [ -z "${days[$day]:-}" ] && [ "${#days[@]}" -lt "$KEEP_DAILY" ]; then
    days["$day"]=1
    keep["$name"]=1
  fi
  if [ -z "${weeks[$week]:-}" ] && [ "${#weeks[@]}" -lt "$KEEP_WEEKLY" ]; then
    weeks["$week"]=1
    keep["$name"]=1
  fi
done

for name in "${names[@]}"; do
  [ -z "${keep[$name]:-}" ] || continue
  [ "$name" != "$newest" ] || continue
  rm -r -- "${root:?}/$name"
  log "removed old backup $name"
done
