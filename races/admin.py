from django.contrib import admin

from .models import Boat


@admin.register(Boat)
class BoatAdmin(admin.ModelAdmin):
    list_display = ["sail_number", "name", "make", "model", "base_number", "owner_name"]
    search_fields = ["sail_number", "name", "owner_name"]
