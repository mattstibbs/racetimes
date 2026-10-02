"""The race office (slice 18): where the race committee sets up the club's boats
and series, on the site's own pages instead of the Django admin.

Every page here is the committee's, and finds rows through ``for_club``.
"""

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Value
from django.db.models.functions import Replace, Upper
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_safe

from . import audit, final, notifications, race_day
from .context_processors import waiting_notices
from .models import YTC_NUMBER_FIELDS, Boat, Race, Series, SeriesEntry
from .office_forms import (
    BoatForm,
    EntryNumberForm,
    RaceForm,
    SeriesForm,
    reason_field,
)
from .roles import committee_required
from .scoring import score_series

COMING_UP = 5  # races listed under Coming up


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
    today = race_day.now().date()
    coming_up = (
        Race.objects.for_club(request.club)
        .filter(date__gte=today, series__declared_final_at__isnull=True)
        .select_related("series")
        .order_by("date", "start_time", "series__name", "number")[:COMING_UP]
    )
    return render(
        request,
        "races/office/home.html",
        {
            "notices": waiting_notices(request.user, request.club),
            "coming_up": coming_up,
            "today": today,
            "series_list": series_list,
            "boat_count": Boat.objects.for_club(request.club).count(),
        },
    )


# --- Boats ----------------------------------------------------------------------------


@committee_required
@require_safe
def boats(request):
    query = request.GET.get("q", "").strip()
    found = search(Boat.objects.for_club(request.club), query)
    return _render(
        request,
        "races/office/boats.html",
        {"boat-table": "races/office/_boat_table.html"},
        {"boats": found.select_related("owner"), "query": query},
    )


def search(boats, query, keep=()):
    """Boats whose sail number, name or owner matches the query, and any in ``keep``.

    Sail numbers match ignoring case and spaces, as the database treats them.
    """
    if not query:
        return boats
    squashed = query.replace(" ", "").upper()
    return boats.annotate(
        squashed=Upper(Replace("sail_number", Value(" "), Value("")))
    ).filter(
        Q(squashed__contains=squashed)
        | Q(name__icontains=query)
        | Q(owner_name__icontains=query)
        | Q(owner__first_name__icontains=query)
        | Q(owner__last_name__icontains=query)
        | Q(pk__in=keep)
    )


def _render(request, template, fragments, context):
    """The whole page, or just the part an HTMX request targets (as results/views.py)."""
    htmx = request.htmx
    if htmx and not htmx.history_restore_request and htmx.target in fragments:
        template = fragments[htmx.target]
    response = render(request, template, context)
    # The same URL answers with a fragment or a whole page, so caches must
    # tell them apart.
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
    form = BoatForm(_posted(request), instance=boat, club=request.club)
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


# --- Series ---------------------------------------------------------------------------


def _series(request, pk):
    return get_object_or_404(Series.objects.for_club(request.club), pk=pk)


def series_can_be_deleted(series):
    """Only while no race in it has a result (slice 18): after that, declare it final."""
    return not audit.series_has_finishes(series)


@committee_required
@require_safe
def series_page(request, pk):
    series = _series(request, pk)
    return render(
        request,
        "races/office/series.html",
        {
            "series": series,
            "races": series.races.annotate(result_count=Count("finishes")),
            "entries": series.entries.select_related("boat").annotate(
                result_count=Count("finishes")
            ),
            "deletable": series_can_be_deleted(series),
        },
    )


@committee_required
def new_series(request):
    return _series_form(request, Series())


@committee_required
def series_settings(request, pk):
    return _series_form(request, _series(request, pk))


def _series_form(request, series):
    adding = series.pk is None
    form = SeriesForm(_posted(request), instance=series, club=request.club)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            series = form.save_audited(request)
        messages.success(request, f"{series} {'created' if adding else 'saved'}.")
        return redirect("races:office_series", series.pk)
    return render(
        request,
        "races/office/series_form.html",
        {"form": form, "series": series, "adding": adding},
    )


@committee_required
def delete_series(request, pk):
    series = _series(request, pk)
    if not series_can_be_deleted(series):
        messages.error(
            request,
            f"{series} has results, so it can't be deleted. "
            "Declare its results final instead.",
        )
        return redirect("races:office_series", series.pk)
    if request.method == "POST":
        entries = list(series.entries.select_related("boat__owner", "series"))
        name = str(series)
        with transaction.atomic():
            series.delete()
            notifications.removed_from_series(entries, request)
        messages.success(request, f"{name} deleted.")
        return redirect("races:office")
    return render(
        request,
        "races/office/delete_series.html",
        {
            "series": series,
            "race_count": series.races.count(),
            "entry_count": series.entries.count(),
        },
    )


# --- Races ----------------------------------------------------------------------------


def _race(request, pk):
    return get_object_or_404(
        Race.objects.for_club(request.club).select_related("series"), pk=pk
    )


@committee_required
def new_race(request, pk):
    series = _series(request, pk)
    if series.is_final:
        return _locked(request, series)
    return _race_form(request, series, Race())


