"""The four roles, in terms of Django accounts (see docs/brief.md).

- Public: not logged in.
- Member: an active account with no staff access.
- Race committee: staff, in the COMMITTEE_GROUP permission group.
- Administrator: a superuser.

Committee pages check ``is_committee`` rather than Django's ``is_staff`` alone,
so staff access only counts with the group (or as the administrator).
"""

from functools import wraps

from django.contrib.auth.decorators import user_passes_test

COMMITTEE_GROUP = "Race committee"


def is_committee(user):
    if not (user.is_active and user.is_staff):
        return False
    return user.is_superuser or user.groups.filter(name=COMMITTEE_GROUP).exists()


def is_member(user):
    """Any logged-in, active account. The committee and administrator are members too."""
    return user.is_authenticated and user.is_active


def committee_required(view):
    """Only the race committee (or the administrator); others are sent to log in."""
    return wraps(view)(user_passes_test(is_committee)(view))


def member_required(view):
    return wraps(view)(user_passes_test(is_member)(view))
