"""
Management command: seed_policy_packs
======================================
Seeds three default environment-aware policy packs:

  production-strict   — production/prod environments
  staging-moderate    — staging/stage environments
  dev-open            — development/dev/test environments

Safe to run multiple times — uses update_or_create.
"""

from django.core.management.base import BaseCommand

from genai.models import PolicyPack

PACK_DEFINITIONS = [
    {
        "slug": "production-strict",
        "name": "Production — Strict",
        "description": (
            "Maximum safety constraints for production environments. "
            "All write actions require explicit approval. "
            "Break-glass is disabled by default. "
            "Blast radius above 1 service always triggers an approval gate."
        ),
        "environment_pattern": "production,prod",
        # Action permissions
        "allow_diagnostic": True,
        "allow_restart_service": True,
        "allow_database_change": False,
        "allow_rollback": True,
        "allow_break_glass": False,
        # Approval gates
        "require_approval_for_restart": True,
        "require_approval_for_db_change": True,
        "require_approval_for_rollback": True,
        # Blast radius threshold before approval is required
        "max_blast_radius_without_approval": 1,
        # Rate limits
        "max_executions_per_service_per_hour": 5,
        # Break-glass config (kept even though disabled by default)
        "break_glass_requires_reason": True,
        "break_glass_notifies_admins": True,
        "is_active": True,
    },
    {
        "slug": "staging-moderate",
        "name": "Staging — Moderate",
        "description": (
            "Balanced controls for staging and pre-production environments. "
            "Restarts are permitted; DB changes and break-glass require approval. "
            "Blast radius above 3 services triggers an approval gate."
        ),
        "environment_pattern": "staging,stage,preprod,pre-prod",
        # Action permissions
        "allow_diagnostic": True,
        "allow_restart_service": True,
        "allow_database_change": True,
        "allow_rollback": True,
        "allow_break_glass": True,
        # Approval gates
        "require_approval_for_restart": False,
        "require_approval_for_db_change": True,
        "require_approval_for_rollback": False,
        # Blast radius threshold
        "max_blast_radius_without_approval": 3,
        # Rate limits
        "max_executions_per_service_per_hour": 20,
        # Break-glass
        "break_glass_requires_reason": True,
        "break_glass_notifies_admins": True,
        "is_active": True,
    },
    {
        "slug": "dev-open",
        "name": "Development — Open",
        "description": (
            "Permissive policy for development and test environments. "
            "All action types are allowed without approval. "
            "Break-glass is enabled but still requires a reason for audit purposes."
        ),
        "environment_pattern": "development,dev,test,local",
        # Action permissions
        "allow_diagnostic": True,
        "allow_restart_service": True,
        "allow_database_change": True,
        "allow_rollback": True,
        "allow_break_glass": True,
        # Approval gates
        "require_approval_for_restart": False,
        "require_approval_for_db_change": False,
        "require_approval_for_rollback": False,
        # Blast radius threshold
        "max_blast_radius_without_approval": 10,
        # Rate limits
        "max_executions_per_service_per_hour": 100,
        # Break-glass
        "break_glass_requires_reason": True,
        "break_glass_notifies_admins": False,
        "is_active": True,
    },
]


class Command(BaseCommand):
    help = "Seed default environment-aware PolicyPack records."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for definition in PACK_DEFINITIONS:
            slug = definition["slug"]
            pack, created = PolicyPack.objects.update_or_create(
                slug=slug,
                defaults={k: v for k, v in definition.items() if k != "slug"},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created PolicyPack: {pack.name} ({slug})"))
            else:
                updated_count += 1
                self.stdout.write(f"  Updated PolicyPack: {pack.name} ({slug})")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created {created_count}, updated {updated_count} policy pack(s)."
            )
        )
