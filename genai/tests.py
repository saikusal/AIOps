from unittest.mock import patch

from django.test import SimpleTestCase

from genai.mcp_client import MCPClient
from genai.mcp_registry import MCPRegistry
from genai.mcp_services import (
    applications_get_component_snapshot,
    applications_get_overview,
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
from genai.multi_step_workflow import build_execution_workflow, build_investigation_workflow, finalize_investigation_workflow
from genai.policy_engine import (
    classify_action,
    evaluate_execution_policy,
    record_execution_attempt,
)
from genai.replay_evaluation import build_replay_scores
from genai.typed_actions import command_from_typed_action, infer_typed_action


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

        self.cache_patcher = patch("genai.policy_engine.cache", _FakeCache(self._cache_store))
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
        self.assertEqual([stage["stage"] for stage in workflow], ["planner", "evidence_checker", "target_selector", "remediation_selector"])
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
            verification={"status": "resolved", "reason": "Error rate dropped"},
            analysis_sections={"remediation_typed_action": {"action": "diagnostic"}},
            execution_status="completed",
            dry_run=False,
        )
        stage_names = [stage["stage"] for stage in workflow]
        self.assertIn("executor", stage_names)
        self.assertIn("verifier", stage_names)
        self.assertEqual(workflow[-1]["stage"], "post_check_validator")
