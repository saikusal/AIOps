# OpsMitra Architecture

This document describes the current implemented architecture of the OpsMitra control plane. It is aligned to the codebase as it exists now:

- **self-hosted control plane** — Django + React, deployed via Docker Compose or Helm
- **air-gapped local inference** through `vLLM` plus an explicit embedding endpoint
- **code-context-aware investigation** and **policy-gated remediation**
- **multi-tenant** with RBAC across every privileged surface
- **fleet-managed** Linux, Kubernetes, and OT targets through a single control plane

Related diagram sources:

- [diagrams/aiops-architecture.mmd](./diagrams/aiops-architecture.mmd)
- [diagrams/aiops-architecture.drawio](./diagrams/aiops-architecture.drawio)

---

## 1. System Overview

The platform has five interacting planes:

1. **Control plane** — Django application for incidents, investigations, runbooks, approvals, policies, signal analytics, fleet onboarding, predictor, and integration writeback.
2. **Inference plane** — Self-hosted `vLLM` serving a local chat/reasoning model plus a separate OpenAI-compatible embedding endpoint.
3. **Observability plane** — Prometheus / VictoriaMetrics, Alertmanager, OpenTelemetry Collector, Jaeger / Tempo, Elasticsearch / OpenSearch, Filebeat, Grafana.
4. **Execution plane** — Fleet agents (Linux, Kubernetes, OT) that receive policy-gated commands from the control plane.
5. **Application plane** — Customer workloads under management; plus a demo workload that produces realistic incidents.

The strongest way to describe the platform:

> A self-hosted, air-gapped AI incident control plane that investigates incidents using observability evidence **and** local code context, then executes remediations only through explicit policy, approval, audit, and rollback boundaries.

---

## 2. High-Level Architecture

```text
              +---------------------------------------------------------------+
              |               Customer Self-Hosted Environment                 |
              +---------------------------------------------------------------+
                                            |
              +-----------------------------+-----------------------------+
              |                                                           |
              v                                                           v
   +----------------------------+                          +----------------------------+
   | Control Plane              |                          | Managed Fleet Targets      |
   | Docker Compose             |                          | Linux servers (SSH)        |
   |   or                       |                          | Kubernetes clusters (agent)|
   | Kubernetes via Helm        |                          | Industrial OT (OPC-UA, …)  |
   +-------------+--------------+                          +--------------+-------------+
                 |                                                        |
   +-------------+--------------+                                         |
   |             |              |                                         |
   v             v              v                                         v
 +--------+ +-----------+ +-----------+                       +-------------------------+
 | Django | | React UI  | | Predictor |                       | aiops-agent             |
 | + ASGI | | (Vite)    | | service   |                       | otelcol, exporters      |
 +---+----+ +-----------+ +-----------+                       | heartbeat, command poll |
     |                                                        +-----------+-------------+
     |                                                                    |
     v                                                                    v
 +---------+   +-----------+   +-----------------+        +---------------------------+
 | Postgres|   | Redis     |   | Local AI runtime |       | applications / containers |
 |+pgvector|   | (queues   |   | vLLM + embeddings|       | services / kubelets / PLCs|
 +---------+   |  + cache) |   | no AI egress     |       +---------------------------+
               +-----------+   +-----------------+
```

Every layer runs on customer infrastructure. The control plane never phones home.

---

## 3. Control Plane

The control plane is the Django project under:

- [aiops_platform](./aiops_platform) — settings, ASGI, URL routing, middleware
- [genai](./genai) — domain logic for alerts, incidents, investigations, EGAP, MCP, code context, integrations, fleet, predictor
- [doc_search](./doc_search) — runbook and documentation indexing

Main responsibilities:

- ingest alerts from Alertmanager and webhook sources
- correlate per-alert lifecycle into incidents
- run AI-assisted streaming investigations
- retrieve metrics, logs, traces, topology, and code context through MCP-style tools
- enforce execution policy, approval, blast radius, and rollback through EGAP
- persist incident timelines, tool traces, and remediation outcomes
- expose tenant-scoped operator APIs to the React UI
- manage fleet onboarding and remote command dispatch
- write incidents back to configured ITSM / notification providers

### 3.1 Entry Points

