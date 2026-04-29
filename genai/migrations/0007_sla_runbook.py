from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0006_targetonboardingrequest"),
    ]

    operations = [
        # SLAPolicy table
        migrations.CreateModel(
            name="SLAPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("priority", models.CharField(
                    choices=[("P1", "P1 - Critical"), ("P2", "P2 - High"), ("P3", "P3 - Medium"), ("P4", "P4 - Low")],
                    max_length=4, unique=True,
                )),
                ("response_minutes", models.PositiveIntegerField(default=60)),
                ("resolution_minutes", models.PositiveIntegerField(default=240)),
                ("escalation_contacts", models.JSONField(blank=True, default=list)),
            ],
            options={"ordering": ["priority"]},
        ),
        # New fields on Incident
        migrations.AddField(
            model_name="incident",
            name="priority",
            field=models.CharField(
                choices=[("P1", "P1 - Critical"), ("P2", "P2 - High"), ("P3", "P3 - Medium"), ("P4", "P4 - Low")],
                default="P3", max_length=4,
            ),
        ),
        migrations.AddField(
            model_name="incident",
            name="sla_response_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="incident",
            name="sla_resolution_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="incident",
            name="sla_response_acknowledged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Runbook table
        migrations.CreateModel(
            name="Runbook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "incident",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runbooks", to="genai.incident",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        # Seed default SLA policies
        migrations.RunPython(
            code=lambda apps, schema: [
                apps.get_model("genai", "SLAPolicy").objects.get_or_create(
                    priority=p, defaults={"response_minutes": resp, "resolution_minutes": res}
                )
                for p, (resp, res) in [("P1", (15, 60)), ("P2", (30, 240)), ("P3", (120, 480)), ("P4", (480, 1440))]
            ],
            reverse_code=migrations.RunPython.noop,
        ),
    ]
