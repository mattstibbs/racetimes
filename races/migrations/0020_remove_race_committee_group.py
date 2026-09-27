"""Remove the old "Race committee" permission group.

Migration 0005 made it, when the race committee was staff in this group.
Since slice 11 a role belongs to a membership of a club (ClubMembership), and
the group grants nothing: races/roles.py never reads it. Migration 0015 has
already turned its members into Demo Club committee memberships.

Deleting it removes its links to permissions and to any accounts in it, and
nothing else. Going back recreates it as 0005 made it.
"""

from importlib import import_module

from django.db import migrations

GROUP = "Race committee"


def remove_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP).delete()


def recreate_group(apps, schema_editor):
    # 0005's own function, so the group comes back with the same permissions.
    import_module("races.migrations.0005_race_committee_group").create_group(
        apps, schema_editor
    )


class Migration(migrations.Migration):
    dependencies = [
        ("races", "0019_series_nhc_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(remove_group, recreate_group)]
