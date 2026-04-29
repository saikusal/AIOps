# Engineer, AI Interview Q&A

This document contains likely interview questions and strong sample answers based on the AIOps, RAG, agentic AI, ITSM integration, and air-gapped platform work already built.

---

## 1) Tell me about the project you built.

**Answer:**

I worked on an air-gapped AIOps platform that combines observability, retrieval-augmented generation, incident intelligence, and controlled agentic workflows. The system ingests alerts, correlates them with telemetry such as logs, metrics, traces, dependency context, historical incidents, and runbooks, then produces grounded operational guidance. We also built controlled remediation flows, approval-aware execution, blast-radius analysis, change-management alignment, and ITSM integrations such as Freshservice. The focus was not just chat, but production-grade AI operations with safety, auditability, and continuous learning.

---

## 2) Walk me through the end-to-end incident flow.

**Answer:**

The flow starts when an alert is triggered from a monitoring source. The alert is ingested and enriched with service metadata, dependency topology, recent metrics, logs, traces, prior similar incidents, and relevant runbooks from the RAG layer. We build a structured evidence object that includes symptoms, likely components, confirming signals, contradicting signals, confidence, and blast radius. That package is sent to the reasoning layer or agent workflow. The platform then produces a diagnosis, investigation steps, and possibly a remediation suggestion. Before anything operational is executed, policy checks, approval gates, environment restrictions, and change-management rules are applied. If approved, the action is executed through a controlled path, then post-action verification checks whether the service actually improved. Finally, the outcome, operator feedback, and remediation result are stored for future learning.

---

## 3) How does your RAG pipeline work?

**Answer:**

We use RAG to ground operational answers in enterprise knowledge rather than relying only on model memory. Runbooks, incident records, support docs, configuration references, and platform notes are ingested, chunked, embedded, and indexed into a searchable knowledge store. When an incident comes in or an operator asks a question, we retrieve the most relevant chunks based on service, alert type, keywords, historical similarity, and semantic search. The retrieved content is merged with live telemetry context before the model answers. That makes the responses more accurate, more explainable, and aligned with actual operational procedures.

---

## 4) What kinds of questions can your RAG system answer?

**Answer:**

It can answer questions such as what this incident means, what similar incidents happened before, which runbook applies, which dependency might be the root cause, what the blast radius is, what changed recently, and which remediation historically worked best. It is useful both during active incidents and for operator self-service.

---

## 5) How do you calculate blast radius?

**Answer:**

Blast radius is derived from dependency mappings, affected upstream and downstream services, service criticality, current health signals, active alerts, and sometimes consumer impact indicators. We do not treat an incident as isolated. We look at the service graph, identify which dependent services are degraded or at risk, and then summarize the likely operational scope. That helps prioritize the incident and also influences whether automated remediation is safe.

---

## 6) How do logs, metrics, and traces become context for the LLM?

**Answer:**

We do not send raw unbounded telemetry directly. We first collect targeted observations from metrics, logs, and traces relevant to the incident window and affected service. Then we convert that into structured evidence, for example spike in error rate, latency increase in downstream dependency, repeated timeout pattern in logs, or healthy trace performance that contradicts a restart recommendation. This structured context is much safer and more stable than dumping large unfiltered blobs into the prompt.

---

## 7) How do you avoid hallucinations?

**Answer:**

We reduce hallucination using multiple layers: retrieval grounding through runbooks and incident history, structured evidence objects, contradiction-aware reasoning, policy controls, allowlisted actions, and post-action verification. The model is not given full autonomy. It reasons over bounded context, while the platform enforces what is allowed. If evidence is weak or contradictory, the system prefers observation, further checks, or escalation instead of a risky action.

---

## 8) Why did you build your own agents instead of using LangChain or LangGraph?

**Answer:**

We built custom agents because our use case was operationally sensitive and air-gapped. We needed precise control over orchestration, security boundaries, tool access, prompt flow, auditability, approval logic, and fallback behavior. LangChain and LangGraph are useful ecosystems, but the core concepts we needed were planner-style orchestration, tool invocation, retrieval grounding, memory, and workflow control. We implemented those capabilities in a way that matched our environment, security requirements, and production controls.

---

## 9) If asked whether you know LangChain, what should you say?

**Answer:**

