"""Give every race already sailed a start sheet: the boats that have a finish.

From slice 6 only a boat on the start sheet can have a finish, so every
existing finish needs its boat on the sheet. Boats without a finish stay off,
so they score DNC exactly as they did before. No emails are sent from a
migration.
"""

from django.db import migrations


def fill_start_sheets(apps, schema_editor):
    Finish = apps.get_model("races", "Finish")
    RaceEntry = apps.get_model("races", "RaceEntry")
    pairs = Finish.objects.values_list("race_id", "entry_id").distinct()
    RaceEntry.objects.bulk_create(
        [RaceEntry(race_id=race_id, entry_id=entry_id) for race_id, entry_id in pairs]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("races", "0007_race_entry"),
    ]

    # Going back needs nothing: undoing 0007 removes the table and its rows.
    operations = [migrations.RunPython(fill_start_sheets, migrations.RunPython.noop)]
