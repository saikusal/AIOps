import logging
import os
import time
import uuid
from pathlib import Path

import psycopg2
from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


APP_NAME = os.environ.get("APP_NAME", "demo-app")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", APP_NAME)
APP_PORT = int(os.environ.get("APP_PORT", "8000"))
DB_HOST = os.environ.get("DEMO_DB_HOST", "toxiproxy")
DB_PORT = int(os.environ.get("DEMO_DB_PORT", "15432"))
DB_NAME = os.environ.get("DEMO_DB_NAME", "aiops")
DB_USER = os.environ.get("DEMO_DB_USER", "user")
DB_PASSWORD = os.environ.get("DEMO_DB_PASSWORD", "password")
LOG_DIR = Path(os.environ.get("DEMO_LOG_DIR", "/var/log/demo"))
DEFAULT_DB_SLEEP = float(os.environ.get("APP_DEFAULT_DB_SLEEP", "0"))

REQUEST_COUNT = Counter(
    "demo_http_requests_total",
    "Total requests handled by the demo service.",
    ["service", "endpoint", "method", "status"],
)
REQUEST_LATENCY = Histogram(
    "demo_http_request_duration_seconds",
    "Request latency for the demo service.",
    ["service", "endpoint", "method", "status"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20),
)
DB_QUERY_LATENCY = Histogram(
    "demo_db_query_duration_seconds",
    "Database query latency for the demo service.",
    ["service", "query_type"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)
DB_ERRORS = Counter(
    "demo_db_errors_total",
    "Database errors encountered by the demo service.",
    ["service", "error_type"],
)
BUSINESS_EVENTS = Counter(
    "demo_business_events_total",
    "Successful business events handled by the demo service.",
    ["service", "event_type"],
)


class OpenTelemetryDefaults(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for field in ("otelTraceID", "otelSpanID", "otelServiceName"):
            if not hasattr(record, field):
                setattr(record, field, "-")
        return True


def configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s service=%(name)s otel_service=%(otelServiceName)s trace_id=%(otelTraceID)s span_id=%(otelSpanID)s %(message)s"
    )

    file_handler = logging.FileHandler(LOG_DIR / f"{APP_NAME}.log")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(OpenTelemetryDefaults())
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(OpenTelemetryDefaults())

    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


def instrument_otel() -> None:
    if os.environ.get("OTEL_ENABLED", "true").lower() != "true":
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    LoggingInstrumentor().instrument(set_logging_format=True)
    Psycopg2Instrumentor().instrument()
    RequestsInstrumentor().instrument()
    FlaskInstrumentor().instrument_app(app)


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )


logger = configure_logging()
app = Flask(__name__)
instrument_otel()


@app.before_request
def mark_start_time():
    request.environ["demo_start_time"] = time.perf_counter()


@app.after_request
def record_metrics(response):
    started_at = request.environ.get("demo_start_time")
    if started_at is not None:
        elapsed = time.perf_counter() - started_at
        labels = {
            "service": APP_NAME,
            "endpoint": request.path,
            "method": request.method,
            "status": str(response.status_code),
        }
        REQUEST_COUNT.labels(**labels).inc()
        REQUEST_LATENCY.labels(**labels).observe(elapsed)
        logger.info(
            "request_complete path=%s status=%s duration=%.4f client=%s",
            request.path,
            response.status_code,
            elapsed,
            request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    return response


def run_service_query(extra_sleep: float):
    total_sleep = max(DEFAULT_DB_SLEEP + extra_sleep, 0)
    query_started = time.perf_counter()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if total_sleep:
                cursor.execute("SELECT pg_sleep(%s)", (total_sleep,))
            cursor.execute(
                """
                SELECT service_name, state, notes, updated_at
                FROM demo_service_state
                WHERE service_name = %s
                ORDER BY updated_at DESC
                LIMIT 5
                """,
                (APP_NAME,),
            )
            rows = cursor.fetchall()
            if APP_NAME == "app-orders":
                cursor.execute(
                    """
                    SELECT COUNT(*)::int, COALESCE(MAX(created_at), NOW())
                    FROM demo_orders
                    """
                )
                total_events, last_event_at = cursor.fetchone()
            elif APP_NAME == "app-inventory":
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(available_quantity), 0)::int,
                           COALESCE(SUM(reserved_quantity), 0)::int
                    FROM demo_inventory
                    """
                )
                available_total, reserved_total = cursor.fetchone()
                total_events = available_total
                last_event_at = reserved_total
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*)::int, COALESCE(SUM(amount), 0)::numeric(10,2)
                    FROM demo_billing
                    """
                )
                total_events, last_event_at = cursor.fetchone()
    query_elapsed = time.perf_counter() - query_started
    DB_QUERY_LATENCY.labels(service=APP_NAME, query_type="primary").observe(query_elapsed)
    return rows, total_events, last_event_at, query_elapsed, total_sleep


