from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0007_sla_runbook"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestigationRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("route", models.CharField(default="investigation", max_length=32)),
                ("question", models.TextField()),
                ("application", models.CharField(blank=True, default="", max_length=120)),
                ("service", models.CharField(blank=True, default="", max_length=120)),
                ("target_host", models.CharField(blank=True, default="", max_length=255)),
                ("scope_json", models.JSONField(blank=True, default=dict)),
                ("evidence_summary", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="running", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("incident", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="investigation_runs", to="genai.incident")),
                ("session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="investigation_runs", to="genai.chatsession")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="aiops_investigation_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="ToolInvocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("invocation_id", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("server_name", models.CharField(max_length=64)),
                ("tool_name", models.CharField(max_length=128)),
                ("request_json", models.JSONField(blank=True, default=dict)),
                ("response_json", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("success", "Success"), ("error", "Error")], default="success", max_length=16)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("error_detail", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("incident", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tool_invocations", to="genai.incident")),
                ("investigation_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tool_invocations", to="genai.investigationrun")),
                ("session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tool_invocations", to="genai.chatsession")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="aiops_tool_invocations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
