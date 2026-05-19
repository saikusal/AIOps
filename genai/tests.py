import os
import logging
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import PropertyMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from genai.code_context_extractors import extract_python_artifacts
from genai.code_context_ingestion import auto_register_target_code_context, ensure_builtin_repository_indexes, sync_repository_index
from genai.code_context_services import find_service_owner, read_code_snippet, route_to_handler, search_code_context, span_to_symbol
from genai.tools.investigation import (
    _assess_code_context_quality,
    _infer_runtime_entities_from_question,
    build_investigation_context,
)
from genai.tools.router import deterministic_route
from genai.archive_service import verify_archive_manifest
from genai.mcp_client import MCPClient
from genai.mcp_registry import MCPRegistry
from genai.mcp_orchestrator import InvestigationMCPOrchestrator
from genai.integrations.registry import IntegrationRegistry
from genai.mcp_services import (
    applications_get_component_snapshot,
    applications_get_overview,
    code_find_service_owner,
    code_read_snippet,
    code_route_to_handler,
    code_search_context,
    code_span_to_symbol,
    logs_search,
    metrics_query_raw,
    metrics_query_service_overview,
    runbooks_search,
    traces_search,
)
from genai.mcp_types import MCPToolCall, MCPToolDefinition
from genai.behavior_versions import current_behavior_version_payload
from genai.execution_safety import (
    action_signature,
    context_fingerprint,
    issue_approval_token,
    resolve_idempotency_key,
    verify_approval_token,
)
from genai.multi_step_workflow import (
    annotate_investigation_workflow_with_iterations,
    build_execution_workflow,
    build_investigation_plan,
    build_iteration_plan,
    build_investigation_workflow,
    finalize_investigation_workflow,
    normalize_investigation_evidence,
)
from genai.policy_engine import (
    classify_action,
    evaluate_execution_policy,
    record_execution_attempt,
)
from genai.replay_evaluation import build_replay_scores
from genai.typed_actions import command_from_typed_action, infer_typed_action
from genai.vector_backend import WeaviateBackend, _generate_embedding, _resolve_embedding_endpoint, reset_embedding_endpoint_state
from genai.models import (
    CodeChangeRecord,
    DataRetentionPolicy,
    DiscoveredService,
    EvidenceBundle,
    EvidenceSnapshot,
    Incident,
    Integration,
    IntegrationBinding,
    IntegrationHealthCheck,
    InvestigationRun,
    InvestigationTranscript,
    RepositoryIndex,
    RouteBinding,
    ServiceRepositoryBinding,
    SpanBinding,
    SymbolRelation,
    Target,
    TargetLogIngestionProfile,
    TargetLogSource,
    TargetPolicyAssignment,
    TargetPolicyProfile,
    TargetRuntimeProfile,
    TargetServiceBinding,
)
<<<<<<< Updated upstream
=======
from genai.alert_pipeline import (
    correlate_incident,
    evaluate_suppression,
    noise_reduction_stats,
    persist_alert_event,
)
from genai.integration_writeback import create_incident_writebacks
from genai.tenancy import get_default_tenant
>>>>>>> Stashed changes
from genai.views import (
    _default_policy_profile_for_target,
    _ensure_investigation_run_for_incident,
    _ensure_target_policy_profiles,
    _fetch_elasticsearch_logs,
    _fetch_metrics_query,
    _fetch_jaeger_traces,
    _fleet_install_prereqs,
    _merge_command_output_into_investigation_run,
    _mark_target_config_apply_requested,
    _serialize_target,
    _target_generated_config_payload,
    _update_target_configuration_from_payload,
    fleet_kubernetes_install_manifest_view,
    fleet_linux_install_script_view,
    genai_chat,
)

User = get_user_model()


class MCPClientTests(SimpleTestCase):
    def test_registry_and_client_invoke_registered_tool(self):
        registry = MCPRegistry()
        registry.register(
            MCPToolDefinition(
                server_name="test-mcp",
                tool_name="demo.echo",
                description="Echo payload",
                handler=lambda params: {"echo": params.get("value")},
            )
        )
        client = MCPClient(registry)
        result = client.invoke(MCPToolCall(server_name="test-mcp", tool_name="demo.echo", params={"value": "ok"}))
        self.assertTrue(result.ok)
        self.assertEqual(result.content, {"echo": "ok"})


class MCPServiceTests(SimpleTestCase):
    def test_applications_overview_filters_by_application(self):
        payload = applications_get_overview(
            build_application_overview=lambda **_: {
                "results": [
                    {"application": "a", "components": []},
                    {"application": "b", "components": []},
                ]
            },
            application="b",
        )
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["application"], "b")

    def test_metrics_query_service_overview_uses_demo_metrics_for_demo_services(self):
        queries = []

        def _fetch(query: str):
            queries.append(query)
            return {"result": []}

        metrics_query_service_overview(service_name="app-inventory", fetch_metrics_query=_fetch)
        self.assertEqual(len(queries), 2)
        self.assertIn('demo_http_request_duration_seconds_bucket{service="app-inventory"}', queries[0])
        self.assertIn('demo_http_requests_total{service="app-inventory",status=~"5.."}', queries[1])


class RouterTests(SimpleTestCase):
    def test_genai_root_route_exists(self):
        response = Client().get("/genai/")
        self.assertIn(response.status_code, {200, 302})

    def test_deterministic_route_sends_code_context_questions_to_investigation(self):
        route = deterministic_route("List down all the endpoints in the current application")
        self.assertEqual(route, "investigation")

    def test_deterministic_route_sends_technology_questions_to_investigation(self):
        route = deterministic_route("What technologies or frameworks are used in the development of this application?")
        self.assertEqual(route, "investigation")

    def test_deterministic_route_sends_code_flow_questions_to_investigation(self):
        route = deterministic_route("Can you explain the code flow for this application?")
        self.assertEqual(route, "investigation")

    def test_deterministic_route_keeps_document_queries_on_docs_route(self):
        route = deterministic_route("Search the runbook documentation for rollback steps")
        self.assertEqual(route, "docs")

    def test_fetch_jaeger_traces_uses_trace_backend_abstraction(self):
        class FakeBackend:
            backend_name = "tempo"

            def search_traces(self, service, limit=5):
                return [{"trace_id": "trace-1", "root_service": service, "root_operation": "checkout", "duration_ms": 12, "span_count": 1, "spans": []}]

            def get_trace(self, trace_id):
                return {
                    "trace_id": trace_id,
                    "root_service": "orders-api",
                    "root_operation": "checkout",
                    "duration_ms": 12,
                    "span_count": 1,
                    "spans": [
                        {
                            "span_id": "span-1",
                            "operation": "checkout",
                            "start_time": 100,
                            "duration_us": 5000,
                            "tags": {"service.name": "orders-api"},
                            "references": [],
                        }
                    ],
                }

        with patch("genai.views.get_trace_backend", return_value=FakeBackend()), patch(
            "genai.views.metadata_cache_get_or_fetch",
            side_effect=lambda _scope, _key, fetcher, **_kwargs: fetcher(),
        ):
            payload = _fetch_jaeger_traces("orders-api")

        self.assertEqual(payload["backend"], "tempo")
        self.assertEqual(payload["data"][0]["traceID"], "trace-1")
        self.assertEqual(payload["data"][0]["spans"][0]["operationName"], "checkout")


<<<<<<< Updated upstream
=======
class AlertEvidencePolicyTests(SimpleTestCase):
    def test_all_demo_rule_alerts_have_explicit_family_mapping(self):
        rules_path = Path(settings.BASE_DIR) / "demo" / "alerts" / "demo-rules.yml"
        rule_text = rules_path.read_text()
        alert_names = re.findall(r"^\s*-\s+alert:\s+([A-Za-z0-9_:-]+)\s*$", rule_text, flags=re.MULTILINE)

        self.assertTrue(alert_names)
        self.assertEqual(set(alert_names), set(DEMO_ALERT_FAMILY_MAP))

    def test_demo_alert_family_mapping_uses_supported_families(self):
        supported = {"availability", "error_rate", "latency", "saturation", "dependency", "generic"}

        self.assertTrue(DEMO_ALERT_FAMILY_MAP)
        self.assertFalse(set(DEMO_ALERT_FAMILY_MAP.values()) - supported)

    def test_each_demo_alert_classifies_to_registered_family(self):
        for alert_name, expected_family in DEMO_ALERT_FAMILY_MAP.items():
            with self.subTest(alert_name=alert_name):
                payload = {
                    "alert_name": alert_name,
                    "status": "firing",
                    "labels": {"alertname": alert_name, "source": "demo"},
                }
                self.assertEqual(_classify_alert_family(payload, {}), expected_family)

    def test_service_down_alert_uses_availability_family_and_control_plane_diagnostic(self):
        context = {
            "alert_name": "DemoServiceDown",
            "target_host": "app-orders",
            "service_name": "app-orders",
            "dependency_graph": {"depends_on": ["db"], "blast_radius": ["gateway", "frontend"]},
            "metrics": {
                "alert_state": {
                    "result": [
                        {
                            "metric": {"alertstate": "pending"},
                            "value": [1715530000, "1"],
                        }
                    ]
                },
                "custom_query": {},
            },
            "elasticsearch": {"hits": {"hits": []}},
            "jaeger": {"data": []},
        }
        alert_payload = {
            "alert_name": "DemoServiceDown",
            "status": "firing",
            "target_host": "app-orders",
            "labels": {"service": "app-orders", "severity": "critical", "source": "demo"},
            "annotations": {"summary": "Demo backend service target is down"},
        }

        evidence = _assess_recommendation_evidence(context)
        plan = _coerce_diagnostic_plan(alert_payload, context, {}, "app-orders")

        self.assertEqual(evidence["alert_family"], "availability")
        self.assertEqual(evidence["safe_action"], "diagnose")
        self.assertIn("unavailable", evidence["confidence_reason"].lower())
        self.assertTrue(any("scrape target" in item.lower() or "availability alert" in item.lower() for item in evidence["hard_evidence"]))
        self.assertEqual(plan["target_host"], "control-agent")
        self.assertEqual(plan["target_type"], "control_plane")
        self.assertEqual(plan["diagnostic_command"], "docker inspect aiops-app-orders")
        self.assertIn("availability incident", plan["summary"].lower())
        self.assertIn("missing application logs or traces do not weaken this scenario", plan["why"].lower())

    def test_latency_alert_is_diagnosable_without_log_contradiction(self):
        context = {
            "alert_name": "DemoAppLatencyHigh",
            "target_host": "app-inventory",
            "service_name": "app-inventory",
            "dependency_graph": {"depends_on": ["db"], "blast_radius": ["gateway", "frontend"]},
            "metrics": {
                "alert_state": {
                    "result": [
                        {
                            "metric": {"alertstate": "firing"},
                            "value": [1715530000, "1"],
                        }
                    ]
                },
                "custom_query": {},
            },
            "elasticsearch": {"hits": {"hits": []}},
            "jaeger": {"data": []},
        }

        evidence = _assess_recommendation_evidence(context)

        self.assertEqual(evidence["alert_family"], "latency")
        self.assertEqual(evidence["safe_action"], "diagnose")
        self.assertNotIn("Recent logs do not contain clear active error messages.", evidence["structured_evidence"]["signals"]["contradicting"])


