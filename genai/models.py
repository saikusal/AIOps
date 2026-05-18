import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


User = get_user_model()

TENANT_ROLE_OWNER = "owner"
TENANT_ROLE_ADMIN = "admin"
TENANT_ROLE_OPERATOR = "operator"
TENANT_ROLE_RESPONDER = "responder"
TENANT_ROLE_VIEWER = "viewer"
TENANT_ROLE_AUDITOR = "auditor"

TENANT_ROLE_CHOICES = (
    (TENANT_ROLE_OWNER, "Owner"),
    (TENANT_ROLE_ADMIN, "Admin"),
    (TENANT_ROLE_OPERATOR, "Operator"),
    (TENANT_ROLE_RESPONDER, "Responder"),
    (TENANT_ROLE_VIEWER, "Viewer"),
    (TENANT_ROLE_AUDITOR, "Auditor"),
)


class Tenant(models.Model):
    """Logical customer/workspace boundary for all operational data."""

    tenant_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    domain = models.CharField(max_length=160, blank=True, default="", db_index=True)
    is_active = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def default_tenant_pk():
    tenant, _ = Tenant.objects.get_or_create(
        slug="default-workspace",
        defaults={"name": "Default Workspace", "metadata_json": {"created_by": "model_default"}},
    )
    return tenant.pk


class TenantMembership(models.Model):
    membership_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="aiops_tenant_memberships")
    role = models.CharField(max_length=32, choices=TENANT_ROLE_CHOICES, default=TENANT_ROLE_VIEWER)
    is_active = models.BooleanField(default=True)
    extra_permissions = models.JSONField(default=list, blank=True)
    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="aiops_tenant_memberships_invited",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tenant__name", "user__username"]
        unique_together = ("tenant", "user")

    def __str__(self):
        return f"{self.tenant}:{self.user}:{self.role}"


class TenantInvitation(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("revoked", "Revoked"),
        ("expired", "Expired"),
    )

    invitation_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(db_index=True)
    role = models.CharField(max_length=32, choices=TENANT_ROLE_CHOICES, default=TENANT_ROLE_VIEWER)
    token = models.CharField(max_length=96, unique=True, default=uuid.uuid4, db_index=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    invited_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_tenant_invitations")
    accepted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_tenant_invitations_accepted")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email}:{self.tenant}:{self.status}"


class TenantAuditEvent(models.Model):
    event_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_tenant_audit_events")
    action = models.CharField(max_length=120, db_index=True)
    object_type = models.CharField(max_length=120, blank=True, default="")
    object_id = models.CharField(max_length=120, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk and TenantAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("Tenant audit events are append-only and cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Tenant audit events are append-only and cannot be deleted.")

    def __str__(self):
        return f"{self.tenant_id}:{self.action}:{self.object_type}:{self.object_id}"


DATA_CLASS_CHOICES = (
    ("hot_telemetry", "Hot Telemetry"),
    ("operational_state", "Operational State"),
    ("runtime_knowledge", "Runtime Knowledge"),
    ("evidence_memory", "Evidence Memory"),
    ("learning_memory", "Learning Memory"),
    ("archived_artifact", "Archived Artifact"),
)

STORE_OWNER_CHOICES = (
    ("postgres", "Postgres"),
    ("redis", "Redis"),
    ("opensearch", "OpenSearch"),
    ("victoriametrics", "VictoriaMetrics"),
    ("tempo", "Tempo"),
    ("object_storage", "Object Storage"),
    ("vector_backend", "Vector Backend"),
)

RETENTION_SUBJECT_CHOICES = (
    ("logs", "Logs"),
    ("traces", "Traces"),
    ("metrics", "Metrics"),
    ("investigation_evidence", "Investigation Evidence"),
    ("execution_history", "Execution History"),
    ("learning_artifacts", "Learning Artifacts"),
    ("runtime_inventory", "Runtime Inventory"),
)

DEPLOYMENT_MODE_CHOICES = (
    ("any", "Any"),
    ("docker_single_node", "Docker Single Node"),
    ("kubernetes_standard", "Kubernetes Standard"),
    ("kubernetes_enterprise", "Kubernetes Enterprise"),
)


class GenAIChatHistory(models.Model):
    """
    Stores a record of each question asked, the raw SQL query generated by the
    Text-to-SQL model, and the final, human-readable answer.
    This also acts as a cache to avoid re-computing answers for repeated questions.
    """
    question = models.TextField(unique=True)
    generated_sql = models.TextField()
    answer = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q: {self.question[:50]}... -> SQL: {self.generated_sql[:80]}..."


class ChatSession(models.Model):
    session_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="chat_sessions")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_chat_sessions")
    title = models.CharField(max_length=255, blank=True, default="")
    context_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"ChatSession<{self.session_id}>"


class ChatMessage(models.Model):
    ROLE_CHOICES = (
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    )

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.session.session_id}:{self.role}:{self.created_at.isoformat()}"


class InvestigationRun(models.Model):
    STATUS_CHOICES = (
        ("queued", "Queued"),
        ("scoping", "Scoping"),
        ("collecting_evidence", "Collecting Evidence"),
        ("assessing_evidence", "Assessing Evidence"),
        ("planning_next_step", "Planning Next Step"),
        ("awaiting_approval", "Awaiting Approval"),
        ("executing", "Executing"),
        ("verifying", "Verifying"),
        ("resolved", "Resolved"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )

    run_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="investigation_runs")
    session = models.ForeignKey("ChatSession", null=True, blank=True, on_delete=models.SET_NULL, related_name="investigation_runs")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_investigation_runs")
    incident = models.ForeignKey("Incident", null=True, blank=True, on_delete=models.SET_NULL, related_name="investigation_runs")
    route = models.CharField(max_length=32, default="investigation")
    question = models.TextField()
    application = models.CharField(max_length=120, blank=True, default="")
    service = models.CharField(max_length=120, blank=True, default="")
    target_host = models.CharField(max_length=255, blank=True, default="")
    current_stage = models.CharField(max_length=64, blank=True, default="queued")
    scope_json = models.JSONField(default=dict, blank=True)
    planner_json = models.JSONField(default=dict, blank=True)
    workflow_json = models.JSONField(default=list, blank=True)
    evidence_bundle_json = models.JSONField(default=dict, blank=True)
    hypotheses_json = models.JSONField(default=list, blank=True)
    missing_evidence_json = models.JSONField(default=list, blank=True)
    contradicting_evidence_json = models.JSONField(default=list, blank=True)
    confidence_score = models.FloatField(default=0.0)
    evidence_summary = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="running")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"InvestigationRun<{self.run_id}>"


