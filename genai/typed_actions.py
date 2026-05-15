import json
import re
from typing import Any, Dict, List, Optional


def build_validation_plan(action_type: str, service: str = "") -> List[str]:
    normalized_service = (service or "").strip()
    if action_type == "restart_service":
        return [
            f"Check service health for {normalized_service or 'the restarted service'}.",
            "Review metrics for latency and error rate regression.",
            "Confirm alert state clears after the restart.",
        ]
    if action_type == "database_change":
        return [
            "Verify the targeted records now satisfy the expected constraint.",
            "Check application error rate and database write failures after the change.",
            "Confirm no new alerts were triggered by the remediation.",
        ]
    if action_type == "diagnostic":
        return [
            "Review the command output for concrete error signatures.",
            "Compare findings with current metrics, logs, and traces before remediating.",
        ]
    if action_type == "rollback":
        return [
            f"Confirm {normalized_service or 'the service'} is healthy after the rollback.",
            "Verify the original failure condition no longer reproduces.",
            "Check that no new alerts were introduced by the rollback.",
            "Review metrics for any latency or error rate regressions.",
        ]
    return ["Run post-action verification before treating the incident as resolved."]


def infer_typed_action(
    *,
    command: str,
    target_host: str,
    why: str = "",
    requires_approval: bool = False,
    service: str = "",
) -> Dict[str, Any]:
    normalized_command = (command or "").strip()
    normalized_service = (service or "").strip()
    action: Dict[str, Any] = {
        "action": "command",
        "target": target_host or "",
        "target_host": target_host or "",
        "service": normalized_service,
        "reason": why or "",
        "requires_approval": bool(requires_approval),
        "command": normalized_command,
        "validation_plan": build_validation_plan("unknown", normalized_service),
        "metadata": {},
    }

    docker_match = re.match(r"^docker restart\s+([A-Za-z0-9_.-]+)$", normalized_command)
    if docker_match:
        container_name = docker_match.group(1)
        action.update(
            {
                "action": "restart_service",
                "target": normalized_service or container_name,
                "reason": why or "Service restart recommended from diagnostic evidence.",
                "validation_plan": build_validation_plan("restart_service", normalized_service or container_name),
                "metadata": {"executor": "docker", "container_name": container_name},
            }
        )
        return action

    kubectl_restart_match = re.match(
        r"^kubectl rollout restart (deployment|statefulset|daemonset)/([A-Za-z0-9_.-]+)(?: -n ([A-Za-z0-9_.-]+))?$",
        normalized_command,
    )
    if kubectl_restart_match:
        workload_kind = kubectl_restart_match.group(1)
        workload_name = kubectl_restart_match.group(2)
        namespace = kubectl_restart_match.group(3) or "default"
        action.update(
            {
                "action": "restart_service",
                "target": normalized_service or workload_name,
                "reason": why or "Kubernetes workload restart recommended from runtime evidence.",
                "validation_plan": build_validation_plan("restart_service", normalized_service or workload_name),
                "metadata": {
                    "executor": "kubernetes",
                    "resource_kind": workload_kind,
                    "resource_name": workload_name,
                    "namespace": namespace,
                },
            }
        )
        return action

    kubectl_diagnostic_prefixes = (
        "kubectl get ",
        "kubectl describe ",
        "kubectl logs ",
    )
    if normalized_command.lower().startswith(kubectl_diagnostic_prefixes):
        action.update(
            {
                "action": "diagnostic",
                "target": normalized_service or target_host or "",
                "validation_plan": build_validation_plan("diagnostic", normalized_service),
                "metadata": {"executor": "kubernetes"},
            }
        )
        return action

    if normalized_command.lower().startswith("psql "):
        sql_match = re.search(r'-c\s+"(.*)"', normalized_command)
        sql = sql_match.group(1) if sql_match else ""
        action.update(
            {
                "action": "database_change",
                "target": normalized_service or "db",
                "target_host": target_host or "db",
                "reason": why or "Targeted database change recommended from live evidence.",
                "validation_plan": build_validation_plan("database_change", normalized_service or "db"),
                "metadata": {"executor": "psql", "sql": sql},
            }
        )
        return action

    diagnostic_prefixes = (
        "tail ",
        "grep ",
        "journalctl ",
        "ss ",
        "curl ",
        "ps ",
        "cat ",
        "docker inspect ",
        "docker ps ",
        "docker logs ",
    )
    if normalized_command.lower().startswith(diagnostic_prefixes):
        action.update(
            {
                "action": "diagnostic",
                "target": normalized_service or target_host or "",
                "validation_plan": build_validation_plan("diagnostic", normalized_service),
            }
        )
        return action

    return action


