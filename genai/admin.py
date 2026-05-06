from django.contrib import admin
from django.contrib import messages

from .code_context_ingestion import sync_repository_index
from .models import (
    AgentBehaviorVersion,
    ArchiveManifest,
    CodeChangeRecord,
    DataRetentionPolicy,
    DeploymentBinding,
    EvidenceArtifact,
    EvidenceBundle,
    EvidenceSnapshot,
    ExecutionIntent,
    InvestigationRun,
    InvestigationTranscript,
    LifecycleJobRun,
    RepositoryIndex,
    RemediationOutcome,
    ReplayEvaluation,
    ReplayScenario,
    RetentionHold,
    RouteBinding,
    Runbook,
    ServiceRepositoryBinding,
    SpanBinding,
    SymbolRelation,
    TargetLogIngestionProfile,
    TargetLogSource,
    TargetPolicyAssignment,
    TargetPolicyProfile,
    TargetRuntimeProfile,
    TargetServiceBinding,
    ToolInvocation,
)


@admin.register(InvestigationRun)
class InvestigationRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "route", "application", "service", "target_host", "status", "current_stage", "updated_at")
    search_fields = ("run_id", "question", "application", "service", "target_host")
    list_filter = ("status", "route", "created_at")
    readonly_fields = ("run_id", "created_at", "updated_at", "completed_at")


@admin.register(ToolInvocation)
class ToolInvocationAdmin(admin.ModelAdmin):
    list_display = ("invocation_id", "server_name", "tool_name", "status", "latency_ms", "created_at")
    search_fields = ("invocation_id", "server_name", "tool_name")
    list_filter = ("server_name", "status", "created_at")
    readonly_fields = ("invocation_id", "created_at")


@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ("slug", "data_category", "subject_type", "deployment_mode", "primary_store", "archive_store", "retention_days", "archive_after_days", "purge_after_days", "is_default")
    search_fields = ("slug", "name", "notes")
    list_filter = ("data_category", "subject_type", "deployment_mode", "primary_store", "archive_store", "is_default", "hold_supported", "object_storage_required", "vector_store_required")
    readonly_fields = ("policy_id", "created_at", "updated_at")


@admin.register(EvidenceBundle)
class EvidenceBundleAdmin(admin.ModelAdmin):
    list_display = ("bundle_id", "investigation_run", "incident", "data_category", "primary_store", "lifecycle_status", "updated_at")
    search_fields = ("bundle_id", "investigation_run__run_id", "incident__incident_key")
    list_filter = ("data_category", "primary_store", "archive_store", "lifecycle_status", "created_at")
    readonly_fields = ("bundle_id", "created_at", "updated_at", "archived_at")


@admin.register(EvidenceSnapshot)
class EvidenceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot_id", "investigation_run", "stage", "iteration_index", "confidence_score", "created_at")
    search_fields = ("snapshot_id", "investigation_run__run_id", "title", "summary")
    list_filter = ("stage", "created_at")
    readonly_fields = ("snapshot_id", "created_at")


@admin.register(InvestigationTranscript)
class InvestigationTranscriptAdmin(admin.ModelAdmin):
    list_display = ("transcript_id", "investigation_run", "sequence_index", "entry_type", "stage", "created_at")
    search_fields = ("transcript_id", "investigation_run__run_id", "title")
    list_filter = ("entry_type", "stage", "created_at")
    readonly_fields = ("transcript_id", "created_at")


# ---------------------------------------------------------------------------
# Track 3.4 — Lifecycle job history
# ---------------------------------------------------------------------------

@admin.register(LifecycleJobRun)
class LifecycleJobRunAdmin(admin.ModelAdmin):
    list_display = ("job_run_id", "job_type", "status", "triggered_by", "records_scanned", "records_pruned", "records_archived", "duration_seconds", "started_at")
    search_fields = ("job_run_id", "job_type", "triggered_by", "error_detail")
    list_filter = ("job_type", "status", "triggered_by", "started_at")
    readonly_fields = ("job_run_id", "started_at", "completed_at", "duration_seconds")


# ---------------------------------------------------------------------------
# Track 3.4 — Retention holds
# ---------------------------------------------------------------------------

@admin.register(RetentionHold)
class RetentionHoldAdmin(admin.ModelAdmin):
    list_display = ("hold_id", "hold_reason", "is_active", "evidence_bundle", "incident", "held_by", "expires_at", "created_at")
    search_fields = ("hold_id", "description", "held_by__username", "incident__incident_key")
    list_filter = ("hold_reason", "is_active", "created_at")
    readonly_fields = ("hold_id", "created_at", "released_at")