class ToolInvocation(models.Model):
    STATUS_CHOICES = (
        ("success", "Success"),
        ("error", "Error"),
    )

    invocation_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="tool_invocations")
    investigation_run = models.ForeignKey("InvestigationRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="tool_invocations")
    session = models.ForeignKey("ChatSession", null=True, blank=True, on_delete=models.SET_NULL, related_name="tool_invocations")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_tool_invocations")
    incident = models.ForeignKey("Incident", null=True, blank=True, on_delete=models.SET_NULL, related_name="tool_invocations")
    server_name = models.CharField(max_length=64)
    tool_name = models.CharField(max_length=128)
    request_json = models.JSONField(default=dict, blank=True)
    response_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="success")
    latency_ms = models.PositiveIntegerField(default=0)
    error_detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.server_name}:{self.tool_name}:{self.invocation_id}"


class DataRetentionPolicy(models.Model):
    policy_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    data_category = models.CharField(max_length=32, choices=DATA_CLASS_CHOICES)
    subject_type = models.CharField(max_length=40, choices=RETENTION_SUBJECT_CHOICES, default="investigation_evidence")
    deployment_mode = models.CharField(max_length=32, choices=DEPLOYMENT_MODE_CHOICES, default="any")
    primary_store = models.CharField(max_length=32, choices=STORE_OWNER_CHOICES)
    archive_store = models.CharField(max_length=32, choices=STORE_OWNER_CHOICES, blank=True, default="")
    retention_days = models.PositiveIntegerField(default=30)
    archive_after_days = models.PositiveIntegerField(default=0)
    purge_after_days = models.PositiveIntegerField(default=0)
    hold_supported = models.BooleanField(default=False)
    object_storage_required = models.BooleanField(default=False)
    vector_store_required = models.BooleanField(default=False)
    trace_backend = models.CharField(max_length=32, blank=True, default="")
    is_default = models.BooleanField(default=False)
    storage_defaults_json = models.JSONField(default=dict, blank=True)
    policy_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_category", "subject_type", "deployment_mode", "name"]

    def __str__(self):
        return f"{self.slug}:{self.data_category}"


class EvidenceBundle(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("archived", "Archived"),
        ("pruned", "Pruned"),
    )

    bundle_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="evidence_bundles")
    investigation_run = models.OneToOneField("InvestigationRun", on_delete=models.CASCADE, related_name="evidence_bundle_record")
    incident = models.ForeignKey("Incident", null=True, blank=True, on_delete=models.SET_NULL, related_name="evidence_bundles")
    retention_policy = models.ForeignKey("DataRetentionPolicy", null=True, blank=True, on_delete=models.SET_NULL, related_name="evidence_bundles")
    data_category = models.CharField(max_length=32, choices=DATA_CLASS_CHOICES, default="evidence_memory")
    primary_store = models.CharField(max_length=32, choices=STORE_OWNER_CHOICES, default="postgres")
    archive_store = models.CharField(max_length=32, choices=STORE_OWNER_CHOICES, blank=True, default="object_storage")
    lifecycle_status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    evidence_summary_json = models.JSONField(default=dict, blank=True)
    artifact_references_json = models.JSONField(default=list, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"EvidenceBundle<{self.bundle_id}>"


class EvidenceSnapshot(models.Model):
    snapshot_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    evidence_bundle = models.ForeignKey("EvidenceBundle", on_delete=models.CASCADE, related_name="snapshots")
    investigation_run = models.ForeignKey("InvestigationRun", on_delete=models.CASCADE, related_name="evidence_snapshots")
    stage = models.CharField(max_length=64, blank=True, default="")
    iteration_index = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    planner_json = models.JSONField(default=dict, blank=True)
    evidence_bundle_json = models.JSONField(default=dict, blank=True)
    missing_evidence_json = models.JSONField(default=list, blank=True)
    contradicting_evidence_json = models.JSONField(default=list, blank=True)
    confidence_score = models.FloatField(default=0.0)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"EvidenceSnapshot<{self.snapshot_id}>"


class InvestigationTranscript(models.Model):
    ENTRY_TYPE_CHOICES = (
        ("stage_transition", "Stage Transition"),
        ("planner", "Planner"),
        ("evidence_assessment", "Evidence Assessment"),
        ("verification", "Verification"),
        ("summary", "Summary"),
    )

    transcript_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    evidence_bundle = models.ForeignKey("EvidenceBundle", on_delete=models.CASCADE, related_name="transcript_entries")
    investigation_run = models.ForeignKey("InvestigationRun", on_delete=models.CASCADE, related_name="transcript_entries")
    sequence_index = models.PositiveIntegerField(default=0)
    entry_type = models.CharField(max_length=32, choices=ENTRY_TYPE_CHOICES, default="stage_transition")
    stage = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=255, blank=True, default="")
    content_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["investigation_run", "sequence_index"], name="uniq_investigation_transcript_sequence"),
        ]

    def __str__(self):
        return f"InvestigationTranscript<{self.transcript_id}>"


# ---------------------------------------------------------------------------
# Track 3.4 — Lifecycle job history
# ---------------------------------------------------------------------------

class LifecycleJobRun(models.Model):
    """Records each execution of a lifecycle maintenance job (pruning, archive, compaction)."""

    JOB_TYPE_CHOICES = (
        ("prune_expired_caches", "Prune Expired Caches"),
        ("prune_stale_snapshots", "Prune Stale Snapshots"),
        ("prune_tool_response_raw", "Prune Raw Tool Responses"),
        ("archive_evidence_bundles", "Archive Evidence Bundles"),
        ("compact_investigation_runs", "Compact Investigation Runs"),
        ("rotate_heartbeat_snapshots", "Rotate Heartbeat Snapshots"),
        ("expire_enrollment_tokens", "Expire Enrollment Tokens"),
        ("prune_replay_scenarios", "Prune Replay Scenarios"),
        ("custom", "Custom"),
    )

    STATUS_CHOICES = (
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    )

    job_run_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    job_type = models.CharField(max_length=64, choices=JOB_TYPE_CHOICES, default="custom")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="running")
    triggered_by = models.CharField(max_length=64, default="cron", blank=True)
    # Counts of affected records
    records_scanned = models.PositiveIntegerField(default=0)
    records_pruned = models.PositiveIntegerField(default=0)
    records_archived = models.PositiveIntegerField(default=0)
    records_skipped = models.PositiveIntegerField(default=0)
    # Payload for job-specific metadata (filters applied, data categories, etc.)
    job_params_json = models.JSONField(default=dict, blank=True)
    result_summary_json = models.JSONField(default=dict, blank=True)
    error_detail = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"LifecycleJobRun<{self.job_type}:{self.status}:{self.started_at.date()}>"


# ---------------------------------------------------------------------------
# Track 3.4 — Retention hold (legal / severity protection)
# ---------------------------------------------------------------------------

