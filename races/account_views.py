"""A person's own account: what's held about them, downloading it, and deleting it (slice 11 part 5).

The account is one across every club, so these pages show and act on every
club's membership, not just the club whose address they're on.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from . import notifications
from .account_deletion import clubs_needing_them, delete_account
from .account_forms import ChangePasswordForm, DeleteAccountForm
from .clubs import club_address
from .models import Club, ClubMembership
from .my_data import my_data

logger = logging.getLogger(__name__)

DELETED = "Your account has been deleted."
PASSWORD_CHANGED = "Your password has been changed. Any other devices logged in to your account have been logged out."
OPERATOR = "The service's operator account can't be deleted here."


@login_required
def account(request):
    memberships = (
        ClubMembership.objects.filter(user=request.user)
        .select_related("club")
        .order_by("club__name")
    )
    return render(
        request,
        "races/account.html",
        {
            "memberships": [(m, club_address(request, m.club)) for m in memberships],
        },
    )


def own_clubs(user):
    """A person's memberships of clubs, waiting or approved, by club name (slice 27).

    Only their own: this is the one page on the service's address that names
    clubs a person belongs to, as My account does at a club.
    """
    return list(
        ClubMembership.objects.filter(
            user=user,
            status__in=[ClubMembership.Status.APPROVED, ClubMembership.Status.WAITING],
        )
        .select_related("club")
        .order_by("club__name")
    )


def landing_after_login(request):
    """Where logging in on the service's own address goes (slice 27).

    The operator to their pages; someone approved at exactly one active club
    straight to its My boats (most people belong to one club); anyone else to
    Your clubs. The session is shared across every club's address in
    production, so they are logged in there already.
    """
    user = request.user
    if user.is_superuser:
        return reverse("races:operator_clubs")
    approved = [
        m
        for m in own_clubs(user)
        if m.is_approved and m.club.status == Club.Status.ACTIVE
    ]
    if len(approved) == 1:
        return club_address(request, approved[0].club, reverse("races:my_boats"))
    return reverse("races:your_clubs")


@login_required
def your_clubs(request):
    """The clubs a person belongs to, with a way into each (slice 27).

    On the service's own address only; at a club, My account lists them.
    """
    if request.club is not None:
        return redirect("races:account")
    rows = [
        {
            "membership": m,
            "active": m.club.status == Club.Status.ACTIVE,
            "address": club_address(request, m.club, reverse("races:my_boats")),
        }
        for m in own_clubs(request.user)
    ]
    return render(request, "races/your_clubs.html", {"rows": rows})


@login_required
def download_my_data(request):
    response = HttpResponse(
        json.dumps(my_data(request.user), indent=2, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )
    day = timezone.localdate().isoformat()
    response["Content-Disposition"] = (
        f'attachment; filename="race-times-my-data-{day}.json"'
    )
    return response


@login_required
def delete_my_account(request):
    user = request.user
    blocking = clubs_needing_them(user)
    form = DeleteAccountForm(request.POST or None, request=request)
    if (
        request.method == "POST"
        and not blocking
        and not user.is_superuser
        and form.is_valid()
    ):
        goodbye = notifications.account_deleted(user, request)
        delete_account(user)
        logout(request)
        notifications.send([goodbye], request)
        messages.success(request, DELETED)
        return redirect("results:home")
    return render(
        request,
        "races/delete_account.html",
        {
            "form": form,
            "blocking": blocking,
            "operator": user.is_superuser,
        },
    )


@login_required
def change_password(request):
    """Change your own password, given the current one (slice 16).

    Every other browser logged in to the account is logged out: Django keeps a
    hash of the password in each session and ends any session whose hash no
    longer matches. update_session_auth_hash keeps this browser logged in.
    """
    form = ChangePasswordForm(data=request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        logger.info("user %s changed their password", user.pk)
        notifications.send([notifications.password_changed(user, request)], request)
        messages.success(request, PASSWORD_CHANGED)
        # The operator, on the service's own address, goes back to their pages.
        if request.club is None and request.user.is_superuser:
            return redirect("races:operator_clubs")
        return redirect("races:account")
    return render(request, "races/change_password.html", {"form": form})
