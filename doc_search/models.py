from django.db import models
from django.contrib.auth.models import User
import os

class Document(models.Model):
    """
    Represents an uploaded document in the system.
    """
    title = models.CharField(max_length=255, null=True, blank=True)
    file = models.FileField(upload_to='documents/')
    source_url = models.URLField(max_length=2048, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('SUCCESS', 'Success'),
            ('FAILED', 'Failed'),
        ],
        default='PENDING'
    )

    def save(self, *args, **kwargs):
        if not self.title and self.file:
            self.title = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or os.path.basename(self.file.name)

class DocumentChunk(models.Model):
    """
    Stores a small chunk of text from a document.
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_text = models.TextField()
    chunk_index = models.IntegerField()

    def __str__(self):
        return f"Chunk {self.chunk_index} from {self.document}"

class DocumentImage(models.Model):
    """
    Stores an image extracted from a document.
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='document_images/')
    page_number = models.IntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image from {self.document.title or 'untitled'} (Page: {self.page_number or 'N/A'})"