class RetentionHold(models.Model):
    """
    Prevents lifecycle jobs from pruning or archiving a protected object.
    Attaches to an EvidenceBundle, Incident, or InvestigationRun by generic reference.
    """

    HOLD_REASON_CHOICES = (
        ("legal", "Legal Hold"),
        ("regulatory", "Regulatory Compliance"),
        ("severity", "High Severity Incident"),
        ("operator", "Operator Manual Hold"),
        ("audit", "Audit Request"),
    )

    hold_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    # Generic reference — exactly one of these should be set
    evidence_bundle = models.ForeignKey(
        "EvidenceBundle",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="retention_holds",
    )
    incident = models.ForeignKey(
        "Incident",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="retention_holds",
    )
    investigation_run = models.ForeignKey(
        "InvestigationRun",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="retention_holds",
    )
    hold_reason = models.CharField(max_length=32, choices=HOLD_REASON_CHOICES, default="operator")
    description = models.TextField(blank=True, default="")
    held_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="aiops_retention_holds",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="aiops_released_retention_holds",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RetentionHold<{self.hold_reason}:{self.hold_id[:8]}>"


# ---------------------------------------------------------------------------
# Track 3.5 — Archive manifest (object-storage index for bundles)
# ---------------------------------------------------------------------------

class ArchiveManifest(models.Model):
    """
    Records the object-storage location and metadata for an archived evidence bundle.
    Postgres holds the manifest; the large payload lives in object storage.
    """

    ARCHIVE_BACKEND_CHOICES = (
        ("minio", "MinIO (local object storage)"),
        ("s3", "AWS S3"),
        ("gcs", "Google Cloud Storage"),
        ("azure_blob", "Azure Blob Storage"),
        ("local_fs", "Local Filesystem (dev/test)"),
    )

    STATUS_CHOICES = (
        ("pending", "Pending Upload"),
        ("uploaded", "Uploaded"),
        ("verified", "Verified"),
        ("failed", "Failed"),
        ("deleted", "Deleted"),
    )

    manifest_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    evidence_bundle = models.OneToOneField(
        "EvidenceBundle",
        on_delete=models.CASCADE,
        related_name="archive_manifest",
    )
    archive_backend = models.CharField(max_length=32, choices=ARCHIVE_BACKEND_CHOICES, default="minio")
    bucket_name = models.CharField(max_length=255, blank=True, default="")
    object_key = models.CharField(max_length=1024, blank=True, default="")
    object_url = models.CharField(max_length=2048, blank=True, default="")
    content_type = models.CharField(max_length=128, default="application/json")
    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    manifest_json = models.JSONField(default=dict, blank=True)
    # Tracks what is included in the archive
    includes_snapshots = models.BooleanField(default=True)
    includes_transcripts = models.BooleanField(default=True)
    includes_tool_responses = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ArchiveManifest<{self.manifest_id[:8]}:{self.status}>"


# ---------------------------------------------------------------------------
# Track 3.5 — Evidence artifact (out-of-line large payload pointer)
# ---------------------------------------------------------------------------

class EvidenceArtifact(models.Model):
    """
    Pointer to a large raw artifact (tool response payload, log excerpt, etc.)
    that is stored out-of-line to keep EvidenceBundle rows lean.
    """

    ARTIFACT_TYPE_CHOICES = (
        ("tool_response", "Tool Response Payload"),
        ("log_excerpt", "Log Excerpt"),
        ("trace_excerpt", "Trace Excerpt"),
        ("metrics_snapshot", "Metrics Snapshot"),
        ("code_snippet", "Code Snippet"),
        ("llm_prompt", "LLM Prompt"),
        ("llm_response", "LLM Response"),
        ("runbook_content", "Runbook Content"),
        ("other", "Other"),
    )

    STORAGE_BACKEND_CHOICES = (
        ("postgres_json", "Postgres JSON (inline)"),
        ("object_storage", "Object Storage"),
        ("local_fs", "Local Filesystem (dev/test)"),
    )

    artifact_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    evidence_bundle = models.ForeignKey(
        "EvidenceBundle",
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    investigation_run = models.ForeignKey(
        "InvestigationRun",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_artifacts",
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_artifacts",
    )
    artifact_type = models.CharField(max_length=32, choices=ARTIFACT_TYPE_CHOICES, default="other")
    storage_backend = models.CharField(max_length=32, choices=STORAGE_BACKEND_CHOICES, default="postgres_json")
    # For postgres_json storage: content stored here
    content_json = models.JSONField(default=dict, blank=True)
    # For object_storage: reference to the archive manifest or direct object key
    object_key = models.CharField(max_length=1024, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    is_pruned = models.BooleanField(default=False)
    pruned_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"EvidenceArtifact<{self.artifact_type}:{self.artifact_id[:8]}>"


PRIORITY_CHOICES = (
    ("P1", "P1 - Critical"),
    ("P2", "P2 - High"),
    ("P3", "P3 - Medium"),
    ("P4", "P4 - Low"),
)

# Default SLA windows (minutes) used when seeding SLAPolicy
SLA_DEFAULTS = {
    "P1": (15, 60),
    "P2": (30, 240),
    "P3": (120, 480),
    "P4": (480, 1440),
}


class SLAPolicy(models.Model):
    """Configurable SLA matrix per priority tier."""
    priority = models.CharField(max_length=4, choices=PRIORITY_CHOICES, unique=True)
    response_minutes = models.PositiveIntegerField(default=60)
    resolution_minutes = models.PositiveIntegerField(default=240)
    escalation_contacts = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return f"SLA-{self.priority} resp={self.response_minutes}m res={self.resolution_minutes}m"


class AlertEvent(models.Model):
    """Normalized alert lifecycle used for dedupe, suppression, and correlation."""

    EVENT_STATUS_CHOICES = (
        ("firing", "Firing"),
        ("resolved", "Resolved"),
        ("unknown", "Unknown"),
    )

    event_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="alert_events")
    source = models.CharField(max_length=64, default="unknown", db_index=True)
    lifecycle_key = models.CharField(max_length=255, db_index=True)
    alert_name = models.CharField(max_length=255, db_index=True)
    fingerprint = models.CharField(max_length=255, blank=True, default="", db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=EVENT_STATUS_CHOICES, default="firing", db_index=True)
    severity = models.CharField(max_length=32, blank=True, default="warning", db_index=True)
    service_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    target_host = models.CharField(max_length=255, blank=True, default="", db_index=True)
    environment = models.CharField(max_length=120, blank=True, default="", db_index=True)
    namespace = models.CharField(max_length=120, blank=True, default="", db_index=True)
    cluster = models.CharField(max_length=120, blank=True, default="", db_index=True)
    labels = models.JSONField(default=dict, blank=True)
    annotations = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    incident = models.ForeignKey("Incident", null=True, blank=True, on_delete=models.SET_NULL, related_name="alert_events")
    repeat_count = models.PositiveIntegerField(default=1)
    suppressed = models.BooleanField(default=False, db_index=True)
    suppression_reason = models.CharField(max_length=255, blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]
        unique_together = ("tenant", "source", "lifecycle_key")

    def __str__(self):
        return f"{self.source}:{self.alert_name}:{self.lifecycle_key}"


class AlertSuppression(models.Model):
    """Operator-managed rule for suppressing known noisy alert lifecycles."""

    suppression_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="alert_suppressions")
    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    alert_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    service_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    target_host = models.CharField(max_length=255, blank=True, default="", db_index=True)
    environment = models.CharField(max_length=120, blank=True, default="", db_index=True)
    reason = models.CharField(max_length=255, blank=True, default="suppression_rule")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by_username = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class MaintenanceWindow(models.Model):
    """Time-bounded suppression window for maintenance and planned work."""

    window_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="maintenance_windows")
    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    service_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    target_host = models.CharField(max_length=255, blank=True, default="", db_index=True)
    environment = models.CharField(max_length=120, blank=True, default="", db_index=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    reason = models.CharField(max_length=255, blank=True, default="maintenance_window")
    created_by_username = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.name


class IncidentCorrelationLink(models.Model):
    """Relationship between separately tracked incidents."""

    link_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="incident_correlation_links")
    source_incident = models.ForeignKey("Incident", on_delete=models.CASCADE, related_name="outgoing_correlation_links")
    related_incident = models.ForeignKey("Incident", on_delete=models.CASCADE, related_name="incoming_correlation_links")
    score = models.PositiveIntegerField(default=0)
    reasons = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        unique_together = ("source_incident", "related_incident")

    def __str__(self):
        return f"{self.source_incident_id}->{self.related_incident_id}:{self.score}"


