from django.core.management.base import BaseCommand

from genai.predictions import store_snapshot
from genai.views import _build_application_overview


class Command(BaseCommand):
    help = "Capture prediction feature snapshots from the current application overview."

    def handle(self, *args, **options):
        overview = _build_application_overview(include_ai=False, include_predictions=False)
        count = 0
        for application in overview.get("results", []):
            for component in application.get("components", []):
                store_snapshot(
                    {
                        **component,
                        "application": application["application"],
                    }
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Captured {count} prediction snapshots."))
