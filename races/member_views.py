"""Pages for members: signing up, and their boats and requests.

Members change nothing directly: every page here that submits something
creates a request for the race committee (see docs/brief.md). A member only
ever sees or acts on their own boats and requests; anything else is a 404, so
the pages do not even confirm that another member's boat or request exists.
"""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import approvals
from .forms import (
    BoatChangeForm, BoatRegistrationForm, EntryRequestForm, LoginForm, SignUpForm,
)
from .models import Boat, BoatRequest, EntryRequest
from .roles import member_required

PENDING_ALREADY = (
    "This boat already has a request waiting for the race committee. "
    "Wait for it to be decided, or withdraw it first."
)


def signup(request):
    if request.user.is_authenticated:
        return redirect("races:my_boats")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return render(request, "registration/signup_done.html", {"email": form.cleaned_data["email"]})
    return render(request, "registration/signup.html", {"form": form})


class LoginView(auth_views.LoginView):
    authentication_form = LoginForm
    redirect_authenticated_user = True


@member_required
def my_boats(request):
    # Only this club's boats and requests: the same person may be a member elsewhere.
    boats = Boat.objects.for_club(request.club).filter(owner=request.user).prefetch_related(
        "series_entries__series"
    )
    boat_requests = BoatRequest.objects.for_club(request.club).filter(
        requested_by=request.user
    ).select_related("boat")
    entry_requests = EntryRequest.objects.for_club(request.club).filter(
        requested_by=request.user
    ).select_related("boat", "series")
    return render(
        request,
        "races/my_boats.html",
        {
            "boats": boats,
            "pending_boats": {r.boat_id for r in boat_requests if r.is_pending},
            "boat_requests": boat_requests,
            "entry_requests": entry_requests,
        },
    )


@member_required
def register_boat(request):
    form = BoatRegistrationForm(request.POST or None, club=request.club)
    if request.method == "POST" and form.is_valid():
        boat_request = form.save(commit=False)
        boat_request.club = request.club
        boat_request.kind = BoatRequest.Kind.REGISTER
        boat_request.requested_by = request.user
        boat_request.save()
        messages.success(request, "Sent to the race committee. You'll see its decision here.")
        return redirect("races:my_boats")
    # A sail number already on record: offer to claim that boat instead.
    existing = getattr(form, "existing_boat", None)
    if existing is not None and existing.owner_id == request.user.pk:
        existing = None  # already theirs; nothing to claim
    return render(request, "races/register_boat.html", {"form": form, "claimable": existing})


@member_required
@require_POST
def claim_boat(request, pk):
    boat = get_object_or_404(Boat.objects.for_club(request.club), pk=pk)
    if boat.owner_id == request.user.pk:
        messages.info(request, f"{boat} is already recorded as yours.")
    elif boat.requests.filter(status=BoatRequest.Status.PENDING).exists():
        messages.error(request, PENDING_ALREADY)
    else:
        BoatRequest.objects.create(
            club=request.club,
            kind=BoatRequest.Kind.CLAIM,
            boat=boat,
            requested_by=request.user,
            member_note=request.POST.get("member_note", "").strip()[:500],
        )
        messages.success(request, f"Asked the race committee to record {boat} as yours.")
    return redirect("races:my_boats")


@member_required
def change_boat(request, pk):
    boat = get_object_or_404(Boat.objects.for_club(request.club), pk=pk, owner=request.user)
    if boat.requests.filter(status=BoatRequest.Status.PENDING).exists():
        messages.error(request, PENDING_ALREADY)
        return redirect("races:my_boats")
    form = BoatChangeForm(request.POST or None, boat=boat)
    if request.method == "POST" and form.is_valid():
        boat_request = form.save(commit=False)
        boat_request.club = request.club
        boat_request.kind = BoatRequest.Kind.CHANGE
        boat_request.boat = boat
        boat_request.requested_by = request.user
        boat_request.save()
        messages.success(request, "Sent to the race committee. Nothing changes until they approve it.")
        return redirect("races:my_boats")
    return render(request, "races/change_boat.html", {"form": form, "boat": boat})


@member_required
def enter_series(request, pk):
    boat = get_object_or_404(Boat.objects.for_club(request.club), pk=pk, owner=request.user)
    form = EntryRequestForm(request.POST or None, boat=boat)
    if request.method == "POST" and form.is_valid():
        EntryRequest.objects.create(
            series=form.cleaned_data["series"],
            boat=boat,
            requested_by=request.user,
            member_note=form.cleaned_data["member_note"],
        )
        messages.success(request, "Sent to the race committee.")
        return redirect("races:my_boats")
    return render(request, "races/enter_series.html", {"form": form, "boat": boat})


@member_required
@require_POST
def withdraw_request(request, kind, pk):
    model = {"boat": BoatRequest, "entry": EntryRequest}.get(kind)
    if model is None:
        return redirect("races:my_boats")
    member_request = get_object_or_404(model.objects.for_club(request.club), pk=pk, requested_by=request.user)
    try:
        approvals.withdraw(member_request)
        messages.success(request, "Request withdrawn.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("races:my_boats")
