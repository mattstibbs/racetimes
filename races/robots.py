"""Keeping every Race Times site out of search engines.

Club results aren't meant to be found by searching the web: people reach a
club's pages through the club. So every response says "don't index this, and
don't follow its links", and /robots.txt asks crawlers not to visit at all.

The ``X-Robots-Tag`` header is what keeps a page out of search results;
robots.txt only asks crawlers to stay away, and a page it blocks can still be
listed, as a bare address, if another site links to it. The header covers
every response, including CSV downloads and error pages, which a ``<meta>``
tag in the page template couldn't.

It's a middleware near the top of the list, before the club lookup, so
/robots.txt answers on every address: the service's, each club's, and one
that names no club or a suspended one.
"""

from django.http import HttpResponse

PATH = "/robots.txt"
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"
NOINDEX = "noindex, nofollow"


class NoIndexMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == PATH:
            response = HttpResponse(ROBOTS_TXT, content_type="text/plain")
        else:
            response = self.get_response(request)
        response["X-Robots-Tag"] = NOINDEX
        return response