- [aiops_platform/urls.py](./aiops_platform/urls.py)
- [genai/urls.py](./genai/urls.py)
- [genai/views.py](./genai/views.py)
- [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py)
- [genai/egap_protocol.py](./genai/egap_protocol.py)
- [genai/alert_pipeline.py](./genai/alert_pipeline.py)

### 3.2 Deployment Targets

| Target | Use |
|---|---|
| **Docker Compose** | Single-node trial, demo, internal staging |
| **Kubernetes (Helm)** | Production. Migration job, ingress, persistent volumes, cluster agent assets |

`entrypoint.sh` runs database migrations automatically on container start. The Helm chart provides an equivalent migration job for upgrades.

---

## 4. Multi-Tenancy and RBAC

Every operational record is tenant-owned.

Core models:

- `Tenant`, `TenantMembership`, `TenantInvitation`, `TenantAuditEvent`
- All incident, alert, integration, execution, fleet, and code-context records carry a tenant foreign key (closed by migration `0029_alter_alertevent_tenant_and_more`).
- Query scoping is enforced via tenant-aware querysets — cross-tenant reads are not permitted.

Backend permissions span tenant, incident, alert, investigation, integration, fleet, execution, cache, lifecycle, code-context, and operations surfaces.

The React UI ships:

- a tenant provider and switcher
- permission-aware navigation
- an admin member-management surface at `/settings/members`

Tenant audit events are append-only at the Django model and signal layer — they cannot be modified or deleted through normal ORM operations.

---

## 5. Air-Gapped Inference And Vector Plane

The inference layer is intentionally local-first.

Implementation:

- [genai/llm_backend.py](./genai/llm_backend.py)
- [genai/vector_backend.py](./genai/vector_backend.py)
- `VLLM_API_URL`, `VLLM_MODEL_NAME`
- `VLLM_EMBEDDING_URL`, `VECTOR_EMBED_MODEL`, `PGVECTOR_DIMENSIONS`

Runtime behavior:

1. Django constructs an evidence-rich, bounded prompt from MCP tool results.
2. The prompt is sent to the local `vLLM` endpoint over the OpenAI-compatible API.
3. The local model returns a grounded answer, typed action recommendation, explanation, or summary.
4. Output is recorded with the full retrieval trace for audit.
5. Code, runbook, and incident-memory semantic search use the explicit embedding endpoint and store vectors in pgvector.

Architecture implications:

- no telemetry leaves the customer network
- no external API key is required for the primary product story
- the same inference path is used for investigations, RCA, remediation reasoning, runbook generation, narrative generation, and post-action analysis
- the model is BYO — any vLLM-compatible model fits
- embedding is intentionally separate from chat inference; instruct models should not be assumed to support `/v1/embeddings`

The application controls what evidence is retrieved and what gets sent to the model. The model does not own direct, uncontrolled access to telemetry or code.

### 5.1 Vector Storage

Compose uses `pgvector/pgvector:pg13` so the database contains the `vector` extension. The application creates a standalone `vector_store` table on first use:

```text
collection, object_id, vector(<PGVECTOR_DIMENSIONS>), metadata, timestamps
```

Current recommended embedding profile:

```env
VLLM_EMBEDDING_URL=http://<embedding-host>:8002/v1/embeddings
VECTOR_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
PGVECTOR_DIMENSIONS=384
```

If pgvector is unavailable in an environment, the vector backend now degrades by skipping vector upsert/search rather than failing incident or investigation flow. Production deployments should still provide pgvector or an external vector backend because code-context, runbook, and incident-memory retrieval quality depends on embeddings.

---

## 6. Alert Ingest Pipeline (AIP)

Implementation: [genai/alert_pipeline.py](./genai/alert_pipeline.py), [genai/models.py](./genai/models.py).

Flow:

```text
1. Prometheus or Alertmanager-compatible source posts to /genai/alerts/ingest/.
2. Pipeline normalizes the payload into IncidentAlert records.
3. Suppression rules and active maintenance windows are evaluated.
4. Lifecycle key derived from alert identity (labels, fingerprint).
5. Dedupe is conservative — preserves per-alert tracking, does not collapse sibling alerts
   from grouped Alertmanager payloads into one ticket.
6. Alerts within the same lifecycle update the same incident.
7. A new alert lifecycle creates a new incident with a unique incident number.
8. Correlation links connect related incidents without forcing merge.
```