# ---------------------------------------------------------------------------
# Track 3.5 — Archive manifests
# ---------------------------------------------------------------------------

@admin.register(ArchiveManifest)
class ArchiveManifestAdmin(admin.ModelAdmin):
    list_display = ("manifest_id", "evidence_bundle", "archive_backend", "status", "size_bytes", "uploaded_at", "verified_at")
    search_fields = ("manifest_id", "object_key", "bucket_name", "checksum_sha256")
    list_filter = ("archive_backend", "status", "includes_snapshots", "includes_transcripts", "includes_tool_responses", "created_at")
    readonly_fields = ("manifest_id", "created_at", "updated_at", "uploaded_at", "verified_at")


@admin.register(EvidenceArtifact)
class EvidenceArtifactAdmin(admin.ModelAdmin):
    list_display = ("artifact_id", "artifact_type", "storage_backend", "size_bytes", "is_pruned", "evidence_bundle", "created_at")
    search_fields = ("artifact_id", "object_key", "evidence_bundle__bundle_id")
    list_filter = ("artifact_type", "storage_backend", "is_pruned", "created_at")
    readonly_fields = ("artifact_id", "created_at", "pruned_at")


@admin.register(Runbook)
class RunbookAdmin(admin.ModelAdmin):
    list_display = ("title", "incident", "created_at")
    search_fields = ("title", "content")
    list_filter = ("created_at",)


@admin.register(AgentBehaviorVersion)
class AgentBehaviorVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "prompt_version", "policy_version", "model_version", "ranking_version", "updated_at")
    search_fields = ("name", "behavior_id", "prompt_version", "policy_version", "model_version")
    list_filter = ("is_active", "created_at")
    readonly_fields = ("behavior_id", "created_at", "updated_at")


@admin.register(ExecutionIntent)
class ExecutionIntentAdmin(admin.ModelAdmin):
    list_display = ("intent_id", "execution_type", "action_type", "service", "environment", "status", "dry_run", "created_at")
    search_fields = ("intent_id", "service", "environment", "target_host", "idempotency_key")
    list_filter = ("execution_type", "status", "dry_run", "environment", "created_at")
    readonly_fields = ("intent_id", "created_at", "updated_at", "executed_at", "completed_at")


@admin.register(RemediationOutcome)
class RemediationOutcomeAdmin(admin.ModelAdmin):
    list_display = ("outcome_id", "action_type", "service", "environment", "success", "verification_status", "created_at")
    search_fields = ("outcome_id", "action_type", "service", "environment")
    list_filter = ("success", "verification_status", "environment", "created_at")
    readonly_fields = ("outcome_id", "created_at")


@admin.register(ReplayScenario)
class ReplayScenarioAdmin(admin.ModelAdmin):
    list_display = ("scenario_id", "source", "title", "created_at")
    search_fields = ("scenario_id", "source", "title")
    list_filter = ("source", "created_at")
    readonly_fields = ("scenario_id", "created_at")


@admin.register(ReplayEvaluation)
class ReplayEvaluationAdmin(admin.ModelAdmin):
    list_display = ("evaluation_id", "scenario", "status", "created_at")
    search_fields = ("evaluation_id", "status")
    list_filter = ("status", "created_at")
    readonly_fields = ("evaluation_id", "created_at")


@admin.action(description="Sync selected repository indexes")
def sync_selected_repository_indexes(modeladmin, request, queryset):
    success = 0
    failures = 0
    for repository in queryset:
        try:
            sync_repository_index(repository)
            success += 1
        except Exception as exc:
            failures += 1
            messages.error(request, f"Failed to sync {repository.name}: {exc}")
    if success:
        messages.success(request, f"Synced {success} repository index(es).")
    if failures:
        messages.warning(request, f"{failures} repository index(es) failed to sync.")


@admin.register(RepositoryIndex)
class RepositoryIndexAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "default_branch", "index_status", "last_indexed_at", "is_active")
    search_fields = ("name", "local_path", "repo_identifier")
    list_filter = ("provider", "index_status", "is_active", "created_at")
    readonly_fields = ("repository_id", "last_indexed_at", "last_index_error", "created_at", "updated_at")
    actions = (sync_selected_repository_indexes,)


@admin.register(ServiceRepositoryBinding)
class ServiceRepositoryBindingAdmin(admin.ModelAdmin):
    list_display = ("service_name", "application_name", "repository_index", "team_name", "ownership_confidence")
    search_fields = ("service_name", "application_name", "team_name", "repository_index__name")
    list_filter = ("created_at",)
    readonly_fields = ("binding_id", "created_at", "updated_at")


