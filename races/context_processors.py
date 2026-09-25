from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import BoatRequest, EntryRequest, Request
from .roles import is_committee, waiting_for_approval


def roles(request):
    """Lets templates show links and notices by role, without repeating the rules."""
    return {
        "is_committee": is_committee(request.user),
        # A function, which templates call when they use it, so pages that
        # never show the notices never run their queries.
        "waiting_notices": lambda: waiting_notices(request.user, getattr(request, "club", None)),
    }


def waiting_notices(user, club):
    """What is waiting for this person to act on, each with where to act.

    Everyone sees only what they can decide: requests for the race committee
    (which includes the administrator), and new accounts for the
    administrator alone.
    """
    notices = []
    if not user.is_active:
        return notices
    if is_committee(user) and club is not None:
        # Only this club's requests (slice 11).
        pending = Request.Status.PENDING
        counts = [
            (BoatRequest.objects.for_club(club).filter(status=pending).count(), "boat request"),
            (EntryRequest.objects.for_club(club).filter(status=pending).count(), "entry request"),
        ]
        if any(number for number, _ in counts):
            notices.append({
                "text": f"{_sentence(counts)} waiting for the race committee.",
                "link": reverse("races:requests"),
                "link_text": "Review requests",
            })
    if user.is_superuser:
        accounts = waiting_for_approval(get_user_model().objects.all()).count()
        if accounts:
            notices.append({
                "text": f"{_sentence([(accounts, 'new account')])} waiting for approval.",
                "link": reverse("admin:auth_user_changelist") + "?approval=waiting",
                "link_text": "Review and approve",
            })
    return notices


def _sentence(counts):
    """[(2, "boat request"), (1, "entry request")] ->
    "2 boat requests and 1 entry request are". Zero counts are left out."""
    waiting = [(number, noun) for number, noun in counts if number]
    parts = [f"{number} {noun}{'' if number == 1 else 's'}" for number, noun in waiting]
    # "is" only for exactly one thing of one kind.
    verb = "is" if len(waiting) == 1 and waiting[0][0] == 1 else "are"
    return f"{' and '.join(parts)} {verb}"