Per-firing history is stored in `IncidentAlert` (with `first_seen_at` / `last_seen_at`), which is the source of truth for density analytics. `AlertEvent` is an upsert summary model — one row per unique alert identity.

---

## 7. Code Context Graph (CCG)

One of the core differentiators of the platform.

Implementation:

- [genai/code_context_ingestion.py](./genai/code_context_ingestion.py)
- [genai/code_context_services.py](./genai/code_context_services.py)
- [genai/code_context_extractors.py](./genai/code_context_extractors.py)
- [genai/mcp_services.py](./genai/mcp_services.py)

### 7.1 Indexed Entities

Core models (in [genai/models.py](./genai/models.py)):

- `RepositoryIndex`
- `ServiceRepositoryBinding`
- `RouteBinding`
- `SpanBinding`
- `DeploymentBinding`
- `CodeChangeRecord`
- `SymbolRelation`

### 7.2 What It Enables

During an investigation, the platform can answer:

- which repository likely owns a failing service
- which file and handler back a route
- which symbol most likely matches a trace span
- which files changed recently on the suspected path
- which related symbols expand the code blast radius
- which snippet should be shown as direct source evidence
- which deployment introduced the suspected change

### 7.3 Sync Flow

The index is populated from local repository paths — no external code-hosting service is required.

```bash
python manage.py sync_code_context
```

Command source: [genai/management/commands/sync_code_context.py](./genai/management/commands/sync_code_context.py).

Behaviors:

- bootstrap known demo repository indexes
- auto-register repositories from target metadata
- extract Python route, span, and relation artifacts
- enrich with recent local git changes when `git` is available

---

## 8. Model Context Protocol (MCP)

Implementation: [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py), [genai/mcp_services.py](./genai/mcp_services.py), [genai/mcp_registry.py](./genai/mcp_registry.py).

The MCP layer gives the local LLM **typed, structured** access to operational data — no free-form retrieval, no hallucination-prone scraping. Tools are grouped:

| Group | Tools |
|---|---|
| **Incidents** | Incident Summary, Incident Timeline |
| **Applications** | App Overview, Topology Graph, Component Detail |
| **Observability** | Service Metrics, Metrics Query, Log Search, Trace Search |
| **Code Context** | Service Owner, Route Handler, Span Symbol, Recent Changes, Recent Deployments, Related Symbols, Blast Radius, Search Context, Read Snippet |
| **Knowledge** | Runbook Search |

### 8.1 Investigation Flow

```text
1. User asks a question, or an alert triggers an investigation.
2. Django derives scope: incident, app, service, target host, tenant.
3. MCP orchestrator selects tools and gathers evidence.
4. Evidence is normalized into a bounded prompt.
5. Local vLLM reasons over that evidence.
6. The answer is stored with full retrieval trace and surfaced to the UI as a stream.
7. Operators see the reasoning unfold in real time, not a static post-hoc report.
```

Live streams are exposed via [genai/investigation_streams.py](./genai/investigation_streams.py).

### 8.2 Why This Matters

This design avoids the weakest common pattern in generic AI observability tools:

- raw dashboards in → vague summary out

Instead, the platform moves from symptom → service → route/span → repository → recent change → source snippet, inside the same investigation loop, with typed evidence at every step.

---

## 9. Execution & Governance Action Protocol (EGAP)

Implementation: [genai/egap_protocol.py](./genai/egap_protocol.py), [genai/policy_engine.py](./genai/policy_engine.py), [genai/execution_safety.py](./genai/execution_safety.py), [genai/blast_radius_estimation.py](./genai/blast_radius_estimation.py), [genai/break_glass_notifications.py](./genai/break_glass_notifications.py).

Every remediation passes through six gates between intent and execution:

| Step | Gate | Behavior |
|---|---|---|
| 01 | **Intent** | Typed `ExecutionIntent` with action type, target service, environment, command preview |
| 02 | **Policy** | `PolicyPack` evaluation. Auto-approve, require human approval, or block |
| 03 | **Blast Radius** | Pre-execution downstream impact map. High-impact actions force approval |
| 04 | **Approval** | Approver identity and written reason required. Break-glass server-enforced, reason-required, audit-logged |
| 05 | **Execute** | Dispatch through governed fleet agent. Rollback snapshot captured before mutation |
| 06 | **Verify** | Post-action verification. Failed verification holds intent in `verification_pending` for operator review |

