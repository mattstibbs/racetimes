"""The operator's pages (slice 11 part 3), at /operator/ on the service's own address.

The operator runs the service: they create clubs, invite each club's first
administrator, and suspend or reactivate a club. They change no club's data,
and see a club's pages only through a membership there, like anyone else
(``races/roles.py``). Everything they do here is recorded in the operator log.

The operator is a superuser, on the service's own address. On a club's
address these pages don't exist.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import club_deletion, club_export, invitations, membership_views, notifications
from .clubs import club_address
from .forms import ClubForm, InvitationForm
from .models import Club, ClubMembership, OperatorAction

Action = OperatorAction.Action


def operator_required(view):
    """Only the operator, and only on the service's own address.

    The public is sent to the admin's login, which is the one login on the
    service's own address. Anyone else logged in is refused (a login redirect
    would loop, see docs/decisions.md).
    """
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.club is not None:
            raise Http404("The operator's pages are on the service's own address.")
        if request.user.is_active and request.user.is_superuser:
            return view(request, *args, **kwargs)
        if request.user.is_authenticated:
            raise PermissionDenied
        return redirect_to_login(request.get_full_path(), reverse("admin:login"))
    return wrapped


def log(request, action, club, detail=""):
    OperatorAction.objects.create(
        who=request.user.get_username(), action=action, club_subdomain=club.subdomain, detail=detail
    )


@operator_required
def clubs(request):
    """Every club, with enough to see at a glance which are in use."""
    approved = Q(memberships__status=ClubMembership.Status.APPROVED)
    found = Club.objects.annotate(
        member_count=Count("memberships", filter=approved, distinct=True),
        series_count=Count("series", distinct=True),
        last_result=Max("series__races__finishes__recorded_at"),
    ).order_by("name")
    return render(request, "operator/clubs.html", {
        "clubs": [(club, club_address(request, club)) for club in found],
        "recent": OperatorAction.objects.all()[:10],
    })


@operator_required
def create_club(request):
    form = ClubForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            club = form.save()
            log(request, Action.CREATED, club, f"{club.name}, contact {club.contact_email}")
        messages.success(request, f"{club.name} created. Now invite its administrator.")
        return redirect("races:operator_club", club.pk)
    return render(request, "operator/create_club.html", {"form": form})


@operator_required
def club_page(request, pk):
    club = get_object_or_404(Club, pk=pk)
    return render(request, "operator/club.html", _club_context(request, club, InvitationForm()))


def _club_context(request, club, form):
    return {
        "club": club,
        "address": club_address(request, club),
        "administrators": club.memberships.filter(
            status=ClubMembership.Status.APPROVED, role=ClubMembership.Role.ADMINISTRATOR
        ).select_related("user"),
        "waiting": club.memberships.filter(status=ClubMembership.Status.WAITING).select_related("user")
        .order_by("created_at"),
        "roles": ClubMembership.Role.choices,
        "invitations": club.invitations.all(),
        "form": form,
        "lasts_days": invitations.LASTS.days,
        "log": OperatorAction.objects.filter(club_subdomain=club.subdomain),
    }


NOT_WHILE_SUSPENDED = "Reactivate the club first: nobody can accept an invitation while its site is paused."


@operator_required
@require_POST
def invite(request, pk):
    """Email someone a link that makes them this club's administrator."""
    club = get_object_or_404(Club, pk=pk)
    form = InvitationForm(request.POST)
    if not club.is_active:
        messages.error(request, NOT_WHILE_SUSPENDED)
        return redirect("races:operator_club", club.pk)
    if not form.is_valid():
        return render(request, "operator/club.html", _club_context(request, club, form), status=400)
    with transaction.atomic():
        invitation = invitations.invite(club, form.cleaned_data["email"], request.user, request)
        log(request, Action.INVITED, club, f"{invitation.email} as {invitation.get_role_display().lower()}")
    messages.success(request, f"Invitation emailed to {invitation.email}. The link lasts {invitations.LASTS.days} days.")
    return redirect("races:operator_club", club.pk)


