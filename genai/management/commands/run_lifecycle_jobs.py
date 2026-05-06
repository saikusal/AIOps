"""
Track 3.4 — run_lifecycle_jobs management command
==================================================
Executes one or more lifecycle maintenance jobs:

  prune_expired_caches         — remove expired telemetry cache rows (semantic_cache)
  prune_stale_snapshots        — delete old EvidenceSnapshots beyond retention window
  prune_tool_response_raw      — wipe large response_json from old ToolInvocations
  archive_evidence_bundles     — call archive_service for bundles past archive_after_days
  compact_investigation_runs   — clear bulky JSON fields from resolved/old runs
  rotate_heartbeat_snapshots   — keep only the last N heartbeats per target
  expire_enrollment_tokens     — mark expired/used tokens as revoked
  prune_replay_scenarios       — delete old ReplayScenario rows

Usage:
  python manage.py run_lifecycle_jobs                         # all jobs
  python manage.py run_lifecycle_jobs --jobs prune_stale_snapshots archive_evidence_bundles
  python manage.py run_lifecycle_jobs --dry-run              # report counts without deleting
  python manage.py run_lifecycle_jobs --jobs rotate_heartbeat_snapshots --keep-heartbeats 5
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from genai.models import (
    DataRetentionPolicy,
    EvidenceBundle,
    EvidenceSnapshot,
    EnrollmentToken,
    InvestigationRun,
    LifecycleJobRun,
    ReplayScenario,
    TargetHeartbeat,
    ToolInvocation,
)

logger = logging.getLogger("lifecycle_jobs")

ALL_JOB_TYPES = [
    "prune_expired_caches",
    "prune_stale_snapshots",
    "prune_tool_response_raw",
    "archive_evidence_bundles",
    "compact_investigation_runs",
    "rotate_heartbeat_snapshots",
    "expire_enrollment_tokens",
    "prune_replay_scenarios",
]


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

def _retention_days_for(job_type: str) -> int:
    """Look up the retention_days for a job type from DataRetentionPolicy, with hardcoded fallbacks."""
    defaults = {
        "prune_stale_snapshots": 30,
        "prune_tool_response_raw": 14,
        "archive_evidence_bundles": 14,
        "compact_investigation_runs": 60,
        "rotate_heartbeat_snapshots": 0,   # uses keep-count, not days
        "expire_enrollment_tokens": 0,     # uses token's own expires_at
        "prune_replay_scenarios": 90,
        "prune_expired_caches": 0,
    }
    policy_subject_map = {
        "prune_stale_snapshots": "investigation_evidence",
        "archive_evidence_bundles": "investigation_evidence",
        "compact_investigation_runs": "investigation_evidence",
        "prune_tool_response_raw": "execution_history",
        "prune_replay_scenarios": "learning_artifacts",
    }
    subject = policy_subject_map.get(job_type)
    if subject:
        try:
            policy = DataRetentionPolicy.objects.filter(
                subject_type=subject, is_default=True
            ).first()
            if policy:
                if job_type == "archive_evidence_bundles":
                    return policy.archive_after_days or defaults[job_type]
                return policy.retention_days or defaults[job_type]
        except Exception:
            pass
    return defaults.get(job_type, 30)


def _has_active_hold(bundle: EvidenceBundle) -> bool:
    """Return True if the bundle or its incident has an active RetentionHold."""
    now = timezone.now()
    from genai.models import RetentionHold
    qs = RetentionHold.objects.filter(is_active=True)
    # Check expiry: ignore holds that have a past expires_at
    qs = qs.exclude(expires_at__lt=now)
    if qs.filter(evidence_bundle=bundle).exists():
        return True
    if bundle.incident and qs.filter(incident=bundle.incident).exists():
        return True
    if bundle.investigation_run and qs.filter(investigation_run=bundle.investigation_run).exists():
        return True
    return False


# ---------------------------------------------------------------------------
# Individual job implementations
# ---------------------------------------------------------------------------

def job_prune_expired_caches(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove stale rows from the semantic_cache table (SemanticCache model).
    These are short-lived and safe to purge aggressively.
    """
    from genai.semantic_cache import SemanticCache  # import model from module
    cutoff = timezone.now() - timezone.timedelta(days=1)
    qs = SemanticCache.objects.filter(created_at__lt=cutoff)
    count = qs.count()
    if not dry_run:
        qs.delete()
    return {"deleted": count if not dry_run else 0, "would_delete": count}


