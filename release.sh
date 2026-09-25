#!/usr/bin/env bash
# The steps that change the database, run once per deploy before the new
# version takes traffic. Production runs this as Render's pre-deploy command:
# if it fails, the deploy stops and the version already live keeps running.
# The free test site has no pre-deploy step, so build.sh runs it instead.
set -o errexit

# Database changes ship with the code, so they apply on the deploy that brings
# them.
python manage.py migrate --no-input
# The table for the cache, which holds failed-login counts (races/throttle.py).
# Does nothing if it is already there.
python manage.py createcachetable
# The operator's first login, from two dashboard settings; never changes an
# existing account.
python manage.py ensure_superuser