Approved intents continue through the actual execution path — they do not stop at the approval gate. Break-glass respects policy packs that disable break-glass.

`ExecutionIntent` stores policy decision, typed action, approval metadata, break-glass metadata, rollback metadata, blast-radius estimate, verification result, and response payload — fully audit-ready.

Database-change rollback supports snapshot capture for supported SQL mutations. The rollback endpoint creates rollback intents and attempts to derive rollback commands.

---

## 10. Fleet Management

The fleet plane manages every target node — Linux servers, Kubernetes clusters, and industrial OT machines — through a single control plane and a single governance model.

Relevant pieces:

- [genai/models.py](./genai/models.py) — `Target`, `TargetProfile`, `FleetAgent`, `TargetPolicyProfile`
- [genai/views.py](./genai/views.py) — `/genai/fleet/onboarding/...`, `/genai/fleet/enroll/...`, `/genai/fleet/install/...`
- [agent](./agent) — agent runtime

### 10.1 Linux Server Enrollment

```text
1. Operator creates an onboarding request with host, user, and PEM key.
2. Control plane validates SSH reachability.
3. Control plane runs a generated Linux bootstrap script remotely.
4. The host installs aiops-agent, OpenTelemetry Collector, and node_exporter.
5. The host enrolls back into Fleet with token-based registration.
6. Periodic heartbeat reports component health and discovered host-side services.
```

When the customer application is running in Docker on a Linux host, the target remains host-centric — Docker becomes a discovered runtime attribute, containers become discovered workloads underneath the host target. No separate cluster onboarding is required for Docker-on-Linux.

### 10.2 Kubernetes Cluster Agent

Kubernetes uses cluster registration rather than SSH login. The cluster agent install delivers:

- namespace, node, deployment, statefulset, daemonset, and ingress discovery
- pod-level metrics collection
- command polling and execution for diagnostics and safe restart actions
- RBAC-scoped API access (no kubeconfig copy-out)

Assets are under `deploy/helm/` and `agent/`.

### 10.3 OT Machine Support

Industrial targets running OPC-UA, MTConnect, Modbus TCP, or MQTT enroll alongside IT fleet nodes in the same control plane with the same governance model. The control plane treats them as discovered targets with constrained command surfaces.

### 10.4 Policy Push and Heartbeat

`TargetPolicyProfile` controls collection intervals, log sources, allowed commands, and execution permissions per target. Missing heartbeats surface immediately in the fleet dashboard with last-seen timestamps.

---

## 11. Signal Analytics

Implementation: [genai/views_analytics.py](./genai/views_analytics.py).

Two views:

- **Signal Heatmap** — services × time-bucket alert density matrix. DB-aggregated via `TruncHour` / `TruncDay` / `TruncMinute`. Color-encoded by count and peak severity. Time-range picker (1h / 6h / 24h / 7d). The heatmap queries `IncidentAlert` (full per-firing history), not `AlertEvent` (upsert summary).
- **Correlated Timeline** — unified event stream across alerts, incidents, and execution intents on a shared time axis with swim lanes. Quadratic Bézier connectors link events by `incident_key`. D3 brush zoom. Break-glass highlighting.

Both views are tenant-scoped, DB-aggregated (no Python loops over large querysets), capped against runaway queries, and auto-refresh on a 30-second interval via React Query. Cross-linking: clicking a heatmap cell filters the timeline to that service; clicking a timeline event surfaces an "Open Incident" action strip.

---

## 12. Integrations

Implementation: [genai/integrations](./genai/integrations), [genai/integration_writeback.py](./genai/integration_writeback.py).

The integration framework supports observability ingest **and** outbound writeback to ITSM, notification, DevOps, cloud, and code providers.

| Category | Providers |
|---|---|
| **Observability** | Prometheus, VictoriaMetrics, Grafana, Splunk, Elasticsearch, OpenSearch, Loki, Datadog, Dynatrace, New Relic, Jaeger, Tempo, InfluxDB, PagerDuty, OpsGenie, Alertmanager |
| **ITSM / Notify / DevOps** | ServiceNow, Jira, Slack, Microsoft Teams, GitHub, GitLab, Bitbucket, Jenkins, Argo CD, Flux CD, Kubernetes, Nagios |
| **Industrial / OT** | OPC-UA, MTConnect, Modbus TCP, MQTT, OSIsoft PI, PROFINET, DNP3, EtherNet/IP |
| **Cloud** | AWS CloudWatch, Azure Monitor, GCP Operations, AWS X-Ray, Azure Sentinel, GCP BigQuery, AWS OpenSearch, Azure Log Analytics |

