import os
import threading

from django.apps import AppConfig
from django.conf import settings


class GenaiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'genai'

    @staticmethod
    def _semantic_cache_enabled() -> bool:
        return os.getenv("AIOPS_SIMPLE_CACHE_ENABLED", "true").strip().lower() not in {"false", "0", "no"}

    @staticmethod
    def _semantic_cache_uses_redis() -> bool:
        backend = str(((getattr(settings, "CACHES", {}) or {}).get("default") or {}).get("BACKEND") or "").strip()
        return backend.startswith("django_redis.")

    def ready(self):
        """
        This method is called when the Django app is ready.
        It's the perfect place to initialize our simple cache.
        """
        if self._semantic_cache_enabled() and self._semantic_cache_uses_redis():
            from .semantic_cache import simple_cache

            # Run initialization in a separate thread to avoid blocking the main app startup
            init_thread = threading.Thread(target=simple_cache.initialize, daemon=True)
            init_thread.start()

        # Initialize Integrations registry
        try:
            import genai.integrations.vendors.prometheus
            import genai.integrations.vendors.opensearch
            import genai.integrations.vendors.tempo
            import genai.integrations.vendors.splunk
            import genai.integrations.vendors.dynatrace
            import genai.integrations.vendors.datadog
            import genai.integrations.vendors.aws
            import genai.integrations.vendors.misc
            import genai.integrations.vendors.alerts_itsm
            import genai.integrations.vendors.devops
        except ImportError:
            pass

        try:
            import genai.signals  # noqa: F401
        except ImportError:
            pass