class IncidentDeepDiveProjectionTests(TestCase):
    def test_alert_event_deduplicates_same_lifecycle(self):
        payload = {
            "alert_name": "DemoAppErrorsHigh",
            "status": "firing",
            "fingerprint": "am-fingerprint-1",
            "starts_at": "2026-05-13T01:00:00Z",
            "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory"},
        }

        first, first_duplicate = persist_alert_event(payload, source="alertmanager")
        second, second_duplicate = persist_alert_event(payload, source="alertmanager")

        self.assertFalse(first_duplicate)
        self.assertTrue(second_duplicate)
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.repeat_count, 2)
        stats = noise_reduction_stats(minutes=1440)
        self.assertEqual(stats["raw_notifications"], 2)
        self.assertEqual(stats["unique_lifecycles"], 1)
        self.assertEqual(stats["duplicate_notifications"], 1)

    def test_alert_suppression_matches_scoped_rule(self):
        AlertSuppression.objects.create(
            name="Suppress inventory demo errors",
            alert_name="DemoAppErrorsHigh",
            service_name="app-inventory",
            reason="planned_validation_noise",
        )
        event, _duplicate = persist_alert_event(
            {
                "alert_name": "DemoAppErrorsHigh",
                "status": "firing",
                "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory"},
            },
            source="manual",
        )

        suppressed, reason = evaluate_suppression(event)

        self.assertTrue(suppressed)
        self.assertEqual(reason, "planned_validation_noise")

    def test_maintenance_window_suppresses_matching_alert(self):
        now = datetime.now(timezone.utc)
        MaintenanceWindow.objects.create(
            name="Inventory deployment",
            service_name="app-inventory",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=10),
            reason="deployment_window",
        )
        event, _duplicate = persist_alert_event(
            {
                "alert_name": "DemoAppLatencyHigh",
                "status": "firing",
                "labels": {"alertname": "DemoAppLatencyHigh", "service": "app-inventory"},
            },
            source="manual",
        )

        suppressed, reason = evaluate_suppression(event)

        self.assertTrue(suppressed)
        self.assertEqual(reason, "deployment_window")

    def test_alert_correlation_links_related_incidents_without_merging(self):
        existing = Incident.objects.create(
            application="customer-portal",
            title="Inventory errors",
            status="investigating",
            severity="critical",
            primary_service="app-inventory",
            target_host="app-inventory",
            labels={"environment": "prod"},
        )
        current = Incident.objects.create(
            application="customer-portal",
            title="Inventory latency",
            status="open",
            severity="warning",
            primary_service="app-inventory",
            target_host="app-inventory",
            labels={"environment": "prod"},
        )
        event, _duplicate = persist_alert_event(
            {
                "alert_name": "DemoAppLatencyHigh",
                "status": "firing",
                "labels": {
                    "alertname": "DemoAppLatencyHigh",
                    "service": "app-inventory",
                    "environment": "prod",
                },
            },
            source="alertmanager",
        )

        links = correlate_incident(event, current)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].related_incident_id, existing.id)
        self.assertIn("same_service", links[0].reasons)
        self.assertEqual(Incident.objects.count(), 2)
        self.assertEqual(IncidentCorrelationLink.objects.count(), 1)

    @patch("genai.views.query_llm")
    @patch("genai.views.collect_alert_context")
    def test_suppressed_ingest_skips_telemetry_and_llm(self, mocked_collect_context, mocked_query_llm):
        AlertSuppression.objects.create(
            name="Suppress inventory demo errors",
            alert_name="DemoAppErrorsHigh",
            service_name="app-inventory",
            reason="planned_validation_noise",
        )

        response = self.client.post(
            "/genai/alerts/ingest/",
            data=json.dumps(
                {
                    "alert_name": "DemoAppErrorsHigh",
                    "status": "firing",
                    "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["status"], "accepted_suppressed")
        self.assertEqual(payload["suppression_reason"], "planned_validation_noise")
        mocked_collect_context.assert_not_called()
        mocked_query_llm.assert_not_called()
        self.assertEqual(AlertEvent.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), 0)

    def test_noise_rules_api_creates_and_disables_controls(self):
        user = get_user_model().objects.create_user(username="noise-operator", password="test")
        self.client.force_login(user)

        create_response = self.client.post(
            "/genai/alerts/noise/rules/",
            data=json.dumps(
                {
                    "rule_type": "suppression",
                    "name": "Suppress inventory error storm",
                    "alert_name": "DemoAppErrorsHigh",
                    "service_name": "app-inventory",
                    "reason": "known_upstream_validation",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(create_response.status_code, 201)
        created = json.loads(create_response.content.decode("utf-8"))["rule"]
        self.assertEqual(created["rule_type"], "suppression")
        self.assertEqual(created["created_by_username"], "noise-operator")
        self.assertTrue(AlertSuppression.objects.filter(suppression_id=created["id"], enabled=True).exists())

        list_response = self.client.get("/genai/alerts/noise/rules/")
        self.assertEqual(list_response.status_code, 200)
        listed = json.loads(list_response.content.decode("utf-8"))
        self.assertEqual(len(listed["suppressions"]), 1)
        self.assertIn("stats", listed)

        disable_response = self.client.post(
            f"/genai/alerts/noise/rules/suppression/{created['id']}/delete/",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(disable_response.status_code, 200)
        self.assertFalse(AlertSuppression.objects.get(suppression_id=created["id"]).enabled)

    def test_incident_save_assigns_human_incident_number(self):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Inventory incident",
            status="open",
            severity="critical",
            primary_service="app-inventory",
            target_host="app-inventory",
        )

        self.assertEqual(incident.incident_number, f"INC-{incident.pk:06d}")

    def test_delete_incident_soft_deletes_and_hides_from_recent_list(self):
        user = get_user_model().objects.create_user(username="operator", password="test")
        self.client.force_login(user)
        incident = Incident.objects.create(
            application="customer-portal",
            title="Inventory incident",
            status="open",
            severity="critical",
            primary_service="app-inventory",
            target_host="app-inventory",
        )

        response = self.client.post(
            f"/genai/incidents/{incident.incident_key}/delete/",
            data=json.dumps({"reason": "Noise during validation."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        incident.refresh_from_db()
        self.assertTrue(incident.is_deleted)
        self.assertEqual(incident.deleted_by_username, "operator")
        self.assertEqual(incident.delete_reason, "Noise during validation.")
        self.assertTrue(incident.timeline.filter(event_type="incident_deleted").exists())

        recent = self.client.get("/genai/incidents/recent/")
        payload = json.loads(recent.content.decode("utf-8"))
        self.assertEqual(payload["results"], [])

    @patch("genai.views._ensure_investigation_run_for_incident", return_value=None)
    def test_same_active_alert_updates_existing_incident(self, _mocked_auto_investigate):
        payload = {
            "alert_name": "DemoAppErrorsHigh",
            "status": "firing",
            "target_host": "app-inventory",
            "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory"},
        }
        context = {"target_host": "app-inventory", "service_name": "app-inventory"}

        first = _correlate_alert_to_incident(payload, context, "Inventory errors detected.", "Initial firing.")
        second = _correlate_alert_to_incident(payload, context, "Inventory errors still detected.", "Repeat firing.")

        self.assertEqual(first.id, second.id)
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(first.alerts.count(), 1)

    @patch("genai.views._ensure_investigation_run_for_incident", return_value=None)
    def test_alert_correlation_without_request_tenant_uses_default_tenant(self, _mocked_auto_investigate):
        payload = {
            "alert_name": "DemoAppErrorsHigh",
            "status": "firing",
            "target_host": "app-inventory",
            "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory", "severity": "critical"},
        }
        context = {"target_host": "app-inventory", "service_name": "app-inventory"}

        incident = _correlate_alert_to_incident(payload, context, "Inventory errors detected.", "Initial firing.", tenant=None)

        self.assertEqual(incident.tenant, get_default_tenant())
        self.assertIsNotNone(incident.tenant_id)

    @patch("genai.views._ensure_investigation_run_for_incident", return_value=None)
    @patch("genai.views.query_llm", return_value=(False, "unavailable", ""))
    @patch("genai.views.collect_alert_context")
    def test_alert_ingest_without_request_tenant_assigns_default_tenant(
        self,
        mocked_collect_context,
        _mocked_query_llm,
        _mocked_auto_investigate,
    ):
        mocked_collect_context.return_value = {
            "target_host": "app-inventory",
            "service_name": "app-inventory",
            "dependency_graph": {},
        }

        response = self.client.post(
            "/genai/alerts/ingest/",
            data=json.dumps(
                {
                    "alert_name": "DemoAppErrorsHigh",
                    "status": "firing",
                    "target_host": "app-inventory",
                    "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory", "severity": "critical"},
                    "annotations": {"summary": "Inventory errors are high."},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        incident = Incident.objects.get()
        alert_event = AlertEvent.objects.get()
        self.assertEqual(incident.tenant, get_default_tenant())
        self.assertEqual(alert_event.tenant, get_default_tenant())
        self.assertEqual(alert_event.incident, incident)

    @patch("genai.views._ensure_investigation_run_for_incident", return_value=None)
    def test_resolved_same_alert_creates_new_incident_on_next_firing(self, _mocked_auto_investigate):
        payload = {
            "alert_name": "DemoAppErrorsHigh",
            "status": "firing",
            "target_host": "app-inventory",
            "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory"},
        }
        context = {"target_host": "app-inventory", "service_name": "app-inventory"}

        first = _correlate_alert_to_incident(payload, context, "Inventory errors detected.", "Initial firing.")
        first.status = "resolved"
        first.resolved_at = datetime.now(timezone.utc)
        first.save(update_fields=["status", "resolved_at", "updated_at"])
        first.alerts.update(status="resolved")

        second = _correlate_alert_to_incident(payload, context, "Inventory errors detected again.", "Fresh firing.")

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(Incident.objects.count(), 2)

    @patch("genai.views._ensure_investigation_run_for_incident", return_value=None)
    def test_alertmanager_starts_at_separates_alert_lifecycles(self, _mocked_auto_investigate):
        context = {"target_host": "app-inventory", "service_name": "app-inventory"}
        base_payload = {
            "alert_name": "DemoAppErrorsHigh",
            "status": "firing",
            "target_host": "app-inventory",
            "fingerprint": "am-fingerprint-1",
            "labels": {"alertname": "DemoAppErrorsHigh", "service": "app-inventory"},
        }

        first = _correlate_alert_to_incident(
            {**base_payload, "starts_at": "2026-05-13T01:00:00Z"},
            context,
            "Inventory errors detected.",
            "Initial firing.",
        )
        repeat = _correlate_alert_to_incident(
            {**base_payload, "starts_at": "2026-05-13T01:00:00Z"},
            context,
            "Inventory errors still detected.",
            "Repeat firing.",
        )
        fresh = _correlate_alert_to_incident(
            {**base_payload, "starts_at": "2026-05-13T02:00:00Z"},
            context,
            "Inventory errors detected again.",
            "Fresh firing.",
        )

        self.assertEqual(first.id, repeat.id)
        self.assertNotEqual(first.id, fresh.id)
        self.assertEqual(Incident.objects.count(), 2)

    @patch("genai.views._ensure_investigation_run_for_incident", return_value=None)
    @patch("genai.views.query_llm")
    @patch("genai.views.collect_alert_context")
    def test_duplicate_alertmanager_notification_skips_full_investigation(self, mocked_collect_context, mocked_query_llm, mocked_auto_investigate):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Inventory incident",
            status="investigating",
            severity="critical",
            primary_service="app-inventory",
            target_host="app-inventory",
        )
        IncidentAlert.objects.create(
            incident=incident,
            alert_name="DemoAppErrorsHigh",
            alert_fingerprint="am-fingerprint-1:2026-05-13T01:00:00Z",
            status="firing",
            target_host="app-inventory",
            service_name="app-inventory",
        )

        response = self.client.post(
            "/genai/alerts/ingest/",
            data=json.dumps(
                {
                    "receiver": "aiops",
                    "status": "firing",
                    "groupKey": "{}:{alertname=\"DemoAppErrorsHigh\"}",
                    "commonLabels": {
                        "alertname": "DemoAppErrorsHigh",
                        "service": "app-inventory",
                        "instance": "app-inventory:8000",
                    },
                    "alerts": [
                        {
                            "status": "firing",
                            "fingerprint": "am-fingerprint-1",
                            "startsAt": "2026-05-13T01:00:00Z",
                            "labels": {
                                "alertname": "DemoAppErrorsHigh",
                                "service": "app-inventory",
                                "instance": "app-inventory:8000",
                            },
                            "annotations": {"summary": "Inventory errors are still high."},
                        },
                        {
                            "status": "firing",
                            "fingerprint": "am-fingerprint-2",
                            "startsAt": "2026-05-13T01:01:00Z",
                            "labels": {
                                "alertname": "DemoAppLatencyHigh",
                                "service": "app-inventory",
                                "instance": "app-inventory:8000",
                            },
                            "annotations": {"summary": "Inventory latency is high."},
                        },
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["status"], "accepted_duplicate")
        self.assertTrue(payload["deduplicated"])
        self.assertEqual(payload["grouped_alert_count"], 2)
        self.assertEqual(len(payload["grouped_incidents"]), 1)
        self.assertEqual(payload["grouped_incidents"][0]["alert_name"], "DemoAppLatencyHigh")
        self.assertEqual(payload["grouped_incidents"][0]["action"], "created")
        mocked_collect_context.assert_not_called()
        mocked_query_llm.assert_not_called()
        self.assertTrue(incident.timeline.filter(event_type="alert_updated").exists())
        self.assertEqual(Incident.objects.count(), 2)
        self.assertEqual(IncidentAlert.objects.count(), 2)
        self.assertEqual(mocked_auto_investigate.call_count, 1)

    def test_deep_dive_projection_does_not_replace_diagnostic_command_with_remediation_command(self):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Inventory incident",
            status="investigating",
            severity="critical",
            primary_service="app-inventory",
            target_host="app-inventory",
        )
        IncidentTimelineEvent.objects.create(
            incident=incident,
            event_type="diagnostic_command_executed",
            title="Diagnostic command executed",
            detail="tail -n 200 /var/log/demo/app-inventory.log",
            payload={
                "command": "tail -n 200 /var/log/demo/app-inventory.log",
                "target_host": "app-inventory",
                "final_answer": "Inventory errors confirmed.",
                "command_output": "status=503",
                "analysis_sections": {
                    "remediation_command": "docker restart aiops-app-inventory",
                    "remediation_target_host": "control-agent",
                },
            },
        )
        IncidentTimelineEvent.objects.create(
            incident=incident,
            event_type="remediation_command_executed",
            title="Remediation command executed",
            detail="docker restart aiops-app-inventory",
            payload={
                "command": "docker restart aiops-app-inventory",
                "target_host": "control-agent",
                "final_answer": "Container restarted.",
                "command_output": "restarted",
            },
        )

        projection = _incident_deep_dive_projection(
            incident=incident,
            linked_recommendation={},
            latest_investigation={},
        )

        self.assertEqual(projection["diagnostic_command"], "tail -n 200 /var/log/demo/app-inventory.log")
        self.assertEqual(projection["target_host"], "app-inventory")
        self.assertEqual(projection["remediation_command"], "docker restart aiops-app-inventory")
        self.assertEqual(projection["remediation_target_host"], "control-agent")
        self.assertEqual(projection["post_remediation_ai_analysis"], "Container restarted.")

    def test_timeline_payload_exposes_backend_resolved_deep_dive_card(self):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Orders availability incident",
            status="open",
            severity="critical",
            primary_service="app-orders",
            target_host="app-orders",
            summary="app-orders is unavailable.",
        )
        InvestigationRun.objects.create(
            incident=incident,
            route="investigation",
            question="Old generic run",
            application="customer-portal",
            service="app-orders",
            target_host="app-orders",
            status="completed",
            current_stage="completed",
            evidence_bundle_json={
                "evidence_assessment": {
                    "safe_action": "observe",
                    "confidence_reason": "No hard failure evidence is present.",
                    "missing_evidence": ["No current service error-rate sample was available."],
                }
            },
            missing_evidence_json=["No current service error-rate sample was available."],
        )
        recent_entry = {
            "alert_id": "alert-demo",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "alert_name": "DemoServiceDown",
            "status": "firing",
            "incident_key": str(incident.incident_key),
            "target_host": "control-agent",
            "target_type": "control_plane",
            "diagnostic_command": "docker inspect aiops-app-orders",
            "should_execute": True,
            "decision_policy": "diagnose",
            "confidence_reason": "The target appears unavailable from the observability control plane.",
            "evidence_assessment": {
                "safe_action": "diagnose",
                "alert_family": "availability",
                "hard_evidence": ["Prometheus indicates the scrape target is unavailable."],
                "missing_evidence": [],
            },
        }

        with patch("genai.views.cache.get", return_value=[recent_entry]), patch(
            "genai.views._compute_incident_revenue_impact",
            return_value=None,
        ):
            from genai.views import _incident_timeline_payload

            payload = _incident_timeline_payload(incident)

        self.assertEqual(payload["deep_dive"]["diagnostic_command"], "docker inspect aiops-app-orders")
        self.assertEqual(payload["deep_dive"]["target_host"], "control-agent")
        self.assertEqual(payload["deep_dive"]["target_type"], "control_plane")
        self.assertTrue(payload["deep_dive"]["should_execute"])
        self.assertEqual(payload["deep_dive"]["decision_policy"], "diagnose")
        self.assertEqual(payload["deep_dive"]["missing_evidence"], [])

    def test_timeline_payload_derives_pending_command_from_active_alert_without_recent_recommendation(self):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Orders availability incident",
            status="open",
            severity="critical",
            primary_service="app-orders",
            target_host="app-orders",
            summary="app-orders is unavailable.",
        )
        IncidentAlert.objects.create(
            incident=incident,
            alert_name="DemoServiceDown",
            status="firing",
            target_host="app-orders",
            service_name="app-orders",
            labels={"service": "app-orders", "source": "demo"},
            annotations={"summary": "Demo backend service target is down"},
            raw_payload={
                "alert_name": "DemoServiceDown",
                "status": "firing",
                "target_host": "app-orders",
                "labels": {"service": "app-orders", "source": "demo"},
                "annotations": {"summary": "Demo backend service target is down"},
            },
        )
        InvestigationRun.objects.create(
            incident=incident,
            route="investigation",
            question="Old generic run",
            application="customer-portal",
            service="app-orders",
            target_host="app-orders",
            status="completed",
            current_stage="completed",
            evidence_bundle_json={"evidence_assessment": {"safe_action": "observe"}},
        )

        metrics_context = {
            "alert_name": "DemoServiceDown",
            "target_host": "app-orders",
            "service_name": "app-orders",
            "dependency_graph": {"depends_on": ["db"], "blast_radius": ["gateway", "frontend"]},
            "metrics": {
                "alert_state": {
                    "result": [{"metric": {"alertstate": "firing"}, "value": [1715530000, "1"]}]
                },
                "custom_query": {},
            },
            "elasticsearch": {"hits": {"hits": []}},
            "jaeger": {"data": []},
        }
        with patch("genai.views.cache.get", return_value=[]), patch(
            "genai.views.collect_alert_context",
            return_value=metrics_context,
        ), patch(
            "genai.views._compute_incident_revenue_impact",
            return_value=None,
        ):
            from genai.views import _incident_timeline_payload

            payload = _incident_timeline_payload(incident)

        self.assertEqual(payload["deep_dive"]["diagnostic_command"], "docker inspect aiops-app-orders")
        self.assertEqual(payload["deep_dive"]["target_host"], "control-agent")
        self.assertTrue(payload["deep_dive"]["should_execute"])
        self.assertEqual(payload["deep_dive"]["decision_policy"], "diagnose")


>>>>>>> Stashed changes
class LogSearchTests(TestCase):
    def test_fetch_elasticsearch_logs_prefers_onboarded_target_metadata_for_prod(self):
        target = Target.objects.create(
            name="orders-prod-01",
            hostname="orders-prod-01.internal",
            environment="production",
            target_type="linux",
        )
        binding = TargetServiceBinding.objects.create(
            target=target,
            service_name="orders-api",
            service_kind="systemd",
            systemd_unit="orders-api.service",
            container_name="orders-api",
            is_primary=True,
        )
        TargetLogSource.objects.create(
            target=target,
            service_binding=binding,
            source_type="file",
            file_path="/var/log/orders/orders-api.log",
            stream_family="logs-orders",
            is_primary=True,
        )

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"hits": {"hits": []}}

        class FakeSession:
            def post(self, _url, json=None, **_kwargs):
                captured["body"] = json
                return FakeResponse()

        with patch("genai.views.ELASTICSEARCH_URL", "http://opensearch:9200"), patch(
            "genai.views.get_http_session",
            return_value=FakeSession(),
        ), patch(
            "genai.views.metadata_cache_get_or_fetch",
            side_effect=lambda _scope, _key, fetcher, **_kwargs: fetcher(),
        ):
            _fetch_elasticsearch_logs("orders-prod-01", "timeout", service_name="orders-api")

        body = captured["body"]
        filters = body["query"]["bool"]["filter"]
        must = body["query"]["bool"]["must"]
        serialized_filter = json.dumps(filters, sort_keys=True)
        serialized_must = json.dumps(must, sort_keys=True)

        self.assertIn('"service_name.keyword": "orders-api"', serialized_filter)
        self.assertIn('"service.name.keyword": "orders-api"', serialized_filter)
        self.assertIn('"target_name.keyword": "orders-prod-01"', serialized_filter)
        self.assertIn('"hostname.keyword": "orders-prod-01.internal"', serialized_filter)
        self.assertIn('"container_name.keyword": "orders-api"', serialized_filter)
        self.assertIn('"journal_unit.keyword": "orders-api.service"', serialized_filter)
        self.assertIn('"/var/log/orders/orders-api.log"', serialized_filter)
        self.assertNotIn('*orders-prod-01.log', serialized_filter)
        self.assertIn('"message": "timeout"', serialized_must)

    def test_fetch_elasticsearch_logs_keeps_demo_file_path_fallback_for_demo_apps(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"hits": {"hits": []}}

        class FakeSession:
            def post(self, _url, json=None, **_kwargs):
                captured["body"] = json
                return FakeResponse()

        with patch("genai.views.ELASTICSEARCH_URL", "http://opensearch:9200"), patch(
            "genai.views.get_http_session",
            return_value=FakeSession(),
        ), patch(
            "genai.views.metadata_cache_get_or_fetch",
            side_effect=lambda _scope, _key, fetcher, **_kwargs: fetcher(),
        ):
            _fetch_elasticsearch_logs("app-inventory", "unauthorized", service_name="app-inventory")

        serialized_filter = json.dumps(captured["body"]["query"]["bool"]["filter"], sort_keys=True)
        self.assertIn('*app-inventory.log', serialized_filter)


class ChatRoutingTests(TestCase):
    @patch("genai.views.investigation_route_tool")
    @patch("genai.views.simple_cache.search")
    def test_genai_chat_skips_simple_cache_for_investigation_questions(self, mocked_cache_search, mocked_investigation_route):
        mocked_cache_search.return_value = {
            "question": "What technologies or frameworks are used in the development of this application?",
            "answer": "Stale cached general answer.",
            "follow_up_questions": [],
        }
        mocked_investigation_route.return_value = {
            "question": "What technologies or frameworks are used in the development of this application?",
            "answer": "Fresh investigation answer.",
            "follow_up_questions": [],
            "cached": False,
        }

        request = RequestFactory().post(
            "/genai/chat/",
            data=json.dumps({"question": "What technologies or frameworks are used in the development of this application?"}),
            content_type="application/json",
        )
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        request.user = type("AnonymousUserStub", (), {"is_authenticated": False})()

        response = genai_chat(request)
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["answer"], "Fresh investigation answer.")
        mocked_cache_search.assert_not_called()
        mocked_investigation_route.assert_called_once()


class IntegrationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="integration-tester", password="secret123")
        self.client.force_login(self.user)

    def test_integration_api_persists_configuration_and_records_health_check(self):
        response = self.client.post(
            "/genai/integrations/prometheus/",
            data=json.dumps(
                {
                    "name": "Prometheus Main",
                    "integration_type": "prometheus",
                    "category": "metrics",
                    "endpoint_url": "http://prometheus:9090",
                    "auth_mode": "none",
                    "enabled": True,
                    "credential": {"secret_ref": "", "credential_metadata": {}},
                    "bindings": [{"environment": "production", "application_name": "customer-portal", "priority": 5, "enabled": True}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        integration = Integration.objects.get(integration_type="prometheus")
        self.assertEqual(integration.endpoint_url, "http://prometheus:9090")
        self.assertEqual(integration.bindings.first().application_name, "customer-portal")

        listing = self.client.get("/genai/integrations/")
        self.assertEqual(listing.status_code, 200)
        payload = json.loads(listing.content.decode("utf-8"))
        self.assertEqual(payload["count"], 1)

        class StubAdapter:
            def __init__(self, _integration):
                self.integration = _integration

            def test_connection(self):
                return True

        with patch("genai.views.IntegrationRegistry.get_adapter", return_value=StubAdapter(integration)):
            health = self.client.post("/genai/integrations/prometheus/test/")
        self.assertEqual(health.status_code, 200)
        integration.refresh_from_db()
        self.assertEqual(integration.health_status, "healthy")
        self.assertEqual(IntegrationHealthCheck.objects.filter(integration=integration).count(), 1)

    def test_known_vendor_without_saved_integration_returns_defaults(self):
        response = self.client.get("/genai/integrations/victoriametrics/")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertFalse(payload["exists"])
        self.assertEqual(payload["integration_type"], "victoriametrics")

    def test_registry_resolves_advertised_vendor_types(self):
        for integration_type in ("victoriametrics", "newrelic", "nagios", "azure", "gcp", "jaeger", "elasticsearch", "loki", "custom"):
            adapter = IntegrationRegistry.get_adapter(Integration(integration_type=integration_type, endpoint_url="http://example.invalid", name=integration_type, category="mixed"))
            self.assertIsNotNone(adapter)


class IntegrationBindingResolutionTests(TestCase):
    def test_fetch_metrics_query_prefers_bound_integration(self):
        target = Target.objects.create(name="orders-prod-01", hostname="orders-prod-01.internal", environment="production", target_type="linux")
        integration = Integration.objects.create(
            name="Prom Main",
            integration_type="prometheus",
            category="metrics",
            endpoint_url="http://prometheus:9090",
            enabled=True,
        )
        IntegrationBinding.objects.create(
            integration=integration,
            target=target,
            application_name="customer-portal",
            environment="production",
            priority=1,
            enabled=True,
        )

        class StubMetricsAdapter:
            def __init__(self, _integration):
                self.integration = _integration

            def fetch_metrics(self, query, _time_range):
                class Row:
                    metric_name = "demo_metric"
                    value = 3.5
                    timestamp = __import__("django").utils.timezone.now()
                    labels = {"service": "orders-api"}

                self.last_query = query
                return [Row()]

        with patch("genai.views.IntegrationRegistry.get_adapter", return_value=StubMetricsAdapter(integration)), patch("genai.views.METRICS_API_URL", ""):
            payload = _fetch_metrics_query(
                "up",
                application="customer-portal",
                service_name="orders-api",
                target_host="orders-prod-01",
                environment="production",
            )

        self.assertEqual(payload["result"][0]["metric"]["__name__"], "demo_metric")
        self.assertEqual(payload["result"][0]["metric"]["service"], "orders-api")

    def test_fetch_logs_and_traces_prefer_bound_integration(self):
        target = Target.objects.create(name="orders-prod-01", hostname="orders-prod-01.internal", environment="production", target_type="linux")
        logs_integration = Integration.objects.create(
            name="OpenSearch Main",
            integration_type="opensearch",
            category="logs",
            endpoint_url="http://opensearch:9200",
            enabled=True,
        )
        traces_integration = Integration.objects.create(
            name="Tempo Main",
            integration_type="tempo",
            category="traces",
            endpoint_url="http://tempo:3200",
            enabled=True,
        )
        IntegrationBinding.objects.create(
            integration=logs_integration,
            target=target,
            application_name="customer-portal",
            environment="production",
            priority=1,
            enabled=True,
        )
        IntegrationBinding.objects.create(
            integration=traces_integration,
            target=target,
            application_name="customer-portal",
            environment="production",
            priority=1,
            enabled=True,
        )

        class StubLogsAdapter:
            def __init__(self, _integration):
                self.integration = _integration

            def fetch_logs(self, _query, _time_range, limit=100):
                class Row:
                    timestamp = __import__("django").utils.timezone.now()
                    message = "db timeout"
                    level = "error"
                    source = "orders-api"
                    attributes = {"service_name": "orders-api"}

                return [Row()]

        class StubTracesAdapter:
            def __init__(self, _integration):
                self.integration = _integration

            def fetch_traces(self, _service_name, _time_range, _tags=None):
                class Row:
                    trace_id = "trace-123"
                    span_id = "span-1"
                    service_name = "orders-api"
                    operation_name = "checkout"
                    duration_ms = 12.0
                    start_time = __import__("django").utils.timezone.now()
                    tags = {"service.name": "orders-api"}

                return [Row()]

        def _resolve_adapter(integration_model):
            if integration_model.integration_type == "opensearch":
                return StubLogsAdapter(integration_model)
            return StubTracesAdapter(integration_model)

        with patch("genai.views.IntegrationRegistry.get_adapter", side_effect=_resolve_adapter), patch("genai.views.ELASTICSEARCH_URL", ""), patch("genai.views.JAEGER_URL", ""):
            logs_payload = _fetch_elasticsearch_logs(
                "orders-prod-01",
                "timeout",
                service_name="orders-api",
                application="customer-portal",
                environment="production",
            )
            traces_payload = _fetch_jaeger_traces(
                "orders-api",
                application="customer-portal",
                target_host="orders-prod-01",
                environment="production",
            )

        self.assertEqual(logs_payload["hits"]["hits"][0]["_source"]["message"], "db timeout")
        self.assertEqual(traces_payload["backend"], "tempo")
        self.assertEqual(traces_payload["data"][0]["traceID"], "trace-123")


class IncidentAutoInvestigationTests(TestCase):
    @patch("genai.views.investigation_route_tool")
    def test_ensure_investigation_run_for_incident_launches_full_run(self, mocked_investigation_route):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Inventory latency incident",
            status="open",
            severity="warning",
            primary_service="app-inventory",
            target_host="app-inventory",
            summary="Inventory is degraded.",
            reasoning="Auto-created for test.",
            blast_radius=["gateway", "app-inventory"],
            dependency_graph={"depends_on": ["db"], "blast_radius": ["gateway", "app-inventory"]},
        )

        def _create_run(*_args, **_kwargs):
            return InvestigationRun.objects.create(
                incident=incident,
                route="investigation",
                question="Auto investigation test",
                application="customer-portal",
                service="app-inventory",
                target_host="app-inventory",
                current_stage="resolved",
                status="resolved",
            )

        mocked_investigation_route.side_effect = _create_run

        run = _ensure_investigation_run_for_incident(incident)
        self.assertIsNotNone(run)
        self.assertEqual(run.incident_id, incident.id)
        self.assertEqual(run.route, "investigation")
        self.assertEqual(run.status, "resolved")
        self.assertEqual(run.target_host, "app-inventory")
        mocked_investigation_route.assert_called_once()

        second = _ensure_investigation_run_for_incident(incident)
        self.assertEqual(run.id, second.id)
        mocked_investigation_route.assert_called_once()

    def test_investigation_plan_and_evidence_bundle_are_normalized(self):
        context = {
            "service_name": "orders-api",
            "target_host": "orders-prod-01",
            "incident": {"incident_key": "inc-1", "status": "open", "title": "Orders degraded"},
            "metrics": {"latency_p95_seconds": {"query": "demo"}},
            "elasticsearch": {"count": 12, "results": [{"message": "timeout"}]},
            "jaeger": {"data": [{"spans": [{"operationName": "checkout"}]}]},
            "dependency_graph": {"depends_on": ["postgres"], "blast_radius": ["gateway"]},
            "code_context": {"owner": {"repository": "orders-repo"}, "recent_changes": {"recent_changes": [1, 2]}},
            "source_context": {"traceback_count": 1},
            "runbooks": {"count": 2},
            "linked_recommendation": {"diagnostic_command": "journalctl -u orders-api"},
            "evidence_assessment": {
                "hard_evidence": ["error-rate spike"],
                "contradicting_evidence": ["inventory healthy"],
                "missing_evidence": ["db saturation check"],
                "safe_action": "diagnose",
                "confidence_reason": "metrics and logs agree",
            },
        }
        plan = build_investigation_plan(
            question="why is orders failing",
            scope={"service": "orders-api"},
            context=context,
        )
        self.assertEqual(plan["selected_target"], "orders-api")
        self.assertTrue(plan["candidate_hypotheses"])

        evidence_bundle = normalize_investigation_evidence(context)
        self.assertEqual(evidence_bundle["logs"]["hit_count"], 12)
        self.assertEqual(evidence_bundle["traces"]["trace_count"], 1)
        self.assertEqual(evidence_bundle["code_context"]["owner_repository"], "orders-repo")
        self.assertEqual(evidence_bundle["evidence_assessment"]["confidence_assessment"]["level"], "low")
        self.assertEqual(evidence_bundle["evidence_assessment"]["contradiction_assessment"]["severity"], "low")
        self.assertEqual(evidence_bundle["evidence_assessment"]["evidence_gap_assessment"]["status"], "low")

        iteration_plan = build_iteration_plan(
            question="why is orders failing",
            scope={"service": "orders-api"},
            context=context,
            planner=plan,
            evidence_bundle=evidence_bundle,
        )
        self.assertTrue(iteration_plan["should_continue"])
        self.assertEqual(iteration_plan["candidate_steps"][0]["tool_name"], "topology.get_dependency_context")
        self.assertEqual(iteration_plan["iterations"][0]["status"], "planned")

        workflow = build_investigation_workflow(
            question="why is orders failing",
            scope={"service": "orders-api"},
            context=context,
        )
        workflow = annotate_investigation_workflow_with_iterations(workflow, iteration_plan)
        self.assertEqual(workflow[1]["stage"], "collecting_evidence")
        self.assertEqual(workflow[3]["details"]["selected_next_tool"], "topology.get_dependency_context")
        finalized = finalize_investigation_workflow(
            workflow,
            {
                "confidence": "medium",
                "confidence_assessment": {"level": "medium", "score": 0.61},
                "contradiction_assessment": {"severity": "low", "count": 1},
                "evidence_gap_assessment": {"status": "low", "count": 1},
                "next_verification_step": "check db saturation",
                "suggested_command": "journalctl -u orders-api",
                "follow_up_questions": ["what changed?"],
            },
        )
        self.assertEqual(finalized[-2]["stage"], "verifying")
        self.assertEqual(finalized[-1]["stage"], "post_check_validator")
        self.assertEqual(finalized[-1]["details"]["confidence_assessment"]["level"], "medium")

    def test_open_search_hit_totals_count_as_logs_present(self):
        context = {
            "service_name": "orders-api",
            "target_host": "orders-prod-01",
            "metrics": {"latency_p95_seconds": {"query": "demo"}},
            "elasticsearch": {
                "hits": {
                    "total": {"value": 2, "relation": "eq"},
                    "hits": [
                        {"_source": {"message": "RuntimeError: boom"}},
                        {"_source": {"message": "db_write_failed"}},
                    ],
                }
            },
            "jaeger": {"data": [{"spans": [{"operationName": "checkout"}]}]},
            "dependency_graph": {"depends_on": ["postgres"], "blast_radius": ["gateway"]},
            "code_context": {"owner": {"repository": "orders-repo"}},
            "evidence_assessment": {"hard_evidence": ["runtime failure"]},
        }

        evidence_bundle = normalize_investigation_evidence(context)
        workflow = build_investigation_workflow(
            question="why is orders failing",
            scope={"service": "orders-api"},
            context=context,
        )

        self.assertEqual(evidence_bundle["logs"]["hit_count"], 2)
        self.assertTrue(workflow[1]["details"]["logs_present"])

    def test_build_investigation_context_fetches_recent_scoped_logs_without_error_keyword(self):
        log_queries = []

        def _fake_fetch_logs(target_host, query_text, *, service_name=None):
            log_queries.append(query_text)
            return {
                "hits": {
                    "total": {"value": 1, "relation": "eq"},
                    "hits": [
                        {
                            "_source": {
                                "message": "RuntimeError: Insufficient inventory for SKU-100: available=0, requested=1"
                            }
                        }
                    ],
                }
            }

        context = build_investigation_context(
            "Auto-investigate incident=inc-1 application=customer-portal service=app-inventory",
            {"application": "customer-portal", "service": "app-inventory", "incident": "inc-1"},
            incident_model=Incident,
            build_application_overview=lambda **_: {
                "results": [
                    {
                        "application": "customer-portal",
                        "components": [{"service": "app-inventory", "target_host": "app-inventory"}],
                    }
                ]
            },
            incident_timeline_payload=lambda _incident: {},
            get_dependency_context=lambda _service: {"depends_on": ["db"], "blast_radius": ["app-inventory", "db"]},
            application_graph_payload=lambda _application: {"nodes": []},
            fetch_elasticsearch_logs=_fake_fetch_logs,
            fetch_jaeger_traces=lambda _service: {},
            fetch_metrics_query=lambda _query: {},
            mcp_orchestrator=None,
        )

        self.assertEqual(log_queries, [""])
        self.assertIn("RuntimeError", context["elasticsearch"]["hits"]["hits"][0]["_source"]["message"])

    def test_code_context_quality_flags_stale_or_weak_mappings(self):
        assessment = _assess_code_context_quality(
            {
                "owner": {
                    "repository": "orders-repo",
                    "ownership_confidence": 0.45,
                    "repository_index_status": "failed",
                    "repository_last_indexed_at": "2026-04-01T00:00:00+00:00",
                },
                "route_binding": {
                    "handler": "orders.views.create_order",
                    "confidence": 0.4,
                },
            }
        )
        self.assertEqual(assessment["quality"], "low")
        self.assertFalse(assessment["safe_to_claim_code_root_cause"])
        self.assertTrue(assessment["stale_index"])
        self.assertTrue(assessment["weak_signals"])

    def test_iteration_plan_stops_when_evidence_is_sufficient(self):
        context = {
            "service_name": "orders-api",
            "target_host": "orders-prod-01",
            "metrics": {"latency_p95_seconds": {"query": "demo"}},
            "elasticsearch": {"count": 3, "results": [{"message": "timeout"}]},
            "jaeger": {"data": [{"spans": [{"operationName": "checkout"}]}]},
            "dependency_graph": {"depends_on": ["postgres"], "blast_radius": ["gateway"]},
            "code_context": {"owner": {"repository": "orders-repo"}, "recent_changes": {"recent_changes": [1]}},
            "source_context": {"traceback_count": 0},
            "runbooks": {"count": 1},
            "evidence_assessment": {
                "hard_evidence": ["error-rate spike"],
                "contradicting_evidence": [],
                "missing_evidence": [],
                "safe_action": "diagnose",
            },
        }
        plan = build_investigation_plan(
            question="why is orders failing",
            scope={"service": "orders-api"},
            context=context,
        )
        evidence_bundle = normalize_investigation_evidence(context)
        iteration_plan = build_iteration_plan(
            question="why is orders failing",
            scope={"service": "orders-api"},
            context=context,
            planner=plan,
            evidence_bundle=evidence_bundle,
        )
        self.assertFalse(iteration_plan["should_continue"])
        self.assertEqual(iteration_plan["stop_reason"], "evidence_sufficient")
        self.assertEqual(iteration_plan["candidate_steps"][0]["tool_name"], "none")


class TypedActionTests(SimpleTestCase):
    def test_infer_kubernetes_rollout_restart_action(self):
        action = infer_typed_action(
            command="kubectl rollout restart deployment/orders-api -n prod",
            target_host="prod-cluster",
            why="Restart the unhealthy workload.",
            requires_approval=True,
            service="orders-api",
        )
        self.assertEqual(action["action"], "restart_service")
        self.assertEqual(action["metadata"]["executor"], "kubernetes")
        self.assertEqual(action["metadata"]["resource_kind"], "deployment")
        self.assertEqual(action["metadata"]["resource_name"], "orders-api")
        self.assertEqual(action["metadata"]["namespace"], "prod")
        self.assertEqual(
            command_from_typed_action(action),
            "kubectl rollout restart deployment/orders-api -n prod",
        )

    def test_component_snapshot_matches_service_or_target_host(self):
        payload = applications_get_component_snapshot(
            application="customer-portal",
            service="gateway",
            build_application_overview=lambda **_: {
                "results": [
                    {
                        "application": "customer-portal",
                        "components": [
                            {"service": "gateway", "target_host": "gw-01", "kind": "gateway"},
                        ],
                    }
                ]
            },
        )
        self.assertEqual(payload["kind"], "gateway")

    def test_metrics_service_overview_returns_expected_keys(self):
        payload = metrics_query_service_overview(
            service_name="gateway",
            fetch_metrics_query=lambda query: {"query": query},
        )
        self.assertIn("latency_p95_seconds", payload)
        self.assertIn("error_rate", payload)

    def test_metrics_raw_query_passthrough(self):
        payload = metrics_query_raw(
            query='up{job="demo"}',
            fetch_metrics_query=lambda query: {"query": query},
        )
        self.assertEqual(payload["query"], 'up{job="demo"}')

    def test_logs_search_passthrough(self):
        payload = logs_search(
            target_host="host-1",
            query="error",
            fetch_elasticsearch_logs=lambda target_host, query: {"target_host": target_host, "query": query},
        )
        self.assertEqual(payload["target_host"], "host-1")
        self.assertEqual(payload["query"], "error")

    def test_traces_search_passthrough(self):
        payload = traces_search(
            service_name="gateway",
            fetch_jaeger_traces=lambda service_name: {"service_name": service_name, "traces": []},
        )
        self.assertEqual(payload["service_name"], "gateway")

    def test_runbooks_search_returns_empty_without_lookup_inputs(self):
        payload = runbooks_search(query="", incident_key="", incident_model=None, runbook_model=None)
        self.assertEqual(payload["count"], 0)

    def test_code_context_services_passthrough(self):
        with patch("genai.mcp_services._code_find_service_owner", return_value={"ok": True, "repository": "orders"}):
            payload = code_find_service_owner(service_name="app-orders", application_name="shop")
            self.assertTrue(payload["ok"])
        with patch("genai.mcp_services._code_route_to_handler", return_value={"ok": True, "handler": "orders_view"}):
            payload = code_route_to_handler(service_name="app-orders", route="/orders", http_method="GET")
            self.assertEqual(payload["handler"], "orders_view")
        with patch("genai.mcp_services._code_span_to_symbol", return_value={"ok": True, "symbol": "checkout"}):
            payload = code_span_to_symbol(service_name="app-orders", span_name="checkout")
            self.assertEqual(payload["symbol"], "checkout")
        with patch("genai.mcp_services._code_search_code_context", return_value={"ok": True, "matches": [{"module_path": "views.py"}]}):
            payload = code_search_context(repository="orders-repo", query="health endpoint")
            self.assertTrue(payload["ok"])
        with patch("genai.mcp_services._code_read_code_snippet", return_value={"ok": True, "snippet": "1 | def health():"}):
            payload = code_read_snippet(repository="orders-repo", module_path="views.py")
            self.assertTrue(payload["ok"])


class PolicyEngineTests(SimpleTestCase):
    def setUp(self):
        self._cache_store = {}

        class _FakeCache:
            def __init__(self, store):
                self.store = store

            def get(self, key, default=None):
                return self.store.get(key, default)

            def set(self, key, value, timeout=None):
                self.store[key] = value

        self.cache_patcher = patch("genai.egap_protocol.cache", _FakeCache(self._cache_store))
        self.cache_patcher.start()

    def tearDown(self):
        self.cache_patcher.stop()

    def test_classify_database_change(self):
        result = classify_action('psql -h db -c "UPDATE orders SET status = \'ok\'"', "remediation")
        self.assertEqual(result["action_type"], "database_change")

    @patch.dict(
        "os.environ",
        {
            "AIOPS_POLICY_ALLOW_PROTECTED_ENV_RESTARTS": "false",
            "AIOPS_POLICY_REQUIRE_APPROVAL_FOR_RESTARTS": "true",
        },
        clear=False,
    )
    def test_restart_blocked_in_production(self):
        decision = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="prod-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "production"}},
            approval_present=True,
            actor="tester",
        )
        self.assertEqual(decision["decision"], "blocked")
        self.assertEqual(decision["environment"], "production")


class TargetConfigurationTests(TestCase):
    def test_default_policy_profile_prefers_db_operator_for_db_targets(self):
        _ensure_target_policy_profiles(target_type="linux", runtime_type="systemd")
        profile = _default_policy_profile_for_target(
            target_type="linux",
            runtime_type="systemd",
            target_role="db",
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.slug, "linux-db-operator")
        self.assertTrue(profile.allow_db_changes)
        self.assertIn("psql -h db -U user -d aiops -c", profile.allowed_command_patterns or [])

    def test_generated_target_config_and_apply_request(self):
        target = Target.objects.create(
            target_id="target-123",
            name="orders-prod-01",
            target_type="linux",
            environment="production",
            hostname="orders-prod-01",
            status="connected",
        )
        profile = TargetPolicyProfile.objects.create(
            slug="linux-app-systemd-test",
            name="Linux App Systemd",
            target_type="linux",
            runtime_type="systemd",
        )
        payload = {
            "runtime_profile": {
                "role": "app",
                "environment": "prod",
                "runtime_type": "systemd",
                "hostname": "orders-prod-01",
                "os_family": "linux",
                "docker_available": False,
                "systemd_available": True,
                "primary_restart_mode": "systemctl",
                "notes": "managed by config editor",
            },
            "policy_profile_slug": profile.slug,
            "service_bindings": [
                {
                    "service_name": "orders-api",
                    "service_kind": "systemd",
                    "systemd_unit": "orders-api.service",
                    "port": 8080,
                    "is_primary": True,
                }
            ],
            "log_sources": [
                {
                    "service_name": "orders-api",
                    "source_type": "journald",
                    "journal_unit": "orders-api.service",
                    "stream_family": "logs-linux",
                    "shipper_type": "fluent-bit",
                    "is_primary": True,
                }
            ],
            "log_ingestion_profile": {
                "shipper_type": "fluent-bit",
                "stream_family": "logs-linux",
                "opensearch_pipeline": "opsmitra-linux-default",
                "record_metadata_json": {"service_name": "orders-api"},
            },
        }

        _update_target_configuration_from_payload(target, payload)
        target.refresh_from_db()

        self.assertTrue(TargetRuntimeProfile.objects.filter(target=target, runtime_type="systemd").exists())
        self.assertTrue(TargetPolicyAssignment.objects.filter(target=target, policy_profile=profile).exists())
        self.assertTrue(TargetServiceBinding.objects.filter(target=target, service_name="orders-api").exists())
        self.assertTrue(TargetLogSource.objects.filter(target=target, source_type="journald").exists())
        self.assertTrue(TargetLogIngestionProfile.objects.filter(target=target, stream_family="logs-linux").exists())

        generated = _target_generated_config_payload(target)
        self.assertEqual(generated["target"]["target_id"], "target-123")
        self.assertEqual(generated["runtime_profile"]["runtime_type"], "systemd")
        self.assertEqual(generated["policy_assignment"]["policy_profile"]["slug"], profile.slug)
        self.assertEqual(generated["service_bindings"][0]["service_name"], "orders-api")
        self.assertTrue(generated["generated_configs"]["fluent_bit"]["enabled"])
        self.assertIn("Logstash_Prefix   logs-linux", generated["generated_configs"]["fluent_bit"]["config"])
        self.assertIn("Systemd_Filter    _SYSTEMD_UNIT=orders-api.service", generated["generated_configs"]["fluent_bit"]["config"])

        apply_payload = _mark_target_config_apply_requested(target)
        self.assertEqual(apply_payload["status"], "requested")

        target.refresh_from_db()
        self.assertEqual(target.policy_assignment.last_apply_status, "requested")
        self.assertEqual(target.log_ingestion_profile.last_apply_status, "requested")

    def test_linux_agent_allowed_commands_include_db_psql_prefix(self):
        allowed_commands_path = Path(settings.BASE_DIR) / "agent" / "allowed_commands.json"
        payload = json.loads(allowed_commands_path.read_text())
        self.assertIn(
            ["psql", "-h", "db", "-U", "user", "-d", "aiops", "-c"],
            payload.get("allowed_prefixes", []),
        )

    @patch.dict(
        "os.environ",
        {
            "AIOPS_POLICY_ALLOW_PROTECTED_ENV_RESTARTS": "true",
            "AIOPS_POLICY_REQUIRE_APPROVAL_FOR_RESTARTS": "true",
        },
        clear=False,
    )
    def test_restart_requires_approval_when_not_present(self):
        decision = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "staging"}},
            approval_present=False,
            actor="tester",
        )
        self.assertEqual(decision["decision"], "requires_approval")
        self.assertTrue(decision["requires_approval"])

    @patch.dict(
        "os.environ",
        {
            "AIOPS_POLICY_ALLOW_DB_CHANGES": "false",
        },
        clear=False,
    )
    def test_database_changes_blocked_by_default(self):
        decision = evaluate_execution_policy(
            command='psql -h db -c "DELETE FROM incidents"',
            target_host="db",
            execution_type="remediation",
            context={"service_name": "db", "labels": {"environment": "staging"}},
            approval_present=True,
            actor="tester",
        )
        self.assertEqual(decision["decision"], "blocked")
        self.assertEqual(decision["action_type"], "database_change")

    @patch.dict(
        "os.environ",
        {
            "AIOPS_POLICY_ALLOW_PROTECTED_ENV_RESTARTS": "true",
            "AIOPS_POLICY_REQUIRE_APPROVAL_FOR_RESTARTS": "false",
            "AIOPS_POLICY_EXECUTION_RETRY_LIMIT": "2",
            "AIOPS_POLICY_RETRY_WINDOW_SECONDS": "3600",
            "AIOPS_POLICY_RESTART_COOLDOWN_SECONDS": "0",
        },
        clear=False,
    )
    def test_retry_limit_blocks_after_recorded_attempts(self):
        first = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "staging"}},
            approval_present=True,
            actor="tester",
        )
        record_execution_attempt(
            policy_decision=first,
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            success=False,
        )
        second = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "staging"}},
            approval_present=True,
            actor="tester",
        )
        record_execution_attempt(
            policy_decision=second,
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            success=False,
        )
        blocked = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "staging"}},
            approval_present=True,
            actor="tester",
        )
        self.assertEqual(blocked["decision"], "blocked")
        self.assertGreaterEqual(blocked["retry_count"], 2)

    @patch.dict(
        "os.environ",
        {
            "AIOPS_POLICY_ALLOW_PROTECTED_ENV_RESTARTS": "true",
            "AIOPS_POLICY_REQUIRE_APPROVAL_FOR_RESTARTS": "false",
            "AIOPS_POLICY_EXECUTION_RETRY_LIMIT": "5",
            "AIOPS_POLICY_RETRY_WINDOW_SECONDS": "3600",
            "AIOPS_POLICY_RESTART_COOLDOWN_SECONDS": "600",
        },
        clear=False,
    )
    def test_cooldown_blocks_immediate_repeat_restart(self):
        decision = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "staging"}},
            approval_present=True,
            actor="tester",
        )
        record_execution_attempt(
            policy_decision=decision,
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            success=True,
        )
        blocked = evaluate_execution_policy(
            command="docker restart aiops-demo-orders",
            target_host="app-orders-01",
            execution_type="remediation",
            context={"service_name": "app-orders", "labels": {"environment": "staging"}},
            approval_present=True,
            actor="tester",
        )
        self.assertEqual(blocked["decision"], "blocked")
        self.assertGreater(blocked["cooldown_remaining_seconds"], 0)