@operator_required
@require_POST
def change_status(request, pk):
    """Suspend a club (its site shows "paused" to everyone), or reactivate it."""
    club = get_object_or_404(Club, pk=pk)
    wanted = request.POST.get("status")
    if wanted in Club.Status.values and wanted != club.status:
        with transaction.atomic():
            club.status = wanted
            club.save(update_fields=["status"])
            log(request, Action.SUSPENDED if wanted == Club.Status.SUSPENDED else Action.REACTIVATED, club)
        messages.success(request, f"{club.name} is now {club.get_status_display().lower()}.")
    return redirect("races:operator_club", club.pk)


@operator_required
def operator_log(request):
    return render(request, "operator/log.html", {"actions": OperatorAction.objects.all()[:500]})


# --- A club's data, and deleting a club (slice 11 part 5) ---------------------------------------


@operator_required
def export_club(request, pk):
    """Everything the club holds, as a ZIP; works while it's suspended, before deletion."""
    club = get_object_or_404(Club, pk=pk)
    response = club_export.download(club)
    log(request, Action.EXPORTED, club)
    return response


NOT_WHILE_ACTIVE = "Suspend the club before deleting it, so its administrators know and its data can be downloaded."
MISTYPED = "Type the club's address exactly, to confirm."


@operator_required
def delete_club(request, pk):
    """Delete a suspended club and everything it holds, once its subdomain is typed to confirm."""
    club = get_object_or_404(Club, pk=pk)
    # (No need to guard the SINGLE_CLUB club: with SINGLE_CLUB set, every address
    # with no club in it shows that club, so these pages don't exist at all.)
    refused = NOT_WHILE_ACTIVE if club.is_active else ""
    error = ""
    if request.method == "POST" and not refused:
        if request.POST.get("confirm", "").strip() != club.subdomain:
            error = MISTYPED
        else:
            with transaction.atomic():
                gone = club_deletion.delete_club(club)
                log(request, Action.DELETED, club, f"{club.name}: {gone['boats']} boats, {gone['series']} series, "
                                                   f"{gone['memberships']} memberships")
            messages.success(request, f"{club.name} and everything it held have been deleted.")
            return redirect("races:operator_clubs")
    return render(request, "operator/delete_club.html", {"club": club, "refused": refused, "error": error},
                  status=400 if error else 200)


# --- People waiting to join (slice 13) -----------------------------------------------------------

NOT_WHILE_SUSPENDED_TO_JOIN = "Reactivate the club first: nobody can use its site while it's paused."


@operator_required
@require_POST
def decide_joining(request, pk, membership_pk):
    """Approve, or turn down, one person waiting to join this club.

    The one exception to "clubs decide their own members" (docs/decisions.md):
    only people waiting, never a role change or a removal. It goes through the
    same code as the club's Members page, and emails the person from the club.
    """
    club = get_object_or_404(Club, pk=pk)
    target = get_object_or_404(club.memberships.select_related("user"), pk=membership_pk)
    action = request.POST.get("action")
    if not club.is_active:
        messages.error(request, NOT_WHILE_SUSPENDED_TO_JOIN)
    elif action in ("approve", "reject") and target.status == ClubMembership.Status.WAITING:
        with transaction.atomic():
            change = membership_views.decide(club, target, action, request.POST.get("role", ""), request.user,
                                             by_name=membership_views.OPERATOR_NAME)
            if change:
                target.refresh_from_db()
                if change == "approved":
                    log(request, Action.APPROVED_JOIN, club,
                        f"{target.user.email} as {target.get_role_display().lower()}")
                else:
                    log(request, Action.TURNED_DOWN, club, target.user.email)
        if change:
            notifications.membership_decided(target, request, change)
            name = target.user.get_full_name() or target.user.get_username()
            messages.success(request, f"{name}: {membership_views.CHANGE_MESSAGES[change]}")
    return redirect(reverse("races:operator_club", args=[club.pk]) + "#waiting")

