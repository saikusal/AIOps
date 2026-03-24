import time

from django.core.management.base import BaseCommand

from genai.predictions import score_components, store_snapshot
from genai.views import _build_application_overview


class Command(BaseCommand):
    help = "Continuously capture snapshots and score service predictions."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=300)

    def handle(self, *args, **options):
        interval = max(30, int(options["interval"]))
        self.stdout.write(self.style.SUCCESS(f"Starting prediction loop with interval={interval}s"))
        while True:
            overview = _build_application_overview(include_ai=False, include_predictions=False)
            components = []
            for application in overview.get("results", []):
                for component in application.get("components", []):
                    item = {**component, "application": application["application"]}
                    store_snapshot(item)
                    components.append(item)
            score_components(components, save_results=True)
            self.stdout.write(self.style.SUCCESS(f"Captured and scored {len(components)} services."))
            time.sleep(interval)
