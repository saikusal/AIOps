# AIOps Architecture

This document describes the current implemented architecture of the AIOps platform. It is aligned to the codebase as it exists now:

- **self-hosted control plane**
- **air-gapped local inference through `vLLM`**
- **code-context-aware investigation and remediation**

Related diagram sources:

- [diagrams/aiops-architecture.mmd](./diagrams/aiops-architecture.mmd)
- [diagrams/aiops-architecture.drawio](./diagrams/aiops-architecture.drawio)

## 1. System Overview

The platform has four interacting planes:

1. **Control plane**
   Django application for incidents, investigations, runbooks, approvals, policies, fleet onboarding, and MCP-style evidence gathering.
2. **Inference plane**
   Self-hosted `vLLM` serving a local Qwen-family model over an OpenAI-compatible API.
3. **Observability plane**
   Prometheus, Alertmanager, Jaeger, Elasticsearch, OpenTelemetry Collector, and Grafana.
4. **Application plane**
   Demo services and fault-injection infrastructure used to generate incidents and validate the operator workflow.

## 2. High-Level Architecture

```text
                         +---------------------------+
                         |       User / Operator     |
                         +-------------+-------------+
                                       |
                     +-----------------+-----------------+
                     |                                   |
                     v                                   v
        +---------------------------+       +---------------------------+
        | React Product UI          |       | Django Control Plane      |
        | frontend/                 |       | genai + doc_search        |
        | :8089                     |       | :8000                     |
        +---------------------------+       +-------------+-------------+
                                                          |
                         +--------------------------------+--------------------------------+
                         |                |                |               |                |
                         v                v                v               v                v
                   +-----------+   +-----------+   +-------------+  +-----------+   +------------+
                   |PostgreSQL |   |   Redis   |   | Local vLLM  |  |  Agents   |   | Code       |
                   | incidents |   | cache     |   | Qwen model  |  | control/db|   | Context    |
                   | metadata  |   | sessions  |   | no egress   |  | execution |   | Engine     |
                   +-----------+   +-----------+   +-------------+  +-----------+   +------------+
                                                                                           |
                                                                                           v
                                                                              +---------------------------+
                                                                              | Local Repositories        |
                                                                              | routes / spans / commits  |
                                                                              | snippets / ownership      |
                                                                              +---------------------------+
```

## 3. Control Plane

The control plane is the Django project under:

- [aiops_platform](./aiops_platform)
- [genai](./genai)
- [doc_search](./doc_search)

Main responsibilities:

- ingest alerts from Alertmanager
- correlate incidents
- run AI-assisted investigations
- retrieve metrics, logs, traces, topology, and code context
- enforce execution policy and approval workflows
- persist incident timelines, tool traces, and remediation outcomes
- expose MCP-style internal endpoints under `/genai/mcp/...`

Important entry points:

- [aiops_platform/urls.py](./aiops_platform/urls.py)
- [genai/urls.py](./genai/urls.py)
- [genai/views.py](./genai/views.py)
- [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py)

## 4. Air-Gapped Inference Plane

The inference layer is intentionally local-first.

Current implementation:

- [genai/llm_backend.py](./genai/llm_backend.py)
- `VLLM_API_URL`
- `VLLM_MODEL_NAME`

Runtime behavior:

1. Django builds an evidence-rich prompt.
2. The prompt is sent to the local `vLLM` endpoint.
3. The local model returns a grounded answer, typed action, explanation, or summary.

Architecture implications:

- no production telemetry needs to be sent to third-party AI APIs
- no external API key is required for the primary product story
- the same backend path is used for investigations, RCA, remediation reasoning, and post-action analysis

## 5. Observability Plane

The observability stack provides the runtime evidence that feeds investigations.

Components:

- Prometheus / VictoriaMetrics-compatible query path
- Alertmanager
- OpenTelemetry Collector
- Jaeger
- Elasticsearch
- Filebeat
- Grafana
- exporters for node, Postgres, and Nginx

Primary flow:

```text
services -> OTEL / exporters -> Prometheus / Jaeger / Elasticsearch
alerts -> Alertmanager -> Django ingest endpoint
investigations -> Django fetches scoped telemetry -> local LLM reasons on retrieved evidence
```

This is deliberate: the model does not own direct uncontrolled access to monitoring systems. The application retrieves evidence and decides what to send to the model.

## 6. Code-Context Engine

This is one of the core differentiators of the platform.

The code-context engine links operational entities back to local source code. It is implemented in:

- [genai/code_context_ingestion.py](./genai/code_context_ingestion.py)
- [genai/code_context_services.py](./genai/code_context_services.py)
- [genai/mcp_services.py](./genai/mcp_services.py)

### 6.1 Indexed Entities

The local index stores:

- repository metadata
- service-to-repository ownership
- route-to-handler bindings
- span-to-symbol bindings
- recent deployment metadata
- recent git change records
- symbol relations

Core models:

- `RepositoryIndex`
- `ServiceRepositoryBinding`
- `RouteBinding`
- `SpanBinding`
- `DeploymentBinding`
- `CodeChangeRecord`
- `SymbolRelation`

These models live in [genai/models.py](./genai/models.py).

### 6.2 What It Enables

During an incident or assistant query, the platform can answer:

- which repository likely owns a failing service
- which file and handler back a route
- which symbol most likely matches a trace span
- which files changed recently on the suspected path
- which related symbols expand the code blast radius
- which snippet should be shown as direct source evidence

### 6.3 Sync Flow

The index is populated from local repository paths.

Important behaviors already implemented:

- bootstrap known demo repository indexes
- auto-register repositories from target metadata
- extract Python route, span, and relation artifacts
- enrich with recent local git changes when `git` is available

Operational command:

```bash
python manage.py sync_code_context
```

Code:

- [genai/management/commands/sync_code_context.py](./genai/management/commands/sync_code_context.py)

## 7. Investigation Orchestration

The assistant investigation path uses an internal MCP-style orchestration layer.

Registered evidence tools include:

- incident timeline lookup
- application graph lookup
- component snapshot lookup
- metrics lookup
- log search
- trace search
- runbook search
- traceback source extraction
- service ownership lookup
- route-to-handler lookup
- span-to-symbol lookup
- recent change lookup
- recent deployment lookup
- related symbol lookup
- code blast-radius lookup
- code search
- code snippet read

This orchestration is implemented in [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py).

### 7.1 Investigation Flow

```text
1. User asks a question or opens an incident.
2. Django derives scope: incident, app, service, target host.
3. MCP-style internal tools collect telemetry and code evidence.
4. Evidence is normalized into a bounded prompt.
5. Local vLLM reasons over that evidence.
6. The answer is stored with retrieval trace and surfaced to UI.
```

### 7.2 Why This Matters

This design avoids the weakest common pattern in generic AI observability tools:

- raw dashboards in
- vague summary out

Instead, the platform can move from:

- symptom
- to service
- to route/span
- to repository
- to recent change
- to source snippet

inside the same investigation loop.

## 8. Application Topology and Blast Radius

There are two blast-radius lenses in the current product:

1. **runtime topology blast radius**
   derived from the application dependency graph
2. **code blast radius**
   derived from symbol and repository relationships

Current runtime graph source:

- [demo/dependencies/application_graph.json](./demo/dependencies/application_graph.json)

This graph powers:

- application topology views
- incident graph views
- dependency summaries
- alert enrichment

The code-context layer adds a second dimension:

- related files
- related symbols
- likely affected handlers
- recent commits on the path

## 9. Alert Ingestion and Recommendation Flow

Current implemented flow:

```text
1. Prometheus evaluates alert rules.
2. Alertmanager sends a webhook to /genai/alerts/ingest/.
3. Django normalizes and stores the alert.
4. The app gathers evidence:
   - metrics
   - logs
   - traces
   - dependency context
   - prediction context
   - code-context lookups when relevant
5. Django sends the bounded evidence package to local vLLM.
6. The model returns diagnosis, explanation, and next-step guidance.
7. The recommendation is stored and shown in dashboards.
```

Key point:

- telemetry retrieval is application-controlled
- code retrieval is application-controlled
- reasoning is local

That is the basis of the self-hosted, air-gapped product pitch.

## 10. Controlled Remediation Flow

The platform separates reasoning from execution.

```text
1. Assistant or alert flow proposes a typed action.
2. Policy engine evaluates environment, service criticality, and safety rules.
3. If allowed, the control plane issues an execution intent.
4. If required, operator approval is enforced.
5. Agent executes only allowlisted commands.
6. Output is returned to Django.
7. Local model analyzes the result and updates the incident/remediation record.
```

Relevant modules:

- [genai/policy_engine.py](./genai/policy_engine.py)
- [genai/execution_safety.py](./genai/execution_safety.py)
- [genai/multi_step_workflow.py](./genai/multi_step_workflow.py)
- [genai/typed_actions.py](./genai/typed_actions.py)
- [agent/agent_server.py](./agent/agent_server.py)

## 11. Frontend Surfaces

There are multiple UI surfaces in the repo:

### Product UI

- [frontend](./frontend)

Main routes include:

- incident workflows
- topology
- assistant
- code context graph
- onboarding
- analytics

Important files:

- [frontend/src/App.tsx](./frontend/src/App.tsx)
- [frontend/src/pages/AssistantPage.tsx](./frontend/src/pages/AssistantPage.tsx)
- [frontend/src/pages/CodeContextPage.tsx](./frontend/src/pages/CodeContextPage.tsx)

### Legacy / Django Template UI

- [genai/templates](./genai/templates)

### Marketing Site

- [opsmitra-site](./opsmitra-site)

## 12. Demo and Chaos Plane

The demo environment exists to show realistic incident propagation across shared dependencies.

Components:

- frontend Nginx
- gateway Nginx
- `app-orders`
- `app-inventory`
- `app-billing`
- demo Postgres
- Toxiproxy

Useful scripts:

- `demo/tools/run-demo-traffic.sh`
- `demo/tools/cut-db-traffic.sh`
- `demo/tools/set-db-latency.sh`
- `demo/tools/stress-db-connections.sh`
- `demo/tools/cut-gateway-traffic.sh`
- `demo/tools/set-gateway-latency.sh`

This plane is useful because it produces:

- shared dependency failures
- downstream blast-radius examples
- realistic logs, traces, and metrics
- reproducible failure paths for code-aware investigation

## 13. Design Positioning

The strongest way to describe the platform is:

> A self-hosted, air-gapped AIOps control plane that investigates incidents using both observability evidence and local code context.

That positioning depends on four claims being true in the implementation:

1. **self-hosted**
   The stack runs under Docker Compose with local services and local data stores.
2. **air-gapped AI**
   Inference is served by local `vLLM`, not an external AI SaaS endpoint.
3. **code-aware**
   Runtime entities are mapped back to repositories, handlers, spans, symbols, changes, and snippets.
4. **controlled execution**
   Remediation is mediated by policy and allowlisted agents rather than arbitrary shell access.

Those claims are supported by the codebase today.
