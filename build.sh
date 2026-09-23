#!/usr/bin/env bash
# Render runs this on every deploy (see render.yaml), before starting the site.
# Any failing step stops the deploy, and the site already live keeps running.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
# Database changes ship with the code, so they apply on the deploy that brings
# them.
python manage.py migrate --no-input
python manage.py ensure_superuser
