import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from genai.integrations.registry import IntegrationRegistry
from genai.models import Integration, IntegrationHealthCheck


class Command(BaseCommand):
    help = "Run health checks for configured integrations."

    def add_arguments(self, parser):
        parser.add_argument("--integration-type", default="", help="Only check one integration type.")
        parser.add_argument("--fail-after", type=int, default=3, help="Mark disabled after N consecutive failures. Use 0 to never disable.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = Integration.objects.filter(enabled=True).select_related("credential").order_by("category", "name")
        integration_type = str(options.get("integration_type") or "").strip()
        if integration_type:
            queryset = queryset.filter(integration_type=integration_type)
        checked = healthy = failing = disabled = 0
        for integration in queryset:
            checked += 1
            started = time.perf_counter()
            ok = False
            message = ""
            try:
                adapter = IntegrationRegistry.get_adapter(integration)
                ok = bool(adapter.test_connection())
                message = "Connection successful." if ok else "Connection failed."
            except Exception as exc:
                message = str(exc)
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            status = "healthy" if ok else "failing"
            if ok:
                healthy += 1
            else:
                failing += 1
            if not options["dry_run"]:
                IntegrationHealthCheck.objects.create(
                    integration=integration,
                    status=status,
                    latency_ms=latency_ms,
                    message=message,
                    details_json={"integration_type": integration.integration_type, "scheduled": True},
                )
                integration.health_status = status
                integration.last_health_check_at = timezone.now()
                update_fields = ["health_status", "last_health_check_at", "updated_at"]
                fail_after = int(options.get("fail_after") or 0)
                if fail_after > 0 and not ok:
                    recent = list(integration.health_checks.order_by("-checked_at").values_list("status", flat=True)[:fail_after])
                    if len(recent) >= fail_after and all(item == "failing" for item in recent):
                        integration.enabled = False
                        disabled += 1
                        update_fields.append("enabled")
                integration.save(update_fields=update_fields)
            self.stdout.write(f"{integration.integration_type}:{integration.name} {status} {latency_ms}ms {message}")
        self.stdout.write(self.style.SUCCESS(f"checked={checked} healthy={healthy} failing={failing} disabled={disabled}"))
