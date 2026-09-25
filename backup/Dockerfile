# The nightly off-site backup of production's database (render.yaml,
# racetimes-backup). Runs backup.sh and exits.
#
# PostgreSQL's own image, so pg_dump matches the server's major version (16),
# plus the standard AWS command-line tool, which talks to any S3-compatible
# storage (Amazon S3, Backblaze B2, ...), and gpg to encrypt. No Python and
# nothing from the app: this image only copies the database.
FROM postgres:16-alpine
RUN apk add --no-cache aws-cli gnupg
COPY backup.sh /usr/local/bin/backup.sh
CMD ["/usr/local/bin/backup.sh"]