class Incident(models.Model):
    STATUS_CHOICES = (
        ("open", "Open"),
        ("investigating", "Investigating"),
        ("resolved", "Resolved"),
    )

    incident_key = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="incidents")
    incident_number = models.CharField(max_length=32, unique=True, null=True, blank=True, db_index=True)
    application = models.CharField(max_length=120, blank=True, default="")
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="open")
    severity = models.CharField(max_length=32, blank=True, default="warning")
    priority = models.CharField(max_length=4, choices=PRIORITY_CHOICES, default="P3")
    primary_service = models.CharField(max_length=120, blank=True, default="")
    target_host = models.CharField(max_length=255, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    reasoning = models.TextField(blank=True, default="")
    blast_radius = models.JSONField(default=list, blank=True)
    dependency_graph = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    annotations = models.JSONField(default=dict, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    # SLA tracking
    sla_response_due_at = models.DateTimeField(null=True, blank=True)
    sla_resolution_due_at = models.DateTimeField(null=True, blank=True)
    sla_response_acknowledged_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by_username = models.CharField(max_length=150, blank=True, default="")
    delete_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.incident_number or self.incident_key}:{self.application or 'unknown'}:{self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.incident_number:
            incident_number = f"INC-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(incident_number=incident_number)
            self.incident_number = incident_number


class IncidentAlert(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="alerts")
    alert_name = models.CharField(max_length=255)
    alert_fingerprint = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, default="firing")
    target_host = models.CharField(max_length=255, blank=True, default="")
    service_name = models.CharField(max_length=120, blank=True, default="")
    labels = models.JSONField(default=dict, blank=True)
    annotations = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.alert_name} -> {self.incident.incident_key}"


class IncidentTimelineEvent(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="timeline")
    event_type = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.incident.incident_key}:{self.event_type}"


class PredictionSnapshot(models.Model):
    application = models.CharField(max_length=120)
    service = models.CharField(max_length=120)
    captured_at = models.DateTimeField(auto_now_add=True)
    metrics = models.JSONField(default=dict)
    features = models.JSONField(default=dict)
    incident_next_15m = models.BooleanField(default=False)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.application}/{self.service} @ {self.captured_at.isoformat()}"


class ServicePrediction(models.Model):
    application = models.CharField(max_length=120)
    service = models.CharField(max_length=120)
    status = models.CharField(max_length=32, default="healthy")
    risk_score = models.FloatField(default=0.0)
    incident_probability = models.FloatField(default=0.0)
    predicted_window_minutes = models.PositiveIntegerField(default=15)
    model_version = models.CharField(max_length=120, default="heuristic-v1")
    features = models.JSONField(default=dict)
    blast_radius = models.JSONField(default=list)
    explanation = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application}/{self.service} risk={self.risk_score:.2f}"


