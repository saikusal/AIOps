# GitNexus Integration Plan

## Objective

Integrate GitNexus into the AIOps platform as the code intelligence backend for incident investigation.

This integration should enable the platform to:

- connect incidents to relevant repositories and services
- identify likely handlers, modules, and symbols behind failing paths
- retrieve code-context evidence during investigations
- show recent changes and likely blast radius for affected components
- improve root-cause analysis with both runtime and code evidence

## System Boundary

### AIOps owns

- alerts and incidents
- metrics, logs, traces, and runbooks
- investigation orchestration
- policy and remediation safety
- action execution and verification
- learning, ranking, and dashboards

### GitNexus owns

- repository indexing
- repository-level structural graph
- code relationship lookup
- route, symbol, and impact context retrieval
- graph-backed code exploration

### AIOps adapter layer owns

- runtime-to-code mapping
- GitNexus client integration
- typed code-context contracts for investigations
- shaping GitNexus outputs into incident-friendly evidence

## Integration Model

GitNexus should run as a separate service.

Recommended model:

1. Repositories are indexed into GitNexus outside the Django app.
2. AIOps stores mappings from runtime services and applications to indexed repositories.
3. AIOps calls GitNexus through a client adapter.
4. Investigation flows request code evidence through AIOps `code.*` tools.
5. The LLM receives compact code-context evidence together with runtime evidence.

This keeps the platform modular and avoids merging a TypeScript code graph engine into the Python incident system.

## Deployment Options

## Option 1: Shared GitNexus Service

One GitNexus instance indexes multiple repositories.

Use when:

- internal platform deployment
- centrally managed repositories
- one control plane is acceptable

Pros:

- simpler operational model
- easier index management
- faster central rollout

Cons:

- stronger multi-tenant isolation requirements
- larger blast radius if misconfigured

## Option 2: Per-Customer GitNexus

Each customer or environment gets its own GitNexus instance.

Use when:

- strict tenant isolation is required
- customer repos cannot be centrally indexed
- air-gapped or sovereign deployments matter

Pros:

- stronger isolation
- better fit for regulated environments

Cons:

- more operational overhead
- per-tenant indexing lifecycle

## Recommended Starting Point

Start with Option 1 for internal rollout, but design the configuration model so Option 2 is possible later.

## Required Configuration

Add AIOps settings for GitNexus:

- `GITNEXUS_ENABLED`
- `GITNEXUS_BASE_URL`
- `GITNEXUS_API_TOKEN`
- `GITNEXUS_TIMEOUT_SECONDS`
- `GITNEXUS_DEFAULT_REPO_NAMESPACE`
- `GITNEXUS_TRANSPORT`
- `GITNEXUS_VERIFY_TLS`

Recommended defaults:

- disabled by default
- HTTP transport first
- token-based authentication

## Local AIOps Models Still Required

GitNexus cannot infer our runtime identity model by itself. AIOps still needs local mappings.

### RepositoryBinding

- `repository_name`
- `gitnexus_repo_id`
- `provider_url`
- `default_branch`
- `is_active`
- `metadata`

### ServiceRepositoryBinding

- `service_name`
- `application_name`
- `repository_binding`
- `team_name`
- `ownership_confidence`
- `metadata`

### RouteBinding

- `service_name`
- `http_method`
- `route_pattern`
- `repository_binding`
- `handler_hint`
- `metadata`

### SpanBinding

- `service_name`
- `span_name`
- `repository_binding`
- `symbol_hint`
- `confidence`
- `metadata`

### DeploymentBinding

- `service_name`
- `environment`
- `version`
- `repository_binding`
- `commit_sha`
- `deployed_at`
- `metadata`

These are not competitors to GitNexus. They are the runtime join layer needed to ask GitNexus the right questions.

## GitNexus Client

Add:

- `genai/gitnexus_client.py`

Responsibilities:

- manage auth and request transport
- translate AIOps requests into GitNexus requests
- normalize GitNexus responses
- handle timeouts, errors, and partial failures
- expose a small internal API to services

Suggested client methods:

- `query_repo_context(...)`
- `get_route_map(...)`
- `get_impact(...)`
- `detect_changes(...)`
- `search_symbols(...)`
- `get_related_context(...)`

## AIOps Adapter Contracts

Investigations should not depend directly on GitNexus tool names. Use stable AIOps contracts.

### `code.find_service_owner`

Purpose:

- determine which repository and team own the affected service

Input:

- `service_name`
- `application_name`

Output:

- `repository`
- `team_name`
- `ownership_confidence`
- `entrypoint_hints`

Primary source:

- AIOps local bindings

### `code.route_to_handler`

Purpose:

- map a failing route to likely handler code

Input:

- `service_name`
- `route`
- `http_method`

Output:

- `repository`
- `handler`
- `module_path`
- `confidence`
- `supporting_context`

Primary sources:

- AIOps route binding
- GitNexus route map or context query

### `code.span_to_symbol`

Purpose:

- map trace span names to likely source symbols

Input:

- `service_name`
- `span_name`

Output:

- `repository`
- `symbol`
- `module_path`
- `confidence`
- `matched_by`

Primary sources:

- AIOps span binding
- GitNexus symbol search or context query