I would say that I understand the design patterns LangChain and LangGraph solve, such as chaining, agents, tools, memory, retrieval, and graph-based orchestration. In this project we implemented those capabilities through our own framework because we needed tighter operational control and air-gapped deployment compatibility. So even if the library was custom, the underlying agentic concepts are the same.

---

## 10) How does the system run in an air-gapped environment?

**Answer:**

The system is designed so that inference, retrieval, embeddings, orchestration, storage, and observability remain inside the controlled environment. Models are hosted locally, documents are embedded locally, and vector search or retrieval infrastructure is deployed internally. Package distribution, model onboarding, and updates are handled through approved offline processes. This avoids sending operational data outside the network and satisfies enterprise security requirements.

---

## 11) What are the challenges of an air-gapped AI platform?

**Answer:**

The main challenges are model distribution, offline dependency management, update cycles, limited access to hosted APIs, operational debugging, and capacity planning. You need strong internal observability, reliable local inference, repeatable packaging, and careful resource sizing. Another challenge is keeping knowledge bases and models fresh without relying on cloud-managed services.

---

## 12) How do you store and retrieve runbooks?

**Answer:**

Runbooks are ingested into the knowledge layer, normalized, chunked, indexed, and tagged with metadata such as service, environment, category, and severity. During retrieval, we use those tags plus semantic similarity to return the most relevant sections. That allows the agent to recommend actions that align with existing enterprise procedures instead of inventing generic responses.

---

## 13) How do you use incident history?

**Answer:**

We use incident history in two ways. First, for retrieval and operator Q&A, where similar prior incidents can be surfaced to help investigation. Second, for learning, where past outcomes influence action ranking. If a remediation consistently helped in a similar context, it should be ranked higher. If an action repeatedly caused only temporary relief or required operator override, the system should downgrade it.

---

## 14) How do you decide whether to recommend restart, observe, escalate, or do nothing?

**Answer:**

That decision depends on evidence quality, contradiction level, service criticality, environment, current risk, recent remediations, and policy restrictions. If the evidence strongly supports a known pattern and the action is safe, the system can recommend a remediation. If evidence is mixed, the system prefers observe or validate-first steps. If the service is critical or the action is high risk, it may require approval or escalation. The model proposes, but platform policy decides.

---

## 15) What is contradiction-aware reasoning?

**Answer:**

Contradiction-aware reasoning means the system does not only collect supporting signals. It also deliberately looks for signals that weaken the hypothesis. For example, logs might suggest the application is failing, but traces may show stable downstream latency and the database may be healthy. In that case, confidence in a restart recommendation should be reduced. This improves trust and reduces false-positive remediation.

---

## 16) How do you keep remediation safe?

**Answer:**

We enforce safety through typed or controlled actions, allowlists, environment-aware restrictions, approval gates, cooldowns, retry limits, critical-service policies, and contradiction checks. We also separate recommendation from execution. Even when the agent suggests a command, the control plane verifies whether that action is actually allowed in that context.

---

## 17) How does change management fit into the platform?

**Answer:**

Change management is important because production actions should not bypass enterprise process. The platform can align remediation or execution flows with approval requirements, restricted maintenance windows, service criticality, and operator authorization. In practice, that means the system can recommend an action, but execution may still require explicit approval or change alignment before proceeding.

---

## 18) What role does Freshservice play?

**Answer:**

Freshservice acts as an external operational platform for ticketing, service workflows, and ITSM-style integration. We integrated with it so incidents, context, and workflows can connect to enterprise support processes. That helps bridge AI reasoning with operational execution, approvals, and service desk visibility.

---

## 19) How do you onboard new servers or services?

**Answer:**

Onboarding typically includes registering the service or server metadata, mapping dependencies, defining observability sources, connecting telemetry, associating runbooks, configuring policies, and validating connectivity. Once onboarding is done, the platform can include that service in incident analysis, blast-radius calculation, retrieval, and operational workflows.

---

## 20) How do you monitor the AI platform itself?

**Answer:**

We treat the AI platform as a production system. We monitor request rates, latency, failure rates, model inference time, retrieval latency, connector health, queue depth, tool execution success, and operational outcomes. We also track agent-level behavior such as suggestion acceptance rate, escalation rate, false-positive actions avoided, and time-to-resolution improvement.

---

## 21) How do you evaluate whether the agent is actually useful?

**Answer:**

