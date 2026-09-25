"""Which club a request is for (slice 11).

Every club has its own address, ``<subdomain>.<SERVICE_DOMAIN>``, and the
middleware here works out the club from the request's host. It attaches it as
``request.club``, which every page then uses (through the ``for_club``
querysets) to show only that club's data.

An address with no club in it, such as the service's own domain, 127.0.0.1 or
the test site on Render, gets the club named by the SINGLE_CLUB setting if
there is one. Otherwise it's the service's own address: only its front page, the
operator's pages and the operator's admin are there.
"""

import sentry_sdk
from django.conf import settings
from django.shortcuts import render

from . import logs
from .models import Club

# Paths that work on the service's own address, with no club: the operator's
# pages (slice 11 part 3), and the Django admin, where the operator logs in and
# manages accounts.
SERVICE_PATHS = ("/admin/", "/operator/")


def subdomain_of(host):
    """The club subdomain in a host name, or None if the host names no club."""
    host = host.split(":")[0].lower().rstrip(".")
    suffix = f".{settings.SERVICE_DOMAIN}"
    if host.endswith(suffix):
        subdomain = host[: -len(suffix)]
        return subdomain or None
    return None


def club_address(request, club, path="/"):
    """A full link to a path on a club's own address, e.g. for an email sent from elsewhere.

    It keeps this request's scheme and any port in its address, as
    ``build_absolute_uri`` does, so it works on demo.localhost:8000 in
    development as well as in production.
    """
    host = f"{club.subdomain}.{settings.SERVICE_DOMAIN}"
    _, colon, port = request.get_host().rpartition(":")
    if colon and port.isdigit():
        host += f":{port}"
    return f"{request.scheme}://{host}{path}"


class ClubMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        subdomain = subdomain_of(request.get_host())
        if subdomain is None and settings.SINGLE_CLUB:
            subdomain = settings.SINGLE_CLUB
        request.club = None
        if subdomain is not None:
            club = Club.objects.filter(subdomain=subdomain).first()
            if club is None:
                return render(request, "clubs/no_club.html", status=404)
            if not club.is_active and not request.user.is_superuser:
                return render(request, "clubs/paused.html", {"paused_club": club}, status=503)
            request.club = club
            # Log lines and error reports say which club (slice 11 part 4).
            logs.club.set(club.subdomain)
            sentry_sdk.set_tag("club", club.subdomain)
        elif not request.path.startswith(SERVICE_PATHS):
            # The service's own address: its front page, and nothing of any club's.
            if request.path == "/":
                return render(request, "clubs/service_home.html", {
                    "contact_email": settings.SERVICE_CONTACT_EMAIL,
                })
            return render(request, "clubs/no_club.html", status=404)
        return self.get_response(request)
