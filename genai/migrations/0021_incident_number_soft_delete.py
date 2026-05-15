from django.db import migrations, models


def backfill_incident_numbers(apps, schema_editor):
    Incident = apps.get_model("genai", "Incident")
    for incident in Incident.objects.filter(incident_number__isnull=True).order_by("id"):
        Incident.objects.filter(pk=incident.pk).update(incident_number=f"INC-{incident.pk:06d}")


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0020_seed_demo_targets"),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="delete_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="incident",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="incident",
            name="deleted_by_username",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="incident",
            name="incident_number",
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="incident",
            name="is_deleted",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(backfill_incident_numbers, migrations.RunPython.noop),
    ]