Integration writeback is **conditional** — only configured, enabled integrations are called. If only ServiceNow is configured, the platform does not attempt to create PagerDuty / Jira / etc. tickets. Health is verified by a recurring `integration-health` cron container in Compose and a CronJob in Helm.

---

## 13. Predictor

Implementation: [predictor service in docker-compose.yml](./docker-compose.yml), prediction models in [genai/models.py](./genai/models.py).

The predictor surfaces forward-looking risk signals — saturation indicators, anomaly forecasts, and pre-incident likelihood scores — alongside the live incident view. The predictor uses the same startup migration path as the rest of the stack.

---

## 14. Frontend Surfaces

### 14.1 Operator Console

- [frontend](./frontend) — React 19, Vite, TanStack Query, D3

Main routes:

- alerts, incidents, investigations
- topology and component detail
- code context graph
- fleet (Linux, Kubernetes, OT)
- analytics (heatmap and correlated timeline)
- integrations
- predictor / intelligence
- tenant settings and member management

Key files:

- [frontend/src/App.tsx](./frontend/src/App.tsx)
- [frontend/src/pages/AssistantPage.tsx](./frontend/src/pages/AssistantPage.tsx)
- [frontend/src/pages/CodeContextPage.tsx](./frontend/src/pages/CodeContextPage.tsx)

### 14.2 Marketing Site

- [opsmitra-site](./opsmitra-site) — Next.js 15 + React 19 public-facing site

### 14.3 Legacy Django Templates

- [genai/templates](./genai/templates) — kept for compatibility; primary UI is the React console

---

## 15. Demo and Chaos Plane

The demo environment exists to produce realistic incident propagation across shared dependencies.

Components:

- frontend Nginx, gateway Nginx
- `app-orders`, `app-inventory`, `app-billing`
- demo Postgres
- Toxiproxy for controlled fault injection

Scripts:

- `demo/tools/run-demo-traffic.sh`
- `demo/tools/cut-db-traffic.sh`, `set-db-latency.sh`, `stress-db-connections.sh`
- `demo/tools/cut-gateway-traffic.sh`, `set-gateway-latency.sh`

The chaos plane produces shared-dependency failures, downstream blast-radius examples, realistic logs / traces / metrics, and reproducible failure paths suitable for validating code-aware investigation end-to-end. See [CHAOS_RUNBOOK.md](./CHAOS_RUNBOOK.md).

---

## 16. Data Lifecycle and Audit

- All operational records are tenant-owned and tenant-scoped.
- Tenant audit events are append-only at the Django model and signal layer.
- Incident timelines record diagnostic execution, remediation execution, policy blocks, approvals, rollback initiation, and generated artifacts.
- `ExecutionIntent` carries the full execution-path metadata for audit (policy decision, typed action, approval, break-glass, rollback, blast-radius, verification, response).
- Retention is configurable per-tenant. See [DATA_MEMORY_LIFECYCLE_DESIGN.md](./DATA_MEMORY_LIFECYCLE_DESIGN.md).

---

## 17. Design Positioning

The strongest production positioning:

> OpsMitra is a self-hosted AI incident control plane that works **beside** existing observability and ITSM tools, turns alerts into evidence-grounded investigations, maps failures back to runtime and code context, and executes remediations only through explicit policy, approval, audit, and rollback boundaries.

That positioning depends on five claims being true in the implementation:

1. **self-hosted** — Docker Compose for single-node installs, Helm chart for Kubernetes production.
2. **air-gapped AI** — inference is served by local `vLLM`, not an external SaaS endpoint.
3. **code-aware** — runtime entities are mapped back to repositories, handlers, spans, symbols, changes, and snippets through the Code Context Graph.
4. **controlled execution** — every remediation is mediated by EGAP — typed intent, policy, blast radius, approval, governed agent dispatch, rollback snapshot, post-verification.
5. **multi-tenant and audited** — tenant scoping enforced at the queryset layer; append-only audit events; full intent metadata captured.

These claims are supported by the codebase today.
