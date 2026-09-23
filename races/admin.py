from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.formsets import DELETION_FIELD_NAME
from django.urls import reverse
from django.utils.html import format_html

from . import audit
from .forms import (
    AuditedInlineForm,
    AuditedInlineFormSet,
    BoatAdminForm,
    RaceInlineFormSet,
    SeriesAdminForm,
)
from .models import Boat, Race, Series, SeriesEntry
from .scoring import score_series

# The admin wraps each save in a transaction, so a change and its history rows
# are saved together or not at all.


@admin.register(Boat)
class BoatAdmin(admin.ModelAdmin):
    form = BoatAdminForm
    list_display = ["sail_number", "name", "make", "model", "base_number", "owner_name"]
    search_fields = ["sail_number", "name", "owner_name"]

    def save_model(self, request, obj, form, change):
        series_list = list(Series.objects.filter(entries__boat=obj).distinct()) if change else []
        before = {series.pk: score_series(series) for series in series_list}
        super().save_model(request, obj, form, change)
        recorded = audit.record(form.scoring_changes, request.user, form.cleaned_data["reason"])
        if audit.needs_reason(recorded):
            for series in series_list:
                effect = audit.describe_effect(before[series.pk], score_series(series))
                messages.info(request, f"{series}: {effect}")


class SeriesEntryInline(admin.TabularInline):
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


class RaceInline(admin.TabularInline):
    model = Race
    form = AuditedInlineForm
    formset = RaceInlineFormSet
    extra = 0
    readonly_fields = ["finishes_link"]

    @admin.display(description="Finishes")
    def finishes_link(self, race):
        if not race.pk:
            return ""
        return format_html(
            '<a href="{}">Enter finishes</a>', reverse("races:finish_entry", args=[race.pk])
        )


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    form = SeriesAdminForm
    list_display = ["name", "series_type", "discards"]
    fieldsets = [
        (None, {"fields": ["name", "series_type"]}),
        ("Scoring rules", {"fields": ["discards", "minimum_finishers", "apply_a5_3"]}),
        ("Corrections", {"fields": ["reason", "history_link"]}),
    ]
    readonly_fields = ["history_link"]
    inlines = [SeriesEntryInline, RaceInline]

    @admin.display(description="History")
    def history_link(self, series):
        if not series.pk:
            return ""
        return format_html(
            '<a href="{}">Scoring history</a>', reverse("races:series_history", args=[series.pk])
        )

    def save_model(self, request, obj, form, change):
        # Scored now, before anything is saved, to say afterwards what moved.
        form.scoring_before = score_series(Series.objects.get(pk=obj.pk)) if change else None
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

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.scoring_before is not None and audit.needs_reason(form.recorded):
            effect = audit.describe_effect(form.scoring_before, score_series(form.instance))
            messages.info(request, f"Correction recorded. {effect}")
