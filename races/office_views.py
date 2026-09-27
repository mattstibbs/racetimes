"""The race office (slice 18): where the race committee sets up the club's boats
and series, on the site's own pages instead of the Django admin.

Every page here is the committee's, and finds rows through ``for_club``.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Value
from django.db.models.functions import Replace, Upper
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_safe

from .context_processors import waiting_notices
from .models import Boat, Series
from .office_forms import BoatForm
from .roles import committee_required


@committee_required
@require_safe
def home(request):
    series_list = (
        Series.objects.for_club(request.club)
        .annotate(
            race_count=Count("races", distinct=True),
            entry_count=Count("entries", distinct=True),
        )
        .order_by("-pk")
    )
    # Open series first, newest first, then the final ones.
    series_list = sorted(series_list, key=lambda series: series.is_final)
    return render(
        request,
        "races/office/home.html",
        {
            "notices": waiting_notices(request.user, request.club),
            "series_list": series_list,
            "boat_count": Boat.objects.for_club(request.club).count(),
        },
    )


# --- Boats ----------------------------------------------------------------------------


@committee_required
@require_safe
def boats(request):
    query = request.GET.get("q", "").strip()
    found = Boat.objects.for_club(request.club).select_related("owner")
    if query:
        # Sail numbers match ignoring case and spaces, as the database treats them.
        squashed = query.replace(" ", "").upper()
        found = found.annotate(
            squashed=Upper(Replace("sail_number", Value(" "), Value("")))
        ).filter(
            Q(squashed__contains=squashed)
            | Q(name__icontains=query)
            | Q(owner_name__icontains=query)
            | Q(owner__first_name__icontains=query)
            | Q(owner__last_name__icontains=query)
        )
    template = "races/office/boats.html"
    # The search box asks for just the table over HTMX, at the same URL.
    htmx = request.htmx
    if htmx and not htmx.history_restore_request and htmx.target == "boat-table":
        template = "races/office/_boat_table.html"
    response = render(request, template, {"boats": found, "query": query})
    patch_vary_headers(response, ["HX-Request", "HX-Target"])
    return response


@committee_required
def new_boat(request):
    return _boat_form(request, Boat())


@committee_required
def change_boat(request, pk):
    return _boat_form(
        request, get_object_or_404(Boat.objects.for_club(request.club), pk=pk)
    )


def _boat_form(request, boat):
    adding = boat.pk is None
    form = BoatForm(request.POST or None, instance=boat, club=request.club)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            boat = form.save_audited(request)
        messages.success(request, f"{boat} {'added' if adding else 'saved'}.")
        return redirect("races:office_boats")
    return render(
        request,
        "races/office/boat_form.html",
        {"form": form, "boat": boat, "adding": adding, "deletable": _deletable(boat)},
    )


def _deletable(boat):
    """A boat can go only if it has never been entered in a series (slice 18)."""
    return boat.pk is not None and not boat.series_entries.exists()


@committee_required
def delete_boat(request, pk):
    boat = get_object_or_404(Boat.objects.for_club(request.club), pk=pk)
    if not _deletable(boat):
        messages.error(
            request,
            f"{boat} has been entered in a series, so it can't be deleted: "
            "its results would go with it.",
        )
        return redirect("races:office_boat", boat.pk)
    if request.method == "POST":
        name = str(boat)
        try:
            boat.delete()
        except ProtectedError:  # entered in a series since the page was opened
            return redirect("races:office_delete_boat", boat.pk)
        messages.success(request, f"{name} deleted.")
        return redirect("races:office_boats")
    return render(
        request,
        "races/office/delete_boat.html",
        {
            "boat": boat,
            "cancel": reverse("races:office_boat", args=[boat.pk]),
            "requests": boat.requests.count() + boat.entry_requests.count(),
        },
    )
