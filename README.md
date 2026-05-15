# OpsMitra

**The self-hosted AI incident control plane that runs entirely inside your network.**

OpsMitra traces live incidents from runtime telemetry all the way into your source code — handler, route, span, and recent commit — then executes governed remediation through a policy-gated execution pipeline. No cloud AI. No data egress. Ever.

Built for teams in manufacturing, finance, defence, healthcare, and regulated enterprise where SaaS AIOps is not an option.

---

## Why OpsMitra

Most observability copilots stop at summarizing dashboards. OpsMitra is built for the harder operational loop:

1. **Ingest** alerts from any Alertmanager-compatible source
2. **Correlate** related events into incidents with full lifecycle tracking
3. **Investigate** with multi-step streaming RCA — evidence collected, hypotheses scored, code path traced in real time
4. **Explain** in plain language, grounded in handler code, spans, commits, and blast radius
5. **Remediate** through `EGAP` — six gates between intent and execution
6. **Verify** the outcome and store the investigation as durable, audited evidence

Three capabilities the market does not combine in one product:

| | OpsMitra | SaaS AIOps |
|---|---|---|
| Air-gapped, no data egress | ✓ | ✗ |
| Code-aware RCA (handler/route/span/commit) | ✓ | ✗ |
| Policy-gated, audited remediation | ✓ | partial |

---

## Core Protocols

OpsMitra ships four architectural primitives that no other platform combines:

- **EGAP** — Execution &amp; Governance Action Protocol. Every action passes through typed intent → policy → blast radius → approval → execute → verify.
- **MCP** — Model Context Protocol. 18 structured tools that give the local LLM typed access to incidents, topology, metrics, logs, traces, code ownership, deployments, and blast radius.
- **AIP** — Alert Ingest Pipeline. Normalizes Alertmanager payloads, dedupes by lifecycle key, correlates alerts to incidents without losing per-alert tracking.
- **CCG** — Code Context Graph. Maps services to repos, routes to handlers, trace spans to source symbols, and deployments to recent commits.

---

## Repository Layout

```
.
├── aiops_platform/       # Django settings, routing, ASGI
├── genai/                # Core backend: EGAP, MCP, alert pipeline, investigations, policy
│   ├── egap_protocol.py
│   ├── policy_engine.py
│   ├── alert_pipeline.py
│   ├── investigation_streams.py
│   ├── code_context_*.py
│   ├── mcp_*.py
│   └── integrations/     # Provider adapters
├── frontend/             # React 19 operator console (Vite)
├── opsmitra-site/        # Public marketing site (Next.js 15)
├── agent/                # Fleet agent for Linux/Kubernetes/OT enrollment
├── predictor/            # Prediction engine deployment
├── deploy/               # Helm chart and Kubernetes assets
├── doc_search/           # Runbook and documentation indexing
├── docker-compose.yml    # Single-node deployment
└── manage.py
```

---

## Architecture

```
┌─────────────────────┐    ┌─────────────────────┐
│  Signals            │ →  │  Runtime Context    │
│  Logs · Metrics ·   │    │  Topology ·         │
│  Traces · Alerts ·  │    │  Incidents ·        │
│  OT                 │    │  Blast Radius       │
└─────────────────────┘    └─────────────────────┘
           ↓                          ↓
┌─────────────────────┐    ┌─────────────────────┐
│  Code Context (CCG) │ →  │  OpsMitra Reasoning │
│  Repos · Routes ·   │    │  RCA · Risk ·       │
│  Spans · Commits    │    │  Runbooks · Plans   │
└─────────────────────┘    └─────────────────────┘
           ↓                          ↓
┌─────────────────────┐    ┌─────────────────────┐
│  Governance (EGAP)  │ →  │  Outcome            │
│  Policies ·         │    │  Safe Remediation · │
│  Approvals · Audit  │    │  Verification ·     │
│  · Rollback         │    │  Fleet              │
└─────────────────────┘    └─────────────────────┘
```

Every layer runs on your infrastructure. The control plane never phones home.

---

## Quick Start

### Docker Compose (single-node trial)

```bash
git clone <your-repo-url> opsmitra
cd opsmitra

# Configure environment
cp .env.example .env
# Edit .env — at minimum set:
#   SECRET_KEY, AGENT_SECRET_TOKEN, AIOPS_INTENT_SIGNING_SECRET
#   VLLM_BASE_URL (your local vLLM endpoint)

# Start the stack
docker compose up -d

# Stack includes:
#   - web (Django backend, port 8000)
#   - frontend-app (React UI, port 5173)
#   - predictor (prediction engine)
#   - db (Postgres), redis, otel-collector
#   - prometheus, vmalert, alertmanager
#   - jaeger, elasticsearch, grafana
#   - db-agent, control-agent (fleet agents)
```

Open `http://localhost:5173`. Default tenant and admin are bootstrapped via the `db-init` service.

### Kubernetes (Helm)

```bash
cd deploy/helm

# Review and edit values
cp values.yaml my-values.yaml
# Set: ingress host, secret references, vLLM endpoint,
#      Postgres/Redis connection details, resource requests

helm install opsmitra . -f my-values.yaml --namespace opsmitra --create-namespace
```

See `deploy/KUBERNETES_DEPLOYMENT.md` for production guidance.

---

## Operator Capabilities

