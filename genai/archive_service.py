"""
Track 3.5 — Archive Service
============================
Handles evidence bundle export and object-storage-ready archive preparation.

Design:
  - Builds a structured JSON archive package from an EvidenceBundle.
  - Computes SHA-256 checksum for integrity verification.
  - Supports two storage backends:
      local_fs   — writes to ARCHIVE_ROOT on the local filesystem (dev/test).
      minio      — uploads to MinIO via boto3-compatible S3 API (Docker default).
      s3         — same boto3 path, different endpoint config.
  - Creates/updates an ArchiveManifest row in Postgres to track object-storage state.
  - Does NOT delete the source row — lifecycle jobs own pruning decisions.

Environment variables consumed (all optional with sensible defaults):
  ARCHIVE_BACKEND          local_fs | minio | s3 | gcs | azure_blob  (default: local_fs)
  ARCHIVE_ROOT             Local path for local_fs backend             (default: /tmp/aiops-archives)
  ARCHIVE_BUCKET           Bucket name for object-storage backends     (default: opsmitra-archives)
  ARCHIVE_S3_ENDPOINT_URL  Override endpoint for MinIO                 (e.g. http://minio:9000)
  ARCHIVE_S3_ACCESS_KEY    S3 / MinIO access key
  ARCHIVE_S3_SECRET_KEY    S3 / MinIO secret key
  ARCHIVE_S3_REGION        AWS region                                  (default: us-east-1)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from django.utils import timezone

logger = logging.getLogger("archive_service")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
ARCHIVE_BACKEND: str = os.environ.get("ARCHIVE_BACKEND", "local_fs")
ARCHIVE_ROOT: str = os.environ.get("ARCHIVE_ROOT", "/tmp/aiops-archives")
ARCHIVE_BUCKET: str = os.environ.get("ARCHIVE_BUCKET", "opsmitra-archives")
ARCHIVE_S3_ENDPOINT_URL: Optional[str] = os.environ.get("ARCHIVE_S3_ENDPOINT_URL")
ARCHIVE_S3_ACCESS_KEY: Optional[str] = os.environ.get("ARCHIVE_S3_ACCESS_KEY")
ARCHIVE_S3_SECRET_KEY: Optional[str] = os.environ.get("ARCHIVE_S3_SECRET_KEY")
ARCHIVE_S3_REGION: str = os.environ.get("ARCHIVE_S3_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_bundle_payload(evidence_bundle) -> Dict[str, Any]:
    """Assemble the full archive payload from an EvidenceBundle and related objects."""
    run = evidence_bundle.investigation_run
    incident = evidence_bundle.incident

    snapshots = []
    for snap in evidence_bundle.snapshots.all().order_by("created_at"):
        snapshots.append({
            "snapshot_id": snap.snapshot_id,
            "stage": snap.stage,
            "iteration_index": snap.iteration_index,
            "title": snap.title,
            "summary": snap.summary,
            "confidence_score": snap.confidence_score,
            "planner_json": snap.planner_json,
            "evidence_bundle_json": snap.evidence_bundle_json,
            "missing_evidence_json": snap.missing_evidence_json,
            "contradicting_evidence_json": snap.contradicting_evidence_json,
            "created_at": snap.created_at.isoformat(),
        })

    transcripts = []
    for entry in evidence_bundle.transcript_entries.all().order_by("sequence_index"):
        transcripts.append({
            "transcript_id": entry.transcript_id,
            "sequence_index": entry.sequence_index,
            "entry_type": entry.entry_type,
            "stage": entry.stage,
            "title": entry.title,
            "content_json": entry.content_json,
            "created_at": entry.created_at.isoformat(),
        })

    payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "exported_at": timezone.now().isoformat(),
        "bundle": {
            "bundle_id": evidence_bundle.bundle_id,
            "data_category": evidence_bundle.data_category,
            "lifecycle_status": evidence_bundle.lifecycle_status,
            "evidence_summary_json": evidence_bundle.evidence_summary_json,
            "artifact_references_json": evidence_bundle.artifact_references_json,
            "metadata_json": evidence_bundle.metadata_json,
            "created_at": evidence_bundle.created_at.isoformat(),
            "updated_at": evidence_bundle.updated_at.isoformat(),
        },
        "investigation_run": {
            "run_id": run.run_id,
            "route": run.route,
            "question": run.question,
            "application": run.application,
            "service": run.service,
            "target_host": run.target_host,
            "status": run.status,
            "current_stage": run.current_stage,
            "confidence_score": run.confidence_score,
            "scope_json": run.scope_json,
            "planner_json": run.planner_json,
            "hypotheses_json": run.hypotheses_json,
            "missing_evidence_json": run.missing_evidence_json,
            "contradicting_evidence_json": run.contradicting_evidence_json,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        } if run else None,
        "incident": {
            "incident_key": incident.incident_key,
            "title": incident.title,
            "status": incident.status,
            "severity": incident.severity,
            "priority": incident.priority,
            "application": incident.application,
            "primary_service": incident.primary_service,
            "opened_at": incident.opened_at.isoformat(),
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        } if incident else None,
        "snapshots": snapshots,
        "transcripts": transcripts,
    }
    return payload


def _compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object_key_for_bundle(bundle_id: str, timestamp: str) -> str:
    date_prefix = timestamp[:10]  # YYYY-MM-DD
    return f"evidence-bundles/{date_prefix}/{bundle_id}.json"


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------

def _write_local_fs(object_key: str, data: bytes) -> str:
    """Write data to local filesystem. Returns the full path as the 'url'."""
    dest = Path(ARCHIVE_ROOT) / object_key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info("archive written to local_fs: %s (%d bytes)", dest, len(data))
    return str(dest)


def _write_s3_compatible(bucket: str, object_key: str, data: bytes) -> str:
    """Upload to S3 / MinIO. Returns the object URL."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        raise RuntimeError(
            "boto3 is required for S3/MinIO archive backend. "
            "Install it with: pip install boto3"
        )

    kwargs: Dict[str, Any] = {
        "region_name": ARCHIVE_S3_REGION,
    }
    if ARCHIVE_S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = ARCHIVE_S3_ENDPOINT_URL
    if ARCHIVE_S3_ACCESS_KEY and ARCHIVE_S3_SECRET_KEY:
        kwargs["aws_access_key_id"] = ARCHIVE_S3_ACCESS_KEY
        kwargs["aws_secret_access_key"] = ARCHIVE_S3_SECRET_KEY

    try:
        s3 = boto3.client("s3", **kwargs)
        s3.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=data,
            ContentType="application/json",
        )
        endpoint = ARCHIVE_S3_ENDPOINT_URL or f"https://s3.{ARCHIVE_S3_REGION}.amazonaws.com"
        url = f"{endpoint}/{bucket}/{object_key}"
        logger.info("archive uploaded to s3://%s/%s (%d bytes)", bucket, object_key, len(data))
        return url
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"S3/MinIO upload failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ArchiveResult:
    """Value object returned by archive_evidence_bundle()."""
    __slots__ = (
        "manifest_id", "object_key", "object_url", "size_bytes",
        "checksum_sha256", "backend", "success", "error",
    )

    def __init__(self, **kw):
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))

    def to_dict(self) -> Dict[str, Any]:
        return {s: getattr(self, s) for s in self.__slots__}


