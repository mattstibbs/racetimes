"""The privacy notice and terms (slice 11 part 5).

The same text on every address, the service's and each club's, so the
footer's links never leave the site you're on.
"""

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def privacy(request):
    return render(
        request, "legal/privacy.html", {"contact_email": settings.SERVICE_CONTACT_EMAIL}
    )


@require_GET
def terms(request):
    return render(
        request, "legal/terms.html", {"contact_email": settings.SERVICE_CONTACT_EMAIL}
    )
