"""The admin site, aware of clubs (slice 11).

The race committee sets up boats, series and races in the Django admin. On a
club's address it shows only that club's rows (``ClubScopedAdmin`` in
``races/admin.py``). On the service's own address, which belongs to no club,
only the operator (a superuser) gets in.
"""

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig
from django.core.exceptions import PermissionDenied



class ClubAdminSite(admin.AdminSite):
    """At a club, the admin is for that club's race committee and administrators.

    Their access comes from their club membership (races/roles.py), not from
    Django's staff flag, which means nothing since slice 11. On the service's
    own address, only the operator (a superuser) gets in.
    """

    def has_permission(self, request):
        # Imported here: the admin site is built before the models are loaded.
        from .roles import is_committee

        club = getattr(request, "club", None)
        if club is None:
            return request.user.is_active and request.user.is_superuser
        return is_committee(request.user, club)

    def login(self, request, extra_context=None):
        # At a club, everyone logs in on the site's own login page, which
        # takes an email and knows about clubs. Someone logged in without the
        # role here is refused rather than sent round in circles.
        from django.contrib.auth.views import redirect_to_login  # needs the models loaded

        if getattr(request, "club", None) is None:
            return super().login(request, extra_context)
        if request.user.is_authenticated:
            raise PermissionDenied
        return redirect_to_login(request.GET.get("next", request.path))


class ClubAdminConfig(AdminConfig):
    default_site = "races.admin_site.ClubAdminSite"
