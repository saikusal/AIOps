from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0011_repositoryindex_symbolrelation_spanbinding_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="targetonboardingrequest",
            name="pem_file",
            field=models.FileField(blank=True, null=True, upload_to="fleet/pem/"),
        ),
        migrations.AlterField(
            model_name="targetonboardingrequest",
            name="ssh_user",
            field=models.CharField(blank=True, default="ec2-user", max_length=120),
        ),
    ]
