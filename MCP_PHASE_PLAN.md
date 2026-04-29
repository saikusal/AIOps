# MCP Phase Plan

## Goal
Move from large prompt-context packaging toward a tool-driven retrieval model where the orchestration layer can fetch only the telemetry and operational data needed for the current investigation.

## Recommended Architecture

Client:
- React frontend

Orchestrator:
- Django `web` app

Tool layer:
- MCP servers for telemetry and operations data

Model layer:
- current AiDE integration first
- later swappable with local or alternate model gateways

## MCP Servers To Build First

### 1. `incidents-mcp`
Responsibilities:
- fetch recent incidents
- fetch incident timeline
- fetch incident graph
- fetch incident summary

### 2. `applications-mcp`
Responsibilities:
- fetch application overview
- fetch application graph
- fetch component health and predictions

### 3. `metrics-mcp`
Responsibilities:
- execute allowlisted metric queries
- fetch current series and aggregates
- support scoped queries by app/service/host

### 4. `logs-mcp`
Responsibilities:
- search Elasticsearch/OpenSearch logs
- return summarized hits
- filter by time range, host, service, severity

### 5. `traces-mcp`
Responsibilities:
- fetch Jaeger traces
- search recent failed or slow traces
- summarize trace evidence

### 6. `runbooks-mcp`
Responsibilities:
- search document/runbook corpus
- return relevant operational guidance

## Backend Integration Pattern

The Django app should remain the orchestrator and audit layer.

Pattern:
1. frontend asks Django
2. Django decides which MCP tools to invoke
3. Django sends compact, scoped tool results to the model
4. Django stores:
   - tool calls
   - parameters
   - latency
   - summarized results

This keeps:
- tenant isolation
- auditability
- rate limiting
- command approval policy

## Prompt Strategy After MCP

Keep only minimal prompt context:
- tenant/user scope
- current application
- current incident
- current service
- current user question

Everything else should be tool-derived on demand.

## Suggested Build Order

1. `incidents-mcp`
2. `applications-mcp`
3. `metrics-mcp`
4. `logs-mcp`
5. `traces-mcp`
6. `runbooks-mcp`

## First Production-Safe Rule

All MCP tools must be:
- tenant-aware
- read-only by default
- audited
- parameterized

Do not expose unrestricted query execution or unrestricted shell through MCP.

## Exit Criteria For Phase 2

Phase 2 is complete when:
- chatbot can investigate an incident using MCP-backed retrieval
- graph pages can load via graph APIs and MCP-backed data sources
- prompts no longer embed large raw observability blobs by default
- all MCP tool calls are logged and attributable
