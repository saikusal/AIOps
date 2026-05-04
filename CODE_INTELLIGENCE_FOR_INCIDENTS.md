# Code Intelligence for Incidents

## Goal

Close the current gap between runtime incident analysis and source-code understanding by integrating GitNexus as the code intelligence backend for AIOps.

Today the platform can:

- detect and correlate incidents
- investigate with metrics, logs, traces, and runbooks
- apply policy-aware remediation flows
- learn from outcomes

What it still cannot do reliably is:

- map an incident to the exact code paths most likely responsible
- identify the likely owning repository, module, handler, or job
- explain runtime failures in terms of source-level architecture
- connect recent code changes or deployments to the active incident

This document proposes a phased architecture that uses GitNexus as an external code intelligence provider instead of building a full source-code graph engine inside AIOps.

## Why GitNexus

GitNexus already provides the hard part of this problem:

- repository indexing
- structural code graph generation
- dependency and call-chain awareness
- MCP and HTTP-accessible code intelligence
- impact and context style queries over indexed repositories

The AIOps platform should not duplicate that work unless there is a clear product or deployment reason to do so.

The cleaner split is:

- AIOps owns incidents, observability, policy, workflow, remediation, and learning
- GitNexus owns repository indexing and code intelligence retrieval

This keeps responsibilities clear and reduces implementation risk.

## Problem Statement

In practice, incident response requires answers to questions like:

- Which repository owns this failing service?
- Which handler serves this failing route?
- Which code path matches this trace span?
- Which worker consumes this failing queue or topic?
- Which recent deploy or commit touched the affected execution path?
- What is the probable blast radius if this module is failing?

The platform already has strong runtime evidence, but runtime-only evidence is not enough to pinpoint root cause with high precision. We need a code-context layer that joins runtime entities with code entities.

## Target Outcome

During an investigation, the system should be able to move through this chain:

1. Incident identifies the affected service, route, host, span, or deployment.
2. Runtime-to-code mappings identify the relevant repository, module, and symbols.
3. Code intelligence retrieves ownership, entrypoints, related dependencies, and recent changes.
4. The investigation pipeline combines runtime and code evidence.
5. The final response points operators to the most likely code area, owner, and change window.

## Guiding Principles

- Do not build a full GitNexus clone before solving the join problem.
- Prefer typed MCP tools over large prompt stuffing.
- Treat code intelligence as an evidence provider, not a replacement for runtime analysis.
- Start with the stack patterns we actually operate: services, HTTP routes, workers, queues, spans, and deployment versions.
- Keep ingestion incremental and configurable. Do not hard-code repo-specific behavior.

## Architecture Overview

Add a GitNexus-backed code-context layer with three parts:

1. GitNexus backend for code graph indexing and retrieval
2. Runtime-to-code mapping models inside AIOps
3. Adapter MCP retrieval tools inside AIOps investigations

### 1. GitNexus Backend

GitNexus should be operated as the code intelligence engine.

Responsibilities:

- index repositories
- maintain repository-level structural graph
- answer code context questions through MCP or HTTP bridge
- expose blast radius, context, route maps, and related symbol information

AIOps should treat GitNexus as an external dependency, similar to how it treats metrics, logs, and traces backends.

### 2. Runtime-to-Code Join Layer in AIOps

This layer maps runtime entities into code entities.

Key joins:

- service name -> repository and module
- application name -> repository and module
- route or endpoint -> controller or handler
- trace span name -> function, method, or handler
- queue or topic -> producer and consumer code
- deployment version -> commit SHA or release identifier
- DB signature or query family -> owning module

### 3. Adapter MCP Retrieval Layer

AIOps should expose its own typed `code.*` tools to the investigation layer, but internally those tools will adapt to GitNexus queries and AIOps mappings.

This is important because the investigation layer should depend on stable AIOps contracts, not directly on GitNexus tool names.

Proposed AIOps adapter tool namespace:

- `code.find_service_owner`
- `code.route_to_handler`
- `code.span_to_symbol`
- `code.find_related_symbols`
- `code.recent_changes_for_component`
- `code.find_recent_deployments`
- `code.blast_radius`
- `code.queue_to_consumers`
- `code.db_access_map`
- `code.find_owner_contacts`

Internally, these tools will combine:

- AIOps runtime-to-code mappings
- GitNexus code graph queries
- optional Git metadata or deployment metadata from AIOps

## Proposed Data Model

These models should live in `genai/models.py` initially. They are still needed even with GitNexus, because GitNexus does not know our runtime entities by default.

### Repository

- `name`
- `url`
- `default_branch`
- `provider`
- `external_id`
- `is_active`
- `metadata`

### CodeService

- `name`
- `repository`
- `environment_scope`
- `team_name`
- `entrypoint_path`
- `metadata`