class TypedActionTests(SimpleTestCase):
    def test_infer_restart_service_action(self):
        action = infer_typed_action(
            command="docker restart aiops-demo-orders",
            target_host="control-agent",
            why="healthcheck failed",
            requires_approval=True,
            service="app-orders",
        )
        self.assertEqual(action["action"], "restart_service")
        self.assertEqual(action["target"], "app-orders")
        self.assertTrue(action["requires_approval"])
        self.assertIn("validation_plan", action)

    def test_infer_database_change_action(self):
        action = infer_typed_action(
            command='psql -h db -U user -d aiops -c "UPDATE inventory SET quantity = 1 WHERE sku = \'A\'"',
            target_host="db",
            why="fix depleted inventory row",
            requires_approval=True,
            service="db",
        )
        self.assertEqual(action["action"], "database_change")
        self.assertEqual(action["target_host"], "db")
        self.assertEqual(action["metadata"]["executor"], "psql")

    def test_command_from_typed_action_reuses_restart_command(self):
        command = command_from_typed_action(
            {
                "action": "restart_service",
                "target": "app-orders",
                "target_host": "control-agent",
                "command": "docker restart aiops-demo-orders",
                "metadata": {"container_name": "aiops-demo-orders"},
            }
        )
        self.assertEqual(command, "docker restart aiops-demo-orders")


