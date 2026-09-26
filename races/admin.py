import json

from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.core.exceptions import ValidationError
from django.forms.formsets import DELETION_FIELD_NAME
from django.urls import reverse
from django.utils.html import format_html

from . import audit, notifications
from .forms import (
    AuditedInlineForm,
    AuditedInlineFormSet,
    BoatAdminForm,
    RaceInlineFormSet,
    SeriesAdminForm,
)
from .models import Boat, BoatRequest, ClubMembership, EntryRequest, Race, Series, SeriesEntry
from .roles import is_committee
from .scoring import score_series

# The admin wraps each save in a transaction, so a change and its history rows
# are saved together or not at all.


# --- Clubs (slice 11) -----------------------------------------------------------------


class ClubScopedAdmin:
    """Shows and edits only the current club's rows.

    On a club's address, lists, searches, choice lists and new rows all belong
    to ``request.club``. On the service's own address only the operator gets
    into the admin at all (races/admin_site.py), and sees every club.
    """

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if request.club is None else queryset.for_club(request.club)

    # Permission comes from the club membership (slice 11 part 2): this club's
    # race committee and administrators may set things up here. Django's own
    # per-model permissions, which came from the old site-wide group, aren't
    # consulted. On the service's own address, only the operator.
    def has_module_permission(self, request):
        return _may_set_up(request)

    def has_view_permission(self, request, obj=None):
        return _may_set_up(request)

    def has_add_permission(self, request, *args):
        return _may_set_up(request)

    def has_change_permission(self, request, obj=None):
        return _may_set_up(request)

    def has_delete_permission(self, request, obj=None):
        return _may_set_up(request)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.club = request.club  # a new boat or series joins this club
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        return super().formfield_for_foreignkey(db_field, request, **_club_choices(db_field, request, kwargs))


def _may_set_up(request):
    if request.club is None:
        return request.user.is_active and request.user.is_superuser
    return is_committee(request.user, request.club)


def _club_choices(db_field, request, kwargs):
    """Only this club's boats and series in a choice list, including autocomplete ones."""
    if request.club is not None and db_field.related_model in (Boat, Series):
        kwargs["queryset"] = db_field.related_model.objects.for_club(request.club)
    return kwargs


class ClubScopedInline(ClubScopedAdmin):
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        return super().formfield_for_foreignkey(db_field, request, **_club_choices(db_field, request, kwargs))


# Clubs and memberships aren't in the admin. The operator creates clubs and
# invites their administrators on the operator's pages (races/operator_views.py,
# slice 11 part 3); a club's administrators manage its people on its Members page.


def _operator_here(request):
    """The operator, on the service's own address (which belongs to no club)."""
    return request.club is None and request.user.is_active and request.user.is_superuser


class ReasonInAdminHistoryMixin:
    """Puts the reason for a change into the admin's own History page.

    Django's log lists which form fields changed, not their values, so it
    showed "Changed Discards and Reason for change." - naming the reason box as
    if it were a field of the record, and losing what was typed in it. Here the
    box is taken out of the field list and its text added at the end.
    """

    def construct_change_message(self, request, form, formsets, add=False):
        message = super().construct_change_message(request, form, formsets, add)
        reason = form.cleaned_data.get("reason", "").strip()
        label = str(form.fields["reason"].label)
        for part in message:
            fields = part.get("changed", {}).get("fields")
            if fields and label in fields:
                fields.remove(label)
        message = [part for part in message if part.get("changed", {}).get("fields", True)]
        if not reason or not message:
            return message
        # Rendered to text here, because the log's structured format has no
        # place for a free-text note.
        text = LogEntry(change_message=json.dumps(message)).get_change_message()
        return f"{text} Reason: {reason}"


def boat_changes(before, after):
    """(label, old, new) for every field that differs between two versions of a boat."""
    changes = []
    for field in Boat._meta.concrete_fields:
        if field.primary_key:
            continue
        name = field.attname
        if getattr(before, name) == getattr(after, name):
            continue
        if field.name == "owner":
            old, new = before.owner_display or "", after.owner_display or ""
        else:
            old, new = getattr(before, field.name), getattr(after, field.name)
        label = field.verbose_name[:1].upper() + field.verbose_name[1:]
        changes.append((label, "" if old is None else str(old), "" if new is None else str(new)))
    return changes