Utility is measured through operational outcomes, not just model quality. We look at whether it reduces mean time to detect or resolve, whether recommendations are accepted, whether it improves triage speed, whether unsafe actions are reduced, and whether operators trust the suggestions. Replay testing, outcome tracking, and operator feedback are all important for evaluation.

---

## 22) What is outcome learning?

**Answer:**

Outcome learning means the platform learns from what happened after an action or recommendation. If a command resolved similar incidents many times, it should be ranked higher in future. If an action was rejected, edited, or caused only partial recovery, that becomes a useful signal. This is stronger than simple memory because it ties recommendations to operational success.

---

## 23) How do you capture operator feedback?

**Answer:**

We treat operator feedback as a first-class signal. We capture whether a recommendation was accepted, rejected, edited, or replaced with a manual fix, along with notes and quality of outcome. That data is useful for improving ranking, identifying weak guidance, and refining policy.

---

## 24) What does post-remediation verification mean?

**Answer:**

Post-remediation verification means we do not stop at command execution. After the action, the system re-checks the health endpoint, alert state, key metrics, log error rate, and trace health to determine whether the service actually improved. This closes the loop and helps prevent false confidence.

---

## 25) How do you support preventive behavior, not just reactive behavior?

**Answer:**

We combine prediction signals, service risk scoring, recent degradation trends, and incident history to identify services that may fail soon. The system can then trigger proactive investigation, watch incident creation, or low-risk preventive recommendations before a severe incident occurs. This shifts the platform from reactive AIOps toward preventive AIOps.

---

## 26) How do you rank remediations?

**Answer:**

We rank remediations based on historical success rate, environment compatibility, safety, blast-radius risk, recent operator overrides, recurrence patterns, and contextual fit. The goal is to prefer actions that worked in similar conditions while avoiding unstable or unsafe recommendations.

---

## 27) How do you handle conflicting evidence from different data sources?

**Answer:**

We do not hide the conflict. We surface it in the structured evidence and lower confidence. For example, if logs indicate failure but metrics remain healthy and traces do not show customer impact, the system should prefer targeted validation steps over immediate remediation. Contradictory evidence is a safety feature, not a problem to suppress.

---

## 28) How do you debug an agent failure?

**Answer:**

I would inspect the full execution trail: input alert, retrieved documents, telemetry summary, tool calls, prompt context, model response, policy decisions, and final output. That helps identify whether the failure came from retrieval quality, stale runbooks, weak prompt framing, connector issues, telemetry gaps, or policy misconfiguration. In production, you need deep traceability of the reasoning workflow.

---

## 29) What would you improve next in the platform?

**Answer:**

The next improvements would be stronger typed actions, better remediation ranking, richer replay and evaluation, more operator feedback integration, tighter change-management automation, and expanded preventive workflows. I would also invest in measurable offline evaluation so behavior changes can be tested safely before production rollout.

---

## 30) If the interviewer asks whether this project matches the JD, what should you say?

**Answer:**

I would say the project is highly aligned with the role because it covers AI operations, production support, incident triage, observability, RAG, agentic workflows, operational improvement, external platform integration, and safe execution in an enterprise setting. It also adds a strong differentiator through air-gapped deployment and custom agent orchestration.

---

## 31) Give one concise answer for “Why are you a fit for this role?”

**Answer:**

I am a strong fit because I have worked on production-oriented AI operations, not just model demos. I have experience with incident-driven workflows, RAG grounding, agent orchestration, observability integration, policy-controlled remediation, ITSM integration, and secure air-gapped deployment. That matches both the technical and operational expectations of this role.

---

## 32) Short version for interview use

**Answer:**

I built an air-gapped AIOps platform where alerts are enriched with logs, metrics, traces, runbooks, and historical incident context through a RAG layer. Custom agents then generate grounded investigation and remediation guidance, while platform policies enforce safety, approvals, and change-management controls. We also integrated ITSM workflows like Freshservice and built feedback and outcome loops for continuous improvement.

---

## 33) Practical tips during the interview

- Keep returning to **production operations**, not just LLM features.
- Emphasize **air-gapped deployment** as a serious engineering differentiator.
- Say **custom agent framework** confidently.
- Explain that **RAG was used for incidents, runbooks, blast radius, and operational Q&A**.
- Highlight **Freshservice integration**, **change management**, and **server onboarding**.
- Use phrases like **policy-controlled**, **evidence-grounded**, **operator-in-the-loop**, and **closed-loop verification**.

