"""Who can do what at a club (slice 11; see docs/brief.md).

Roles belong to a person's membership of a club, not to their account:

- Public: anyone, logged in or not, without an approved membership here.
- Member: an approved membership of this club, in any role.
- Race committee: an approved membership as committee or administrator.
- Club administrator: an approved membership as administrator.
- Operator: a superuser. Runs the service; has no role at a club unless
  given a membership there like anyone else.

Django's is_staff flag and the old "Race committee" group mean nothing any
more. Every check takes the club, which pages get from ``request.club``.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import ClubMembership

COMMITTEE_ROLES = (ClubMembership.Role.COMMITTEE, ClubMembership.Role.ADMINISTRATOR)


def membership(user, club):
    """This person's membership of this club, whatever its status, or None."""
    if club is None or not user.is_authenticated or not user.is_active:
        return None
    # Pages ask several times per request; remember the answer on the user.
    cache = user.__dict__.setdefault("_club_memberships", {})
    if club.pk not in cache:
        cache[club.pk] = ClubMembership.objects.filter(user=user, club=club).first()
    return cache[club.pk]


def forget_memberships(user):
    user.__dict__.pop("_club_memberships", None)


def _approved(user, club):
    found = membership(user, club)
    return found if found is not None and found.is_approved else None


def is_member(user, club):
    """An approved member of this club, in any role."""
    return _approved(user, club) is not None


def is_committee(user, club):
    found = _approved(user, club)
    return found is not None and found.role in COMMITTEE_ROLES


def is_club_administrator(user, club):
    found = _approved(user, club)
    return found is not None and found.role == ClubMembership.Role.ADMINISTRATOR


def _requiring(check):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if check(request.user, request.club):
                return view(request, *args, **kwargs)
            if request.user.is_authenticated:
                # Logged in without the role here: say so (templates/403.html).
                # Sending them to log in would loop, since the login page sends
                # anyone already logged in straight back.
                raise PermissionDenied
            return redirect_to_login(request.get_full_path())
        return wrapped
    return decorator


def member_required(view):
    """Only approved members of this club. The public is sent to log in; anyone else is refused."""
    return _requiring(is_member)(view)


def committee_required(view):
    """Only this club's race committee (and its administrators)."""
    return _requiring(is_committee)(view)


def club_administrator_required(view):
    return _requiring(is_club_administrator)(view)
