import logging
from typing import Any, Dict, List

from django.db import transaction

from .integrations.registry import IntegrationRegistry
from .models import Incident, IncidentExternalTicket, IncidentTimelineEvent, Integration

logger = logging.getLogger("genai.integration_writeback")

WRITEBACK_TYPES = {"pagerduty", "servicenow", "jira", "opsgenie", "slack", "teams"}


def _incident_environment(incident: Incident) -> str:
    labels = incident.labels or {}
    return str(labels.get("environment") or labels.get("env") or "").strip()


def _candidate_integrations(incident: Incident) -> List[Integration]:
    environment = _incident_environment(incident)
    application = incident.application or ""
    candidates = (
        Integration.objects.filter(enabled=True, integration_type__in=WRITEBACK_TYPES)
        .select_related("credential")
        .prefetch_related("bindings")
        .order_by("category", "name")
    )
    if getattr(incident, "tenant_id", None):
        candidates = candidates.filter(tenant=incident.tenant)
    ranked: List[tuple[int, Integration]] = []
    for integration in candidates:
        metadata = integration.metadata_json or {}
        if metadata.get("incident_writeback_enabled") is False:
            continue
        bindings = list(integration.bindings.all())
        if not bindings:
            ranked.append((100, integration))
            continue
        for binding in bindings:
            if not binding.enabled:
                continue
            score = int(binding.priority or 10)
            if binding.application_name and binding.application_name != application:
                continue
            if binding.environment and binding.environment != environment:
                continue
            ranked.append((score, integration))
            break
    ranked.sort(key=lambda item: item[0])
    seen: set[int] = set()
    result: List[Integration] = []
    for _score, integration in ranked:
        if integration.id in seen:
            continue
        seen.add(integration.id)
        result.append(integration)
    return result


def _timeline_payload(ticket: IncidentExternalTicket) -> Dict[str, Any]:
    return {
        "integration_id": str(ticket.integration.integration_id),
        "integration_type": ticket.integration.integration_type,
        "integration_name": ticket.integration.name,
        "external_id": ticket.external_id,
        "external_key": ticket.external_key,
        "external_url": ticket.external_url,
        "status": ticket.status,
        "message": ticket.message,
    }


def create_incident_writebacks(incident_id: int) -> None:
    incident = Incident.objects.filter(id=incident_id, is_deleted=False).first()
    if not incident:
        return
    for integration in _candidate_integrations(incident):
        if IncidentExternalTicket.objects.filter(incident=incident, integration=integration).exists():
            continue
        try:
            adapter = IntegrationRegistry.get_adapter(integration)
            create_method = getattr(adapter, "create_incident_ticket", None)
            if not callable(create_method):
                continue
            result = create_method(incident)
            ticket = IncidentExternalTicket.objects.create(
                tenant=incident.tenant,
                incident=incident,
                integration=integration,
                external_id=str(result.get("external_id") or ""),
                external_key=str(result.get("external_key") or ""),
                external_url=str(result.get("external_url") or ""),
                status="created",
                message=str(result.get("message") or "External incident created."),
                payload=result,
            )
            IncidentTimelineEvent.objects.create(
                incident=incident,
                event_type="external_ticket_created",
                title=f"{integration.name} ticket created",
                detail=ticket.external_key or ticket.external_id or ticket.message,
                payload=_timeline_payload(ticket),
            )
        except Exception as exc:
            logger.exception("Incident writeback failed for incident=%s integration=%s", incident.incident_key, integration.integration_type)
            ticket = IncidentExternalTicket.objects.create(
                tenant=incident.tenant,
                incident=incident,
                integration=integration,
                status="failed",
                message=str(exc),
                payload={"error": str(exc)},
            )
            IncidentTimelineEvent.objects.create(
                incident=incident,
                event_type="external_ticket_failed",
                title=f"{integration.name} ticket creation failed",
                detail=str(exc),
                payload=_timeline_payload(ticket),
            )


def schedule_incident_writebacks(incident: Incident) -> None:
    transaction.on_commit(lambda: create_incident_writebacks(incident.id))
