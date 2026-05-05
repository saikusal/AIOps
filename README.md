# AIOps Platform

> **Air-gapped, self-hosted, code-aware incident operations.**

This project is an AIOps control plane for teams that want AI-assisted incident investigation and remediation without sending telemetry or source context to external SaaS platforms.

The product pitch is simple:

- **Self-hosted**: runs inside your environment on your own infrastructure.
- **Air-gapped AI**: inference is served locally through `vLLM`.
- **Code-context aware**: incidents are grounded not only in metrics, logs, and traces, but also in repository ownership, route handlers, spans, symbols, recent commits, and source snippets.

## What Makes This Different

Most observability copilots can summarize dashboards. This platform is aimed at the next step:

1. ingest alerts and correlate incidents,
2. retrieve telemetry evidence,
3. map the failure back to code,
4. suggest the safest validation or remediation path,
5. optionally execute allowlisted actions through controlled agents.

The implemented stack already supports that story:

- local LLM inference in [genai/llm_backend.py](./genai/llm_backend.py)
- MCP-style investigation tooling in [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py)
- local code indexing and enrichment in [genai/code_context_ingestion.py](./genai/code_context_ingestion.py)
- runtime-to-code lookups in [genai/code_context_services.py](./genai/code_context_services.py)
- code-aware assistant and graph UX in [frontend/src/pages/AssistantPage.tsx](./frontend/src/pages/AssistantPage.tsx) and [frontend/src/pages/CodeContextPage.tsx](./frontend/src/pages/CodeContextPage.tsx)

## Core Capabilities

| Capability | What it does |
|---|---|
| **Incident correlation** | Groups related alerts into incidents with timeline, severity, blast radius, and investigation context. |
| **AI investigation** | Pulls metrics, logs, traces, runbooks, topology, and code context into a single grounded answer. |
| **Code-context awareness** | Resolves service ownership, route handlers, spans, related symbols, recent deployments, and recent commits. |
| **Source evidence retrieval** | Reads local source snippets and traceback-linked files for prompt grounding. |
| **Topology + blast radius** | Combines application dependency graph context with code blast radius and runtime impact. |
| **Guided remediation** | Produces typed actions and approval-aware remediation plans, then delegates execution to agents. |
| **Prediction + risk** | Tracks service risk scores and short-horizon incident probability. |
| **Runbook grounding** | Searches uploaded operational documents through `doc_search/`. |

## Architecture Summary

```text
┌──────────────────────────────── CUSTOMER NETWORK ────────────────────────────┐
│                                                                              │
│  Control Plane Host                                                          │
│       ├── React UI (frontend/, :8089)                                        │
│       ├── Django control plane (genai + doc_search, :8000)                   │
│       ├── PostgreSQL + Redis                                                 │
│       ├── Prometheus / Alertmanager / Jaeger / Elasticsearch                 │
│       ├── vLLM + Qwen (local inference, no telemetry egress)                 │
│       ├── control-agent / db-agent                                           │
│       └── Code-context engine                                                │
│           ├── local repository indexes                                       │
│           ├── service -> repo ownership                                      │
│           ├── route -> handler mapping                                       │
│           ├── span -> symbol mapping                                         │
│           └── recent commit / snippet enrichment                             │
│                                                                              │
│  Monitored Linux Servers                                                     │
│       ├── aiops-agent                                                        │
│       ├── OpenTelemetry Collector                                            │
│       ├── node_exporter                                                      │
│       ├── log shipping / discovery                                           │
│       └── optional Docker runtime                                            │
│           └── applications and containers                                    │
│                                                                              │
└────────────────────────────── No external AI calls ──────────────────────────┘
```

For the full write-up, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Repository Layout