def log_service_state(cursor, state: str, notes: str):
    cursor.execute(
        """
        INSERT INTO demo_service_state (service_name, state, notes)
        VALUES (%s, %s, %s)
        """,
        (APP_NAME, state, notes),
    )


def parse_write_payload():
    payload = request.get_json(silent=True) or {}
    return {
        "order_ref": payload.get("order_ref") or f"ord-{uuid.uuid4().hex[:8]}",
        "customer_name": payload.get("customer_name") or "Ajith Demo User",
        "sku": payload.get("sku") or "SKU-100",
        "quantity": int(payload.get("quantity") or 1),
        "amount": float(payload.get("amount") or 199.0),
        "db_sleep_seconds": float(payload.get("db_sleep_seconds") or 0),
    }


def handle_orders_write(cursor, payload):
    cursor.execute(
        """
        INSERT INTO demo_orders (order_ref, customer_name, sku, quantity, status)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            payload["order_ref"],
            payload["customer_name"],
            payload["sku"],
            payload["quantity"],
            "created",
        ),
    )
    order_id, created_at = cursor.fetchone()
    log_service_state(
        cursor,
        "healthy",
        f"Order {payload['order_ref']} created for {payload['customer_name']} ({payload['quantity']} x {payload['sku']}).",
    )
    return {
        "service": APP_NAME,
        "event": "order_created",
        "order_id": order_id,
        "order_ref": payload["order_ref"],
        "created_at": created_at.isoformat(),
    }


def handle_inventory_write(cursor, payload):
    cursor.execute(
        """
        SELECT product_name, available_quantity, reserved_quantity
        FROM demo_inventory
        WHERE sku = %s
        FOR UPDATE
        """,
        (payload["sku"],),
    )
    inventory_row = cursor.fetchone()
    if not inventory_row:
        raise ValueError(f"Unknown SKU {payload['sku']}")
    product_name, available_quantity, reserved_quantity = inventory_row
    if available_quantity < payload["quantity"]:
        raise RuntimeError(
            f"Insufficient inventory for {payload['sku']}: available={available_quantity}, requested={payload['quantity']}"
        )
    cursor.execute(
        """
        UPDATE demo_inventory
        SET available_quantity = available_quantity - %s,
            reserved_quantity = reserved_quantity + %s,
            updated_at = NOW()
        WHERE sku = %s
        RETURNING available_quantity, reserved_quantity, updated_at
        """,
        (payload["quantity"], payload["quantity"], payload["sku"]),
    )
    updated_available, updated_reserved, updated_at = cursor.fetchone()
    log_service_state(
        cursor,
        "healthy",
        f"Reserved {payload['quantity']} units of {payload['sku']} for order {payload['order_ref']}.",
    )
    return {
        "service": APP_NAME,
        "event": "inventory_reserved",
        "order_ref": payload["order_ref"],
        "sku": payload["sku"],
        "product_name": product_name,
        "available_quantity": updated_available,
        "reserved_quantity": updated_reserved,
        "updated_at": updated_at.isoformat(),
    }


def handle_billing_write(cursor, payload):
    cursor.execute(
        """
        INSERT INTO demo_billing (order_ref, amount, status)
        VALUES (%s, %s, %s)
        RETURNING id, created_at
        """,
        (payload["order_ref"], payload["amount"], "authorized"),
    )
    billing_id, created_at = cursor.fetchone()
    log_service_state(
        cursor,
        "healthy",
        f"Authorized payment of ${payload['amount']:.2f} for order {payload['order_ref']}.",
    )
    return {
        "service": APP_NAME,
        "event": "payment_authorized",
        "billing_id": billing_id,
        "order_ref": payload["order_ref"],
        "amount": payload["amount"],
        "created_at": created_at.isoformat(),
    }


def run_write_transaction(payload):
    query_started = time.perf_counter()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if payload["db_sleep_seconds"] > 0:
                cursor.execute("SELECT pg_sleep(%s)", (payload["db_sleep_seconds"],))
            if APP_NAME == "app-orders":
                result = handle_orders_write(cursor, payload)
                event_type = "order_created"
            elif APP_NAME == "app-inventory":
                result = handle_inventory_write(cursor, payload)
                event_type = "inventory_reserved"
            elif APP_NAME == "app-billing":
                result = handle_billing_write(cursor, payload)
                event_type = "payment_authorized"
            else:
                raise RuntimeError(f"Unsupported service {APP_NAME}")
        conn.commit()
    query_elapsed = time.perf_counter() - query_started
    DB_QUERY_LATENCY.labels(service=APP_NAME, query_type="write").observe(query_elapsed)
    BUSINESS_EVENTS.labels(service=APP_NAME, event_type=event_type).inc()
    result["db_duration_seconds"] = round(query_elapsed, 4)
    result["db_sleep_seconds"] = payload["db_sleep_seconds"]
    return result


@app.get("/health")
def health():
    return jsonify({"service": APP_NAME, "status": "ok", "port": APP_PORT})


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.get("/query")
def query():
    extra_sleep = float(request.args.get("sleep", "0") or 0)
    try:
        rows, total_events, last_event_marker, query_elapsed, total_sleep = run_service_query(extra_sleep)
    except Exception as exc:
        DB_ERRORS.labels(service=APP_NAME, error_type=exc.__class__.__name__).inc()
        logger.exception("db_query_failed path=%s error=%s", request.path, exc)
        return (
            jsonify(
                {
                    "service": APP_NAME,
                    "status": "error",
                    "error": str(exc),
                    "db_host": DB_HOST,
                    "db_port": DB_PORT,
                }
            ),
            503,
        )

    logger.info(
        "db_query_complete rows=%s total_events=%s db_duration=%.4f db_sleep=%.2f",
        len(rows),
        total_events,
        query_elapsed,
        total_sleep,
    )
    return jsonify(
        {
            "service": APP_NAME,
            "status": "ok",
            "db_host": DB_HOST,
            "db_port": DB_PORT,
            "db_duration_seconds": round(query_elapsed, 4),
            "db_sleep_seconds": total_sleep,
            "records": [
                {
                    "service_name": row[0],
                    "state": row[1],
                    "notes": row[2],
                    "updated_at": row[3].isoformat(),
                }
                for row in rows
            ],
            "summary": {
                "service": APP_NAME,
                "total_events": total_events,
                "last_event_marker": str(last_event_marker),
            },
        }
    )


@app.post("/write")
def write():
    payload = parse_write_payload()
    try:
        result = run_write_transaction(payload)
    except Exception as exc:
        DB_ERRORS.labels(service=APP_NAME, error_type=exc.__class__.__name__).inc()
        logger.exception("db_write_failed service=%s order_ref=%s error=%s", APP_NAME, payload["order_ref"], exc)
        return (
            jsonify(
                {
                    "service": APP_NAME,
                    "status": "error",
                    "order_ref": payload["order_ref"],
                    "error": str(exc),
                }
            ),
            503,
        )

    logger.info(
        "db_write_complete service=%s event=%s order_ref=%s db_duration=%.4f",
        APP_NAME,
        result["event"],
        result["order_ref"],
        result["db_duration_seconds"],
    )
    return jsonify({"status": "ok", **result}), 201


@app.get("/hold")
def hold():
    hold_seconds = float(request.args.get("seconds", "10") or 10)
    try:
        started_at = time.perf_counter()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(%s)", (hold_seconds,))
                cursor.execute("SELECT COUNT(*) FROM demo_service_state")
                count = cursor.fetchone()[0]
        query_elapsed = time.perf_counter() - started_at
        DB_QUERY_LATENCY.labels(service=APP_NAME, query_type="hold").observe(query_elapsed)
        logger.warning("db_hold_complete hold_seconds=%.2f rows=%s", hold_seconds, count)
        return jsonify(
            {
                "service": APP_NAME,
                "status": "ok",
                "held_seconds": hold_seconds,
                "row_count": count,
                "db_duration_seconds": round(query_elapsed, 4),
            }
        )
    except Exception as exc:
        DB_ERRORS.labels(service=APP_NAME, error_type=exc.__class__.__name__).inc()
        logger.exception("db_hold_failed seconds=%s error=%s", hold_seconds, exc)
        return jsonify({"service": APP_NAME, "status": "error", "error": str(exc)}), 503


@app.get("/")
def root():
    return jsonify(
        {
            "service": APP_NAME,
            "message": "Use /query, /hold, /health, or /metrics.",
        }
    )
