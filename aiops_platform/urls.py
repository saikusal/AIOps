"""aiops_platform URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView


def healthz(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('', RedirectView.as_view(url='/genai/widget/', permanent=False)),
    path('healthz/', healthz, name='healthz'),
    path('accounts/', include('allauth.urls')),
    path('genai/', include('genai.urls')),
    path('documents/', include('doc_search.urls')),
]

if os.getenv("ENABLE_DJANGO_ADMIN", "false").strip().lower() in {"1", "true", "yes", "on"}:
    urlpatterns.insert(0, path('admin/', admin.site.urls))

# This is the correct and standard way to serve static and media files in a
# development environment.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
