from django.core.management.base import BaseCommand

from genai.views import _ensure_target_policy_profiles


class Command(BaseCommand):
    help = "Seed or refresh default target policy profiles for Track 1."

    def handle(self, *args, **options):
        profiles = _ensure_target_policy_profiles()
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(profiles)} target policy profile(s)."))
