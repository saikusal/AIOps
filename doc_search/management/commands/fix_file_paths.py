import os
from django.core.management.base import BaseCommand
from django.conf import settings
from doc_search.models import Document
from django.core.files.base import ContentFile

class Command(BaseCommand):
    help = 'Finds documents saved in the wrong location and moves them to the correct subdirectory.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting to check for misplaced document files..."))
        
        # The correct subdirectory where files should be.
        upload_subdir = 'documents'
        
        # Get all document records from the database.
        documents = Document.objects.all()
        moved_count = 0

        for doc in documents:
            # Check if the file path already starts with the correct subdirectory.
            if not doc.file.name.startswith(upload_subdir + '/'):
                # This is a misplaced file.
                old_path = doc.file.path
                old_filename = os.path.basename(doc.file.name)
                new_name = os.path.join(upload_subdir, old_filename)
                new_path = os.path.join(settings.MEDIA_ROOT, new_name)

                self.stdout.write(f"Found misplaced file: '{doc.file.name}'. Moving to '{new_name}'...")

                if os.path.exists(old_path):
                    try:
                        # Ensure the target directory exists.
                        os.makedirs(os.path.dirname(new_path), exist_ok=True)
                        
                        # Move the physical file.
                        os.rename(old_path, new_path)
                        
                        # Update the database record to point to the new path.
                        doc.file.name = new_name
                        doc.save()
                        
                        self.stdout.write(self.style.SUCCESS(f"Successfully moved and updated '{old_filename}'."))
                        moved_count += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Could not move file '{old_filename}': {e}"))
                else:
                    self.stdout.write(self.style.WARNING(f"File not found at old path: '{old_path}'. Skipping."))

        if moved_count == 0:
            self.stdout.write(self.style.SUCCESS("No misplaced files found. All documents are in the correct location."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Finished. Successfully moved {moved_count} file(s)."))