def archive_evidence_bundle(
    evidence_bundle,
    backend: Optional[str] = None,
    includes_tool_responses: bool = False,
) -> ArchiveResult:
    """
    Export an EvidenceBundle to object storage and record an ArchiveManifest.

    Args:
        evidence_bundle: EvidenceBundle model instance.
        backend: Override the ARCHIVE_BACKEND env variable.
        includes_tool_responses: Whether to include raw ToolInvocation payloads.

    Returns:
        ArchiveResult with success flag and metadata.
    """
    # Import here to avoid circular at module load time
    from genai.models import ArchiveManifest

    chosen_backend = backend or ARCHIVE_BACKEND
    now_ts = timezone.now().isoformat()

    # --- Build payload ---
    try:
        payload = _build_bundle_payload(evidence_bundle)
        if includes_tool_responses:
            run = evidence_bundle.investigation_run
            if run:
                tool_calls = list(run.tool_invocations.values(
                    "invocation_id", "tool_name", "status", "latency_ms",
                    "request_json", "response_json", "created_at",
                ))
                payload["tool_invocations"] = tool_calls
        raw_data = json.dumps(payload, indent=2, default=str).encode("utf-8")
    except Exception as exc:
        logger.error("failed to build archive payload for bundle %s: %s", evidence_bundle.bundle_id, exc)
        return ArchiveResult(success=False, error=str(exc))

    checksum = _compute_checksum(raw_data)
    object_key = _object_key_for_bundle(evidence_bundle.bundle_id, now_ts)

    # --- Write to chosen backend ---
    try:
        if chosen_backend == "local_fs":
            object_url = _write_local_fs(object_key, raw_data)
        elif chosen_backend in ("minio", "s3"):
            object_url = _write_s3_compatible(ARCHIVE_BUCKET, object_key, raw_data)
        else:
            raise ValueError(f"Unsupported archive backend: {chosen_backend}")
    except Exception as exc:
        logger.error("archive write failed for bundle %s: %s", evidence_bundle.bundle_id, exc)
        # Persist the failed manifest so the operator can retry
        manifest, _ = ArchiveManifest.objects.get_or_create(
            evidence_bundle=evidence_bundle,
            defaults={"archive_backend": chosen_backend},
        )
        manifest.status = "failed"
        manifest.object_key = object_key
        manifest.size_bytes = len(raw_data)
        manifest.checksum_sha256 = checksum
        manifest.manifest_json = {"error": str(exc), "attempted_at": now_ts}
        manifest.save(update_fields=["status", "object_key", "size_bytes", "checksum_sha256", "manifest_json", "updated_at"])
        return ArchiveResult(success=False, error=str(exc))

    # --- Persist manifest ---
    manifest, created = ArchiveManifest.objects.get_or_create(
        evidence_bundle=evidence_bundle,
        defaults={"archive_backend": chosen_backend},
    )
    manifest.archive_backend = chosen_backend
    manifest.bucket_name = ARCHIVE_BUCKET if chosen_backend != "local_fs" else ""
    manifest.object_key = object_key
    manifest.object_url = object_url
    manifest.size_bytes = len(raw_data)
    manifest.checksum_sha256 = checksum
    manifest.status = "uploaded"
    manifest.includes_snapshots = True
    manifest.includes_transcripts = True
    manifest.includes_tool_responses = includes_tool_responses
    manifest.uploaded_at = timezone.now()
    manifest.manifest_json = {
        "schema_version": "1.0",
        "exported_at": now_ts,
        "snapshot_count": len(payload.get("snapshots", [])),
        "transcript_count": len(payload.get("transcripts", [])),
    }
    manifest.save()

    # Mark the bundle as archived
    evidence_bundle.lifecycle_status = "archived"
    evidence_bundle.archived_at = timezone.now()
    evidence_bundle.save(update_fields=["lifecycle_status", "archived_at", "updated_at"])

    logger.info(
        "bundle %s archived to %s (%s, %d bytes, sha256=%s)",
        evidence_bundle.bundle_id, object_url, chosen_backend, len(raw_data), checksum[:12],
    )
    return ArchiveResult(
        manifest_id=str(manifest.manifest_id),
        object_key=object_key,
        object_url=object_url,
        size_bytes=len(raw_data),
        checksum_sha256=checksum,
        backend=chosen_backend,
        success=True,
        error=None,
    )


