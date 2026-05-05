import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from genai.code_context_extractors import extract_python_artifacts
from genai.code_context_ingestion import auto_register_target_code_context, ensure_builtin_repository_indexes, sync_repository_index
from genai.code_context_services import find_service_owner, read_code_snippet, route_to_handler, search_code_context, span_to_symbol
from genai.tools.investigation import _infer_runtime_entities_from_question
from genai.mcp_client import MCPClient
from genai.mcp_registry import MCPRegistry
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
from genai.multi_step_workflow import build_execution_workflow, build_investigation_workflow, finalize_investigation_workflow
from genai.policy_engine import (
    classify_action,
    evaluate_execution_policy,
    record_execution_attempt,
)
from genai.replay_evaluation import build_replay_scores
from genai.typed_actions import command_from_typed_action, infer_typed_action
from genai.models import CodeChangeRecord, RepositoryIndex, RouteBinding, ServiceRepositoryBinding, SpanBinding, SymbolRelation, Target


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
