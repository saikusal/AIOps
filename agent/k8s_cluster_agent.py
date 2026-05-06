#!/usr/bin/env python3
import json
import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


CONTROL_PLANE_URL = os.getenv("CONTROL_PLANE_URL", "").rstrip("/")
ENROLL_TOKEN = os.getenv("ENROLL_TOKEN", "").strip()
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "").strip() or socket.gethostname()
TARGET_ENVIRONMENT = os.getenv("TARGET_ENVIRONMENT", "production").strip() or "production"
VERIFY_SSL = str(os.getenv("VERIFY_SSL", "true")).strip().lower() not in {"false", "0", "no"}
HEARTBEAT_INTERVAL_SECONDS = max(int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60") or 60), 15)
COMMAND_POLL_INTERVAL_SECONDS = max(int(os.getenv("COMMAND_POLL_INTERVAL_SECONDS", "5") or 5), 2)
STATE_FILE = Path(os.getenv("STATE_FILE", "/tmp/opsmitra-k8s-agent-state.json"))

K8S_HOST = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
K8S_PORT = os.getenv("KUBERNETES_SERVICE_PORT", "443")
K8S_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
K8S_CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("opsmitra-k8s-agent")


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def _agent_headers(state: Dict[str, Any]) -> Dict[str, str]:
    token = str(state.get("cluster_agent_auth_token") or "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Cluster-Agent-Token"] = token
    return headers


def _service_account_headers() -> Dict[str, str]:
    token = K8S_TOKEN_PATH.read_text(encoding="utf-8").strip()
    return {"Authorization": f"Bearer {token}"}


def _k8s_api_get(path: str) -> Tuple[Dict[str, Any], Optional[str]]:
    url = f"https://{K8S_HOST}:{K8S_PORT}{path}"
    verify: Any = str(K8S_CA_PATH) if K8S_CA_PATH.exists() else VERIFY_SSL
    try:
        response = requests.get(url, headers=_service_account_headers(), verify=verify, timeout=30)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:
        return {}, str(exc)


def _discover_cluster() -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    queries = {
        "namespaces": "/api/v1/namespaces",
        "nodes": "/api/v1/nodes",
        "services": "/api/v1/services",
        "deployments": "/apis/apps/v1/deployments",
        "statefulsets": "/apis/apps/v1/statefulsets",
        "daemonsets": "/apis/apps/v1/daemonsets",
        "ingresses": "/apis/networking.k8s.io/v1/ingresses",
    }
    raw: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for key, path in queries.items():
        payload, error = _k8s_api_get(path)
        if error:
            errors.append(f"{key}: {error}")
            raw[key] = {"items": []}
        else:
            raw[key] = payload

    discovered_services: List[Dict[str, Any]] = []

    for item in raw.get("services", {}).get("items", []):
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        ports = spec.get("ports") or [{}]
        for port_spec in ports:
            discovered_services.append(
                {
                    "service_name": metadata.get("name", "service"),
                    "process_name": "kubernetes-service",
                    "port": port_spec.get("port"),
                    "status": "observed",
                    "metadata_json": {
                        "runtime": "kubernetes",
                        "resource_kind": "Service",
                        "namespace": metadata.get("namespace", "default"),
                        "cluster_ip": spec.get("clusterIP", ""),
                        "type": spec.get("type", ""),
                        "selector": spec.get("selector") or {},
                    },
                }
            )

    for resource_kind in ("deployments", "statefulsets", "daemonsets"):
        kind = resource_kind[:-1].capitalize() if resource_kind.endswith("s") else resource_kind.capitalize()
        for item in raw.get(resource_kind, {}).get("items", []):
            metadata = item.get("metadata", {})
            template_spec = ((item.get("spec") or {}).get("template") or {}).get("spec") or {}
            images = [container.get("image", "") for container in template_spec.get("containers") or [] if container.get("image")]
            discovered_services.append(
                {
                    "service_name": metadata.get("name", kind.lower()),
                    "process_name": "kubernetes-workload",
                    "port": None,
                    "status": "observed",
                    "metadata_json": {
                        "runtime": "kubernetes",
                        "resource_kind": kind,
                        "namespace": metadata.get("namespace", "default"),
                        "images": images,
                        "replicas": (item.get("spec") or {}).get("replicas"),
                    },
                }
            )

    for item in raw.get("ingresses", {}).get("items", []):
        metadata = item.get("metadata", {})
        discovered_services.append(
            {
                "service_name": metadata.get("name", "ingress"),
                "process_name": "kubernetes-ingress",
                "port": 80,
                "status": "observed",
                "metadata_json": {
                    "runtime": "kubernetes",
                    "resource_kind": "Ingress",
                    "namespace": metadata.get("namespace", "default"),
                },
            }
        )

    metadata_json = {
        "container_runtime": "kubernetes",
        "kubernetes_available": True,
        "namespace_count": len(raw.get("namespaces", {}).get("items", [])),
        "node_count": len(raw.get("nodes", {}).get("items", [])),
        "service_count": len(raw.get("services", {}).get("items", [])),
        "deployment_count": len(raw.get("deployments", {}).get("items", [])),
        "statefulset_count": len(raw.get("statefulsets", {}).get("items", [])),
        "daemonset_count": len(raw.get("daemonsets", {}).get("items", [])),
        "ingress_count": len(raw.get("ingresses", {}).get("items", [])),
        "cluster_name": CLUSTER_NAME,
        "discovery_errors": errors,
    }
    return metadata_json, discovered_services, errors


def _enroll(state: Dict[str, Any]) -> str:
    payload = {
        "token": ENROLL_TOKEN,
        "target_id": state.get("target_id") or "",
        "name": CLUSTER_NAME,
        "hostname": CLUSTER_NAME,
        "environment": TARGET_ENVIRONMENT,
        "os_name": "Kubernetes",
        "collector_status": "healthy",
        "metadata_json": {
            "container_runtime": "kubernetes",
            "cluster_name": CLUSTER_NAME,
        },
        "components": [
            "OpsMitra Cluster Agent",
            "Kubernetes discovery helper",
            "cluster heartbeat",
        ],
    }
    response = requests.post(
        f"{CONTROL_PLANE_URL}/genai/fleet/enroll/",
        json=payload,
        verify=VERIFY_SSL,
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    target = body.get("target") or {}
    target_id = str(target.get("target_id") or "").strip()
    if not target_id:
        raise RuntimeError("Enrollment response did not include target_id")
    state["target_id"] = target_id
    if body.get("cluster_agent_auth_token"):
        state["cluster_agent_auth_token"] = str(body.get("cluster_agent_auth_token"))
    _save_state(state)
    return target_id


def _poll_commands(target_id: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    response = requests.post(
        f"{CONTROL_PLANE_URL}/genai/fleet/targets/{target_id}/agent/poll/",
        headers=_agent_headers(state),
        json={},
        verify=VERIFY_SSL,
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("commands") or []


def _post_command_result(target_id: str, state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    response = requests.post(
        f"{CONTROL_PLANE_URL}/genai/fleet/targets/{target_id}/agent/result/",
        headers=_agent_headers(state),
        json=payload,
        verify=VERIFY_SSL,
        timeout=30,
    )
    response.raise_for_status()


def _is_allowed_kubectl_command(command: str) -> bool:
    normalized = " ".join(str(command or "").strip().split())
    allowed_prefixes = (
        "kubectl get ",
        "kubectl describe ",
        "kubectl logs ",
        "kubectl rollout restart deployment/",
        "kubectl rollout restart statefulset/",
        "kubectl rollout restart daemonset/",
    )
    return any(normalized.startswith(prefix) for prefix in allowed_prefixes)


def _execute_command(command: str) -> Dict[str, Any]:
    normalized = " ".join(str(command or "").strip().split())
    if not normalized:
        return {"success": False, "output": "", "error": "empty command"}
    if not _is_allowed_kubectl_command(normalized):
        return {"success": False, "output": "", "error": "command not allowed by cluster agent policy"}
    try:
        result = subprocess.run(
            normalized.split(),
            capture_output=True,
            text=True,
            timeout=90,
        )
        return {
            "success": result.returncode == 0,
            "output": (result.stdout or result.stderr or "")[:12000],
            "error": "" if result.returncode == 0 else f"command exited with {result.returncode}",
        }
    except Exception as exc:
        return {"success": False, "output": "", "error": str(exc)}


def _heartbeat(target_id: str) -> None:
    metadata_json, discovered_services, errors = _discover_cluster()
    payload = {
        "status": "warning" if errors else "connected",
        "collector_status": "warning" if errors else "healthy",
        "metadata_json": metadata_json,
        "components": [
            {"name": "OpsMitra Cluster Agent", "status": "healthy", "version": "v1"},
            {"name": "Kubernetes discovery helper", "status": "warning" if errors else "healthy"},
        ],
        "discovered_services": discovered_services,
    }
    response = requests.post(
        f"{CONTROL_PLANE_URL}/genai/fleet/targets/{target_id}/heartbeat/",
        json=payload,
        verify=VERIFY_SSL,
        timeout=60,
    )
    response.raise_for_status()


def main() -> int:
    if not CONTROL_PLANE_URL or not ENROLL_TOKEN:
        logger.error("CONTROL_PLANE_URL and ENROLL_TOKEN are required")
        return 1
    state = _load_state()
    last_heartbeat_at = 0.0
    while True:
        try:
            target_id = state.get("target_id") or _enroll(state)
            now = time.time()
            if now - last_heartbeat_at >= HEARTBEAT_INTERVAL_SECONDS:
                _heartbeat(target_id)
                logger.info("Cluster heartbeat sent for %s", target_id)
                last_heartbeat_at = now
            commands = _poll_commands(target_id, state)
            for item in commands:
                command_id = str(item.get("command_id") or "").strip()
                command = str(item.get("command") or "").strip()
                if not command_id:
                    continue
                result = _execute_command(command)
                _post_command_result(
                    target_id,
                    state,
                    {
                        "command_id": command_id,
                        "success": result["success"],
                        "output": result["output"],
                        "error": result["error"],
                        "metadata_json": {"command": command},
                    },
                )
        except Exception as exc:
            logger.exception("Cluster agent loop failed: %s", exc)
            state.pop("target_id", None)
            _save_state(state)
            last_heartbeat_at = 0.0
        time.sleep(COMMAND_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
