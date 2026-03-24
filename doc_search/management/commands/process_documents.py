import os
import fitz  # PyMuPDF
import django
from docx import Document as DocxDocument
from django.core.management.base import BaseCommand
from django.conf import settings
from doc_search.models import Document, DocumentChunk


class Command(BaseCommand):
    help = 'Processes uploaded documents to extract text, chunk it, and save chunks into the database.'

    def handle(self, *args, **options):
        self.stdout.write('Starting document processing...')
        
        # Pick up all pending docs
        pending_docs = Document.objects.filter(processing_status='PENDING')

        for doc in pending_docs:
            self.stdout.write(f'Processing document: {doc.file.name}')
            doc.processing_status = 'PROCESSING'
            doc.save()

            try:
                file_path = os.path.join(settings.MEDIA_ROOT, doc.file.name)
                text = ''

                # --- Extract text depending on file type ---
                if file_path.endswith('.pdf'):
                    with fitz.open(file_path) as pdf:
                        for page in pdf:
                            text += page.get_text()
                elif file_path.endswith('.docx'):
                    docx_doc = DocxDocument(file_path)
                    for para in docx_doc.paragraphs:
                        text += para.text + '\n'
                else:
                    self.stdout.write(self.style.WARNING(f'Unsupported file type: {doc.file.name}'))
                    doc.processing_status = 'FAILED'
                    doc.save()
                    continue

                # --- Split into chunks ---
                chunks = self.create_chunks(text)
                
                # --- Save chunks to DB ---
                for i, chunk_text in enumerate(chunks):
                    DocumentChunk.objects.create(
                        document=doc,
                        chunk_text=chunk_text,
                        chunk_index=i
                        
                    )
                
                doc.processing_status = 'SUCCESS'
                doc.save()
                self.stdout.write(self.style.SUCCESS(f'Successfully processed and chunked: {doc.file.name}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing {doc.file.name}: {e}'))
                doc.processing_status = 'FAILED'
                doc.save()

        self.stdout.write(self.style.SUCCESS('Document processing finished.'))

    def create_chunks(self, text, chunk_size=1000, overlap=200):
        """Splits text into overlapping chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks