from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Boat, Race, Series, SeriesEntry


@admin.register(Boat)
class BoatAdmin(admin.ModelAdmin):
    list_display = ["sail_number", "name", "make", "model", "base_number", "owner_name"]
    search_fields = ["sail_number", "name", "owner_name"]


class SeriesEntryInline(admin.TabularInline):
    model = SeriesEntry
    extra = 0
    autocomplete_fields = ["boat"]


class RaceInline(admin.TabularInline):
    model = Race
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
    list_display = ["name", "series_type", "discards"]
    fieldsets = [
        (None, {"fields": ["name", "series_type"]}),
        ("Scoring rules", {"fields": ["discards", "minimum_finishers", "apply_a5_3"]}),
    ]
    inlines = [SeriesEntryInline, RaceInline]
