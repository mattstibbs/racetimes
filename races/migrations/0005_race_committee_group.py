"""Create the "Race committee" permission group.

The committee is staff in this group. It grants the racing models and nothing
about users or groups, so the committee cannot manage accounts, their own
included; that is the administrator's (a superuser's) alone. Requests and the
change history are view-only in the admin: requests are decided on the
Requests page, which applies them, and the history is never edited.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP = "Race committee"

FULL = ["boat", "series", "seriesentry", "race", "finish"]
VIEW_ONLY = ["boatrequest", "entryrequest", "scoringchange"]


def create_group(apps, schema_editor):
    # Permissions are normally created after all migrations have run, so on a
    # fresh database they do not exist yet. Create them now.
    # The migration's stand-in app config lacks `models_module`, which
    # create_permissions checks only to skip apps with no models; set it for
    # the call.
    app_config = apps.get_app_config("races")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    codenames = [f"{action}_{model}" for model in FULL for action in ("add", "change", "delete", "view")]
    codenames += [f"view_{model}" for model in VIEW_ONLY]
    group, _ = Group.objects.get_or_create(name=GROUP)
    group.permissions.set(
        Permission.objects.filter(content_type__app_label="races", codename__in=codenames)
    )


def remove_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("races", "0004_member_requests"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_group, remove_group)]
