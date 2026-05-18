from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0029_alter_alertevent_tenant_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantmembership",
            name="extra_permissions",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