class PhaseTwoHelperTests(SimpleTestCase):
    def test_behavior_version_payload_uses_env_defaults(self):
        payload = current_behavior_version_payload()
        self.assertIn("prompt_version", payload)
        self.assertIn("policy_version", payload)
        self.assertIn("ranking_version", payload)

    def test_approval_token_round_trip(self):
        raw_token, token_hash, expires_at = issue_approval_token("intent-123")
        self.assertTrue(verify_approval_token(raw_token, token_hash, expires_at))

    def test_idempotency_key_is_deterministic(self):
        first = resolve_idempotency_key(
            execution_type="remediation",
            incident_key="inc-1",
            action_payload={"action": "restart_service", "target": "app-orders"},
            original_question="restart orders",
        )
        second = resolve_idempotency_key(
            execution_type="remediation",
            incident_key="inc-1",
            action_payload={"action": "restart_service", "target": "app-orders"},
            original_question="restart orders",
        )
        self.assertEqual(first, second)

    def test_signatures_change_when_action_changes(self):
        first = action_signature({"action": "restart_service", "target": "app-orders"})
        second = action_signature({"action": "restart_service", "target": "app-billing"})
        self.assertNotEqual(first, second)
        self.assertNotEqual(
            context_fingerprint({"incident_key": "1", "service": "app-orders"}),
            context_fingerprint({"incident_key": "1", "service": "app-billing"}),
        )

    def test_replay_scores_reward_resolved_safe_execution(self):
        scores = build_replay_scores(
            verification={"status": "resolved"},
            policy_decision={"decision": "allowed", "blocked": False, "action_type": "restart_service"},
            execution_success=True,
        )
        self.assertGreater(scores["overall"], 0.5)


