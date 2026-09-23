from django.contrib import admin

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


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ["name", "series_type", "discards"]
    fieldsets = [
        (None, {"fields": ["name", "series_type"]}),
        ("Scoring rules", {"fields": ["discards", "minimum_finishers", "apply_a5_3"]}),
    ]
    inlines = [SeriesEntryInline, RaceInline]
