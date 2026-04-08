from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0005_fleet_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TargetOnboardingRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("onboarding_id", models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ("target_type", models.CharField(default="linux", max_length=32)),
                ("name", models.CharField(max_length=160)),
                ("hostname", models.CharField(max_length=255)),
                ("ssh_user", models.CharField(default="ec2-user", max_length=120)),
                ("ssh_port", models.PositiveIntegerField(default=22)),
                ("pem_file", models.FileField(upload_to="fleet/pem/")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("validated", "Validated"), ("installing", "Installing"), ("installed", "Installed"), ("failed", "Failed")], default="draft", max_length=32)),
                ("connectivity_status", models.CharField(default="untested", max_length=32)),
                ("connectivity_message", models.TextField(blank=True, default="")),
                ("last_connectivity_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_install_at", models.DateTimeField(blank=True, null=True)),
                ("install_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_onboarding_requests", to=settings.AUTH_USER_MODEL)),
                ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="onboarding_requests", to="genai.telemetryprofile")),
                ("target", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="onboarding_requests", to="genai.target")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