class MultiStepWorkflowTests(SimpleTestCase):
    def test_investigation_workflow_has_expected_stages(self):
        workflow = build_investigation_workflow(
            question="What caused the incident?",
            scope={"application": "customer-portal", "service": "gateway"},
            context={
                "application": "customer-portal",
                "service_name": "gateway",
                "target_host": "gw-01",
                "linked_recommendation": {"diagnostic_command": "tail -n 100 /var/log/demo/gateway.log"},
                "runbooks": {"count": 1},
                "evidence_assessment": {
                    "hard_evidence": ["5xx spike"],
                    "contradicting_evidence": ["db healthy"],
                    "missing_evidence": [],
                    "confidence_reason": "Multiple signals agree.",
                },
            },
        )
        self.assertEqual(
            [stage["stage"] for stage in workflow],
            ["planner", "collecting_evidence", "assessing_evidence", "planning_next_step", "remediation_selector"],
        )
        finalized = finalize_investigation_workflow(workflow, {"confidence": "high", "next_verification_step": "Check gateway logs", "follow_up_questions": ["What changed?"]})
        self.assertEqual(finalized[-1]["stage"], "post_check_validator")

    def test_execution_workflow_has_executor_and_verifier(self):
        workflow = build_execution_workflow(
            execution_type="remediation",
            question="Apply restart",
            typed_action={"action": "restart_service", "target": "app-orders"},
            target_host="control-agent",
            policy_decision={"decision": "allowed", "requires_approval": True},
            ranking={"score": 0.8, "sample_size": 5},
            baseline_evidence={"signals": {"confirming": ["high 5xx"], "contradicting": ["db healthy"]}, "confidence_score": 0.7},
            verification={
                "status": "resolved",
                "reason": "Error rate dropped",
                "verification_loop_state": "closed",
                "requires_follow_up": False,
                "issue_score_delta": -0.7,
                "recommended_next_step": "Close the incident or continue passive monitoring for recurrence.",
            },
            analysis_sections={"remediation_typed_action": {"action": "diagnostic"}},
            execution_status="completed",
            dry_run=False,
        )
        stage_names = [stage["stage"] for stage in workflow]
        self.assertIn("executor", stage_names)
        self.assertIn("verifier", stage_names)
        self.assertEqual(workflow[-1]["stage"], "post_check_validator")
        verifier = next(stage for stage in workflow if stage["stage"] == "verifier")
        self.assertEqual(verifier["details"]["verification_loop_state"], "closed")
        self.assertFalse(verifier["details"]["requires_follow_up"])