def verify_archive_manifest(manifest) -> bool:
    """
    Re-download the archive and verify its SHA-256 checksum.
    Updates manifest.status to 'verified' or 'failed'.
    """
    try:
        if manifest.archive_backend == "local_fs":
            path = Path(manifest.object_key)
            if not path.exists():
                raise FileNotFoundError(f"Archive file not found: {path}")
            raw_data = path.read_bytes()
        elif manifest.archive_backend in ("minio", "s3"):
            try:
                import boto3
            except ImportError:
                raise RuntimeError("boto3 is required for S3/MinIO verification.")
            kwargs: Dict[str, Any] = {"region_name": ARCHIVE_S3_REGION}
            if ARCHIVE_S3_ENDPOINT_URL:
                kwargs["endpoint_url"] = ARCHIVE_S3_ENDPOINT_URL
            if ARCHIVE_S3_ACCESS_KEY and ARCHIVE_S3_SECRET_KEY:
                kwargs["aws_access_key_id"] = ARCHIVE_S3_ACCESS_KEY
                kwargs["aws_secret_access_key"] = ARCHIVE_S3_SECRET_KEY
            s3 = boto3.client("s3", **kwargs)
            resp = s3.get_object(Bucket=manifest.bucket_name, Key=manifest.object_key)
            raw_data = resp["Body"].read()
        else:
            raise ValueError(f"Cannot verify unsupported backend: {manifest.archive_backend}")

        actual_checksum = _compute_checksum(raw_data)
        if actual_checksum == manifest.checksum_sha256:
            manifest.status = "verified"
            manifest.verified_at = timezone.now()
            manifest.save(update_fields=["status", "verified_at", "updated_at"])
            logger.info("manifest %s verified OK", manifest.manifest_id)
            return True
        else:
            manifest.status = "failed"
            manifest.manifest_json["verify_error"] = (
                f"checksum mismatch: expected {manifest.checksum_sha256}, got {actual_checksum}"
            )
            manifest.save(update_fields=["status", "manifest_json", "updated_at"])
            logger.warning("manifest %s checksum mismatch", manifest.manifest_id)
            return False
    except Exception as exc:
        manifest.status = "failed"
        manifest.manifest_json["verify_error"] = str(exc)
        manifest.save(update_fields=["status", "manifest_json", "updated_at"])
        logger.error("manifest %s verification error: %s", manifest.manifest_id, exc)
        return False
