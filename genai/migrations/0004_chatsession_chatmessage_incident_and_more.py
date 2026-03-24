from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("genai", "0003_predictionsnapshot_serviceprediction"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("context_json", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_activity_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="aiops_chat_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="Incident",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("incident_key", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("application", models.CharField(blank=True, default="", max_length=120)),
                ("title", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("open", "Open"), ("investigating", "Investigating"), ("resolved", "Resolved")], default="open", max_length=32)),
                ("severity", models.CharField(blank=True, default="warning", max_length=32)),
                ("primary_service", models.CharField(blank=True, default="", max_length=120)),
                ("target_host", models.CharField(blank=True, default="", max_length=255)),
                ("summary", models.TextField(blank=True, default="")),
                ("reasoning", models.TextField(blank=True, default="")),
                ("blast_radius", models.JSONField(blank=True, default=list)),
                ("dependency_graph", models.JSONField(blank=True, default=dict)),
                ("labels", models.JSONField(blank=True, default=dict)),
                ("annotations", models.JSONField(blank=True, default=dict)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="IncidentTimelineEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("detail", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="timeline", to="genai.incident")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="IncidentAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alert_name", models.CharField(max_length=255)),
                ("alert_fingerprint", models.CharField(blank=True, default="", max_length=255)),
                ("status", models.CharField(default="firing", max_length=32)),
                ("target_host", models.CharField(blank=True, default="", max_length=255)),
                ("service_name", models.CharField(blank=True, default="", max_length=120)),
                ("labels", models.JSONField(blank=True, default=dict)),
                ("annotations", models.JSONField(blank=True, default=dict)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="genai.incident")),
            ],
            options={"ordering": ["-last_seen_at"]},
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("user", "User"), ("assistant", "Assistant"), ("system", "System")], max_length=16)),
                ("content", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="genai.chatsession")),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