class TelemetryProfile(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    summary = models.TextField(blank=True, default="")
    default_for_target = models.CharField(max_length=32, default="linux")
    components = models.JSONField(default=list, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Target(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("connected", "Connected"),
        ("warning", "Warning"),
        ("degraded", "Degraded"),
        ("disconnected", "Disconnected"),
    )

    target_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="targets")
    name = models.CharField(max_length=160)
    target_type = models.CharField(max_length=32, default="linux")
    environment = models.CharField(max_length=64, blank=True, default="production")
    hostname = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.CharField(max_length=64, blank=True, default="")
    os_name = models.CharField(max_length=120, blank=True, default="")
    os_version = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    profile = models.ForeignKey(TelemetryProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="targets")
    collector_status = models.CharField(max_length=32, default="pending")
    metadata_json = models.JSONField(default=dict, blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class TargetPolicyProfile(models.Model):
    TARGET_TYPE_CHOICES = (
        ("linux", "Linux"),
        ("kubernetes", "Kubernetes"),
    )
    RUNTIME_TYPE_CHOICES = (
        ("any", "Any"),
        ("systemd", "Systemd"),
        ("docker", "Docker"),
        ("standalone", "Standalone"),
        ("kubernetes", "Kubernetes"),
    )
    SUDO_MODE_CHOICES = (
        ("none", "None"),
        ("limited", "Limited"),
        ("full", "Full"),
    )

    profile_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    target_type = models.CharField(max_length=32, choices=TARGET_TYPE_CHOICES, default="linux")
    runtime_type = models.CharField(max_length=32, choices=RUNTIME_TYPE_CHOICES, default="any")
    allow_service_status = models.BooleanField(default=True)
    allow_service_restart = models.BooleanField(default=False)
    allow_docker_logs = models.BooleanField(default=False)
    allow_docker_restart = models.BooleanField(default=False)
    allow_journal_logs = models.BooleanField(default=True)
    allow_file_logs = models.BooleanField(default=False)
    allow_db_diagnostics = models.BooleanField(default=False)
    allow_db_changes = models.BooleanField(default=False)
    allow_process_kill = models.BooleanField(default=False)
    requires_approval_for_restart = models.BooleanField(default=True)
    requires_approval_for_write_actions = models.BooleanField(default=True)
    sudo_mode = models.CharField(max_length=16, choices=SUDO_MODE_CHOICES, default="limited")
    allowed_command_patterns = models.JSONField(default=list, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TargetPolicyAssignment(models.Model):
    assignment_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    target = models.OneToOneField(Target, on_delete=models.CASCADE, related_name="policy_assignment")
    policy_profile = models.ForeignKey(
        TargetPolicyProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="target_assignments",
    )
    override_json = models.JSONField(default=dict, blank=True)
    config_version = models.PositiveIntegerField(default=1)
    last_applied_at = models.DateTimeField(null=True, blank=True)
    last_apply_status = models.CharField(max_length=32, blank=True, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.target.name}:{self.policy_profile.name if self.policy_profile else 'unassigned'}"


class TargetRuntimeProfile(models.Model):
    ROLE_CHOICES = (
        ("app", "Application"),
        ("db", "Database"),
        ("cache", "Cache"),
        ("gateway", "Gateway"),
        ("custom", "Custom"),
    )
    ENVIRONMENT_CHOICES = (
        ("prod", "Production"),
        ("staging", "Staging"),
        ("dev", "Development"),
        ("test", "Test"),
    )
    RUNTIME_TYPE_CHOICES = (
        ("systemd", "Systemd"),
        ("docker", "Docker"),
        ("standalone", "Standalone"),
        ("kubernetes", "Kubernetes"),
        ("unknown", "Unknown"),
    )
    RESTART_MODE_CHOICES = (
        ("systemctl", "Systemctl"),
        ("docker", "Docker"),
        ("kubectl", "Kubectl"),
        ("process", "Process"),
        ("manual", "Manual"),
        ("unknown", "Unknown"),
    )

    profile_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    target = models.OneToOneField(Target, on_delete=models.CASCADE, related_name="runtime_profile")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="app")
    environment = models.CharField(max_length=32, choices=ENVIRONMENT_CHOICES, default="prod")
    runtime_type = models.CharField(max_length=32, choices=RUNTIME_TYPE_CHOICES, default="unknown")
    hostname = models.CharField(max_length=255, blank=True, default="")
    os_family = models.CharField(max_length=64, blank=True, default="")
    docker_available = models.BooleanField(default=False)
    systemd_available = models.BooleanField(default=False)
    primary_restart_mode = models.CharField(max_length=32, choices=RESTART_MODE_CHOICES, default="unknown")
    notes = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.target.name}:{self.runtime_type}:{self.role}"


class TargetServiceBinding(models.Model):
    SERVICE_KIND_CHOICES = (
        ("systemd", "Systemd"),
        ("docker_container", "Docker Container"),
        ("process", "Process"),
        ("database", "Database"),
        ("kubernetes_workload", "Kubernetes Workload"),
    )

    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="service_bindings")
    service_name = models.CharField(max_length=160, db_index=True)
    service_kind = models.CharField(max_length=32, choices=SERVICE_KIND_CHOICES)
    systemd_unit = models.CharField(max_length=255, blank=True, default="")
    container_name = models.CharField(max_length=255, blank=True, default="")
    process_name = models.CharField(max_length=255, blank=True, default="")
    port = models.PositiveIntegerField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    restart_command_template = models.TextField(blank=True, default="")
    status_command_template = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service_name"]
        unique_together = ("target", "service_name", "service_kind", "systemd_unit", "container_name", "process_name")

    def __str__(self):
        return f"{self.target.name}:{self.service_name}"


class TargetLogSource(models.Model):
    SOURCE_TYPE_CHOICES = (
        ("journald", "Journald"),
        ("file", "File"),
        ("docker", "Docker"),
        ("database", "Database"),
        ("kubernetes", "Kubernetes"),
    )

    source_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="log_sources")
    service_binding = models.ForeignKey(
        TargetServiceBinding,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="log_sources",
    )
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPE_CHOICES)
    journal_unit = models.CharField(max_length=255, blank=True, default="")
    file_path = models.CharField(max_length=1024, blank=True, default="")
    container_name = models.CharField(max_length=255, blank=True, default="")
    stream_family = models.CharField(max_length=120, blank=True, default="")
    parser_name = models.CharField(max_length=120, blank=True, default="")
    include_patterns = models.JSONField(default=list, blank=True)
    exclude_patterns = models.JSONField(default=list, blank=True)
    shipper_type = models.CharField(max_length=64, blank=True, default="")
    parser_type = models.CharField(max_length=120, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target", "-is_primary", "source_type"]

    def __str__(self):
        return f"{self.target.name}:{self.source_type}"


class TargetLogIngestionProfile(models.Model):
    profile_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    target = models.OneToOneField(Target, on_delete=models.CASCADE, related_name="log_ingestion_profile")
    shipper_type = models.CharField(max_length=64, default="fluent-bit")
    stream_family = models.CharField(max_length=120, blank=True, default="")
    opensearch_pipeline = models.CharField(max_length=255, blank=True, default="")
    record_metadata_json = models.JSONField(default=dict, blank=True)
    config_version = models.PositiveIntegerField(default=1)
    last_applied_at = models.DateTimeField(null=True, blank=True)
    last_apply_status = models.CharField(max_length=32, blank=True, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.target.name}:{self.shipper_type}:{self.stream_family or 'unassigned'}"


class EnrollmentToken(models.Model):
    token = models.CharField(max_length=96, unique=True, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="enrollment_tokens")
    target_type = models.CharField(max_length=32, default="linux")
    target_name = models.CharField(max_length=160, blank=True, default="")
    profile = models.ForeignKey(TelemetryProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrollment_tokens")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_enrollment_tokens")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.target_type}:{self.token[:12]}"

    @property
    def is_valid(self) -> bool:
        return (not self.revoked) and self.expires_at > timezone.now()


class TargetComponent(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="components")
    name = models.CharField(max_length=120)
    version = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=32, default="pending")
    metadata_json = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("target", "name")

    def __str__(self):
        return f"{self.target.name}:{self.name}"


class TargetHeartbeat(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="heartbeats")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.target.name}:{self.created_at.isoformat()}"


class DiscoveredService(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="discovered_services")
    service_name = models.CharField(max_length=160)
    process_name = models.CharField(max_length=160, blank=True, default="")
    port = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, default="observed")
    metadata_json = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service_name"]
        unique_together = ("target", "service_name", "port")

    def __str__(self):
        return f"{self.target.name}:{self.service_name}"


