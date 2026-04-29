import os

def instrument():
    """
    Initializes OpenTelemetry instrumentation for the Django application
    if the OTEL_ENABLED environment variable is set to "true".
    
    This function sets up the tracer provider, exporter, and processors,
    and then applies automatic instrumentation for supported libraries.
    """
    if os.environ.get("OTEL_ENABLED", "false").lower() != "true":
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Get configuration from environment variables
    service_name = os.environ.get("OTEL_SERVICE_NAME", "aiops-web")
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # A Resource identifies the service that is producing the telemetry data.
    resource = Resource.create(attributes={
        "service.name": service_name
    })

    # The TracerProvider is the entry point of the API. It provides access to Tracers.
    provider = TracerProvider(resource=resource)

    # The OTLPSpanExporter sends trace data to an OTel Collector.
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

    # The BatchSpanProcessor receives spans and batches them for export.
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Set the global TracerProvider.
    trace.set_tracer_provider(provider)

    # --- Apply Automatic Instrumentation ---
    # This is the magic that automatically creates spans for common operations.
    
    # Instrument Django for web requests
    DjangoInstrumentor().instrument()

    # Instrument Psycopg2 for PostgreSQL database calls
    Psycopg2Instrumentor().instrument()

    # Instrument Redis for cache calls
    RedisInstrumentor().instrument()

    # Instrument the requests library for any outgoing HTTP calls
    RequestsInstrumentor().instrument()
    
    # Instrument the logging library to correlate logs with traces
    LoggingInstrumentor().instrument(set_logging_format=True)
