from django.urls import path
from . import views

app_name = 'doc_search'

urlpatterns = [
    # This single URL now handles both displaying the form and processing the upload.
    path('', views.document_manager, name='document_list'),
    path('search/', views.search_documents, name='search_documents'),
    path('service_request/', views.service_request_handler, name='service_request_handler'),
    path('delete/<int:doc_id>/', views.delete_document, name='delete_document'),
]
