"""Which club a request is for (slice 11).

Every club has its own address, ``<subdomain>.<SERVICE_DOMAIN>``, and the
middleware here works out the club from the request's host. It attaches it as
``request.club``, which every page then uses (through the ``for_club``
querysets) to show only that club's data.

An address with no club in it, such as the service's own domain, 127.0.0.1 or
the test site on Render, gets the club named by the SINGLE_CLUB setting if
there is one. Otherwise it's the service's own address: only its front page and
the operator's admin are there.
"""

from django.conf import settings
from django.shortcuts import render

from .models import Club

# Paths that work on the service's own address, with no club.
SERVICE_PATHS = ("/admin/",)


def subdomain_of(host):
    """The club subdomain in a host name, or None if the host names no club."""
    host = host.split(":")[0].lower().rstrip(".")
    suffix = f".{settings.SERVICE_DOMAIN}"
    if host.endswith(suffix):
        subdomain = host[: -len(suffix)]
        return subdomain or None
    return None


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
        elif not request.path.startswith(SERVICE_PATHS):
            # The service's own address. Part 3 of slice 11 gives it a proper
            # front page; until then it says what the service is.
            if request.path == "/":
                return render(request, "clubs/service_home.html")
            return render(request, "clubs/no_club.html", status=404)
        return self.get_response(request)