@admin.register(RouteBinding)
class RouteBindingAdmin(admin.ModelAdmin):
    list_display = ("service_name", "http_method", "route_pattern", "handler_name", "repository_index", "confidence")
    search_fields = ("service_name", "route_pattern", "handler_name", "handler_file_path", "repository_index__name")
    list_filter = ("http_method", "created_at")
    readonly_fields = ("binding_id", "created_at", "updated_at")


@admin.register(SpanBinding)
class SpanBindingAdmin(admin.ModelAdmin):
    list_display = ("service_name", "span_name", "symbol_name", "repository_index", "confidence")
    search_fields = ("service_name", "span_name", "symbol_name", "symbol_file_path", "repository_index__name")
    list_filter = ("created_at",)
    readonly_fields = ("binding_id", "created_at", "updated_at")


@admin.register(DeploymentBinding)
class DeploymentBindingAdmin(admin.ModelAdmin):
    list_display = ("service_name", "environment", "version", "commit_sha", "repository_index", "deployed_at")
    search_fields = ("service_name", "environment", "version", "commit_sha", "repository_index__name")
    list_filter = ("environment", "created_at")
    readonly_fields = ("binding_id", "created_at", "updated_at")


@admin.register(CodeChangeRecord)
class CodeChangeRecordAdmin(admin.ModelAdmin):
    list_display = ("repository_index", "commit_sha", "author", "title", "committed_at")
    search_fields = ("commit_sha", "author", "title", "repository_index__name")
    list_filter = ("created_at",)
    readonly_fields = ("change_id", "created_at")


@admin.register(SymbolRelation)
class SymbolRelationAdmin(admin.ModelAdmin):
    list_display = ("repository_index", "source_symbol", "target_symbol", "relation_type", "confidence")
    search_fields = ("source_symbol", "target_symbol", "source_file_path", "target_file_path", "repository_index__name")
    list_filter = ("relation_type", "created_at")
    readonly_fields = ("relation_id", "created_at", "updated_at")


@admin.register(TargetPolicyProfile)
class TargetPolicyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "target_type", "runtime_type", "sudo_mode", "is_active", "updated_at")
    search_fields = ("name", "slug", "description")
    list_filter = ("target_type", "runtime_type", "sudo_mode", "is_active", "created_at")
    readonly_fields = ("profile_id", "created_at", "updated_at")


@admin.register(TargetPolicyAssignment)
class TargetPolicyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("target", "policy_profile", "config_version", "last_apply_status", "last_applied_at", "updated_at")
    search_fields = ("target__name", "target__target_id", "policy_profile__name", "policy_profile__slug")
    list_filter = ("last_apply_status", "updated_at")
    readonly_fields = ("assignment_id", "created_at", "updated_at")


@admin.register(TargetRuntimeProfile)
class TargetRuntimeProfileAdmin(admin.ModelAdmin):
    list_display = ("target", "role", "environment", "runtime_type", "primary_restart_mode", "docker_available", "systemd_available")
    search_fields = ("target__name", "target__target_id", "hostname", "os_family")
    list_filter = ("role", "environment", "runtime_type", "primary_restart_mode", "docker_available", "systemd_available")
    readonly_fields = ("profile_id", "created_at", "updated_at")


@admin.register(TargetServiceBinding)
class TargetServiceBindingAdmin(admin.ModelAdmin):
    list_display = ("target", "service_name", "service_kind", "port", "is_primary", "updated_at")
    search_fields = ("target__name", "service_name", "systemd_unit", "container_name", "process_name")
    list_filter = ("service_kind", "is_primary", "updated_at")
    readonly_fields = ("binding_id", "created_at", "updated_at")


@admin.register(TargetLogSource)
class TargetLogSourceAdmin(admin.ModelAdmin):
    list_display = ("target", "source_type", "stream_family", "shipper_type", "is_primary", "updated_at")
    search_fields = ("target__name", "journal_unit", "file_path", "container_name", "stream_family", "shipper_type")
    list_filter = ("source_type", "shipper_type", "is_primary", "updated_at")
    readonly_fields = ("source_id", "created_at", "updated_at")


@admin.register(TargetLogIngestionProfile)
class TargetLogIngestionProfileAdmin(admin.ModelAdmin):
    list_display = ("target", "shipper_type", "stream_family", "config_version", "last_apply_status", "last_applied_at")
    search_fields = ("target__name", "shipper_type", "stream_family", "opensearch_pipeline")
    list_filter = ("shipper_type", "last_apply_status", "updated_at")
    readonly_fields = ("profile_id", "created_at", "updated_at")