class TargetOnboardingRequest(models.Model):
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("validated", "Validated"),
        ("installing", "Installing"),
        ("installed", "Installed"),
        ("failed", "Failed"),
    )

    onboarding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="onboarding_requests")
    target_type = models.CharField(max_length=32, default="linux")
    name = models.CharField(max_length=160)
    hostname = models.CharField(max_length=255)
    target_role = models.CharField(max_length=32, default="app")
    runtime_type = models.CharField(max_length=32, default="unknown")
    target_environment = models.CharField(max_length=32, default="prod")
    ssh_user = models.CharField(max_length=120, default="ec2-user", blank=True)
    ssh_port = models.PositiveIntegerField(default=22)
    profile = models.ForeignKey(TelemetryProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="onboarding_requests")
    policy_profile = models.ForeignKey(
        TargetPolicyProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="onboarding_requests",
    )
    config_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    pem_file = models.FileField(upload_to="fleet/pem/", blank=True, null=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    connectivity_status = models.CharField(max_length=32, default="untested")
    connectivity_message = models.TextField(blank=True, default="")
    last_connectivity_check_at = models.DateTimeField(null=True, blank=True)
    last_install_at = models.DateTimeField(null=True, blank=True)
    install_message = models.TextField(blank=True, default="")
    target = models.ForeignKey(Target, null=True, blank=True, on_delete=models.SET_NULL, related_name="onboarding_requests")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_onboarding_requests")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name}:{self.hostname}"


class Runbook(models.Model):
    """AI-generated runbook produced from incident RCA and remediation steps."""
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="runbooks")
    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name="runbooks", null=True, blank=True
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AgentBehaviorVersion(models.Model):
    behavior_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    name = models.CharField(max_length=120, default="default")
    prompt_version = models.CharField(max_length=120, default="prompt-v1")
    policy_version = models.CharField(max_length=120, default="policy-v1")
    model_version = models.CharField(max_length=120, default="model-v1")
    evidence_rules_version = models.CharField(max_length=120, default="evidence-v1")
    ranking_version = models.CharField(max_length=120, default="ranking-v1")
    metadata_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name}:{self.behavior_id}"


class PolicyPack(models.Model):
    """Environment-aware policy pack that controls which actions are allowed, and under what conditions."""

    pack_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    environment_pattern = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Comma-separated environment names this pack applies to (e.g. 'production,prod').",
    )
    # Allowed action categories
    allow_diagnostic = models.BooleanField(default=True)
    allow_restart_service = models.BooleanField(default=False)
    allow_database_change = models.BooleanField(default=False)
    allow_rollback = models.BooleanField(default=True)
    allow_break_glass = models.BooleanField(default=False)
    # Approval gates
    require_approval_for_restart = models.BooleanField(default=True)
    require_approval_for_db_change = models.BooleanField(default=True)
    require_approval_for_rollback = models.BooleanField(default=False)
    # Blast radius thresholds
    max_blast_radius_without_approval = models.PositiveIntegerField(
        default=1,
        help_text="Blast radius count above which approval is always required.",
    )
    # Rate limiting
    max_executions_per_service_per_hour = models.PositiveIntegerField(default=10)
    # Break-glass
    break_glass_requires_reason = models.BooleanField(default=True)
    break_glass_notifies_admins = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    def environments(self):
        return [e.strip().lower() for e in (self.environment_pattern or "").split(",") if e.strip()]


class ExecutionIntent(models.Model):
    STATUS_CHOICES = (
        ("planned", "Planned"),
        ("approval_required", "Approval Required"),
        ("approved", "Approved"),
        ("dry_run", "Dry Run"),
        ("blocked", "Blocked"),
        ("break_glass", "Break Glass"),
        ("executing", "Executing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("expired", "Expired"),
        ("rollback_pending", "Rollback Pending"),
        ("rolled_back", "Rolled Back"),
        ("verification_pending", "Verification Pending"),
        ("verified", "Verified"),
    )

    intent_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="execution_intents")
    session = models.ForeignKey(ChatSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="execution_intents")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_execution_intents")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="execution_intents")
    behavior_version = models.ForeignKey(AgentBehaviorVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="execution_intents")
    # Original intent this record is rolling back (null for non-rollback intents)
    original_intent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rollback_intents",
    )
    policy_pack = models.ForeignKey(
        PolicyPack,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execution_intents",
    )
    execution_type = models.CharField(max_length=32, default="diagnostic")
    action_type = models.CharField(max_length=64, blank=True, default="")
    service = models.CharField(max_length=120, blank=True, default="")
    environment = models.CharField(max_length=64, blank=True, default="")
    target_host = models.CharField(max_length=255, blank=True, default="")
    command = models.TextField(blank=True, default="")
    action_json = models.JSONField(default=dict, blank=True)
    action_signature = models.CharField(max_length=128, blank=True, default="", db_index=True)
    request_signature = models.CharField(max_length=128, blank=True, default="")
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    requires_approval = models.BooleanField(default=False)
    approval_token_hash = models.CharField(max_length=128, blank=True, default="")
    approval_expires_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_execution_intents")
    # Enriched approval metadata (B1)
    approver_identity = models.CharField(max_length=255, blank=True, default="")
    approval_reason = models.TextField(blank=True, default="")
    # Break-glass (A3)
    break_glass = models.BooleanField(default=False, db_index=True)
    break_glass_reason = models.TextField(blank=True, default="")
    dry_run = models.BooleanField(default=False)
    rollback_json = models.JSONField(default=dict, blank=True)
    # Pre-execution DB state snapshot for data-safe rollback (B2-DB)
    rollback_snapshot_json = models.JSONField(default=dict, blank=True,
        help_text="Pre-execution DB state snapshot for data-safe rollback generation.")
    # Pre-execution blast radius estimate (B2)
    estimated_blast_radius_json = models.JSONField(default=dict, blank=True)
    policy_decision_json = models.JSONField(default=dict, blank=True)
    ranking_json = models.JSONField(default=dict, blank=True)
    verification_json = models.JSONField(default=dict, blank=True)
    # Whether verification must pass before the linked incident can be resolved (B3)
    requires_verification = models.BooleanField(default=False)
    response_json = models.JSONField(default=dict, blank=True)
    context_fingerprint = models.CharField(max_length=128, blank=True, default="", db_index=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="planned")
    executed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.intent_id}:{self.execution_type}:{self.status}"