def infer_rollback_action(
    *,
    original_command: str,
    original_action_type: str,
    target_host: str,
    service: str = "",
    why: str = "",
) -> Dict[str, Any]:
    """Build a typed rollback action that reverses a previously executed action."""
    normalized_service = (service or "").strip()
    rollback_command = _derive_rollback_command(original_command, original_action_type, target_host, normalized_service)
    return {
        "action": "rollback",
        "target": normalized_service or target_host or "",
        "target_host": target_host or "",
        "service": normalized_service,
        "reason": why or f"Rolling back: {original_command[:80]}",
        "requires_approval": True,
        "command": rollback_command,
        "validation_plan": build_validation_plan("rollback", normalized_service),
        "metadata": {
            "original_command": original_command,
            "original_action_type": original_action_type,
            "rollback_derived": True,
        },
    }


def _derive_rollback_command(
    original_command: str,
    original_action_type: str,
    target_host: str,
    service: str,
) -> str:
    """Derive a best-effort rollback command from the original."""
    normalized = (original_command or "").strip()

    if original_action_type == "restart_service":
        # A restart is its own rollback — restarting again returns to clean state
        return normalized

    docker_match = re.match(r"^docker restart\s+([A-Za-z0-9_.-]+)$", normalized)
    if docker_match:
        return normalized

    kubectl_match = re.match(
        r"^kubectl rollout restart (deployment|statefulset|daemonset)/([A-Za-z0-9_.-]+)(?: -n ([A-Za-z0-9_.-]+))?$",
        normalized,
    )
    if kubectl_match:
        kind = kubectl_match.group(1)
        name = kubectl_match.group(2)
        ns = kubectl_match.group(3) or "default"
        return f"kubectl rollout undo {kind}/{name} -n {ns}"

    if original_action_type == "database_change":
        return f"# Manual rollback required — review the SQL change and apply inverse: {normalized[:120]}"

    return f"# Rollback command must be supplied manually for: {normalized[:120]}"


def command_from_typed_action(action_payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(action_payload, dict):
        return ""
    action_type = str(action_payload.get("action") or "").strip()
    if not action_type:
        return str(action_payload.get("command") or "").strip()

    if action_type == "restart_service":
        metadata = action_payload.get("metadata") or {}
        executor = str(metadata.get("executor") or "").strip()
        if executor == "kubernetes":
            resource_kind = str(metadata.get("resource_kind") or "deployment").strip()
            resource_name = str(metadata.get("resource_name") or "").strip()
            namespace = str(metadata.get("namespace") or "default").strip()
            if resource_name:
                return f"kubectl rollout restart {resource_kind}/{resource_name} -n {namespace}".strip()
        container_name = str(metadata.get("container_name") or "").strip()
        return f"docker restart {container_name}".strip() if container_name else ""

    if action_type == "database_change":
        return str(action_payload.get("command") or "").strip()

    if action_type == "rollback":
        return str(action_payload.get("command") or "").strip()

    return str(action_payload.get("command") or "").strip()


def action_summary(action_payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(action_payload, dict):
        return ""
    action_type = str(action_payload.get("action") or "command").replace("_", " ").strip()
    target = str(action_payload.get("target") or action_payload.get("target_host") or "").strip()
    reason = str(action_payload.get("reason") or "").strip()
    summary_bits = [action_type.title()]
    if target:
        summary_bits.append(f"target={target}")
    if reason:
        summary_bits.append(reason)
    return " | ".join(summary_bits)


def serialize_action_signature(action_payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(action_payload, dict):
        return ""
    compact = {
        "action": action_payload.get("action"),
        "target": action_payload.get("target"),
        "target_host": action_payload.get("target_host"),
        "command": action_payload.get("command"),
        "metadata": action_payload.get("metadata") or {},
    }
    return json.dumps(compact, sort_keys=True)
