from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0002_alter_genaichathistory_question"),
    ]

    operations = [
        migrations.CreateModel(
            name="PredictionSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("application", models.CharField(max_length=120)),
                ("service", models.CharField(max_length=120)),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                ("metrics", models.JSONField(default=dict)),
                ("features", models.JSONField(default=dict)),
                ("incident_next_15m", models.BooleanField(default=False)),
            ],
            options={"ordering": ["-captured_at"]},
        ),
        migrations.CreateModel(
            name="ServicePrediction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("application", models.CharField(max_length=120)),
                ("service", models.CharField(max_length=120)),
                ("status", models.CharField(default="healthy", max_length=32)),
                ("risk_score", models.FloatField(default=0.0)),
                ("incident_probability", models.FloatField(default=0.0)),
                ("predicted_window_minutes", models.PositiveIntegerField(default=15)),
                ("model_version", models.CharField(default="heuristic-v1", max_length=120)),
                ("features", models.JSONField(default=dict)),
                ("blast_radius", models.JSONField(default=list)),
                ("explanation", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