class RemediationOutcome(models.Model):
    outcome_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="remediation_outcomes")
    execution_intent = models.ForeignKey(ExecutionIntent, on_delete=models.CASCADE, related_name="outcomes")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="remediation_outcomes")
    action_type = models.CharField(max_length=64, blank=True, default="")
    service = models.CharField(max_length=120, blank=True, default="")
    environment = models.CharField(max_length=64, blank=True, default="")
    context_fingerprint = models.CharField(max_length=128, blank=True, default="", db_index=True)
    action_signature = models.CharField(max_length=128, blank=True, default="", db_index=True)
    success = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=64, blank=True, default="")
    time_to_recovery_seconds = models.PositiveIntegerField(null=True, blank=True)
    recurrence_within_minutes = models.PositiveIntegerField(null=True, blank=True)
    blast_radius_risk = models.FloatField(null=True, blank=True)
    operator_override = models.BooleanField(default=False)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type}:{self.service}:{self.success}"


class ReplayScenario(models.Model):
    scenario_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="replay_scenarios")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="replay_scenarios")
    session = models.ForeignKey(ChatSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="replay_scenarios")
    source = models.CharField(max_length=32, default="execution")
    title = models.CharField(max_length=255, blank=True, default="")
    alert_payload_json = models.JSONField(default=dict, blank=True)
    metrics_snapshot_json = models.JSONField(default=dict, blank=True)
    logs_snapshot_json = models.JSONField(default=dict, blank=True)
    traces_snapshot_json = models.JSONField(default=dict, blank=True)
    dependency_context_json = models.JSONField(default=dict, blank=True)
    prior_incident_memory_json = models.JSONField(default=dict, blank=True)
    chosen_action_json = models.JSONField(default=dict, blank=True)
    outcome_json = models.JSONField(default=dict, blank=True)
    behavior_version_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source}:{self.scenario_id}"


class ReplayEvaluation(models.Model):
    STATUS_CHOICES = (
        ("completed", "Completed"),
        ("failed", "Failed"),
    )

    evaluation_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    scenario = models.ForeignKey(ReplayScenario, on_delete=models.CASCADE, related_name="evaluations")
    execution_intent = models.ForeignKey(ExecutionIntent, null=True, blank=True, on_delete=models.SET_NULL, related_name="replay_evaluations")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="completed")
    scores_json = models.JSONField(default=dict, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.evaluation_id}:{self.status}"


class OperatorFeedback(models.Model):
    FEEDBACK_CHOICES = (
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("edited", "Edited"),
        ("manual_fix", "Manual Fix Applied"),
    )

    QUALITY_CHOICES = (
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("partial", "Partial"),
        ("poor", "Poor"),
        ("unknown", "Unknown"),
    )

    feedback_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="operator_feedback")
    execution_intent = models.ForeignKey(ExecutionIntent, null=True, blank=True, on_delete=models.SET_NULL, related_name="operator_feedback")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="operator_feedback")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="aiops_operator_feedback")
    feedback_type = models.CharField(max_length=32, choices=FEEDBACK_CHOICES)
    outcome_quality = models.CharField(max_length=32, choices=QUALITY_CHOICES, default="unknown")
    service = models.CharField(max_length=120, blank=True, default="")
    environment = models.CharField(max_length=64, blank=True, default="")
    action_type = models.CharField(max_length=64, blank=True, default="")
    context_fingerprint = models.CharField(max_length=128, blank=True, default="", db_index=True)
    original_action_json = models.JSONField(default=dict, blank=True)
    submitted_action_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.feedback_type}:{self.service}:{self.created_at.isoformat()}"


class RepositoryIndex(models.Model):
    INDEX_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("indexed", "Indexed"),
        ("failed", "Failed"),
    )

    repository_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="repository_indexes")
    name = models.CharField(max_length=255)
    local_path = models.CharField(max_length=1024, unique=True)
    default_branch = models.CharField(max_length=255, blank=True, default="main")
    provider = models.CharField(max_length=64, blank=True, default="local")
    repo_identifier = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    index_status = models.CharField(max_length=16, choices=INDEX_STATUS_CHOICES, default="pending")
    last_indexed_at = models.DateTimeField(null=True, blank=True)
    last_index_error = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}:{self.local_path}"


class ServiceRepositoryBinding(models.Model):
    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    service_name = models.CharField(max_length=120, db_index=True)
    application_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    repository_index = models.ForeignKey(RepositoryIndex, on_delete=models.CASCADE, related_name="service_bindings")
    team_name = models.CharField(max_length=255, blank=True, default="")
    ownership_confidence = models.FloatField(default=0.5)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service_name", "application_name"]
        unique_together = ("service_name", "application_name", "repository_index")

    def __str__(self):
        return f"{self.service_name}:{self.repository_index.name}"


class RouteBinding(models.Model):
    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    service_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    repository_index = models.ForeignKey(RepositoryIndex, on_delete=models.CASCADE, related_name="route_bindings")
    http_method = models.CharField(max_length=16, blank=True, default="ANY")
    route_pattern = models.CharField(max_length=512, db_index=True)
    handler_name = models.CharField(max_length=255, blank=True, default="")
    handler_file_path = models.CharField(max_length=1024, blank=True, default="")
    line_start = models.PositiveIntegerField(null=True, blank=True)
    line_end = models.PositiveIntegerField(null=True, blank=True)
    confidence = models.FloatField(default=0.5)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["route_pattern", "http_method"]
        unique_together = ("repository_index", "http_method", "route_pattern", "handler_name", "handler_file_path")

    def __str__(self):
        return f"{self.http_method}:{self.route_pattern}"


class SpanBinding(models.Model):
    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    service_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    repository_index = models.ForeignKey(RepositoryIndex, on_delete=models.CASCADE, related_name="span_bindings")
    span_name = models.CharField(max_length=255, db_index=True)
    symbol_name = models.CharField(max_length=255, blank=True, default="")
    symbol_file_path = models.CharField(max_length=1024, blank=True, default="")
    line_start = models.PositiveIntegerField(null=True, blank=True)
    line_end = models.PositiveIntegerField(null=True, blank=True)
    confidence = models.FloatField(default=0.5)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["span_name"]
        unique_together = ("repository_index", "span_name", "symbol_name", "symbol_file_path")

    def __str__(self):
        return f"{self.span_name}:{self.symbol_name}"


class DeploymentBinding(models.Model):
    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    service_name = models.CharField(max_length=120, db_index=True)
    environment = models.CharField(max_length=64, blank=True, default="", db_index=True)
    version = models.CharField(max_length=255, db_index=True)
    repository_index = models.ForeignKey(RepositoryIndex, on_delete=models.CASCADE, related_name="deployment_bindings")
    commit_sha = models.CharField(max_length=64, blank=True, default="", db_index=True)
    deployed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-deployed_at", "-created_at"]
        unique_together = ("service_name", "environment", "version", "repository_index")

    def __str__(self):
        return f"{self.service_name}:{self.version}"


