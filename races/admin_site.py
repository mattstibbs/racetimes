"""The admin site, aware of clubs (slice 11).

The race committee sets up boats, series and races in the Django admin. On a
club's address it shows only that club's rows (``ClubScopedAdmin`` in
``races/admin.py``). On the service's own address, which belongs to no club,
only the operator (a superuser) gets in.
"""

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig


class ClubAdminSite(admin.AdminSite):
    def has_permission(self, request):
        if getattr(request, "club", None) is None and not request.user.is_superuser:
            return False
        return super().has_permission(request)


class ClubAdminConfig(AdminConfig):
    default_site = "races.admin_site.ClubAdminSite"