---

## 34) Python survival section: 15 likely coding questions with code

These are practical Python questions more likely for this role than algorithm-heavy puzzles. Focus on writing clear, working code and explaining the approach.

---

### 1. Parse a JSON alert payload and extract key fields

**Question:** Write a function that accepts an alert payload and returns service, severity, alert name, and timestamp.

```python
def parse_alert(payload: dict) -> dict:
	return {
		"service": payload.get("service", "unknown"),
		"severity": payload.get("severity", "unknown"),
		"alert_name": payload.get("alert_name", "unknown"),
		"timestamp": payload.get("timestamp"),
	}


sample = {
	"service": "orders-api",
	"severity": "critical",
	"alert_name": "HighErrorRate",
	"timestamp": "2026-04-24T10:15:00Z",
}

print(parse_alert(sample))
```

---

### 2. Count how many alerts occurred per service

**Question:** Given a list of alert dictionaries, count alerts by service.

```python
def count_alerts_by_service(alerts: list[dict]) -> dict:
	counts = {}
	for alert in alerts:
		service = alert.get("service", "unknown")
		counts[service] = counts.get(service, 0) + 1
	return counts


alerts = [
	{"service": "orders"},
	{"service": "payments"},
	{"service": "orders"},
]

print(count_alerts_by_service(alerts))
```

---

### 3. Filter only critical alerts

**Question:** Return only alerts with severity `critical`.

```python
def filter_critical_alerts(alerts: list[dict]) -> list[dict]:
	return [alert for alert in alerts if alert.get("severity") == "critical"]


alerts = [
	{"service": "orders", "severity": "warning"},
	{"service": "payments", "severity": "critical"},
	{"service": "search", "severity": "critical"},
]

print(filter_critical_alerts(alerts))
```

---

### 4. Find the top error message in logs

**Question:** Given a list of log lines, return the most frequent error line.

```python
def most_common_error(logs: list[str]) -> str | None:
	counts = {}
	for line in logs:
		counts[line] = counts.get(line, 0) + 1

	if not counts:
		return None

	return max(counts, key=counts.get)


logs = [
	"timeout connecting to db",
	"timeout connecting to db",
	"service unavailable",
]

print(most_common_error(logs))
```

---

### 5. Retry an API call with basic exception handling

**Question:** Write a function that retries a failing API call up to 3 times.

```python
import time
import requests


def fetch_with_retry(url: str, retries: int = 3, delay: int = 2) -> dict:
	last_error = None

	for attempt in range(1, retries + 1):
		try:
			response = requests.get(url, timeout=10)
			response.raise_for_status()
			return response.json()
		except Exception as exc:
			last_error = exc
			if attempt < retries:
				time.sleep(delay)

	raise RuntimeError(f"API call failed after {retries} attempts: {last_error}")
```

---

### 6. Read a log file and return lines containing `ERROR`

**Question:** Read a file and return matching lines.

```python
def find_error_lines(file_path: str) -> list[str]:
	matches = []
	with open(file_path, "r", encoding="utf-8") as file:
		for line in file:
			if "ERROR" in line:
				matches.append(line.strip())
	return matches
```

---

### 7. Convert alert records into a summary string for an LLM

**Question:** Build a concise text summary from alert objects.

```python
def build_alert_summary(alerts: list[dict]) -> str:
	lines = []
	for alert in alerts:
		line = (
			f"Service={alert.get('service', 'unknown')}, "
			f"Severity={alert.get('severity', 'unknown')}, "
			f"Alert={alert.get('alert_name', 'unknown')}"
		)
		lines.append(line)
	return "\n".join(lines)


alerts = [
	{"service": "orders", "severity": "critical", "alert_name": "HighLatency"},
	{"service": "payments", "severity": "warning", "alert_name": "PodRestarts"},
]

print(build_alert_summary(alerts))
```

---

### 8. Basic class for an incident record

**Question:** Create a class to represent an incident.

```python
class Incident:
	def __init__(self, incident_id: str, service: str, severity: str, status: str = "open"):
		self.incident_id = incident_id
		self.service = service
		self.severity = severity
		self.status = status

	def close(self) -> None:
		self.status = "closed"

	def to_dict(self) -> dict:
		return {
			"incident_id": self.incident_id,
			"service": self.service,
			"severity": self.severity,
			"status": self.status,
		}


incident = Incident("INC-101", "orders", "critical")
incident.close()
print(incident.to_dict())
```

