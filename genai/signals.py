from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .investigation_streams import investigation_streaming_enabled, publish_investigation_run_snapshot
from .integration_writeback import schedule_incident_writebacks
from .models import Incident, IncidentTimelineEvent, InvestigationRun, TenantAuditEvent, ToolInvocation


def _publish_after_commit(run_id: str) -> None:
    if not run_id or not investigation_streaming_enabled():
        return
    transaction.on_commit(lambda: publish_investigation_run_snapshot(run_id))


@receiver(post_save, sender=InvestigationRun)
def publish_investigation_run_update(sender, instance: InvestigationRun, **kwargs):
    _publish_after_commit(str(instance.run_id or ""))


@receiver(post_save, sender=ToolInvocation)
def publish_tool_invocation_update(sender, instance: ToolInvocation, **kwargs):
    if instance.investigation_run_id:
        _publish_after_commit(str(instance.investigation_run.run_id))


@receiver(post_save, sender=IncidentTimelineEvent)
def publish_incident_timeline_update(sender, instance: IncidentTimelineEvent, **kwargs):
    if not instance.incident_id or not investigation_streaming_enabled():
        return
    run = (
        InvestigationRun.objects.filter(incident_id=instance.incident_id)
        .order_by("-updated_at")
        .first()
    )
    if run:
        _publish_after_commit(str(run.run_id))


@receiver(post_save, sender=Incident)
def create_external_tickets_for_incident(sender, instance: Incident, created: bool, **kwargs):
    if created:
        schedule_incident_writebacks(instance)


@receiver(pre_delete, sender=TenantAuditEvent)
def prevent_tenant_audit_event_delete(sender, instance: TenantAuditEvent, **kwargs):
    raise ValueError("Tenant audit events are append-only and cannot be deleted.")
