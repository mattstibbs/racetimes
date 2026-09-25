"""Slice 11 part 2: everyone keeps the access they had, as a membership of the first club.

Before clubs, roles were site-wide:
- the administrator was a superuser;
- the race committee was staff in the "Race committee" group;
- a member was any active account;
- a new sign-up waited, switched off and never logged in, until the
  administrator approved it.

Each becomes a membership of the first club (Demo Club):

| Before                                    | Membership                    |
|-------------------------------------------|-------------------------------|
| superuser                                 | administrator, approved       |
| staff in the Race committee group         | race committee, approved      |
| any other active account                  | member, approved              |
| switched off, never logged in (waiting)   | member, waiting               |
| switched off after logging in             | member, removed               |

A waiting sign-up's account is switched on. Under slice 11 an account can
log in once its email is confirmed, and it's the membership that waits.
These people typed their email when they signed up, before confirmation
existed, so they aren't made to confirm it now.

The group and the staff flags are left in place, but nothing reads them any
more. The superuser stays a superuser: that's now the service's operator.
"""

import os

from django.conf import settings
from django.db import migrations
from django.utils import timezone


def memberships(apps, schema_editor):
    Club = apps.get_model("races", "Club")
    Membership = apps.get_model("races", "ClubMembership")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    club = Club.objects.filter(subdomain=os.environ.get("FIRST_CLUB_SUBDOMAIN", "demo")).first()
    if club is None:
        return
    now = timezone.now()
    for user in User.objects.all():
        in_committee = user.is_staff and user.groups.filter(name="Race committee").exists()
        if user.is_superuser:
            role, status = "ADMINISTRATOR", "APPROVED"
        elif in_committee:
            role, status = "COMMITTEE", "APPROVED"
        elif user.is_active:
            role, status = "MEMBER", "APPROVED"
        elif user.last_login is None:
            role, status = "MEMBER", "WAITING"
            user.is_active = True
            user.save(update_fields=["is_active"])
        else:
            role, status = "MEMBER", "REMOVED"
        Membership.objects.get_or_create(
            user=user, club=club,
            defaults={"role": role, "status": status,
                      "decided_at": now if status != "WAITING" else None,
                      "decided_by_name": "(moved from site-wide roles)" if status != "WAITING" else ""},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("races", "0014_club_memberships"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(memberships, migrations.RunPython.noop)]
