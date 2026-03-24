from django.core.management.base import BaseCommand

from genai.predictions import train_model


class Command(BaseCommand):
    help = "Train the service-risk prediction model from stored prediction snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--min-rows", type=int, default=24)

    def handle(self, *args, **options):
        result = train_model(min_rows=options["min_rows"])
        if result["ok"]:
            self.stdout.write(self.style.SUCCESS(result["detail"]))
        else:
            self.stdout.write(self.style.WARNING(result["detail"]))