```text
aiops_platform/     Django project settings and wiring
genai/              incidents, investigation flows, MCP services, remediation logic
doc_search/         document ingestion and retrieval
frontend/           React/Vite product UI
opsmitra-site/      Next.js marketing site
agent/              allowlisted remote execution agents
demo/               demo application, dependencies, and chaos tooling
Observability/      Grafana dashboards and provisioning
diagrams/           Mermaid and draw.io architecture sources
docker-compose.yml  stack orchestration
```

## Key Runtime Areas

### 1. Self-Hosted LLM Inference

All model calls are routed through `vLLM` using the OpenAI-compatible `/v1/chat/completions` interface.

- local endpoint configured by `VLLM_API_URL`
- local model name configured by `VLLM_MODEL_NAME`
- current backend implementation lives in [genai/llm_backend.py](./genai/llm_backend.py)

The main positioning is local reasoning on local data. No production telemetry needs to leave the environment to generate investigations, explanations, or remediation advice.

### 2. Code-Context Engine

The code-context layer is a first-class part of the product story, not a side feature.

It indexes local repositories into Django models such as:

- `RepositoryIndex`
- `ServiceRepositoryBinding`
- `RouteBinding`
- `SpanBinding`
- `DeploymentBinding`
- `CodeChangeRecord`
- `SymbolRelation`

That enables the platform to answer questions like:

- Which repository owns `app-orders`?
- Which handler likely serves `/health` or `/orders/create`?
- Which symbol matches a failing trace span?
- What changed recently on the suspected failure path?
- Which source files or related symbols are in the blast radius?

The implementation is in:

- [genai/code_context_ingestion.py](./genai/code_context_ingestion.py)
- [genai/code_context_services.py](./genai/code_context_services.py)
- [genai/mcp_services.py](./genai/mcp_services.py)
- [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py)

### 3. Investigation Orchestration

Investigation requests are routed through MCP-style internal tools that gather evidence from:

- incidents
- application topology
- metrics
- logs
- traces
- runbooks
- traceback-linked source
- code-context services

This allows the assistant to reason over curated evidence rather than raw unrestricted access.

### 4. Controlled Execution

Execution is separated from reasoning.

- the assistant proposes typed actions
- the policy layer decides what is allowed or requires approval
- `control-agent` and `db-agent` execute only allowlisted commands

Relevant code:

- [genai/policy_engine.py](./genai/policy_engine.py)
- [genai/execution_safety.py](./genai/execution_safety.py)
- [genai/typed_actions.py](./genai/typed_actions.py)
- [agent/agent_server.py](./agent/agent_server.py)

## Deployment

### Deployment Model

The current product shape is:

- **Today**: self-host the control plane on a customer Linux server using Docker Compose.
- **Today**: onboard customer Linux servers by installing collectors and an AIOps agent bundle over SSH.
- **Next**: package the control plane for Kubernetes-based customer environments.
- **Later**: add first-class Kubernetes onboarding for monitored customer clusters.

This means the product is already self-hosted and centralized, but the monitored estate can be much larger than the single host that runs the control plane.

### Prerequisites

- Docker + Docker Compose
- NVIDIA GPU for local `vLLM` serving
- `nvidia-container-toolkit` on the host

### 1. Start `vLLM`

Run the local model server separately from Compose:

```bash
docker run -d \
  --name vllm-qwen \
  --gpus all \
  --restart unless-stopped \
  -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct-AWQ \
  --quantization awq_marlin \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.90 \
  --served-model-name qwen32b \
  --trust-remote-code
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Minimum values to review:

```bash
POSTGRES_PASSWORD=change-me
AGENT_SECRET_TOKEN=replace-with-a-long-random-secret
VLLM_API_URL=http://172.17.0.1:8001/v1/chat/completions
VLLM_MODEL_NAME=qwen32b
AIOPS_CODE_CONTEXT_ENABLED=true
AIOPS_CODE_CONTEXT_PROVIDER=internal
AIOPS_CODE_CONTEXT_AUTO_ROOTS=/source
```

### 3. Start The Stack

```bash
docker compose up -d --build
```

### 4. Optional: Sync Code Context

If you have active repository indexes or mounted source roots, sync the local code-context database:

```bash
docker compose exec web python manage.py sync_code_context
```

For a single named repository:

```bash
docker compose exec web python manage.py sync_code_context --repository customer-portal-demo
```

## Fleet Onboarding

The implemented onboarding path is Linux-first.

- the control plane generates an enrollment token and Linux bootstrap command
- the bootstrap installs `OpenTelemetry Collector`, `node_exporter`, and the AIOps heartbeat/service bundle
- the target enrolls back into the control plane and starts periodic heartbeat reporting
- discovered target metadata is used to enrich fleet inventory and code-context registration

Relevant backend endpoints and logic:

- [genai/urls.py](./genai/urls.py)
- [genai/views.py](./genai/views.py)
- [genai/models.py](./genai/models.py)

## Docker Workloads On Linux Hosts

If the customer application runs as Docker containers on Linux servers, the onboarding model still starts at the Linux host.

- **Primary target**: the Linux server
- **Runtime on that target**: Docker
- **Workloads to discover**: containers, images, ports, health, and logs

The current implementation already supports Linux host enrollment and safe Docker-oriented remediation commands, but it does **not** yet perform full Docker workload auto-discovery during heartbeat. Today the heartbeat reports the installed host-side collectors back to Fleet.

The next step for Docker-aware discovery is:

1. inspect the local Docker runtime from the installed agent
2. enumerate running containers, image names, ports, labels, and health state
3. publish those containers as `discovered_services`
4. map container and service metadata into topology and code-context registration

That keeps the model simple:

- Docker on Linux is treated as a Linux target with an additional runtime discovery layer
- Kubernetes will be treated separately as a cluster-level onboarding path

## Main URLs

| Surface | URL |
|---|---|
| React product UI | `http://localhost:8089` |
| Django backend | `http://localhost:8000` |
| Assistant | `http://localhost:8089/genai` |
| Code Context Graph | `http://localhost:8089/code-context` |
| Alert dashboard | `http://localhost:8000/genai/alerts/dashboard/` |
| Incident dashboard | `http://localhost:8000/genai/incidents/dashboard/` |
| Demo app | `http://localhost:8088` |
| Prometheus | `http://localhost:9090` |
| Alertmanager | `http://localhost:9093` |
| Grafana | `http://localhost:3000` |
| Jaeger | `http://localhost:16686` |

## Chaos And Demo

The demo stack is designed to produce realistic failure propagation across shared dependencies.

Useful scripts in [demo/tools](./demo/tools):

- `run-demo-traffic.sh`
- `cut-db-traffic.sh`
- `set-db-latency.sh`
- `stress-db-connections.sh`
- `cut-gateway-traffic.sh`
- `set-gateway-latency.sh`
- `reset-db-proxy.sh`
- `reset-gateway-proxy.sh`

See [CHAOS_RUNBOOK.md](./CHAOS_RUNBOOK.md) for scenarios.

## Security Model

| Concern | Approach |
|---|---|
| **AI data egress** | Model inference is served locally through `vLLM`. |
| **Tool access** | The assistant works through explicit internal MCP-style services rather than unrestricted external access. |
| **Command execution** | Agents run allowlisted commands only. |
| **Execution approval** | Higher-risk actions pass through policy and approval tokens. |
| **Repository context** | Source code stays local; the code-context engine reads from indexed local paths. |

## Related Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [CHAOS_RUNBOOK.md](./CHAOS_RUNBOOK.md)
- [MCP_PHASE_PLAN.md](./MCP_PHASE_PLAN.md)
- [CODE_CONTEXT_ENGINE_PLAN.md](./CODE_CONTEXT_ENGINE_PLAN.md)
- [CODE_INTELLIGENCE_FOR_INCIDENTS.md](./CODE_INTELLIGENCE_FOR_INCIDENTS.md)
