#!/bin/sh
# Copy production's database off-site, encrypted (slice 12).
#
#   1. pg_dump in PostgreSQL's compressed "custom" format, which pg_restore
#      reads back;
#   2. encrypted with gpg (AES-256) using BACKUP_PASSPHRASE, so the storage
#      provider never holds readable personal data. Keep the passphrase in a
#      password manager too: without it, the copies can't be read;
#   3. uploaded to BACKUP_BUCKET, named by the date and time.
#
# How long copies are kept is set on the bucket (a lifecycle rule), not here:
# see docs/production.md.
#
# Needs: DATABASE_URL, BACKUP_BUCKET, BACKUP_PASSPHRASE, and for the upload
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION and, for
# storage other than Amazon's, BACKUP_ENDPOINT_URL. With BACKUP_TO_DIR set it
# writes the file there instead of uploading, which is how it's tested.
set -eu

: "${DATABASE_URL:?}" "${BACKUP_PASSPHRASE:?}"
name="racetimes-$(date -u +%Y-%m-%dT%H%MZ).dump.gpg"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

pg_dump --format=custom --no-owner --no-privileges --dbname="$DATABASE_URL" --file="$work/db.dump"
gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo AES256 --output "$work/$name" "$work/db.dump" \
    3<<PASS
$BACKUP_PASSPHRASE
PASS

if [ -n "${BACKUP_TO_DIR:-}" ]; then
    cp "$work/$name" "$BACKUP_TO_DIR/$name"
else
    : "${BACKUP_BUCKET:?}"
    aws s3 cp "$work/$name" "s3://$BACKUP_BUCKET/$name" --only-show-errors \
        ${BACKUP_ENDPOINT_URL:+--endpoint-url "$BACKUP_ENDPOINT_URL"}
fi
# The name and size, never the contents: this goes to Render's log.
echo "Backed up $name ($(wc -c < "$work/$name") bytes)"
