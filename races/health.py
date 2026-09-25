"""The health check at /health/ (slice 11 part 4).

The host and an external uptime check poll it to see whether the site is up.
It's a middleware, first in the list, so it answers before anything else runs:
- no club lookup, so it works on every address;
- no HTTPS redirect, because hosts poll over plain HTTP;
- no ALLOWED_HOSTS check, because hosts poll with an internal address.

It asks the database one trivial question. "ok" means the site and its
database are working; "error" (503) means they aren't. It gives no other
detail, writes nothing and sets no cookie.
"""

import logging

from django.db import connection
from django.http import HttpResponse

logger = logging.getLogger(__name__)

PATH = "/health/"


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info != PATH:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            logger.exception("Health check: the database didn't answer")
            return _plain("error", status=503)
        return _plain("ok")


def _plain(text, status=200):
    response = HttpResponse(text, content_type="text/plain; charset=utf-8", status=status)
    response["Cache-Control"] = "no-store"
    return response
