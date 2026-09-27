"""The service's own front page (slice 19): a landing page for clubs, and Find my club.

It's only on the service's own address, ``racetimes.co.uk``. The club
middleware (``races/clubs.py``) decides which address a request is for, and
calls ``home`` for ``/`` there; a club's address never reaches it.

Find my club lists active clubs by name and address, and nothing else about
them: a club's site is public already, so its name and address are too. A
suspended club isn't listed. As on the results home page, the same URL
answers with the whole page, or over HTMX with just the matches.
"""

from django.conf import settings
from django.db.models import Q
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

from .clubs import club_address
from .models import Club

MIN_QUERY = 2
MAX_MATCHES = 10


def home(request):
    query = request.GET.get("club", "").strip()
    searched = "club" in request.GET
    matches = None
    if len(query) >= MIN_QUERY:
        matches = [(club, club_address(request, club)) for club in find_clubs(query)]
    context = {
        "contact_email": settings.SERVICE_CONTACT_EMAIL,
        "service_domain": settings.SERVICE_DOMAIN,
        "query": query,
        "searched": searched,
        "matches": matches,
        "max_matches": MAX_MATCHES,
        "min_query": MIN_QUERY,
    }
    template = "clubs/service_home.html"
    htmx = request.htmx
    if htmx and not htmx.history_restore_request and htmx.target == "club-matches":
        template = "clubs/_club_matches.html"
    response = render(request, template, context)
    # The same URL answers with a fragment or the whole page, so caches must
    # tell them apart.
    patch_vary_headers(response, ["HX-Request", "HX-Target"])
    return response


def find_clubs(query):
    """Active clubs whose name or address contains the query, ignoring case.

    At most MAX_MATCHES + 1, so the page can say there are more.
    """
    return list(
        Club.objects.filter(status=Club.Status.ACTIVE)
        .filter(Q(name__icontains=query) | Q(subdomain__icontains=query))
        .order_by("name")[: MAX_MATCHES + 1]
    )