def job_prune_stale_snapshots(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete EvidenceSnapshot rows older than the retention window.
    Skips bundles protected by an active RetentionHold.
    """
    retention_days = _retention_days_for("prune_stale_snapshots")
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)

    # Collect bundle IDs that are on hold
    if not dry_run:
        from genai.models import RetentionHold
        held_bundle_ids = set(
            RetentionHold.objects.filter(
                is_active=True, evidence_bundle__isnull=False
            ).exclude(expires_at__lt=timezone.now())
            .values_list("evidence_bundle_id", flat=True)
        )
    else:
        held_bundle_ids = set()

    qs = EvidenceSnapshot.objects.filter(created_at__lt=cutoff).exclude(
        evidence_bundle_id__in=held_bundle_ids
    )
    count = qs.count()
    if not dry_run:
        qs.delete()
    return {"deleted": count if not dry_run else 0, "would_delete": count, "retention_days": retention_days}


def job_prune_tool_response_raw(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wipe the large response_json field on old ToolInvocation rows,
    keeping the metadata (tool_name, status, latency) intact.
    Raw payloads are high-value for recent debugging but waste storage long-term.
    """
    retention_days = _retention_days_for("prune_tool_response_raw")
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    qs = ToolInvocation.objects.filter(
        created_at__lt=cutoff
    ).exclude(response_json={})
    count = qs.count()
    if not dry_run:
        qs.update(response_json={}, request_json={})
    return {"pruned": count if not dry_run else 0, "would_prune": count, "retention_days": retention_days}


def job_archive_evidence_bundles(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Archive EvidenceBundle records that are past archive_after_days and still active.
    Calls archive_service.archive_evidence_bundle() for each eligible bundle.
    Skips any bundle with an active RetentionHold.
    """
    from genai.archive_service import archive_evidence_bundle

    archive_after_days = _retention_days_for("archive_evidence_bundles")
    cutoff = timezone.now() - timezone.timedelta(days=archive_after_days)

    qs = EvidenceBundle.objects.filter(
        lifecycle_status="active",
        created_at__lt=cutoff,
    ).select_related("investigation_run", "incident")

    archived = 0
    skipped = 0
    failed = 0

    for bundle in qs:
        if _has_active_hold(bundle):
            skipped += 1
            continue
        if dry_run:
            archived += 1
            continue
        result = archive_evidence_bundle(bundle)
        if result.success:
            archived += 1
        else:
            failed += 1
            logger.warning("archive failed for bundle %s: %s", bundle.bundle_id, result.error)

    return {
        "archived": archived if not dry_run else 0,
        "would_archive": archived if dry_run else 0,
        "skipped_on_hold": skipped,
        "failed": failed,
        "archive_after_days": archive_after_days,
    }


def job_compact_investigation_runs(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clear bulky JSON fields (workflow_json, evidence_bundle_json) from old completed runs.
    Keeps planner_json, hypotheses_json, scope_json for audit traceability.
    Only targets runs that have an EvidenceBundle (so their data is archived/snapshotted).
    """
    retention_days = _retention_days_for("compact_investigation_runs")
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)

    qs = InvestigationRun.objects.filter(
        status__in=["completed", "resolved", "failed"],
        updated_at__lt=cutoff,
        evidence_bundle_record__isnull=False,  # only if bundle exists
    ).exclude(workflow_json=[], evidence_bundle_json={})

    count = qs.count()
    if not dry_run:
        qs.update(workflow_json=[], evidence_bundle_json={})
    return {"compacted": count if not dry_run else 0, "would_compact": count, "retention_days": retention_days}


def job_rotate_heartbeat_snapshots(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only the last N heartbeats per target. Delete the rest.
    N is controlled by --keep-heartbeats (default 10).
    """
    from genai.models import Target
    keep = int(options.get("keep_heartbeats", 10))

    pruned = 0
    for target in Target.objects.all():
        heartbeat_ids = list(
            TargetHeartbeat.objects.filter(target=target)
            .order_by("-created_at")
            .values_list("id", flat=True)
        )
        to_delete_ids = heartbeat_ids[keep:]
        if to_delete_ids:
            count = len(to_delete_ids)
            if not dry_run:
                TargetHeartbeat.objects.filter(id__in=to_delete_ids).delete()
            pruned += count

    return {"pruned": pruned if not dry_run else 0, "would_prune": pruned, "keep_per_target": keep}


def job_expire_enrollment_tokens(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark enrollment tokens that are past their expiry or already used as revoked.
    Does NOT delete them — keeps the audit trail.
    """
    from django.db.models import Q
    now = timezone.now()
    qs = EnrollmentToken.objects.filter(revoked=False).filter(
        Q(expires_at__lt=now) | Q(used_at__isnull=False)
    )
    count = qs.count()
    if not dry_run:
        qs.update(revoked=True)
    return {"revoked": count if not dry_run else 0, "would_revoke": count}


def job_prune_replay_scenarios(dry_run: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete old ReplayScenario rows (and cascading ReplayEvaluations).
    Keeps recent scenarios useful for planner learning.
    """
    retention_days = _retention_days_for("prune_replay_scenarios")
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    qs = ReplayScenario.objects.filter(created_at__lt=cutoff)
    count = qs.count()
    if not dry_run:
        qs.delete()
    return {"deleted": count if not dry_run else 0, "would_delete": count, "retention_days": retention_days}


# ---------------------------------------------------------------------------
# Job dispatch table
# ---------------------------------------------------------------------------

JOB_DISPATCH = {
    "prune_expired_caches": job_prune_expired_caches,
    "prune_stale_snapshots": job_prune_stale_snapshots,
    "prune_tool_response_raw": job_prune_tool_response_raw,
    "archive_evidence_bundles": job_archive_evidence_bundles,
    "compact_investigation_runs": job_compact_investigation_runs,
    "rotate_heartbeat_snapshots": job_rotate_heartbeat_snapshots,
    "expire_enrollment_tokens": job_expire_enrollment_tokens,
    "prune_replay_scenarios": job_prune_replay_scenarios,
}


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Run Track 3.4 lifecycle maintenance jobs (pruning, archiving, compaction)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--jobs",
            nargs="*",
            default=ALL_JOB_TYPES,
            choices=ALL_JOB_TYPES,
            help="Which jobs to run. Defaults to all jobs.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be done without making any changes.",
        )
        parser.add_argument(
            "--keep-heartbeats",
            type=int,
            default=10,
            help="Number of heartbeats to keep per target (rotate_heartbeat_snapshots).",
        )

    def handle(self, *args, **options):
        jobs_to_run: List[str] = options["jobs"] or ALL_JOB_TYPES
        dry_run: bool = options["dry_run"]
        triggered_by = "management_command"

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode — no changes will be made.\n"))

        overall_start = time.monotonic()

        for job_type in jobs_to_run:
            fn = JOB_DISPATCH.get(job_type)
            if not fn:
                self.stderr.write(f"Unknown job: {job_type}")
                continue

            self.stdout.write(f"→ {job_type} ... ", ending="")
            job_start = time.monotonic()

            # Create a LifecycleJobRun record
            job_run = LifecycleJobRun.objects.create(
                job_type=job_type,
                status="running",
                triggered_by=triggered_by,
                job_params_json={"dry_run": dry_run, "keep_heartbeats": options.get("keep_heartbeats", 10)},
            )

            try:
                result = fn(dry_run=dry_run, options=options)
                duration = time.monotonic() - job_start

                job_run.status = "completed"
                job_run.result_summary_json = result
                job_run.records_scanned = result.get("would_delete", result.get("would_prune", result.get("would_archive", result.get("would_compact", result.get("would_revoke", 0)))))
                job_run.records_pruned = result.get("deleted", result.get("pruned", result.get("compacted", result.get("revoked", 0))))
                job_run.records_archived = result.get("archived", 0)
                job_run.records_skipped = result.get("skipped_on_hold", 0)
                job_run.completed_at = timezone.now()
                job_run.duration_seconds = round(duration, 3)
                job_run.save()

                self.stdout.write(
                    self.style.SUCCESS(f"done ({duration:.2f}s) — {result}")
                )
            except Exception as exc:
                duration = time.monotonic() - job_start
                logger.exception("lifecycle job %s failed", job_type)
                job_run.status = "failed"
                job_run.error_detail = str(exc)
                job_run.completed_at = timezone.now()
                job_run.duration_seconds = round(duration, 3)
                job_run.save()
                self.stderr.write(self.style.ERROR(f"FAILED ({job_type}): {exc}"))

        total = time.monotonic() - overall_start
        self.stdout.write(
            self.style.SUCCESS(f"\nLifecycle jobs completed in {total:.2f}s.")
        )