class CodeChangeRecord(models.Model):
    change_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    repository_index = models.ForeignKey(RepositoryIndex, on_delete=models.CASCADE, related_name="change_records")
    commit_sha = models.CharField(max_length=64, db_index=True)
    author = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=512, blank=True, default="")
    changed_files = models.JSONField(default=list, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-committed_at", "-created_at"]
        unique_together = ("repository_index", "commit_sha")

    def __str__(self):
        return f"{self.repository_index.name}:{self.commit_sha[:12]}"


class SymbolRelation(models.Model):
    relation_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    repository_index = models.ForeignKey(RepositoryIndex, on_delete=models.CASCADE, related_name="symbol_relations")
    source_symbol = models.CharField(max_length=255, db_index=True)
    source_file_path = models.CharField(max_length=1024, blank=True, default="")
    target_symbol = models.CharField(max_length=255, db_index=True)
    target_file_path = models.CharField(max_length=1024, blank=True, default="")
    relation_type = models.CharField(max_length=64, default="calls")
    confidence = models.FloatField(default=0.5)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_symbol", "target_symbol"]
        unique_together = (
            "repository_index",
            "source_symbol",
            "source_file_path",
            "target_symbol",
            "target_file_path",
            "relation_type",
        )

    def __str__(self):
        return f"{self.source_symbol}->{self.target_symbol}"


# ---------------------------------------------------------------------------
# Track 4 — Integrations and Telemetry Adapters
# ---------------------------------------------------------------------------

class Integration(models.Model):
    INTEGRATION_TYPE_CHOICES = (
        ("prometheus", "Prometheus"),
        ("victoriametrics", "VictoriaMetrics"),
        ("tempo", "Tempo"),
        ("jaeger", "Jaeger"),
        ("opensearch", "OpenSearch"),
        ("elasticsearch", "Elasticsearch"),
        ("loki", "Loki"),
        ("splunk", "Splunk"),
        ("dynatrace", "Dynatrace"),
        ("datadog", "Datadog"),
        ("newrelic", "New Relic"),
        ("nagios", "Nagios"),
        ("aws", "AWS"),
        ("azure", "Azure"),
        ("gcp", "GCP"),
        ("alertmanager", "Alertmanager"),
        ("pagerduty", "PagerDuty"),
        ("servicenow", "ServiceNow"),
        ("jira", "Jira"),
        ("opsgenie", "Opsgenie"),
        ("slack", "Slack"),
        ("teams", "Microsoft Teams"),
        ("github", "GitHub"),
        ("gitlab", "GitLab"),
        ("bitbucket", "Bitbucket"),
        ("jenkins", "Jenkins"),
        ("argocd", "Argo CD"),
        ("fluxcd", "Flux CD"),
        ("kubernetes", "Kubernetes"),
        ("custom", "Custom"),
    )

    CATEGORY_CHOICES = (
        ("metrics", "Metrics"),
        ("logs", "Logs"),
        ("traces", "Traces"),
        ("alerts", "Alerts"),
        ("topology", "Topology/Inventory"),
        ("cloud", "Cloud Control Plane"),
        ("itsm", "ITSM/Incident Management"),
        ("notifications", "Notifications"),
        ("deployments", "Deployments"),
        ("code", "Source Control"),
        ("mixed", "Mixed/Hybrid"),
    )

    AUTH_MODE_CHOICES = (
        ("none", "None"),
        ("basic", "Basic Auth"),
        ("bearer", "Bearer Token"),
        ("api_key", "API Key"),
        ("oauth2", "OAuth2"),
        ("iam_role", "IAM Role"),
        ("webhook", "Webhook URL"),
    )

    STATUS_CHOICES = (
        ("healthy", "Healthy"),
        ("degraded", "Degraded"),
        ("failing", "Failing"),
        ("unknown", "Unknown"),
    )

    integration_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="integrations")
    name = models.CharField(max_length=255)
    integration_type = models.CharField(max_length=64, choices=INTEGRATION_TYPE_CHOICES)
    category = models.CharField(max_length=64, choices=CATEGORY_CHOICES)
    endpoint_url = models.CharField(max_length=1024, blank=True, default="")
    auth_mode = models.CharField(max_length=32, choices=AUTH_MODE_CHOICES, default="none")
    enabled = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    health_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="unknown")
    last_health_check_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_integration_type_display()})"


class IntegrationCredential(models.Model):
    credential_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE, related_name="credential")
    secret_ref = models.CharField(max_length=255, blank=True, default="", help_text="Reference to external secret manager or encrypted store")
    credential_metadata = models.JSONField(default=dict, blank=True)
    rotation_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Creds for {self.integration.name}"


class IntegrationBinding(models.Model):
    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="bindings")
    environment = models.CharField(max_length=120, blank=True, default="")
    application_name = models.CharField(max_length=120, blank=True, default="")
    target = models.ForeignKey("Target", null=True, blank=True, on_delete=models.SET_NULL, related_name="integration_bindings")
    priority = models.PositiveIntegerField(default=10, help_text="Lower number means higher priority for query resolution")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "-updated_at"]

    def __str__(self):
        scope = self.application_name or self.environment or (self.target.name if self.target else "Global")
        return f"{self.integration.name} -> {scope} (Priority: {self.priority})"


class IntegrationHealthCheck(models.Model):
    STATUS_CHOICES = (
        ("healthy", "Healthy"),
        ("degraded", "Degraded"),
        ("failing", "Failing"),
    )

    check_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="health_checks")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    checked_at = models.DateTimeField(auto_now_add=True)
    latency_ms = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True, default="")
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self):
        return f"{self.integration.name} check at {self.checked_at.isoformat()} - {self.status}"


class IncidentExternalTicket(models.Model):
    STATUS_CHOICES = (
        ("created", "Created"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    )

    ticket_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    tenant = models.ForeignKey(Tenant, default=default_tenant_pk, on_delete=models.CASCADE, related_name="incident_external_tickets")
    incident = models.ForeignKey("Incident", on_delete=models.CASCADE, related_name="external_tickets")
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="incident_tickets")
    external_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    external_key = models.CharField(max_length=255, blank=True, default="")
    external_url = models.CharField(max_length=1024, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="created")
    message = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("incident", "integration")

    def __str__(self):
        return f"{self.incident_id}:{self.integration.integration_type}:{self.external_key or self.external_id or self.status}"


class CloudAccountBinding(models.Model):
    binding_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, db_index=True)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="cloud_bindings")
    provider = models.CharField(max_length=64, default="aws")
    account_id = models.CharField(max_length=120, blank=True, default="")
    subscription_id = models.CharField(max_length=120, blank=True, default="")
    project_id = models.CharField(max_length=120, blank=True, default="")
    scope_name = models.CharField(max_length=255, blank=True, default="")
    environment = models.CharField(max_length=120, blank=True, default="")
    enabled = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.integration.name} -> {self.provider} ({self.scope_name or 'Global'})"
