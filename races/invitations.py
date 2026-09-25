"""Inviting someone to run a club, and accepting (slice 11 part 3).

The operator invites a new club's first administrator from the operator's
pages (``races/operator_views.py``). The invitation is emailed as a link to the
club's own address. The link is a signed token naming the invitation, so
nothing secret is stored, and it lasts 7 days: longer than a sign-up
confirmation, since a club may take a while to get round to it.

Opening the link proves the email address. Someone with no account makes one
there, and is logged in straight away; someone with an account logs in first.
Either way, accepting gives them an approved membership of the club, in the
invitation's role, and the link can't be used again.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from . import notifications
from .clubs import club_address
from .forms import InvitedSignUpForm
from .models import ClubInvitation, ClubMembership
from .roles import forget_memberships

LASTS = timedelta(days=7)
SALT = "races.invitations"


def token_for(invitation):
    return signing.dumps(invitation.pk, salt=SALT)


def invitation_from(token, club):
    """The unused invitation to this club that a token names, or None.

    None too if the token was tampered with or is over 7 days old, or names
    another club's invitation.
    """
    try:
        pk = signing.loads(token, salt=SALT, max_age=LASTS)
    except signing.BadSignature:  # includes SignatureExpired
        return None
    return ClubInvitation.objects.filter(pk=pk, club=club, accepted_at__isnull=True).first()


def invite(club, email, by, request):
    """Record an invitation and email its link. Returns the invitation."""
    invitation = ClubInvitation.objects.create(club=club, email=email, invited_by_name=by.get_username())
    link = club_address(request, club, reverse("races:accept_invitation", args=[token_for(invitation)]))
    notifications.invitation(invitation, request, link)
    return invitation


@require_http_methods(["GET", "POST"])
def accept_invitation(request, token):
    """The link from the invitation email, on the club's own address."""
    invitation = invitation_from(token, request.club)
    if invitation is None:
        return render(request, "races/invitation.html", {"valid": False}, status=400)
    # Members' usernames are their emails; an older account made in the admin
    # may have another username, but the same email.
    account = get_user_model().objects.filter(
        Q(username__iexact=invitation.email) | Q(email__iexact=invitation.email)
    ).first()
    context = {"valid": True, "invitation": invitation, "account": account}
    signed_in_as_someone_else = request.user.is_authenticated and (
        account is None or request.user.pk != account.pk
    )
    if signed_in_as_someone_else:
        return render(request, "races/invitation.html", {**context, "someone_else": True})

    if account is None:
        # No account yet: make one here. The invitation proves the email.
        form = InvitedSignUpForm(request.POST or None, email=invitation.email)
        if request.method == "POST" and form.is_valid():
            with transaction.atomic():
                user = form.save()
                _accept(invitation, user)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return _accepted(request, invitation)
        return render(request, "races/invitation.html", {**context, "form": form})

    if request.user.is_authenticated:  # as the invited account
        if request.method == "POST":
            with transaction.atomic():
                _accept(invitation, request.user)
            return _accepted(request, invitation)
        return render(request, "races/invitation.html", {**context, "ready": True})

    # An account exists: they log in as it first.
    context["login_url"] = f"{reverse('races:login')}?{urlencode({'next': request.path})}"
    return render(request, "races/invitation.html", context)


def _accept(invitation, user):
    invitation = ClubInvitation.objects.select_for_update().get(pk=invitation.pk)
    if invitation.accepted_at is not None:
        return  # accepted a moment ago, in another tab
    membership, _ = ClubMembership.objects.get_or_create(user=user, club=invitation.club)
    membership.role, membership.status = invitation.role, ClubMembership.Status.APPROVED
    membership.decided_by_name, membership.decided_at = invitation.invited_by_name, timezone.now()
    membership.save()
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    forget_memberships(user)


def _accepted(request, invitation):
    messages.success(request, f"Welcome to {invitation.club.name}. You're its {invitation.get_role_display().lower()}.")
    if invitation.role == ClubMembership.Role.ADMINISTRATOR:
        return redirect("races:members")
    return redirect("races:my_boats")
