# AIOps Platform

> **Air-gapped AI Operations. Your data never leaves your infrastructure.**

An enterprise-grade, self-hosted AIOps observability and incident management platform powered by open-source LLMs running entirely within your own environment — no internet connection required, no data sent to third parties.

---

## The Core USP: Truly Air-Gapped AI

Most AI-powered observability tools require sending your operational data — logs, metrics, traces, incident details, error messages — to external cloud APIs. This creates:

- **Security exposure** — sensitive infrastructure telemetry transmitted to third-party services
- **Compliance risk** — violations of data residency, GDPR, PCI-DSS, or internal data classification policies
- **Dependency risk** — outages when the external AI service is unavailable
- **Egress cost** — continuous data transfer charges at scale

**This platform eliminates all of the above.**

The AI engine runs on your own hardware using **[Qwen2.5-7B-Instruct-AWQ](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-AWQ)** served locally via **[vLLM](https://github.com/vllm-project/vllm)**. Every inference call — incident RCA, blast radius analysis, remediation suggestions, post-mortem analysis — executes entirely within your network perimeter. Zero bytes of operational data leave the server.

---

## Dual-LLM Architecture: Local-First with Optional Fallback

All AI calls go through vLLM — a self-hosted, air-gapped inference server running Qwen2.5 on your GPU. No external API keys required, no data leaves the server.

| Mode | LLM | Internet Required | Data Leaves Server | GPU Required |
|---|---|---|---|---|
| `vllm` | Qwen2.5-7B-Instruct-AWQ | ❌ No | ❌ Never | ✅ Yes (A10G / similar) |

- All AI calls go to the local Qwen model running in a vLLM container on your GPU server. No network egress.
- The same call path (`query_llm()`) is used across all features: investigation, RCA, command analysis, remediation planning, post-mortem generation.

---

## What the Platform Does

Operators get a single workspace for the entire incident lifecycle:

| Capability | Description |
|---|---|
| **Correlated Incident Workspace** | Alerts correlated into incidents with timeline, graph view, and AI-generated RCA |
| **AI Investigation** | Ask free-form questions about any incident; AI fetches telemetry context and explains root cause |
| **Blast Radius Mapping** | Dependency graph-aware impact analysis across services, databases, and infrastructure |
| **Guided Remediation** | AI proposes concrete remediation commands; operators approve, and the control agent executes them |
| **Diagnostic Execution** | Run allowlisted diagnostic commands on remote agents with AI analysis of the output |
| **Post-Remediation Analysis** | Automated AI commentary on whether the remediation resolved the issue |
| **Predictions & Risk Scoring** | Service-level risk scoring and incident probability forecasting |
| **Document-Backed Guidance** | Upload runbooks; retrieval-augmented answers grounded in your own operational knowledge |
| **Revenue Impact Tracking** | Business impact calculation attached to every incident |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  YOUR NETWORK PERIMETER                  │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                    │
│  │  React UI    │───▶│  Django API  │                    │
│  │  (port 8089) │    │  (port 8000) │                    │
│  └──────────────┘    └──────┬───────┘                    │
│                             │                            │
│          ┌──────────────────┼──────────────────┐         │
│          │                  │                  │         │
│  ┌───────▼──────┐  ┌────────▼──────┐  ┌───────▼──────┐  │
│  │   vLLM +     │  │  Prometheus   │  │  PostgreSQL   │  │
│  │  Qwen2.5-7B  │  │  VictoriaM.   │  │  + Redis     │  │
│  │  (port 8001) │  │  Grafana      │  │               │  │
│  │  ← LOCAL AI  │  │  Jaeger       │  │               │  │
│  └──────────────┘  │  Elasticsearch│  └───────────────┘  │
│                    └───────────────┘                      │
│  ┌──────────────┐  ┌───────────────┐                      │
│  │ control-agent│  │   db-agent    │                      │
│  │ (port 9999)  │  │  (port 9998)  │                      │
│  └──────────────┘  └───────────────┘                      │
│                                                          │
│                    ← No egress. Ever. →                  │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Backend
- Python · Django · Django ORM · PostgreSQL · Redis (Valkey)

### AI / Inference Layer (Air-Gapped)
- **[vLLM](https://github.com/vllm-project/vllm)** — high-throughput LLM serving engine
- **[Qwen2.5-7B-Instruct-AWQ](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-AWQ)** — quantized open-source instruction model, 8K–32K context, runs on a single A10G (24 GB)
- AWQ 4-bit quantization — ~4–5 GB VRAM for weights, enabling 16K+ context on modest GPU hardware
- OpenAI-compatible API via vLLM — zero application-layer changes needed to switch models

### Investigation & Orchestration
- Prompt-based orchestration in `genai/`
- Document-backed retrieval in `doc_search/`
- Prediction workflows in `genai/predictions.py`
- Atomic cross-worker incident counters via Redis

### Frontend
- React · TypeScript · Vite · TanStack Query · React Router
- React Three Fiber / Three.js for dependency graph views

### Observability Stack
- Prometheus · VictoriaMetrics · Alertmanager · Grafana
- OpenTelemetry Collector · Jaeger (distributed tracing)
- Elasticsearch + Filebeat (log aggregation)
- node-exporter · postgres-exporter · nginx exporters

### Automation / Execution
- `control-agent` — Docker command execution (container restarts, status checks)
- `db-agent` — PostgreSQL diagnostics
- Allowlisted command execution with auth token enforcement

### Demo / Chaos
- Nginx frontend and gateway · Flask demo microservices
- Toxiproxy for fault injection · PostgreSQL

### Packaging / Runtime
- Docker · Docker Compose · Nginx

---

## Repository Layout

```text
aiops_platform/     Django project settings and app wiring
genai/              AI assistant, incidents, predictions, execution flows
  llm_backend.py    LLM abstraction layer (vLLM / Qwen)
doc_search/         Document upload, processing, and retrieval
frontend/           React frontend (Vite + TypeScript)
demo/               Demo application, chaos tooling, dependency graph
agent/              Secure execution agents and allowlists
  control-agent.Dockerfile
  agent_server.py
  control_allowed_commands.json
Observability/      Grafana provisioning and dashboards
filebeat/           Log shipping configuration
diagrams/           Architecture diagram sources
docker-compose.yml  Full stack orchestration
```

---

## Key Product Areas

### 1. Air-Gapped Investigation Assistant
Free-form AI chat grounded in live telemetry context (metrics, logs, traces, incident data). All inference runs locally. Includes revenue/business impact alongside technical RCA.

### 2. Correlated Incident Workspace
Alerts correlated into incidents enriched with timeline, dependency graph, blast radius, AI-generated root cause, and remediation recommendation — all locally computed.

### 3. Guided Remediation with Agent Execution
AI proposes remediation commands, operators approve, the `control-agent` executes them. Post-execution AI analysis confirms resolution. No human needs to SSH.

### 4. Application & Service Health
Service portfolios with component health scoring, AI insight summaries, prediction risk, and graph entry points.

### 5. Dependency Graph (3D)
Live topology graphs powered by React Three Fiber — application dependencies, incident blast radius, alert-linked graph traversal.

### 6. Predictions & Risk Scoring
Service-level anomaly risk scoring and incident probability forecasting.

### 7. Document-Backed Runbooks
Upload operational runbooks; the platform uses retrieval-augmented generation to answer operator questions grounded in your own documentation.

---

## Deployment

### Prerequisites

- Docker + Docker Compose
- NVIDIA GPU (A10G 24 GB recommended; any 16 GB+ VRAM Ampere/Ada GPU works) for `vllm` mode
- NVIDIA drivers + `nvidia-container-toolkit` installed on the host

### 1. Start vLLM (run once, separate from Compose)

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

> First run downloads ~4 GB from HuggingFace. After that, the model is cached in `~/.cache/huggingface` and vLLM starts in seconds.

### 2. Configure Environment

```bash
cp .env.example .env
```

**Minimum required values in `.env`:**

```bash
# --- LLM (vLLM / Qwen, air-gapped) ---
VLLM_API_URL=http://172.17.0.1:8001/v1/chat/completions   # Docker bridge IP → host vLLM
VLLM_MODEL_NAME=qwen32b
VLLM_MAX_TOKENS=4096
VLLM_MAX_MODEL_LEN=16384

# --- Core ---
POSTGRES_PASSWORD=your_secure_password
AGENT_SECRET_TOKEN=your_secure_agent_token
SSO_ENABLED=false   # set true + provide GOOGLE_CLIENT_ID/SECRET for SSO

# --- Public access (for EC2 / remote deployment) ---
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,<your-server-ip>
DJANGO_CSRF_TRUSTED_ORIGINS=http://<your-server-ip>:8000
AIOPS_PUBLIC_BASE_URL=http://<your-server-ip>:8000
```

### 3. Start the Platform

```bash
docker compose up -d --build
```

### Service URLs

| Service | URL |
|---|---|
| React UI | `http://localhost:8089` |
| Django backend | `http://localhost:8000` |
| Prometheus | `http://localhost:9090` |
| Alertmanager | `http://localhost:9093` |
| Grafana | `http://localhost:3000` |
| Demo app | `http://localhost:8088` |
| Jaeger | `http://localhost:16686` |

---

## Changing the vLLM Model

Update `VLLM_MODEL_NAME` and `VLLM_API_URL` in `.env` to point at a different model served by vLLM, then restart the `web` container — no rebuild required:
```bash
docker compose up -d --no-deps web
```

---

## Security Model

| Concern | How It Is Addressed |
|---|---|
| **Data egress** | In `vllm` mode, zero operational data leaves the server. All AI inference is local. |
| **Agent execution** | Commands are allowlisted in `agent/control_allowed_commands.json`. Only explicitly listed commands can run. |
| **Agent auth** | Every agent request requires a `Bearer` token (`AGENT_SECRET_TOKEN`). Unauthenticated requests are rejected with HTTP 401. |
| **Network isolation** | The compose stack uses internal Docker networks; only necessary ports are exposed. |
| **Model provenance** | Qwen2.5 is Apache 2.0 licensed. AWQ weights are sourced directly from HuggingFace under the same license. |

---

## Chaos and Demo

Chaos tooling lives under `demo/tools/`. Use it to inject faults and validate that the AIOps platform detects, correlates, and recommends correctly.

```bash
bash demo/tools/run-demo-traffic.sh      # simulate normal load
bash demo/tools/chaos-inject.sh          # inject failures
```

See [CHAOS_RUNBOOK.md](./CHAOS_RUNBOOK.md) for detailed scenarios.

---

## Architecture and Roadmaps

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [FRONTEND_MIGRATION_PLAN.md](./FRONTEND_MIGRATION_PLAN.md)
- [MCP_PHASE_PLAN.md](./MCP_PHASE_PLAN.md)
- [CHAOS_RUNBOOK.md](./CHAOS_RUNBOOK.md)

---

## Notes

- The internal Django project package has been renamed to `aiops_platform` to align with the product identity.
- `.env` is intentionally gitignored — never commit credentials.
- `172.17.0.1` is the default Docker bridge gateway IP. If your server uses a different bridge subnet, adjust `VLLM_API_URL` accordingly (`docker network inspect bridge | grep Gateway`).
- Local runtime data (Postgres volumes, media files, model cache) is gitignored.
