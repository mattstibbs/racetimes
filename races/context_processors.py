from django.urls import reverse

from .models import BoatRequest, ClubMembership, EntryRequest, Request
from .roles import is_club_administrator, is_committee, is_member, membership


def roles(request):
    """Lets templates show links and notices by role at this club, without repeating the rules."""
    club = getattr(request, "club", None)
    user = request.user
    return {
        "is_member": is_member(user, club),
        "is_committee": is_committee(user, club),
        "is_club_administrator": is_club_administrator(user, club),
        # Logged in here with no approved membership: waiting, removed or none.
        "club_membership": membership(user, club),
        # A function, which templates call when they use it, so pages that
        # never show the notices never run their queries.
        "waiting_notices": lambda: waiting_notices(user, club),
    }


def waiting_notices(user, club):
    """What is waiting at this club for this person to act on, each with where to act.

    Everyone sees only what they can decide: members' requests for the race
    committee (which includes administrators), and people asking to join for
    the club's administrators alone.
    """
    notices = []
    if club is None or not is_committee(user, club):
        return notices
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
    if is_club_administrator(user, club):
        joining = club.memberships.filter(status=ClubMembership.Status.WAITING).count()
        if joining:
            notices.append({
                "text": f"{_sentence([(joining, 'person')]).replace('persons', 'people')} waiting to join the club.",
                "link": reverse("races:members"),
                "link_text": "Review members",
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
