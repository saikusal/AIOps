"""
Migration 0028 — ExecutionIntent rollback_snapshot_json
=========================================================
Adds rollback_snapshot_json to ExecutionIntent for storing pre-execution
DB state captures used to generate data-safe rollback commands.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0027_remediation_safety"),
    ]

    operations = [
        migrations.AddField(
            model_name="executionintent",
            name="rollback_snapshot_json",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Pre-execution DB state snapshot for data-safe rollback generation.",
            ),
        ),
    ]
