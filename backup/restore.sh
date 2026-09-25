#!/bin/sh
# Restore one of backup.sh's copies into an EMPTY database (slice 12).
#
#   BACKUP_PASSPHRASE=... backup/restore.sh <file.dump.gpg> <target DATABASE_URL>
#
# Download the file from the bucket first (the storage's web page, or
# `aws s3 cp`). Never point this at production's live database: restore into a
# new one, check it (docs/production.md), then switch the site over.
set -eu

file="${1:?the .dump.gpg file}"
target="${2:?the target database's URL}"
: "${BACKUP_PASSPHRASE:?}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 \
    --decrypt --output "$work/db.dump" "$file" \
    3<<PASS
$BACKUP_PASSPHRASE
PASS
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$target" "$work/db.dump"
echo "Restored $(basename "$file")"