---

### 9. Merge telemetry from metrics, logs, and traces into one object

**Question:** Combine multiple sources into one dictionary.

```python
def build_context(metrics: dict, logs: list[str], traces: list[dict]) -> dict:
	return {
		"metrics": metrics,
		"log_count": len(logs),
		"sample_logs": logs[:3],
		"trace_count": len(traces),
		"sample_traces": traces[:2],
	}


metrics = {"error_rate": 12.5, "latency_p95": 840}
logs = ["timeout", "db error", "timeout", "retry failed"]
traces = [{"trace_id": "t1"}, {"trace_id": "t2"}, {"trace_id": "t3"}]

print(build_context(metrics, logs, traces))
```

---

### 10. Deduplicate alerts by fingerprint

**Question:** Remove duplicate alerts using a fingerprint field.

```python
def deduplicate_alerts(alerts: list[dict]) -> list[dict]:
	seen = set()
	unique_alerts = []

	for alert in alerts:
		fingerprint = alert.get("fingerprint")
		if fingerprint and fingerprint not in seen:
			seen.add(fingerprint)
			unique_alerts.append(alert)

	return unique_alerts


alerts = [
	{"fingerprint": "abc", "service": "orders"},
	{"fingerprint": "abc", "service": "orders"},
	{"fingerprint": "xyz", "service": "payments"},
]

print(deduplicate_alerts(alerts))
```

---

### 11. Sort incidents by severity

**Question:** Sort incidents so `critical` comes before `high`, `medium`, and `low`.

```python
def sort_by_severity(incidents: list[dict]) -> list[dict]:
	priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
	return sorted(incidents, key=lambda item: priority.get(item.get("severity", "low"), 99))


incidents = [
	{"id": "1", "severity": "medium"},
	{"id": "2", "severity": "critical"},
	{"id": "3", "severity": "high"},
]

print(sort_by_severity(incidents))
```

---

### 12. Load configuration from environment variables

**Question:** Read environment variables safely with defaults.

```python
import os


def load_config() -> dict:
	return {
		"db_host": os.getenv("DB_HOST", "localhost"),
		"db_port": int(os.getenv("DB_PORT", "5432")),
		"model_name": os.getenv("MODEL_NAME", "local-llm"),
		"debug": os.getenv("DEBUG", "false").lower() == "true",
	}


print(load_config())
```

---

### 13. Write a function to detect restart-like commands

**Question:** Detect whether a command looks like a restart command.

```python
def looks_like_restart(command: str) -> bool:
	if not command:
		return False

	text = command.lower()
	keywords = ["restart", "rollout restart", "systemctl restart", "kubectl delete pod"]
	return any(keyword in text for keyword in keywords)


print(looks_like_restart("kubectl rollout restart deployment orders-api"))
print(looks_like_restart("check health endpoint"))
```

---

### 14. Save structured output to a JSON file

**Question:** Store a Python object as formatted JSON.

```python
import json


def save_json(data: dict, file_path: str) -> None:
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(data, file, indent=2)


payload = {
	"service": "orders",
	"status": "degraded",
	"recommended_action": "observe and validate db latency",
}

save_json(payload, "incident_output.json")
```

---

### 15. Compute a simple incident risk score

**Question:** Write a small function that calculates a risk score from error rate, latency, and active alerts.

```python
def calculate_risk_score(error_rate: float, latency_ms: float, active_alerts: int) -> float:
	score = 0.0
	score += min(error_rate * 2, 40)
	score += min(latency_ms / 50, 30)
	score += min(active_alerts * 10, 30)
	return round(min(score, 100.0), 2)


print(calculate_risk_score(error_rate=12.5, latency_ms=800, active_alerts=2))
```

---

## How to handle coding questions if you get stuck

Use this structure in the interview:

1. Clarify the input and expected output.
2. Start with a simple working version.
3. Explain assumptions clearly.
4. Add error handling if time permits.
5. Prefer readable Python over clever Python.

Example phrase:

> “I’ll start with a simple working version, then improve it for edge cases if needed.”

---

## What to revise before the interview

- dictionaries and lists
- loops and conditions
- functions
- `try/except`
- reading JSON and files
- environment variables
- API calls using `requests`
- basic classes
- sorting and filtering
- string handling

That should be enough for a practical Python screening aligned to this role.