| Surface | What it does |
|---|---|
| **Alert Intelligence** | Suppression rules, maintenance windows, dedupe, correlation, noise stats |
| **Incident Command** | Lifecycle tracking, timeline, generated runbooks, SLA acknowledgement, archive/restore |
| **Streaming Investigations** | Multi-step RCA with live evidence collection and hypothesis scoring |
| **Code Context Graph** | Repo · route · handler · span · symbol mapping; recent-commit correlation |
| **Change Risk Analysis** | Pre-execution blast radius estimation maps downstream owners |
| **Signal Analytics** | Service × time-bucket heatmaps, correlated timelines with brush zoom |
| **Prediction Engine** | Forward-looking risk and saturation signals |
| **Safe Remediation** | EGAP-gated execution with approval, break-glass, rollback, post-verification |
| **Fleet Management** | Linux server, K8s cluster, and OT machine enrollment |
| **Audit Lifecycle** | Tenant audit events, append-only incident timeline, data retention policies |

---

## Integrations

**Observability** — Prometheus, VictoriaMetrics, Grafana, Splunk, Elasticsearch, OpenSearch, Loki, Datadog, Dynatrace, New Relic, Jaeger, Tempo, InfluxDB, PagerDuty, OpsGenie, Alertmanager.

**ITSM, DevOps &amp; Notify** — ServiceNow, Jira, Slack, Microsoft Teams, GitHub, GitLab, Bitbucket, Jenkins, Argo CD, Flux CD, Kubernetes, Nagios.

**Industrial / OT** — OPC-UA, MTConnect, Modbus TCP, MQTT, OSIsoft PI, PROFINET, DNP3, EtherNet/IP.

**Cloud** — AWS CloudWatch, Azure Monitor, GCP Operations, AWS X-Ray, Azure Sentinel, GCP BigQuery, AWS OpenSearch, Azure Log Analytics.

Incident writeback is conditional — only configured integrations are called. If only ServiceNow is configured, it will not try to create PagerDuty or Jira tickets.

---

## Security &amp; Governance

- **Multi-tenant RBAC** with six roles, tenant audit events at the Django model/signal layer
- **EGAP policy packs** with environment-aware controls and per-action allowlists
- **Approval tokens** with required approver identity and reason
- **Break-glass** enforced server-side, reason-required, audit-logged
- **Rollback snapshots** captured before SQL mutations and supported infrastructure changes
- **Post-action verification** holds remediation in `verification_pending` until confirmed
- **Append-only audit trail** for tenant, integration, execution, fleet, and operator actions

See `ARCHITECTURE.md` for design details.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Django 5, Django REST Framework, Channels (ASGI) |
| Database | PostgreSQL 16 |
| Cache &amp; queues | Redis / Valkey |
| AI inference | vLLM (BYOL — any vLLM-compatible model) |
| Operator UI | React 19, Vite, TanStack Query, D3 |
| Marketing site | Next.js 15, React 19, TypeScript |
| Telemetry | OpenTelemetry Collector, Prometheus, VictoriaMetrics, Jaeger, Elasticsearch, Filebeat |
| Deployment | Docker Compose, Helm chart |

---

## Configuration Highlights

Production-critical environment variables:

```bash
SECRET_KEY=...                       # Django secret
AGENT_SECRET_TOKEN=...               # Fleet agent enrollment
MCP_INTERNAL_TOKEN=...               # MCP server auth
AIOPS_INTENT_SIGNING_SECRET=...      # EGAP intent signing

DATABASE_URL=postgres://...          # Managed Postgres recommended in prod
REDIS_URL=redis://...                # Managed Redis or in-cluster

VLLM_BASE_URL=http://vllm:8000       # Your local vLLM endpoint
VLLM_MODEL=...                       # Model id

DJANGO_ALLOWED_HOSTS=opsmitra.example.com
CSRF_TRUSTED_ORIGINS=https://opsmitra.example.com
```

See `deploy/README.md` and `deploy/KUBERNETES_DEPLOYMENT.md` for full reference.

---

## Documentation

| Document | Purpose |
|---|---|
| `ARCHITECTURE.md` | System design and component boundaries |
| `CODE_CONTEXT_ENGINE_PLAN.md` | Code Context Graph design |
| `AGENT_POLICY_AND_RUNTIME_DESIGN.md` | EGAP and agent runtime |
| `INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md` | Integration framework |
| `DATA_MEMORY_LIFECYCLE_DESIGN.md` | Retention and lifecycle |
| `CHAOS_RUNBOOK.md` | Failure-mode validation |
| `deploy/KUBERNETES_DEPLOYMENT.md` | Helm install and upgrade |

---

## Positioning

> OpsMitra is a self-hosted AI incident control plane that works **beside** existing observability and ITSM tools, turns alerts into evidence-grounded investigations, maps failures back to runtime and code context, and executes remediations only through explicit policy, approval, audit, and rollback boundaries.

It is not a replacement for enterprise observability suites on day one. The strongest initial wedge is regulated or privacy-sensitive teams that want local AI-assisted incident investigation and controlled remediation without sending telemetry, logs, traces, code context, or remediation decisions to an external SaaS copilot.

---

## License

Proprietary. All rights reserved.

---

## Contact

For demos, pilots, and partnership inquiries: **hello@opsmitra.ai**
