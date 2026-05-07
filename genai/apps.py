from django.apps import AppConfig


class GenaiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'genai'

    def ready(self):
        """
        This method is called when the Django app is ready.
        It's the perfect place to initialize our simple cache.
        """
        from .semantic_cache import simple_cache
        import threading

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
        except ImportError:
            pass