@committee_required
def change_race(request, pk):
    race = _race(request, pk)
    if race.series.is_final:
        return _locked(request, race.series)
    return _race_form(request, race.series, race)


def _race_form(request, series, race):
    adding = race.pk is None
    form = RaceForm(_posted(request), instance=race, series=series)
    if request.method == "POST" and form.is_valid():
        before = score_series(series)
        with transaction.atomic():
            race = form.save()
            recorded = audit.record(
                form.scoring_changes, request.user, form.cleaned_data.get("reason", "")
            )
        messages.success(
            request, f"Race {race.number} {'added' if adding else 'saved'}."
        )
        _say_what_moved(request, series, before, recorded)
        return redirect("races:office_series", series.pk)
    return render(
        request,
        "races/office/race_form.html",
        {"form": form, "series": series, "race": race, "adding": adding},
    )


def _say_what_moved(request, series, before, recorded):
    if audit.needs_reason(recorded):
        effect = audit.describe_effect(before, score_series(series))
        messages.info(request, f"Correction recorded. {effect}")


class RemovalForm(forms.Form):
    """Confirms a removal, with a reason when it's a correction."""

    def __init__(self, *args, changes, **kwargs):
        super().__init__(*args, **kwargs)
        self.changes = changes
        if audit.needs_reason(changes):
            self.fields["reason"] = reason_field()
            self.fields["reason"].required = True
            self.fields["reason"].error_messages["required"] = audit.REASON_REQUIRED

    def reason_given(self):
        return self.cleaned_data.get("reason", "")


@committee_required
def remove_race(request, pk):
    race = _race(request, pk)
    series = race.series
    if series.is_final:
        return _locked(request, series)
    form = RemovalForm(_posted(request), changes=audit.changes_to_delete(race))
    if request.method == "POST" and form.is_valid():
        before = score_series(series)
        with transaction.atomic():
            # Recorded while the race still exists; its finishes go with it.
            recorded = audit.record(form.changes, request.user, form.reason_given())
            race.delete()
        messages.success(request, f"Race {race.number} removed.")
        _say_what_moved(request, series, before, recorded)
        return redirect("races:office_series", series.pk)
    return render(
        request,
        "races/office/remove.html",
        {
            "form": form,
            "series": series,
            "title": f"Remove race {race.number}?",
            "result_count": race.finishes.count(),
            "what": "race",
        },
    )


# --- Entries --------------------------------------------------------------------------


class EnterBoatsForm(forms.Form):
    boat = forms.ModelMultipleChoiceField(
        queryset=Boat.objects.none(),
        error_messages={"required": "Tick at least one boat to enter."},
    )

    def __init__(self, *args, series, **kwargs):
        super().__init__(*args, **kwargs)
        self.series = series
        self.fields["boat"].queryset = Boat.objects.for_club(series.club).exclude(
            series_entries__series=series
        )
        # Adding a boat to a series with results changes its A5.2 entry count.
        if audit.series_has_finishes(series):
            self.fields["reason"] = reason_field()
            self.fields["reason"].required = True
            self.fields["reason"].error_messages["required"] = audit.REASON_REQUIRED

    def clean_boat(self):
        # A boat can only be entered if it has the number this series is scored
        # on (slice 24). They are listed, so the committee can see which, but
        # not enterable.
        lacking = [
            boat for boat in self.cleaned_data["boat"] if self.series.boats_lack(boat)
        ]
        if lacking:
            names = ", ".join(str(boat) for boat in lacking)
            raise ValidationError(
                f"{names} {'has' if len(lacking) == 1 else 'have'} no "
                f"{self.series.number_label}, which this "
                f"{self.series.get_handicap_system_display()} series needs. "
                "Give the boat one first."
            )
        self.number_used = self._numbers_chosen(self.cleaned_data["boat"])
        return self.cleaned_data["boat"]

    def _numbers_chosen(self, boats):
        """Which YTC number each boat is entered on (slice 25): {boat pk: choice}.

        The page asks per boat that has both; a boat with one is entered on it,
        and a choice for a number she doesn't have is refused, naming her.
        """
        if self.series.handicap_system != Series.HandicapSystem.YTC:
            return {}
        chosen, wrong = {}, []
        for boat in boats:
            asked = self.data.get(f"number_{boat.pk}") or ""
            used = asked or SeriesEntry.default_number_used(boat)
            field = {v: k for k, v in YTC_NUMBER_FIELDS.items()}.get(used)
            if field is None or getattr(boat, field) is None:
                wrong.append(boat)
            else:
                chosen[boat.pk] = used
        if wrong:
            names = ", ".join(str(boat) for boat in wrong)
            raise ValidationError(
                f"{names} {'does' if len(wrong) == 1 else 'do'} not have the number "
                "chosen. Choose a number the boat has."
            )
        return chosen

    def clean(self):
        cleaned = super().clean()
        try:
            final.check_series_open(self.series.pk)
        except ValidationError as locked:
            raise ValidationError(locked.messages) from None
        return cleaned