@admin.register(Boat)
class BoatAdmin(ClubScopedAdmin, ReasonInAdminHistoryMixin, admin.ModelAdmin):
    form = BoatAdminForm
    list_display = ["sail_number", "name", "make", "model", "base_number", "owner_display"]
    search_fields = ["sail_number", "name", "owner_name", "owner__first_name", "owner__last_name"]

    @admin.display(description="Owner")
    def owner_display(self, boat):
        return boat.owner_display

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # A plain list of active accounts. Django's search box would need
        # permission to browse accounts, which the committee does not have.
        if db_field.name == "owner":
            # Only this club's approved members can own its boats (slice 11).
            kwargs["queryset"] = get_user_model().objects.filter(
                is_active=True, memberships__club=request.club,
                memberships__status=ClubMembership.Status.APPROVED,
            ).order_by("first_name", "last_name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        series_list = list(Series.objects.for_club(obj.club).filter(entries__boat=obj).distinct()) if change else []
        before = {series.pk: score_series(series) for series in series_list}
        stored = Boat.objects.for_club(obj.club).select_related("owner").get(pk=obj.pk) if change else None
        super().save_model(request, obj, form, change)
        if stored is not None:
            # The owner hears about any change the committee makes to their
            # boat; if the owner itself changed, the previous owner hears too.
            owners = [obj.owner]
            if stored.owner_id != obj.owner_id:
                owners.append(stored.owner)
            notifications.boat_updated(obj, boat_changes(stored, obj), owners, request)
        recorded = audit.record(form.scoring_changes, request.user, form.cleaned_data["reason"])
        if audit.needs_reason(recorded):
            for series in series_list:
                effect = audit.describe_effect(before[series.pk], score_series(series))
                messages.info(request, f"{series}: {effect}")


class SeriesEntryInline(ClubScopedInline, admin.TabularInline):
    model = SeriesEntry
    form = AuditedInlineForm
    formset = AuditedInlineFormSet
    extra = 0
    autocomplete_fields = ["boat"]

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class Form(formset.form):
            def hand_clean_DELETE(self):
                # The admin's own message here lists "protected related
                # objects"; say what it means for a race committee instead.
                if self.cleaned_data.get(DELETION_FIELD_NAME) and self.instance.pk:
                    numbers = sorted(
                        self.instance.finishes.values_list("race__number", flat=True)
                    )
                    if numbers:
                        raise ValidationError(
                            f"{self.instance} cannot be removed from this series: it has "
                            f"results in {audit.race_list(numbers)}, and removing it would "
                            "lose them. A boat that has entered is scored for the whole "
                            "series (RRS A2.2), so leave it entered: races it misses are "
                            "scored DNC."
                        )
                super().hand_clean_DELETE()

        formset.form = Form
        return formset


class RaceInline(ClubScopedInline, admin.TabularInline):
    model = Race
    form = AuditedInlineForm
    formset = RaceInlineFormSet
    extra = 0
    readonly_fields = ["finishes_link"]

    @admin.display(description="Race day")
    def finishes_link(self, race):
        if not race.pk:
            return ""
        return format_html(
            '<a href="{}">Race day page</a>', reverse("races:race_day", args=[race.pk])
        )


@admin.register(Series)
class SeriesAdmin(ClubScopedAdmin, ReasonInAdminHistoryMixin, admin.ModelAdmin):
    form = SeriesAdminForm
    list_display = ["name", "series_type", "discards"]
    fieldsets = [
        (None, {"fields": ["name", "series_type"]}),
        ("Scoring rules", {"fields": [
            "discards", "minimum_finishers", "apply_a5_3",
            # Slice 14: the optional extra NHC steps (nhc/options.py).
            "nhc_cap_extremes", "nhc_realign_to_base",
        ]}),
        ("Corrections", {"fields": ["reason", "history_link"]}),
    ]
    readonly_fields = ["history_link"]
    inlines = [SeriesEntryInline, RaceInline]

    @admin.display(description="History")
    def history_link(self, series):
        if not series.pk:
            return ""
        return format_html(
            '<a href="{}">Scoring history</a> &middot; <a href="{}">Final results</a>',
            reverse("races:series_history", args=[series.pk]),
            reverse("races:final", args=[series.pk]),
        )

    def save_model(self, request, obj, form, change):
        # Scored now, before anything is saved, to say afterwards what moved.
        form.scoring_before = score_series(Series.objects.for_club(obj.club).get(pk=obj.pk)) if change else None
        form.recorded = []
        super().save_model(request, obj, form, change)
        form.recorded += audit.record(
            form.scoring_changes, request.user, form.cleaned_data["reason"]
        )

    def save_formset(self, request, form, formset, change):
        reason = form.cleaned_data["reason"]
        # Removals are recorded while the rows still exist, additions once they do.
        form.recorded += audit.record(formset.removal_changes, request.user, reason)
        super().save_formset(request, form, formset, change)
        form.recorded += audit.record(formset.changes_to_record(), request.user, reason)
        if formset.model is SeriesEntry:
            notifications.entered_in_series(formset.new_objects, request)
            notifications.removed_from_series(formset.deleted_objects, request)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.scoring_before is not None and audit.needs_reason(form.recorded):
            effect = audit.describe_effect(form.scoring_before, score_series(form.instance))
            messages.info(request, f"Correction recorded. {effect}")


# --- Members' requests: read-only here, decided on the Requests page ----------


class RequestAdmin(ClubScopedAdmin, admin.ModelAdmin):
    list_filter = ["status"]
    readonly_fields = ["decided_by"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Deciding a request applies it; changing its status here would not.
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # a request is a record of what was asked and decided

    def changelist_view(self, request, extra_context=None):
        messages.info(request, format_html(
            'Requests are approved or rejected on the <a href="{}">Requests page</a>.',
            reverse("races:requests"),
        ))
        return super().changelist_view(request, extra_context)


@admin.register(BoatRequest)
class BoatRequestAdmin(RequestAdmin):
    list_display = ["created_at", "kind", "boat", "sail_number", "requested_by", "status", "decided_by_name"]


@admin.register(EntryRequest)
class EntryRequestAdmin(RequestAdmin):
    list_display = ["created_at", "boat", "series", "requested_by", "status", "decided_by_name"]


# --- Accounts and groups: the operator's alone ---------------------------------------
#
# Since slice 11, a club's administrator manages its people on the club's
# Members page (races/membership_views.py), never here. Accounts span every
# club, so the Django admin for them is the operator's, on the service's own
# address only.

User = get_user_model()
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class OperatorAccountAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "is_active", "is_superuser", "date_joined"]

    def has_module_permission(self, request):
        return _operator_here(request)

    def has_view_permission(self, request, obj=None):
        return _operator_here(request)

    def has_add_permission(self, request):
        return _operator_here(request)

    def has_change_permission(self, request, obj=None):
        return _operator_here(request)

    def has_delete_permission(self, request, obj=None):
        return _operator_here(request)


@admin.register(Group)
class OperatorGroupAdmin(GroupAdmin):
    def has_module_permission(self, request):
        return _operator_here(request)

    def has_view_permission(self, request, obj=None):
        return _operator_here(request)
