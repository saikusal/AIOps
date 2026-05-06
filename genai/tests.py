import os
import logging
import json
import shutil
import subprocess
import tempfile
from unittest.mock import PropertyMock, patch

from django.test import RequestFactory, SimpleTestCase, TestCase

from genai.code_context_extractors import extract_python_artifacts
from genai.code_context_ingestion import auto_register_target_code_context, ensure_builtin_repository_indexes, sync_repository_index
from genai.code_context_services import find_service_owner, read_code_snippet, route_to_handler, search_code_context, span_to_symbol
from genai.tools.investigation import _assess_code_context_quality, _infer_runtime_entities_from_question
from genai.mcp_client import MCPClient
from genai.mcp_registry import MCPRegistry
from genai.mcp_orchestrator import InvestigationMCPOrchestrator
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
from genai.models import (
    CodeChangeRecord,
    DataRetentionPolicy,
    DiscoveredService,
    EvidenceBundle,
    EvidenceSnapshot,
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
from genai.views import (
    _fleet_install_prereqs,
    _mark_target_config_apply_requested,
    _serialize_target,
    _target_generated_config_payload,
    _update_target_configuration_from_payload,
    fleet_kubernetes_install_manifest_view,
    fleet_linux_install_script_view,
)


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