@committee_required
def enter_boats(request, pk):
    series = _series(request, pk)
    if series.is_final:
        return _locked(request, series)
    form = EnterBoatsForm(_posted(request), series=series)
    if request.method == "POST" and form.is_valid():
        before = score_series(series)
        with transaction.atomic():
            entries = [
                SeriesEntry(
                    series=series,
                    boat=boat,
                    ytc_number_used=form.number_used.get(
                        boat.pk, SeriesEntry.NumberUsed.SPINNAKER
                    ),
                )
                for boat in form.cleaned_data["boat"]
            ]
            changes = [
                change for entry in entries for change in audit.changes_to_save(entry)
            ]
            SeriesEntry.objects.bulk_create(entries)  # for_club: not needed, creating
            recorded = audit.record(
                changes, request.user, form.cleaned_data.get("reason", "")
            )
            notifications.entered_in_series(entries, request)
        count = len(entries)
        messages.success(
            request, f"{count} boat{'' if count == 1 else 's'} entered in {series}."
        )
        _say_what_moved(request, series, before, recorded)
        return redirect("races:office_series", series.pk)
    query = request.GET.get("q", "").strip()
    ticked = {
        pk
        for pk in request.GET.getlist("boat") + request.POST.getlist("boat")
        if pk.isdigit()
    }
    # The same for the number each was to be entered on (slice 25).
    chosen = {
        key.removeprefix("number_"): value
        for key, value in {**request.GET.dict(), **request.POST.dict()}.items()
        if key.startswith("number_") and key.removeprefix("number_").isdigit()
    }
    # Boats ticked before a search stay listed, and ticked, whatever it finds.
    unentered = form.fields["boat"].queryset
    boats = list(search(unentered, query, keep=ticked).select_related("owner"))
    for boat in boats:
        boat.chosen_number = chosen.get(
            str(boat.pk)
        ) or SeriesEntry.default_number_used(boat)
    return _render(
        request,
        "races/office/enter_boats.html",
        {"boat-choices": "races/office/_boat_choices.html"},
        {
            "form": form,
            "series": series,
            "boats": boats,
            # Boats the series can't take yet: listed, but not tickable (slice 24).
            "lacking": {boat.pk for boat in boats if series.boats_lack(boat)},
            "ticked": ticked,
            "chosen": chosen,
            "query": query,
            "any_to_enter": unentered.exists(),
        },
    )


@committee_required
def change_entry_number(request, pk):
    """Change which YTC number a boat races on in one series (slice 25)."""
    entry = get_object_or_404(
        SeriesEntry.objects.for_club(request.club).select_related("series", "boat"),
        pk=pk,
    )
    series = entry.series
    if series.is_final:
        return _locked(request, series)
    if not entry.is_ytc:
        messages.error(request, f"{series} is not an RYA YTC series.")
        return redirect("races:office_series", series.pk)
    form = EntryNumberForm(_posted(request), instance=entry)
    if request.method == "POST" and form.is_valid():
        before = score_series(series)
        with transaction.atomic():
            form.save()
            recorded = audit.record(
                form.scoring_changes, request.user, form.cleaned_data.get("reason", "")
            )
        messages.success(
            request, f"{entry.boat} now races on her {entry.number_label}."
        )
        _say_what_moved(request, series, before, recorded)
        return redirect("races:office_series", series.pk)
    return render(
        request,
        "races/office/entry_number.html",
        {"form": form, "series": series, "entry": entry},
    )


@committee_required
def remove_entry(request, pk):
    entry = get_object_or_404(
        SeriesEntry.objects.for_club(request.club).select_related("series", "boat"),
        pk=pk,
    )
    series = entry.series
    if series.is_final:
        return _locked(request, series)
    numbers = sorted(entry.finishes.values_list("race__number", flat=True))
    if numbers:
        messages.error(
            request,
            f"{entry} cannot be removed from this series: it has results in "
            f"{audit.race_list(numbers)}, and removing it would lose them. A boat "
            "that has entered is scored for the whole series (RRS A2.2), so leave "
            "it entered: races it misses are scored DNC.",
        )
        return redirect("races:office_series", series.pk)
    form = RemovalForm(_posted(request), changes=audit.changes_to_delete(entry))
    if request.method == "POST" and form.is_valid():
        before = score_series(series)
        with transaction.atomic():
            recorded = audit.record(form.changes, request.user, form.reason_given())
            entry.delete()
            notifications.removed_from_series([entry], request)
        messages.success(request, f"{entry} removed from {series}.")
        _say_what_moved(request, series, before, recorded)
        return redirect("races:office_series", series.pk)
    return render(
        request,
        "races/office/remove.html",
        {
            "form": form,
            "series": series,
            "title": f"Remove {entry} from {series}?",
            "what": "entry",
        },
    )


def _locked(request, series):
    messages.error(request, FINAL_LOCKED)
    return redirect("races:office_series", series.pk)


FINAL_LOCKED = "This series' results are final. Reopen results to change it."


def _posted(request):
    # Not "request.POST or None": a confirmation page's POST can be empty, and
    # must still count as submitted.
    return request.POST if request.method == "POST" else None
