from django.contrib import admin

from .models import (
    AgentBehaviorVersion,
    ExecutionIntent,
    InvestigationRun,
    RemediationOutcome,
    ReplayEvaluation,
    ReplayScenario,
    Runbook,
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
