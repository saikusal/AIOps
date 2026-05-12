"""
Data migration: seed Target, TargetServiceBinding, and TargetLogSource records
for the three demo applications (app-inventory, app-orders, app-billing).

WHY THIS EXISTS
---------------
_elasticsearch_identity_clauses() in views.py builds ES filter queries by
looking up Target → TargetLogSource.file_path in the database.  Without these
records the function falls through to the broken demo-fallback path and returns
0 log hits, so the investigation agent never sees error messages.

PRODUCTION ONBOARDING
---------------------
When a real customer onboards a new application through the platform UI/API,
the onboarding handler (TargetOnboardingRequest approval flow) must create the
same three objects:
  1. Target           – the host/service identity
  2. TargetServiceBinding – links the target to a service_name (used by ES query)
  3. TargetLogSource  – stores the log file path (used by ES identity filter)
No code or Filebeat config changes are needed after that point.
"""

from django.db import migrations


DEMO_SERVICES = [
    {
        "hostname": "app-inventory",
        "name": "app-inventory",
        "service_name": "app-inventory",
        "container_name": "app-inventory",
        "log_file_path": "/var/log/demo/app-inventory.log",
    },
    {
        "hostname": "app-orders",
        "name": "app-orders",
        "service_name": "app-orders",
        "container_name": "app-orders",
        "log_file_path": "/var/log/demo/app-orders.log",
    },
    {
        "hostname": "app-billing",
        "name": "app-billing",
        "service_name": "app-billing",
        "container_name": "app-billing",
        "log_file_path": "/var/log/demo/app-billing.log",
    },
]


def seed_demo_targets(apps, schema_editor):
    Target = apps.get_model("genai", "Target")
    TargetServiceBinding = apps.get_model("genai", "TargetServiceBinding")
    TargetLogSource = apps.get_model("genai", "TargetLogSource")

    for svc in DEMO_SERVICES:
        # Target — get_or_create so re-running is safe
        target, _ = Target.objects.get_or_create(
            hostname=svc["hostname"],
            defaults={
                "name": svc["name"],
                "target_type": "docker",
                "environment": "demo",
                "status": "connected",
            },
        )

        # TargetServiceBinding — links target to the service_name ES queries on
        binding, _ = TargetServiceBinding.objects.get_or_create(
            target=target,
            service_name=svc["service_name"],
            service_kind="docker_container",
            container_name=svc["container_name"],
            defaults={
                "is_primary": True,
                "systemd_unit": "",
                "process_name": "",
            },
        )

        # TargetLogSource — the file_path _elasticsearch_identity_clauses uses
        TargetLogSource.objects.get_or_create(
            target=target,
            source_type="file",
            file_path=svc["log_file_path"],
            defaults={
                "service_binding": binding,
                "is_primary": True,
                "shipper_type": "filebeat",
                "parser_type": "python-structured",
                "container_name": svc["container_name"],
            },
        )


def remove_demo_targets(apps, schema_editor):
    """Reverse migration: remove only the demo seeds (safe to call even if already deleted)."""
    Target = apps.get_model("genai", "Target")
    Target.objects.filter(
        hostname__in=[s["hostname"] for s in DEMO_SERVICES],
        environment="demo",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("genai", "0019_integration_integrationhealthcheck_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_demo_targets, reverse_code=remove_demo_targets),
    ]
