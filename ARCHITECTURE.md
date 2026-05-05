# AIOps Architecture

This document describes the current implemented architecture of the AIOps platform. It is aligned to the codebase as it exists now:

- **self-hosted control plane**
- **air-gapped local inference through `vLLM`**
- **code-context-aware investigation and remediation**

Related diagram sources:

- [diagrams/aiops-architecture.mmd](./diagrams/aiops-architecture.mmd)
- [diagrams/aiops-architecture.drawio](./diagrams/aiops-architecture.drawio)

## 1. System Overview

The platform currently has four interacting planes:

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
             +-------------------------------------------------------------------+
             |                 Customer Self-Hosted Environment                   |
             +-------------------------------------------------------------------+
                                       |
                +----------------------+----------------------+
                |                                             |
                v                                             v
   +---------------------------+                 +-------------------------------+
   | Control Plane Host        |                 | Monitored Linux Servers       |
   | Docker Compose today      |                 | external targets              |
   | Kubernetes packaging next |                 | onboarded over SSH            |
   +-------------+-------------+                 +---------------+---------------+
                 |                                               |
       +---------+---------+                                     |
       |                   |                                     |
       v                   v                                     v
 +-------------+   +---------------+                +-----------------------------+
 | Django + UI |   | Local vLLM    |                | aiops-agent                 |
 | incidents   |   | Qwen via vLLM |                | otelcol + node_exporter     |
 | fleet       |   | no AI egress  |                | logs + heartbeat            |
 | code ctx    |   +---------------+                | optional Docker runtime      |
 +------+------+                                        +-------------+------------+
        |                                                             |
        v                                                             v
 +-------------+   +---------------+                     +--------------------------+
 | Postgres    |   | Observability |                     | applications / containers|
 | Redis       |   | Prom/AM/JGR/ES|                     | processes / services     |
 +-------------+   +---------------+                     +--------------------------+
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

### 3.1 Deployment Shape

The current supported control-plane deployment is:

- one customer-managed Linux host
- Docker Compose for service packaging and startup
- local Postgres, Redis, observability components, and `vLLM`

The next packaging target is:

- Kubernetes deployment for the control plane itself
- most likely via Helm charts and environment-specific values

That distinction matters:

- `Docker Compose` is the current control-plane deployment mechanism
- customer servers being monitored do not need to run your platform containers
- larger enterprise environments can later run the same control plane on Kubernetes

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

## 6. Fleet Onboarding and Remote Collection

The onboarding module is implemented today as a Linux-first remote enrollment flow.

Relevant pieces:

- [genai/models.py](./genai/models.py)
- [genai/views.py](./genai/views.py)
- `/genai/fleet/onboarding/...`
- `/genai/fleet/enroll/...`
- `/genai/fleet/install/linux/`

### 6.1 Current Linux Flow

```text
1. Operator creates an onboarding request with host, user, and PEM key.
2. Control plane validates SSH reachability.
3. Control plane runs a generated Linux bootstrap script remotely.
4. The host installs aiops-agent, OpenTelemetry Collector, and node_exporter.
5. The host enrolls back into Fleet with token-based registration.
6. Periodic heartbeat reports component health and discovered host-side services.
```

Current seeded profiles are Linux-specific and include components such as:

- `AIOps Supervisor`
- `OpenTelemetry Collector`
- `node_exporter`
- `log shipper`
- `discovery helper`

### 6.2 Dockerized Applications On Linux Hosts

When the customer application is running in Docker on a Linux server, the target model remains host-centric:

- the target is still the Linux server
- Docker is a runtime attribute of that server
- containers become discovered workloads underneath the host target

The current codebase already supports Docker-oriented remediation commands and a Fleet model that can receive `discovered_services`, but the Linux heartbeat script does not yet enumerate customer containers. Today it reports the installed collectors themselves.

The intended Docker auto-discovery flow is:

```text
1. Onboard the Linux host with the existing SSH/bootstrap path.
2. Detect whether Docker is present and reachable.
3. Enumerate running containers, image names, labels, ports, and health.
4. Publish each container as a discovered service or workload.
5. Feed that runtime inventory into topology, investigation scope, and code-context binding.
```

That is the right extension point for Docker-on-Linux environments. It should not require a separate cluster onboarding path.

### 6.3 Kubernetes Status

Kubernetes onboarding is not implemented yet.

There are two separate Kubernetes workstreams:

1. deploy the control plane itself on Kubernetes
2. onboard customer Kubernetes clusters as monitored targets

Those should be treated separately from Linux host onboarding because Kubernetes needs:

- cluster registration rather than SSH login
- RBAC-scoped API access rather than per-host bootstrap
- Helm or operator-based collectors rather than a shell installer

## 7. Code-Context Engine

This is one of the core differentiators of the platform.

The code-context engine links operational entities back to local source code. It is implemented in:

- [genai/code_context_ingestion.py](./genai/code_context_ingestion.py)
- [genai/code_context_services.py](./genai/code_context_services.py)
- [genai/mcp_services.py](./genai/mcp_services.py)

### 7.1 Indexed Entities

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

### 7.2 What It Enables

During an incident or assistant query, the platform can answer:

- which repository likely owns a failing service
- which file and handler back a route
- which symbol most likely matches a trace span
- which files changed recently on the suspected path
- which related symbols expand the code blast radius
- which snippet should be shown as direct source evidence

### 7.3 Sync Flow

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

## 8. Investigation Orchestration

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

### 8.1 Investigation Flow

```text
1. User asks a question or opens an incident.
2. Django derives scope: incident, app, service, target host.
3. MCP-style internal tools collect telemetry and code evidence.
4. Evidence is normalized into a bounded prompt.
5. Local vLLM reasons over that evidence.
6. The answer is stored with retrieval trace and surfaced to UI.
```

### 8.2 Why This Matters

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

## 9. Application Topology and Blast Radius

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

## 10. Alert Ingestion and Recommendation Flow

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

## 11. Controlled Remediation Flow

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

## 12. Frontend Surfaces

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

## 13. Demo and Chaos Plane

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

## 14. Design Positioning

The strongest way to describe the platform is:

> A self-hosted, air-gapped AIOps control plane that investigates incidents using both observability evidence and local code context.

That positioning depends on four claims being true in the implementation:

1. **self-hosted**
   The stack currently runs under Docker Compose with local services and local data stores, with Kubernetes packaging planned next.
2. **air-gapped AI**
   Inference is served by local `vLLM`, not an external AI SaaS endpoint.
3. **code-aware**
   Runtime entities are mapped back to repositories, handlers, spans, symbols, changes, and snippets.
4. **controlled execution**
   Remediation is mediated by policy and allowlisted agents rather than arbitrary shell access.

Those claims are supported by the codebase today.
