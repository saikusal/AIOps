from django.core.management.base import BaseCommand
from transformers import pipeline
import ssl
ssl._create_default_https_context = ssl._create_default_https_context

class Command(BaseCommand):
    help = 'Downloads and caches the Generative AI model to avoid delays on first use.'

    def handle(self, *args, **options):
        self.stdout.write("Starting Generative AI model download...")
        try:
            # --- SSL Fix for Corporate Networks ---
            ssl._create_default_https_context = ssl._create_default_https_context
            # Using a small but SPECIALIZED Text-to-SQL model for accuracy and stability.
            pipeline('text2text-generation', model='cssupport/t5-small-awesome-text-to-sql')
            self.stdout.write(self.style.SUCCESS('Successfully downloaded and cached the Generative AI model.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to download model: {e}'))
            # Depending on the policy, you might want to exit with an error code
            # to fail the build process if the model is critical.
            # raise e
