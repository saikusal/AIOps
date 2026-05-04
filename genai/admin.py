from django.contrib import admin
from django.contrib import messages

from .code_context_ingestion import sync_repository_index
from .models import (
    AgentBehaviorVersion,
    CodeChangeRecord,
    DeploymentBinding,
    ExecutionIntent,
    InvestigationRun,
    RepositoryIndex,
    RemediationOutcome,
    ReplayEvaluation,
    ReplayScenario,
    RouteBinding,
    Runbook,
    ServiceRepositoryBinding,
    SpanBinding,
    SymbolRelation,
    ToolInvocation,
)


@admin.register(InvestigationRun)
class InvestigationRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "route", "application", "service", "target_host", "status", "updated_at")
    search_fields = ("run_id", "question", "application", "service", "target_host")
    list_filter = ("status", "route", "created_at")
    readonly_fields = ("run_id", "created_at", "updated_at", "completed_at")


@admin.register(ToolInvocation)
class ToolInvocationAdmin(admin.ModelAdmin):
    list_display = ("invocation_id", "server_name", "tool_name", "status", "latency_ms", "created_at")
    search_fields = ("invocation_id", "server_name", "tool_name")
    list_filter = ("server_name", "status", "created_at")
    readonly_fields = ("invocation_id", "created_at")


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