### `code.recent_changes_for_component`

Purpose:

- identify whether recent code changes likely touched the affected area

Input:

- `repository`
- `module_path`
- `symbol`
- `hours`

Output:

- `recent_changes`
- `authors`
- `commit_shas`
- `risk_summary`

Primary sources:

- GitNexus change detection
- local deployment binding if available

### `code.blast_radius`

Purpose:

- estimate what else may be affected by the failing component

Input:

- `repository`
- `symbol`
- `route`

Output:

- `upstream_callers`
- `downstream_dependencies`
- `affected_paths`
- `risk_level`

Primary source:

- GitNexus impact or context retrieval

## Incident-to-Code Lookup Flow

## Step 1: Runtime scope is identified

Investigation starts with:

- incident key
- service name
- application name
- route or endpoint
- span names
- deployment version
- logs or trace hints

## Step 2: AIOps resolves repository bindings

Use local bindings to find:

- repository candidate
- team owner
- matching route binding
- matching span binding

## Step 3: AIOps queries GitNexus

Use binding context to ask GitNexus for:

- route map details
- symbol context
- related module context
- change history
- blast radius

## Step 4: AIOps normalizes code evidence

Code evidence should be compact and incident-shaped:

- likely repository
- likely module
- likely handler or symbol
- recent change candidates
- likely owner
- likely blast radius

## Step 5: Investigation merges runtime and code evidence

Runtime evidence:

- metrics
- logs
- traces
- runbooks
- topology

Code evidence:

- owner
- module
- handler
- recent changes
- blast radius

## Step 6: LLM gets a compact combined evidence pack

The LLM should receive:

- user question
- incident scope
- condensed runtime evidence
- condensed code evidence
- contradiction notes
- expected structured response schema

## Step 7: Response surfaces likely code cause

Final investigation answer should include:

- likely failing component
- suspected code location
- recent change window
- owner or team
- next verification step

## Investigation Prompt Enrichment

Add code evidence fields into the investigation prompt context:

- `code_owner`
- `code_repository`
- `code_module`
- `code_handler`
- `recent_code_changes`
- `code_blast_radius`

The prompt should continue to require:

- grounded answers only
- contradiction awareness
- explicit next verification step

## UI Changes

## Incident Detail View

Add a code intelligence section:

- repository
- team owner
- likely module
- likely handler
- recent deploy version
- recent changes
- blast radius summary

## Investigation Response Panel

Expose code evidence inline:

- likely code area
- likely owner
- code change indicators
- direct links to repo context if available

## Operations Dashboard

Add code-context visibility:

- GitNexus lookup success rate
- top incidents by code-change correlation
- most frequently implicated repositories

## Failure Handling

GitNexus should be treated as an optional enrichment dependency.

If GitNexus is unavailable:

- investigations must still work
- code evidence should be omitted cleanly
- tool invocations should record failure reason
- UI should indicate code enrichment unavailable

Do not make incident workflows hard-dependent on GitNexus availability.

## Security and Access

Questions that must be handled explicitly:

- Which repositories are allowed to be indexed?
- Can one tenant query another tenant’s repo graph?
- Should GitNexus links be exposed directly in the UI?
- How are tokens stored and rotated?

Minimum requirements:

- token-based auth
- per-environment config
- repository allowlists
- audit for code-context tool usage

## Rollout Plan

## Phase 1: Foundation

Deliverables:

- GitNexus configuration
- `gitnexus_client.py`
- repository and runtime binding models
- admin support for bindings

Outcome:

- AIOps can identify which repos and services are linked

## Phase 2: Read-Only Code Context

Deliverables:

- `code.find_service_owner`
- `code.route_to_handler`
- `code.span_to_symbol`
- HTTP or in-process adapter handlers

Outcome:

- investigations can retrieve likely repo, handler, and symbol context

## Phase 3: Investigation Integration

Deliverables:

- `investigation.py` enrichment with code-context lookups
- code evidence in investigation response
- UI visibility in incident and investigation screens

Outcome:

- incident RCA starts including likely code locations

## Phase 4: Change and Blast Radius

Deliverables:

- `code.recent_changes_for_component`
- `code.blast_radius`
- deployment and change correlation

Outcome:

- incidents can be linked to probable code changes and wider code impact

## Phase 5: Feedback and Learning

Deliverables:

- store whether code-context predictions were useful
- correlate outcomes with code-change evidence
- include code-context confidence in ranking and replay

Outcome:

- platform improves how it uses code evidence over time

## Implementation Tasks in This Repo

### New files

- `genai/gitnexus_client.py`
- `genai/code_context_types.py`
- `genai/code_context_services.py`

### Existing files to update

- `genai/models.py`
- `genai/mcp_services.py`
- `genai/mcp_orchestrator.py`
- `genai/tools/investigation.py`
- `genai/views.py`
- `genai/admin.py`
- `genai/tests.py`
- `.env.example`
- `docker-compose.yml`

## Recommended First Slice

Implement this in the following order:

1. GitNexus config and client
2. repository and service binding models
3. `code.find_service_owner`
4. `code.route_to_handler`
5. `code.span_to_symbol`
6. investigation enrichment using those three lookups
7. incident UI section for code context

This is the smallest useful integration slice.
