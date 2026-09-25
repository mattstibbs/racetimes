#!/usr/bin/env bash
# The free test site's build (see render.yaml). Any failing step stops the
# deploy, and the site already live keeps running.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
# The free plan has no pre-deploy step, so the database steps run here, during
# the build. Production runs release.sh as its pre-deploy command instead.
./release.sh
