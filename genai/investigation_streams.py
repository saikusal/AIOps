import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

import redis
from django.conf import settings


logger = logging.getLogger("genai")

_FALSEY = {"false", "0", "no"}


def investigation_streaming_enabled() -> bool:
    explicit = getattr(settings, "AIOPS_INVESTIGATION_STREAMS_ENABLED", None)
    if explicit is not None:
        return bool(explicit)
    return str(os.getenv("AIOPS_INVESTIGATION_STREAMS_ENABLED", "true")).strip().lower() not in _FALSEY


def _redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(getattr(settings, "AIOPS_INVESTIGATION_STREAM_REDIS_DB", 2)),
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        health_check_interval=30,
    )


def _channel_name(run_id: str) -> str:
    return f"aiops:investigation:{run_id}:stream"


def _snapshot_key(run_id: str) -> str:
    return f"aiops:investigation:{run_id}:snapshot"


def _version_key(run_id: str) -> str:
    return f"aiops:investigation:{run_id}:version"


def _load_run(run_id: str):
    from .models import InvestigationRun

    return (
        InvestigationRun.objects.select_related("incident", "session", "evidence_bundle_record")
        .prefetch_related("tool_invocations")
        .filter(run_id=run_id)
        .first()
    )


def load_cached_stream_snapshot(run_id: str) -> Optional[Dict[str, Any]]:
    if not investigation_streaming_enabled():
        return None
    try:
        payload = _redis_client().get(_snapshot_key(run_id))
        if not payload:
            return None
        return json.loads(payload)
    except Exception:
        logger.debug("Failed to load cached investigation snapshot for %s", run_id, exc_info=True)
        return None


def publish_investigation_run_snapshot(run_id: str) -> None:
    if not run_id or not investigation_streaming_enabled():
        return
    try:
        run = _load_run(run_id)
        if not run:
            return
        from .views import _serialize_investigation_live_payload

        payload = _serialize_investigation_live_payload(run)
        client = _redis_client()
        version = int(client.incr(_version_key(run_id)))
        serialized_payload = json.dumps(payload, default=str)
        envelope = json.dumps(
            {
                "event": "snapshot",
                "version": version,
                "payload": payload,
            },
            default=str,
        )
        ttl = int(getattr(settings, "AIOPS_INVESTIGATION_STREAM_SNAPSHOT_TTL", 900))
        pipeline = client.pipeline()
        pipeline.setex(_snapshot_key(run_id), ttl, serialized_payload)
        pipeline.publish(_channel_name(run_id), envelope)
        pipeline.execute()
    except Exception:
        logger.debug("Failed to publish investigation stream snapshot for %s", run_id, exc_info=True)


def open_investigation_stream_subscription(run_id: str) -> Tuple[redis.Redis, redis.client.PubSub]:
    client = _redis_client()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(_channel_name(run_id))
    return client, pubsub