class CodeContextExtractorTests(SimpleTestCase):
    def test_runtime_entity_inference_uses_live_application_overview(self):
        inferred = _infer_runtime_entities_from_question(
            "How does app-orders integrate with other systems?",
            build_application_overview=lambda **_: {
                "results": [
                    {
                        "application": "customer-portal",
                        "title": "Customer Portal",
                        "components": [
                            {"service": "app-orders", "target_host": "app-orders", "title": "Orders"},
                            {"service": "gateway", "target_host": "gateway", "title": "Gateway"},
                        ],
                    }
                ]
            },
        )
        self.assertEqual(inferred["application"], "customer-portal")
        self.assertEqual(inferred["service"], "app-orders")

    def test_extract_python_artifacts_finds_route_and_span(self):
        temp_dir = tempfile.mkdtemp(prefix="aiops-code-context-")
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        file_path = os.path.join(temp_dir, "app.py")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(
                """
from fastapi import APIRouter
router = APIRouter()

@router.get("/orders")
def list_orders():
    with tracer.start_as_current_span("orders.list"):
        return fetch_orders()
"""
            )
        artifacts = extract_python_artifacts(temp_dir)
        self.assertEqual(artifacts["route_bindings"][0]["route_pattern"], "/orders")
        self.assertEqual(artifacts["span_bindings"][0]["span_name"], "orders.list")
        self.assertTrue(any(rel["target_symbol"] == "fetch_orders" for rel in artifacts["symbol_relations"]))


class CodeContextIntegrationTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aiops-repo-")
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        repo_file = os.path.join(self.temp_dir, "views.py")
        with open(repo_file, "w", encoding="utf-8") as handle:
            handle.write(
                """
from fastapi import APIRouter
router = APIRouter()

def helper():
    return True

@router.get("/health")
def health():
    with tracer.start_as_current_span("health.check"):
        helper()
        return {"ok": True}
"""
            )
        subprocess.run(["git", "-C", self.temp_dir, "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", self.temp_dir, "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", self.temp_dir, "-c", "user.email=test@example.com", "-c", "user.name=Test User", "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_sync_repository_index_populates_bindings(self):
        repository = RepositoryIndex.objects.create(
            name="orders-repo",
            local_path=self.temp_dir,
            metadata={"service_names": ["app-orders"], "application_name": "shop", "team_name": "orders-team"},
        )
        result = sync_repository_index(repository, recent_commit_limit=5)
        self.assertEqual(result["route_count"], 1)
        self.assertEqual(RouteBinding.objects.filter(repository_index=repository).count(), 1)
        self.assertEqual(SpanBinding.objects.filter(repository_index=repository).count(), 1)
        self.assertTrue(SymbolRelation.objects.filter(repository_index=repository).exists())
        self.assertTrue(ServiceRepositoryBinding.objects.filter(repository_index=repository, service_name="app-orders").exists())

    @patch("genai.code_context_ingestion.shutil.which", return_value=None)
    def test_sync_repository_index_succeeds_without_git_binary(self, mocked_which):
        repository = RepositoryIndex.objects.create(
            name="orders-repo-no-git",
            local_path=self.temp_dir,
            metadata={"service_names": ["app-orders"], "application_name": "shop", "team_name": "orders-team"},
        )
        result = sync_repository_index(repository, recent_commit_limit=5)
        repository.refresh_from_db()
        self.assertEqual(result["route_count"], 1)
        self.assertEqual(result["recent_commit_count"], 0)
        self.assertEqual(repository.index_status, "indexed")
        self.assertEqual(repository.last_index_error, "")
        self.assertEqual(repository.metadata.get("git_available"), False)
        self.assertIn(
            "git_binary_unavailable_recent_change_enrichment_skipped",
            repository.metadata.get("index_warnings", []),
        )
        self.assertEqual(CodeChangeRecord.objects.filter(repository_index=repository).count(), 0)
        mocked_which.assert_called()

    def test_code_context_services_resolve_owner_route_and_span(self):
        repository = RepositoryIndex.objects.create(
            name="orders-repo",
            local_path=self.temp_dir,
            metadata={"service_names": ["app-orders"], "application_name": "shop", "team_name": "orders-team"},
        )
        sync_repository_index(repository, recent_commit_limit=5)
        owner = find_service_owner(service_name="app-orders", application_name="shop")
        self.assertTrue(owner["ok"])
        self.assertEqual(owner["repository"], "orders-repo")
        route = route_to_handler(service_name="app-orders", route="/health", http_method="GET")
        self.assertTrue(route["ok"])
        self.assertIn("health", route["handler"])
        span = span_to_symbol(service_name="app-orders", span_name="health.check")
        self.assertTrue(span["ok"])
        self.assertEqual(span["symbol"], "health")

    def test_code_context_search_and_snippet_resolution(self):
        repository = RepositoryIndex.objects.create(
            name="orders-repo",
            local_path=self.temp_dir,
            metadata={"service_names": ["app-orders"], "application_name": "shop", "team_name": "orders-team"},
        )
        sync_repository_index(repository, recent_commit_limit=5)
        search_result = search_code_context(
            repository="orders-repo",
            query="Which module handles the health endpoint?",
            service_name="app-orders",
            limit=4,
        )
        self.assertTrue(search_result["ok"])
        self.assertTrue(search_result["matches"])
        endpoint_result = search_code_context(
            repository="orders-repo",
            query="Can you provide details about the application's endpoints?",
            service_name="app-orders",
            limit=6,
        )
        self.assertTrue(endpoint_result["ok"])
        self.assertGreater(endpoint_result["route_inventory"]["route_count"], 0)
        self.assertTrue(endpoint_result["route_inventory"]["sample_routes"])
        snippet_result = read_code_snippet(
            repository="orders-repo",
            module_path="views.py",
            symbol="health",
            line_start=6,
            line_end=10,
            context_lines=4,
        )
        self.assertTrue(snippet_result["ok"])
        self.assertIn("def health()", snippet_result["snippet"])

    @patch.dict(
        "os.environ",
        {
            "AIOPS_CODE_CONTEXT_ENABLED": "true",
            "AIOPS_CODE_CONTEXT_PROVIDER": "internal",
        },
        clear=False,
    )
    def test_auto_register_target_code_context_from_target_metadata(self):
        target = Target.objects.create(
            name="orders-host",
            target_type="linux",
            environment="staging",
            metadata_json={
                "repo_path": self.temp_dir,
                "repo_name": "orders-repo",
                "service_names": ["app-orders"],
                "application_name": "shop",
                "team_name": "orders-team",
            },
        )
        results = auto_register_target_code_context(target)
        self.assertEqual(len(results), 1)
        repository = RepositoryIndex.objects.get(name="orders-repo")
        self.assertEqual(repository.local_path, self.temp_dir)
        self.assertTrue(ServiceRepositoryBinding.objects.filter(repository_index=repository, service_name="app-orders").exists())

    @patch.dict(
        "os.environ",
        {
            "AIOPS_CODE_CONTEXT_ENABLED": "true",
            "AIOPS_CODE_CONTEXT_PROVIDER": "internal",
            "AIOPS_CODE_CONTEXT_AUTO_ROOTS": "",
        },
        clear=False,
    )
    def test_auto_register_target_code_context_from_discovered_service_metadata(self):
        target = Target.objects.create(
            name="orders-host",
            target_type="linux",
            environment="production",
            metadata_json={},
        )
        results = auto_register_target_code_context(
            target,
            discovered_services=[
                {
                    "service_name": "app-orders",
                    "metadata_json": {
                        "repo_path": self.temp_dir,
                        "repo_name": "orders-repo",
                        "application_name": "shop",
                        "team_name": "orders-team",
                        "version": "2026.05.04",
                    },
                }
            ],
        )
        self.assertEqual(len(results), 1)
        repository = RepositoryIndex.objects.get(name="orders-repo")
        owner = find_service_owner(service_name="app-orders", application_name="shop")
        self.assertEqual(owner["repository"], repository.name)

    def test_builtin_customer_portal_repository_bootstrap_registers_demo_repo(self):
        repositories = ensure_builtin_repository_indexes()
        self.assertTrue(any(repo.name == "customer-portal-demo" for repo in repositories))
        repository = RepositoryIndex.objects.get(name="customer-portal-demo")
        self.assertTrue(repository.local_path.endswith("/demo"))
        owner = find_service_owner(service_name="app-orders", application_name="customer-portal")
        self.assertTrue(owner["ok"])
        self.assertEqual(owner["repository"], "customer-portal-demo")


class FleetInstallScriptTests(SimpleTestCase):
    def test_fleet_install_prereqs_require_agent_secret_token_for_linux(self):
        with patch("genai.views.AGENT_SECRET_TOKEN", ""), patch.dict(os.environ, {"AGENT_SECRET_TOKEN": ""}, clear=False):
            prereqs = _fleet_install_prereqs("linux")
            self.assertFalse(prereqs["control_plane_ready"])
            self.assertTrue(prereqs["missing_requirements"])

    def test_linux_install_script_includes_optional_docker_discovery(self):
        request = RequestFactory().get("/genai/fleet/install/linux/")
        response = fleet_linux_install_script_view(request)
        script = response.content.decode("utf-8")

        self.assertIn('shutil.which("docker")', script)
        self.assertIn('docker socket not found', script)
        self.assertIn('docker_container_count=', script)
        self.assertIn('docker inspect', script)
        self.assertIn('["docker", "restart"]', script)
        self.assertIn('systemctl_binary = shutil.which("systemctl")', script)
        self.assertIn('"list-units", "--type=service", "--state=running"', script)
        self.assertIn('ss_binary = shutil.which("ss")', script)
        self.assertIn('"-tulpnH"', script)
        self.assertIn('container_runtime="docker"', script)
        self.assertIn('AGENT_AUTH_TOKEN=', script)
        self.assertIn('aiops-command-agent.service', script)
        self.assertIn('/opt/aiops-agent/agent_server.py', script)

    def test_kubernetes_install_prereqs_do_not_require_agent_secret(self):
        prereqs = _fleet_install_prereqs("kubernetes")
        self.assertTrue(prereqs["control_plane_ready"])

    def test_kubernetes_manifest_contains_cluster_agent_resources(self):
        from genai.models import EnrollmentToken, TelemetryProfile
        profile = TelemetryProfile(slug="kubernetes-observability", name="Kubernetes", default_for_target="kubernetes")
        token = EnrollmentToken(token="k8s_demo_token", target_type="kubernetes", target_name="prod-cluster")
        with patch("genai.views.EnrollmentToken.objects") as token_objects:
            token.profile = profile
            token.revoked = False
            token_objects.select_related.return_value.filter.return_value.first.return_value = token
            with patch.object(EnrollmentToken, "is_valid", new_callable=PropertyMock, return_value=True):
                request = RequestFactory().get("/genai/fleet/install/kubernetes/?token=k8s_demo_token")
                response = fleet_kubernetes_install_manifest_view(request)
        manifest = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("opsmitra-cluster-agent", manifest)
        self.assertIn("ClusterRole", manifest)
        self.assertIn("CONTROL_PLANE_URL", manifest)
        self.assertIn("ENROLL_TOKEN", manifest)


class FleetSerializationTests(TestCase):
    def test_serialize_target_surfaces_docker_runtime_summary_and_workloads(self):
        target = Target.objects.create(
            name="orders-host",
            target_type="linux",
            environment="production",
            hostname="orders-host-1",
            status="connected",
            collector_status="healthy",
            metadata_json={
                "container_runtime": "docker",
                "docker_available": True,
                "docker_container_count": 2,
            },
        )
        DiscoveredService.objects.create(
            target=target,
            service_name="node_exporter",
            process_name="node_exporter",
            port=9100,
            status="observed",
            metadata_json={},
        )
        DiscoveredService.objects.create(
            target=target,
            service_name="app-orders",
            process_name="docker",
            port=8080,
            status="running",
            metadata_json={
                "runtime": "docker",
                "container_name": "aiops-app-orders",
                "image": "customer/orders:2026.05.05",
            },
        )

        payload = _serialize_target(target)

        self.assertEqual(payload["discovered_service_count"], 2)
        self.assertEqual(payload["runtime_summary"]["container_runtime"], "docker")
        self.assertTrue(payload["runtime_summary"]["docker_available"])
        self.assertEqual(payload["runtime_summary"]["docker_container_count"], 2)
        self.assertEqual(payload["runtime_summary"]["host_service_count"], 1)
        self.assertEqual(len(payload["workload_preview"]), 1)
        self.assertEqual(payload["workload_preview"][0]["service_name"], "app-orders")


class TrackThreeFixTests(SimpleTestCase):
    def test_resolve_embedding_endpoint_derives_from_chat_completion_url(self):
        with patch.dict(
            os.environ,
            {"VLLM_API_URL": "http://10.0.0.8:8001/v1/chat/completions", "VLLM_EMBEDDING_URL": ""},
            clear=False,
        ):
            self.assertEqual(_resolve_embedding_endpoint(), "http://10.0.0.8:8001/v1/embeddings")

    def test_generate_embedding_disables_endpoint_after_404(self):
        class FakeResponse:
            status_code = 404

            def raise_for_status(self):
                import requests
                error = requests.HTTPError("404 not found")
                error.response = self
                raise error

        with patch.dict(
            os.environ,
            {"VLLM_EMBEDDING_URL": "http://10.0.0.8:8001/v1/embeddings"},
            clear=False,
        ), patch("requests.post", return_value=FakeResponse()) as mocked_post:
            reset_embedding_endpoint_state()
            self.assertIsNone(_generate_embedding("orders endpoint"))
            self.assertIsNone(_generate_embedding("orders endpoint again"))
        self.assertEqual(mocked_post.call_count, 1)
        reset_embedding_endpoint_state()

    def test_weaviate_uuid_mapping_is_deterministic(self):
        backend = WeaviateBackend(url="http://weaviate:8080")
        first = backend._uuid_for_object("code_embeddings", "route:repo:123")
        second = backend._uuid_for_object("code_embeddings", "route:repo:123")
        third = backend._uuid_for_object("code_embeddings", "route:repo:456")
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_verify_archive_manifest_local_fs_uses_object_url_path(self):
        temp_dir = tempfile.mkdtemp(prefix="aiops-archive-")
        try:
            archive_file = Path(temp_dir) / "bundle.json"
            payload = b'{"bundle":"ok"}'
            archive_file.write_bytes(payload)

            class DummyManifest:
                archive_backend = "local_fs"
                object_url = str(archive_file)
                object_key = "evidence-bundles/2026-05-06/bundle.json"
                checksum_sha256 = __import__("hashlib").sha256(payload).hexdigest()
                manifest_json = {}
                status = "uploaded"
                verified_at = None
                manifest_id = "manifest-1"

                def save(self, **_kwargs):
                    return None

            manifest = DummyManifest()
            self.assertTrue(verify_archive_manifest(manifest))
            self.assertEqual(manifest.status, "verified")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class InvestigationDurabilityTests(TestCase):
    def test_orchestrator_persists_evidence_bundle_snapshots_and_transcript(self):
        retention = DataRetentionPolicy.objects.create(
            slug="evidence-memory-default",
            name="Evidence Memory Default",
            data_category="evidence_memory",
            primary_store="postgres",
            archive_store="object_storage",
            retention_days=30,
            archive_after_days=14,
            purge_after_days=120,
            is_default=True,
        )
        run = InvestigationRun.objects.create(
            question="why are 503s happening on orders?",
            application="customer-portal",
            service="app-orders",
            route="investigation",
            status="scoping",
            current_stage="scoping",
        )
        orchestrator = InvestigationMCPOrchestrator(
            question=run.question,
            logger=logging.getLogger("test"),
            incident_model=None,
            find_investigation_incident=lambda *_args, **_kwargs: None,
            build_application_overview=lambda **_kwargs: {},
            incident_timeline_payload=lambda *_args, **_kwargs: {},
            get_dependency_context=lambda *_args, **_kwargs: {},
            application_graph_payload=lambda *_args, **_kwargs: {},
            fetch_elasticsearch_logs=lambda *_args, **_kwargs: {},
            fetch_jaeger_traces=lambda *_args, **_kwargs: {},
            fetch_metrics_query=lambda *_args, **_kwargs: {},
        )
        orchestrator.investigation_run = run

        orchestrator.update_run_state(
            status="collecting_evidence",
            current_stage="collecting_evidence",
            target_host="orders-prod-01",
            planner_json={"next_step": "logs.search", "iteration_plan": {"should_continue": True}},
            workflow_json=[{"stage": "collecting_evidence", "status": "running"}],
            evidence_bundle_json={"evidence_assessment": {"summary": "Logs and metrics suggest backend dependency failure."}},
            missing_evidence_json=["confirm downstream dependency state"],
            contradicting_evidence_json=["ingress metrics remained healthy"],
            confidence_score=0.64,
        )
        run.refresh_from_db()
        bundle = EvidenceBundle.objects.get(investigation_run=run)

        self.assertEqual(bundle.retention_policy, retention)
        self.assertEqual(bundle.primary_store, "postgres")
        self.assertEqual(bundle.archive_store, "object_storage")
        self.assertGreaterEqual(EvidenceSnapshot.objects.filter(investigation_run=run).count(), 1)
        self.assertGreaterEqual(InvestigationTranscript.objects.filter(investigation_run=run).count(), 1)

        latest_snapshot = EvidenceSnapshot.objects.filter(investigation_run=run).order_by("-created_at").first()
        self.assertEqual(latest_snapshot.stage, "collecting_evidence")
        self.assertEqual(latest_snapshot.confidence_score, 0.64)
        self.assertEqual(latest_snapshot.missing_evidence_json, ["confirm downstream dependency state"])
        self.assertEqual(latest_snapshot.contradicting_evidence_json, ["ingress metrics remained healthy"])

    def test_command_output_merges_back_into_latest_investigation_run(self):
        incident = Incident.objects.create(
            application="customer-portal",
            title="Inventory 503s",
            status="open",
            severity="critical",
            primary_service="app-inventory",
            target_host="app-inventory",
            summary="Inventory writes are failing.",
        )
        run = InvestigationRun.objects.create(
            incident=incident,
            question="Investigate inventory incident",
            application="customer-portal",
            service="app-inventory",
            target_host="app-inventory",
            route="investigation",
            status="resolved",
            current_stage="resolved",
            planner_json={
                "iteration_plan": {
                    "candidate_steps": [
                        {"tool_name": "logs.search", "reason": "Relevant log evidence is missing or empty for the current scope."},
                        {"tool_name": "topology.get_dependency_context", "reason": "Dependency context should be re-checked."},
                    ],
                    "iterations": [
                        {"iteration": 1, "selected_tool": "logs.search", "status": "planned"},
                        {"iteration": 2, "selected_tool": "topology.get_dependency_context", "status": "planned"},
                    ],
                }
            },
            workflow_json=[
                {"stage": "collecting_evidence", "details": {"logs_present": False, "metrics_present": True, "traces_present": True}},
                {"stage": "assessing_evidence", "details": {"hard_evidence": [], "missing_evidence": ["No logs found"], "contradicting_evidence": []}},
                {"stage": "planning_next_step", "details": {"selected_next_tool": "logs.search", "iteration_plan": {"candidate_steps": [{"tool_name": "logs.search"}]}}},
            ],
            evidence_bundle_json={
                "logs": {"ok": False, "hit_count": 0},
                "evidence_assessment": {
                    "hard_evidence": [],
                    "missing_evidence": ["No logs found"],
                    "contradicting_evidence": [],
                    "confidence_assessment": {
                        "supporting_evidence_count": 0,
                        "hard_evidence_count": 0,
                        "missing_evidence_count": 1,
                        "contradicting_evidence_count": 0,
                        "summary": "",
                    },
                    "contradiction_assessment": {
                        "severity": "none",
                        "count": 0,
                        "blocks_dependency_claim": False,
                        "summary": "",
                    },
                    "evidence_gap_assessment": {
                        "status": "low",
                        "count": 1,
                        "summary": "",
                    },
                },
            },
            missing_evidence_json=["No logs found"],
            contradicting_evidence_json=[],
        )
        bundle = EvidenceBundle.objects.create(
            investigation_run=run,
            incident=incident,
            data_category="evidence_memory",
            primary_store="postgres",
            archive_store="object_storage",
        )

        _merge_command_output_into_investigation_run(
            incident=incident,
            target_host="app-inventory",
            service_name="app-inventory",
            command_output='Traceback (most recent call last):\nRuntimeError: Insufficient inventory for SKU-100: available=0, requested=1\nstatus=503',
            analysis_sections={"evidence": ["RuntimeError: Insufficient inventory for SKU-100", "status=503"]},
            execution_type="diagnostic",
        )

        run.refresh_from_db()
        bundle.refresh_from_db()
        self.assertEqual(run.current_stage, "verifying")
        self.assertTrue(run.evidence_bundle_json["logs"]["ok"])
        self.assertGreaterEqual(run.evidence_bundle_json["logs"]["hit_count"], 1)
        self.assertTrue(run.workflow_json[0]["details"]["logs_present"])
        self.assertEqual(run.workflow_json[2]["details"]["selected_next_tool"], "topology.get_dependency_context")
        self.assertFalse(any(step.get("tool_name") == "logs.search" for step in run.planner_json["iteration_plan"]["candidate_steps"]))
        self.assertFalse(any(step.get("selected_tool") == "logs.search" for step in run.planner_json["iteration_plan"]["iterations"]))
        self.assertIn("RuntimeError: Insufficient inventory for SKU-100", run.evidence_bundle_json["evidence_assessment"]["hard_evidence"])
        latest_snapshot = EvidenceSnapshot.objects.filter(investigation_run=run).order_by("-created_at").first()
        self.assertEqual(latest_snapshot.stage, "verifying")
        self.assertEqual(bundle.evidence_summary_json["post_command_log_hit_count"], run.evidence_bundle_json["logs"]["post_command_hit_count"])

    def test_investigation_detail_view_surfaces_bundle_snapshot_and_transcript_refs(self):
        retention = DataRetentionPolicy.objects.create(
            slug="evidence-memory-default",
            name="Evidence Memory Default",
            data_category="evidence_memory",
            primary_store="postgres",
            archive_store="object_storage",
            retention_days=30,
            archive_after_days=14,
            purge_after_days=120,
            is_default=True,
        )
        run = InvestigationRun.objects.create(
            question="orders api 503s",
            application="customer-portal",
            service="app-orders",
            route="investigation",
            status="resolved",
            current_stage="resolved",
            confidence_score=0.82,
        )
        bundle = EvidenceBundle.objects.create(
            investigation_run=run,
            retention_policy=retention,
            data_category="evidence_memory",
            primary_store="postgres",
            archive_store="object_storage",
            evidence_summary_json={"summary": "backend issue"},
        )
        EvidenceSnapshot.objects.create(
            evidence_bundle=bundle,
            investigation_run=run,
            stage="resolved",
            iteration_index=1,
            title="Final evidence snapshot",
            summary="Dependency failure confirmed.",
            confidence_score=0.82,
        )
        InvestigationTranscript.objects.create(
            evidence_bundle=bundle,
            investigation_run=run,
            sequence_index=1,
            entry_type="summary",
            stage="resolved",
            title="Investigation completed",
            content_json={"status": "resolved"},
        )

        request = RequestFactory().get(f"/genai/investigations/{run.run_id}/")
        from genai.views import investigation_detail_view

        response = investigation_detail_view(request, str(run.run_id))
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["evidence_bundle_ref"]["bundle_id"], str(bundle.bundle_id))
        self.assertEqual(payload["evidence_bundle_ref"]["retention_policy"], "evidence-memory-default")
        self.assertEqual(payload["evidence_bundle_ref"]["snapshot_count"], 1)
        self.assertEqual(payload["evidence_bundle_ref"]["transcript_entry_count"], 1)
        self.assertEqual(len(payload["evidence_snapshots"]), 1)
        self.assertEqual(len(payload["investigation_transcript"]), 1)


class RetentionPolicyViewTests(TestCase):
    def test_lifecycle_retention_policies_view_groups_by_deployment_mode(self):
        DataRetentionPolicy.objects.create(
            slug="logs-default",
            name="Logs Default",
            data_category="hot_telemetry",
            subject_type="logs",
            deployment_mode="any",
            primary_store="opensearch",
            archive_store="object_storage",
            retention_days=14,
            archive_after_days=7,
            purge_after_days=30,
            hold_supported=True,
            object_storage_required=True,
            is_default=True,
            storage_defaults_json={"opensearch_stream_families": ["logs-linux-default"]},
        )
        DataRetentionPolicy.objects.create(
            slug="metrics-kubernetes-default",
            name="Metrics Kubernetes Default",
            data_category="hot_telemetry",
            subject_type="metrics",
            deployment_mode="kubernetes_standard",
            primary_store="victoriametrics",
            archive_store="object_storage",
            retention_days=21,
            archive_after_days=14,
            purge_after_days=45,
            is_default=True,
        )

        request = RequestFactory().get("/genai/lifecycle/retention-policies/?deployment_mode=kubernetes_standard")
        request.user = type("User", (), {"is_authenticated": True})()

        from genai.views import lifecycle_retention_policies_view

        response = lifecycle_retention_policies_view(request)
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["count"], 2)
        self.assertIn("kubernetes_standard", payload["grouped_by_deployment_mode"])
        self.assertIn("any", payload["grouped_by_deployment_mode"])
        self.assertEqual(payload["storage_direction"]["tempo"], "traces")
