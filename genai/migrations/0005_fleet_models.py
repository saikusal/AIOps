# Generated manually for fleet Phase 2
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0004_chatsession_chatmessage_incident_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TelemetryProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("summary", models.TextField(blank=True, default="")),
                ("default_for_target", models.CharField(default="linux", max_length=32)),
                ("components", models.JSONField(blank=True, default=list)),
                ("capabilities", models.JSONField(blank=True, default=list)),
                ("config_json", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Target",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_id", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("name", models.CharField(max_length=160)),
                ("target_type", models.CharField(default="linux", max_length=32)),
                ("environment", models.CharField(blank=True, default="production", max_length=64)),
                ("hostname", models.CharField(blank=True, default="", max_length=255)),
                ("ip_address", models.CharField(blank=True, default="", max_length=64)),
                ("os_name", models.CharField(blank=True, default="", max_length=120)),
                ("os_version", models.CharField(blank=True, default="", max_length=120)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("connected", "Connected"), ("warning", "Warning"), ("degraded", "Degraded"), ("disconnected", "Disconnected")], default="pending", max_length=32)),
                ("collector_status", models.CharField(default="pending", max_length=32)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("enrolled_at", models.DateTimeField(auto_now_add=True)),
                ("last_heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="targets", to="genai.telemetryprofile")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="TargetHeartbeat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="heartbeats", to="genai.target")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TargetComponent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("version", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(default="pending", max_length=32)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="components", to="genai.target")),
            ],
            options={"ordering": ["name"], "unique_together": {("target", "name")}},
        ),
        migrations.CreateModel(
            name="DiscoveredService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_name", models.CharField(max_length=160)),
                ("process_name", models.CharField(blank=True, default="", max_length=160)),
                ("port", models.PositiveIntegerField(blank=True, null=True)),
                ("status", models.CharField(default="observed", max_length=32)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discovered_services", to="genai.target")),
            ],
            options={"ordering": ["service_name"], "unique_together": {("target", "service_name", "port")}},
        ),
        migrations.CreateModel(
            name="EnrollmentToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(db_index=True, max_length=96, unique=True)),
                ("target_type", models.CharField(default="linux", max_length=32)),
                ("target_name", models.CharField(blank=True, default="", max_length=160)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked", models.BooleanField(default=False)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_enrollment_tokens", to=settings.AUTH_USER_MODEL)),
                ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="enrollment_tokens", to="genai.telemetryprofile")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
