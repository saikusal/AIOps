import json
import re
from typing import Callable, Optional, Tuple

import requests


_SERVICE_ALIASES = {
    "orders": "app-orders",
    "order": "app-orders",
    "inventory": "app-inventory",
    "billing": "app-billing",
    "database": "db",
    "postgres": "db",
    "postgresql": "db",
}

_KNOWN_SERVICES = {"frontend", "gateway", "db", "app-orders", "app-inventory", "app-billing"}


def _strip_promql_response(value: str) -> str:
    query = (value or "").strip()
    if query.startswith("```"):
        query = re.sub(r"^```(?:promql|prometheus)?\s*", "", query, flags=re.IGNORECASE)
        query = re.sub(r"\s*```$", "", query)
    return query.strip().strip("`").strip()


def _extract_service_name(prompt: str) -> str:
    text = (prompt or "").strip().lower()
    quoted = re.search(r"['\"]([^'\"]+)['\"]\s+service", text)
    if quoted:
        candidate = quoted.group(1).strip()
        return _SERVICE_ALIASES.get(candidate, candidate)
    for service in sorted(_KNOWN_SERVICES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(service)}\b", text):
            return service
    for alias, service in _SERVICE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return service
    return ""


def _deterministic_promql(prompt: str) -> str:
    text = (prompt or "").lower()
    service = _extract_service_name(prompt)
    if not service:
        return ""

    if "error rate" in text or "5xx" in text or "error" in text:
        if service in {"app-orders", "app-inventory", "app-billing"}:
            return f'sum(rate(demo_http_requests_total{{service="{service}",status=~"5.."}}[5m])) or vector(0)'
        if service == "db":
            # The demo database is exported through postgres_exporter, not HTTP
            # request metrics. Return a valid zero-valued rate when no HTTP
            # error metric exists, rather than letting the LLM invent SNMP
            # interface error PromQL for `ifName="db"`.
            return 'sum(rate(demo_http_requests_total{service="db",status=~"5.."}[5m])) or vector(0)'
        if service in {"frontend", "gateway"}:
            return f'sum(rate(nginx_http_requests_total{{service="{service}",status=~"5.."}}[5m])) or vector(0)'

    if "latency" in text or "p95" in text or "response time" in text:
        if service in {"app-orders", "app-inventory", "app-billing"}:
            return f'histogram_quantile(0.95, sum(rate(demo_http_request_duration_seconds_bucket{{service="{service}"}}[5m])) by (le))'

    if "up" in text or "available" in text or "status" in text:
        if service == "db":
            return 'up{job="postgres-exporter"}'
        if service in {"app-orders", "app-inventory", "app-billing"}:
            return f'up{{job="demo-apps",instance="{service}:8000"}}'
        if service in {"frontend", "gateway"}:
            return f'nginx_up{{service="{service}"}}'

    return ""


def _is_obviously_invalid_promql(query: str) -> bool:
    # Prometheus uses RE2 regexes; lookaround/backrefs are invalid and are a
    # common LLM hallucination for label matchers.
    return bool(re.search(r"\(\?[=!<]", query or "") or re.search(r"\\[1-9]", query or ""))