### CodeModule

- `repository`
- `service`
- `name`
- `path`
- `module_type`
- `metadata`

### CodeSymbol

- `repository`
- `module`
- `service`
- `symbol_type`
- `qualified_name`
- `display_name`
- `file_path`
- `line_start`
- `line_end`
- `language`
- `metadata`

### RouteCodeMapping

- `repository`
- `service`
- `http_method`
- `route_pattern`
- `handler_symbol`
- `module`
- `metadata`

### TraceCodeMapping

- `service`
- `span_name`
- `span_pattern`
- `symbol`
- `confidence`
- `metadata`

### QueueCodeMapping

- `service`
- `queue_name`
- `mapping_type`
- `symbol`
- `module`
- `metadata`

### ServiceCodeMapping

- `service_name`
- `application_name`
- `repository`
- `module`
- `team_name`
- `ownership_confidence`
- `metadata`

### DeploymentCodeMapping

- `service`
- `environment`
- `version`
- `commit_sha`
- `repository`
- `deployed_at`
- `metadata`

### CodeChangeRecord

- `repository`
- `commit_sha`
- `author`
- `title`
- `changed_files`
- `changed_symbols`
- `committed_at`
- `metadata`

## Evidence Flow During Investigation

Current investigation flow is:

1. determine scope
2. gather incident, topology, metrics, logs, traces, runbooks
3. assess evidence
4. ask LLM for grounded answer

Target enriched flow:

1. determine scope
2. gather incident, topology, metrics, logs, traces, runbooks
3. derive runtime code hints
4. call AIOps `code.*` adapter MCP tools
5. merge code evidence with runtime evidence
6. assess support vs contradiction
7. ask LLM for grounded answer including likely code area and recent change window

## Runtime Code Hints

Investigation should derive lookup hints from existing evidence:

- incident service name
- application name
- route path from logs or trace attributes
- span name from traces
- deployment version from alert labels or service metadata
- queue or topic from logs or worker traces
- SQL error signatures from logs

These hints become the inputs to code-context MCP tools.

## AIOps Adapter Contracts

All responses should be typed and compact.

### `code.find_service_owner`

Input:

- `service_name`
- `application_name`

Output:

- `repository`
- `service`
- `team_name`
- `ownership_confidence`
- `entrypoints`
- `notes`

### `code.route_to_handler`

Input:

- `service_name`
- `route`
- `http_method`

Output:

- `handler_symbol`
- `module_path`
- `repository`
- `related_symbols`
- `confidence`

### `code.span_to_symbol`

Input:

- `service_name`
- `span_name`

Output:

- `symbol`
- `module_path`
- `repository`
- `confidence`
- `matched_by`

### `code.recent_changes_for_component`

Input:

- `repository`
- `module_path`
- `service_name`
- `hours`

Output:

- `changes`
- `authors`
- `commit_shas`
- `risk_summary`

### `code.blast_radius`

Input:

- `repository`
- `symbol`

Output:

- `upstream_callers`
- `downstream_dependencies`
- `affected_routes`
- `affected_jobs`
- `risk_level`

## GitNexus Integration Model

GitNexus should remain a separate service or sidecar, not merged into the Django application.

Recommended deployment model:

- AIOps platform runs as it does today
- GitNexus indexes selected repositories separately
- AIOps stores references from services and applications to indexed repositories
- AIOps adapter services call GitNexus over MCP or HTTP bridge

This separation avoids mixing:

- Python incident orchestration concerns
- Node and Tree-sitter code indexing concerns

## Mapping GitNexus Capabilities to AIOps Needs

GitNexus already has concepts and tools that are close to what we need.

### GitNexus capability -> AIOps adapter

- GitNexus `context` -> `code.find_related_symbols`
- GitNexus `impact` -> `code.blast_radius`
- GitNexus `route_map` -> `code.route_to_handler`
- GitNexus `query` -> fallback search for route, symbol, or module matches
- GitNexus `detect_changes` -> `code.recent_changes_for_component`
- GitNexus `api_impact` -> route blast-radius enrichment

Some AIOps needs still require local mapping and enrichment:

- `code.find_service_owner`
  - requires service-to-repo ownership data from AIOps
- `code.span_to_symbol`
  - requires span naming conventions and local mapping rules
- `code.find_recent_deployments`
  - requires deployment records from AIOps or CI/CD integration
- `code.find_owner_contacts`
  - requires team or service ownership metadata

## Rollout Plan

## Phase 1: Ownership and Mapping Foundation

Deliverables:

- GitNexus integration settings
- repository and service metadata models
- `ServiceCodeMapping`
- `RouteCodeMapping`
- `TraceCodeMapping`
- `DeploymentCodeMapping`
- admin visibility for mappings
- read-only AIOps adapter tools:
  - `code.find_service_owner`
  - `code.route_to_handler`
  - `code.span_to_symbol`
  - `code.find_recent_deployments`

Primary value:

- identify likely repo and handler during incidents

## Phase 2: Change Intelligence

Deliverables:

- ingest commit metadata and changed files
- `CodeChangeRecord`
- adapter tools:
  - `code.recent_changes_for_component`
  - `code.find_owner_contacts`

Primary value:

- answer whether a recent change likely caused the incident

## Phase 3: Dependency and Blast Radius

Deliverables:

- module and symbol graph
- GitNexus-backed call and dependency retrieval
- adapter tools:
  - `code.find_related_symbols`
  - `code.blast_radius`
  - `code.queue_to_consumers`
  - `code.db_access_map`

Primary value:

- identify broader impact and better remediation choices

## Phase 4: Investigation and UI Integration

Deliverables:

- enrich investigation pipeline with code-context retrieval
- show code evidence in incident and investigation UI
- expose:
  - likely repo
  - likely module
  - likely handler
  - recent deploys
  - recent changes
  - owner or team
  - blast radius

Primary value:

- operators can move directly from incident to likely code area

## Ingestion Strategy

Start simple.

Initial ingestion sources:

- Git provider APIs or exported metadata
- service catalog or internal ownership metadata
- deployment metadata from CI/CD or release records
- route manifests or framework introspection where available
- OpenTelemetry span naming conventions
- manually curated mappings for critical services
- GitNexus indexed repository metadata

Avoid rebuilding universal source parsing in AIOps. GitNexus should carry that responsibility. The first win comes from accurate joins and adapter logic, not duplicating parser sophistication.

## How This Fits the Current Platform

This proposal fits the existing architecture cleanly.

Current components already in place:

- MCP retrieval layer
- investigation orchestrator
- tool invocation audit
- multi-step investigation workflow
- policy engine
- execution safety and learning layers

Integration points:

- add `code-context-mcp` adapter tools alongside existing MCP tools
- extend investigation orchestration to request code evidence when service, route, span, or deployment hints exist
- store code retrieval audit using existing `ToolInvocation`
- extend operations and investigations dashboards with code-context visibility

## Changes Required in This Repo

### New models

Add initial code intelligence models in `genai/models.py`.

### New services

Add:

- `genai/code_context_services.py`
- `genai/code_context_types.py`
- `genai/code_context_ingestion.py`
- `genai/gitnexus_client.py`

### MCP support

Add:

- `code.*` tool registrations in `genai/mcp_orchestrator.py`
- code-context handlers in `genai/mcp_services.py`
- optional HTTP endpoints under `/genai/mcp/code/...`

### Investigation integration

Update:

- `genai/tools/investigation.py`

Add conditional retrieval rules:

- if service in scope -> lookup owner and module
- if route in evidence -> map to handler
- if span in evidence -> map to symbol
- if deployment version exists -> fetch recent deployment and changes

### UI integration

Update incident and investigation views to surface:

- likely repo
- likely module
- likely handler
- likely owner
- recent deploy
- recent changes

## Risks and Constraints

### Risk: poor naming consistency

If service names, route names, and span names are inconsistent, mapping quality will be weak.

Mitigation:

- introduce confidence scores
- support manual overrides
- start with critical services

### Risk: GitNexus integration assumptions do not match our stack

GitNexus may not directly answer every runtime mapping question out of the box.

Mitigation:

- put an adapter layer in AIOps
- keep service, span, route, and deployment mappings local
- use GitNexus for structural retrieval, not as a replacement for runtime identity mapping

### Risk: stale code mappings

Mappings drift after releases or refactors.

Mitigation:

- support periodic sync
- track freshness timestamps
- flag stale mappings in UI

## Recommendation

Build this in a narrow, high-value sequence:

1. integrate GitNexus as an external code intelligence backend
2. add local service, route, span, and deployment mappings
3. add AIOps adapter MCP tools for owner and handler lookup
4. enrich investigations with code evidence
5. add recent change and blast-radius retrieval through GitNexus-backed adapter logic

That sequence closes the main incident-to-code gap without requiring AIOps to build and maintain a full dedicated code intelligence engine.

## Proposed First Implementation Slice

If we start implementation in this repo, the first slice should be:

1. add GitNexus integration config and client
2. add mapping models and migration
3. add read-only adapter services
4. add `code.find_service_owner`, `code.route_to_handler`, `code.span_to_symbol`
5. add HTTP MCP endpoints for those tools
6. enrich `investigation.py` to fetch code context when hints are available
7. surface code evidence in the investigation response and dashboard

This is the smallest slice that materially improves root-cause precision.
