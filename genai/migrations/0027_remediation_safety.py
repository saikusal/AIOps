"""
Migration 0027 — Remediation Safety
=====================================
Adds all model changes required for the remediation safety work:

  - PolicyPack model (environment-aware policy packs)
  - ExecutionIntent: new status choices, break_glass fields, approver_identity,
    approval_reason, original_intent FK, policy_pack FK,
    estimated_blast_radius_json, requires_verification
"""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0026_alter_alertevent_unique_together"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # PolicyPack                                                           #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="PolicyPack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pack_id", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("environment_pattern", models.CharField(
                    blank=True,
                    default="",
                    help_text="Comma-separated environment names this pack applies to (e.g. 'production,prod').",
                    max_length=120,
                )),
                ("allow_diagnostic", models.BooleanField(default=True)),
                ("allow_restart_service", models.BooleanField(default=False)),
                ("allow_database_change", models.BooleanField(default=False)),
                ("allow_rollback", models.BooleanField(default=True)),
                ("allow_break_glass", models.BooleanField(default=False)),
                ("require_approval_for_restart", models.BooleanField(default=True)),
                ("require_approval_for_db_change", models.BooleanField(default=True)),
                ("require_approval_for_rollback", models.BooleanField(default=False)),
                ("max_blast_radius_without_approval", models.PositiveIntegerField(
                    default=1,
                    help_text="Blast radius count above which approval is always required.",
                )),
                ("max_executions_per_service_per_hour", models.PositiveIntegerField(default=10)),
                ("break_glass_requires_reason", models.BooleanField(default=True)),
                ("break_glass_notifies_admins", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),

        # ------------------------------------------------------------------ #
        # ExecutionIntent — new fields                                         #
        # ------------------------------------------------------------------ #

        # original_intent self-FK for rollback chains
        migrations.AddField(
            model_name="executionintent",
            name="original_intent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rollback_intents",
                to="genai.executionintent",
            ),
        ),

        # policy_pack FK
        migrations.AddField(
            model_name="executionintent",
            name="policy_pack",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="execution_intents",
                to="genai.policypack",
            ),
        ),

        # Break-glass fields
        migrations.AddField(
            model_name="executionintent",
            name="break_glass",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="executionintent",
            name="break_glass_reason",
            field=models.TextField(blank=True, default=""),
        ),

        # Enriched approval metadata
        migrations.AddField(
            model_name="executionintent",
            name="approver_identity",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="executionintent",
            name="approval_reason",
            field=models.TextField(blank=True, default=""),
        ),

        # Pre-execution blast radius estimate
        migrations.AddField(
            model_name="executionintent",
            name="estimated_blast_radius_json",
            field=models.JSONField(blank=True, default=dict),
        ),

        # Post-action verification gate flag
        migrations.AddField(
            model_name="executionintent",
            name="requires_verification",
            field=models.BooleanField(default=False),
        ),

        # Extended status choices — Django stores choices as varchar so
        # the underlying DB column already accepts any string; we just
        # update the in-Python validation via AlterField.
        migrations.AlterField(
            model_name="executionintent",
            name="status",
            field=models.CharField(
                choices=[
                    ("planned", "Planned"),
                    ("approval_required", "Approval Required"),
                    ("approved", "Approved"),
                    ("dry_run", "Dry Run"),
                    ("blocked", "Blocked"),
                    ("break_glass", "Break Glass"),
                    ("executing", "Executing"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("expired", "Expired"),
                    ("rollback_pending", "Rollback Pending"),
                    ("rolled_back", "Rolled Back"),
                    ("verification_pending", "Verification Pending"),
                    ("verified", "Verified"),
                ],
                default="planned",
                max_length=32,
            ),
        ),
    ]
