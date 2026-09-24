from django.contrib.auth import get_user_model

from .roles import is_committee, waiting_for_approval


def roles(request):
    """Lets templates show links by role, without repeating the rules."""
    return {
        "is_committee": is_committee(request.user),
        # Only the administrator manages accounts, so only they are told about
        # sign-ups. A function, which templates call when they use it, so pages
        # that never show it never run the query.
        "accounts_waiting": lambda: _accounts_waiting(request.user),
    }


def _accounts_waiting(user):
    if not (user.is_active and user.is_superuser):
        return 0
    return waiting_for_approval(get_user_model().objects.all()).count()