def handle_prometheus_query(
    prompt: str,
    llm_query: Callable[[str], Tuple[bool, int, str]],
    prometheus_url: Optional[str],
    logger,
) -> Tuple[Optional[dict], dict, str, str]:
    """
    Handles an observability query by dynamically generating and executing a PromQL query.
    Returns (result_payload, visualization_payload, error_text, generated_query).
    """
    if not prometheus_url:
        return None, {}, "Prometheus URL not configured", ""

    text_to_promql_prompt = (
        "You are a Prometheus expert for an IT infrastructure environment. Your task is to convert a user's question into a valid PromQL query. "
        "Determine if the user is asking about a **Network Device**, a **Server**, or a specific **Process**. Then, use the appropriate metrics.\n"
        "Return ONLY the PromQL query string. Do not add any explanation or markdown.\n\n"
        "--- CONTEXT 1: Network Device Metrics (SNMP Exporter) ---\n"
        "Use these for questions about switches, routers, and bandwidth.\n"
        "Metrics: ifHCInOctets, ifHCOutOctets, ifInErrors, ifOutErrors, ifOperStatus.\n"
        "Labels: 'instance' (device IP), 'ifName' (interface name).\n"
        "Example Q: 'What is the bandwidth for 172.24.95.10?' -> A: sum by (instance) (rate(ifHCInOctets{instance=\"172.24.95.10\"}[5m]))\n\n"
        "--- CONTEXT 2: Server Metrics (Node Exporter) ---\n"
        "Use these for general questions about servers, CPU, memory, and disk space.\n"
        "Metrics: node_cpu_seconds_total, node_memory_MemTotal_bytes, node_memory_MemAvailable_bytes, node_filesystem_size_bytes, node_filesystem_avail_bytes.\n"
        "Labels: 'instance' (server IP/hostname), 'device' (for disks), 'mountpoint'.\n"
        "Example Q: 'CPU usage for server 10.0.1.5?' -> A: 100 - (avg by (instance) (rate(node_cpu_seconds_total{instance=\"10.0.1.5\",mode='idle'}[5m])) * 100)\n\n"
        "--- CONTEXT 3: Per-Process Metrics (Process Exporter) ---\n"
        "Use these for specific questions about running processes like 'java' or 'nginx'.\n"
        "Metrics:\n"
        "- namedprocess_namegroup_cpu_seconds_total: CPU time for a process group.\n"
        "- namedprocess_namegroup_memory_bytes: Memory usage (resident, virtual, etc.). Use `memtype='resident'` for actual physical memory.\n"
        "- namedprocess_namegroup_num_threads: Number of threads.\n"
        "Labels: 'instance' (server IP), 'groupname' (the name of the process, e.g., 'java', 'nginx').\n"
        "Example Q: 'Which process is using the most CPU on 10.1.10.4?' -> A: topk(5, sum by (groupname) (rate(namedprocess_namegroup_cpu_seconds_total{instance=\"10.1.10.4\"}[5m])))\n"
        "Example Q: 'How much memory is the java process using on server 10.1.10.4?' -> A: namedprocess_namegroup_memory_bytes{groupname='java', instance='10.1.10.4', memtype='resident'}\n\n"
        f"--- TASK ---\n"
        f"Generate the PromQL query for this question: '{prompt}'"
    )

    deterministic_query = _deterministic_promql(prompt)
    if deterministic_query:
        promql_query = deterministic_query
        logger.info("Using deterministic PromQL query: %s", promql_query)
    else:
        ok, status, generated_query = llm_query(text_to_promql_prompt)
        if not ok or not generated_query.strip():
            logger.error("Failed to generate PromQL query. Status: %s, Body: %s", status, generated_query)
            return None, {}, "Sorry, I couldn't understand how to query that. Please try rephrasing your question.", ""
        promql_query = _strip_promql_response(generated_query)
        if _is_obviously_invalid_promql(promql_query):
            logger.warning("Rejected invalid generated PromQL query: %s", promql_query)
            return None, {}, "Sorry, I generated an invalid Prometheus query for that request. Please try a service metric question such as error rate, latency, or availability.", promql_query
    logger.info("Dynamically generated PromQL query: %s", promql_query)

    try:
        response = requests.get(f"{prometheus_url}/api/v1/query", params={"query": promql_query}, timeout=10)
        response.raise_for_status()
        prometheus_data = response.json()
    except requests.exceptions.RequestException as exc:
        logger.exception("Failed to query Prometheus with generated query: %s", exc)
        return None, {}, f"Error executing query against Prometheus: {exc}", promql_query

    if not prometheus_data.get("data", {}).get("result"):
        return None, {}, "Sorry, your query returned no data. Please check the device or interface name and try again.", promql_query

    results_to_text_prompt = (
        "You are an IT infrastructure observability expert. Your job is to interpret raw Prometheus data, provide a clear answer, and suggest relevant follow-up actions or diagnostic commands.\n"
        "1.  **Answer:** Directly answer the user's question based on the data.\n"
        "    - For **Bandwidth**, convert bytes/sec to a readable format like Mbps or Gbps.\n"
        "    - For **CPU Usage**, state the percentage clearly.\n"
        "    - For **Memory/Disk**, convert bytes to a readable format like MB, GB, or TB.\n"
        "    - For **Status**, explain the value (1=up, 2=down).\n"
        "    - For **Errors/Discards**, state the count. If it's high, mention that it might indicate a problem.\n"
        "2.  **Suggestions:** Provide a list of 2-3 insightful follow-up questions.\n"
        "3.  **Suggested Command:** If relevant, suggest a single, non-destructive Linux command that could help diagnose the issue further. For example, if CPU is high, suggest `top -b -n 1`. If disk is low, suggest `df -h`. If network errors are high, suggest `ip -s link show [interface]`.\n\n"
        "Format the output as a JSON object with three keys: 'answer' (string), 'follow_up_questions' (list of strings), and 'suggested_command' (string or null).\n\n"
        f"USER'S QUESTION: {prompt}\n"
        f"PROMETHEUS DATA: {json.dumps(prometheus_data.get('data', {}), indent=2)}\n\n"
        "JSON Response:"
    )

    ok, _status, body = llm_query(results_to_text_prompt)
    if not ok:
        return None, {}, "Error: AI service failed to interpret the data.", promql_query

    target_host = None
    try:
        result_list = prometheus_data.get("data", {}).get("result", [])
        if result_list:
            metric_info = result_list[0].get("metric", {})
            if "instance" in metric_info:
                target_host = metric_info["instance"]
                if ":" in target_host:
                    target_host = target_host.split(":")[0]
                logger.info("Extracted target_host='%s' from Prometheus data.", target_host)
    except Exception as exc:
        logger.warning("Could not extract target_host from Prometheus data: %s", exc)

    try:
        start_index = body.find("{")
        end_index = body.rfind("}")
        if start_index != -1 and end_index != -1:
            response_data = json.loads(body[start_index:end_index + 1])
        else:
            response_data = {"answer": body, "follow_up_questions": [], "suggested_command": None}
        answer = response_data.get("answer", body)
        follow_ups = response_data.get("follow_up_questions", [])
        suggested_command = response_data.get("suggested_command")
    except json.JSONDecodeError:
        answer = body
        follow_ups = []
        suggested_command = None

    final_result = {
        "answer": answer,
        "follow_up_questions": follow_ups,
        "suggested_command": suggested_command,
        "target_host": target_host,
    }
    return final_result, {}, "", promql_query
