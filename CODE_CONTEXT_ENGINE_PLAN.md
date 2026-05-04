# Code Context Engine Plan

## Positioning

This is the primary product path for code-aware incident investigation in AIOps.

It is designed for:

- air-gapped deployments
- sovereign environments
- self-hosted operation
- customer-controlled repository access

GitNexus remains a useful reference architecture and an optional integration mode, but it is not the default dependency for the product.

## Objective

Build an internal code-context engine that gives the investigation system enough source-code awareness to connect incidents with likely code locations.

The goal is not to build a general-purpose code exploration product.

The goal is to support incident response questions such as:

- which repository owns the failing service
- which route handler likely serves the failing endpoint
- which symbol likely matches the failing trace span
- which recent code changes affected the impacted module
- what other modules or entrypoints may be affected

## Scope

The engine should support:

- local repository indexing
- repository metadata and ownership mapping
- route-to-handler extraction
- span-to-symbol mapping
- deployment-to-commit mapping
- recent change lookup
- limited dependency and blast-radius analysis

The engine should not initially attempt:

- universal deep static analysis for all languages
- full IDE-grade refactoring intelligence
- generic code chat across every file

## Why This Path

This architecture aligns with the product claim.

If AIOps says it supports sovereign and air-gapped environments, then all major reasoning inputs must be operable locally:

- runtime evidence
- LLM inference
- code intelligence

Relying on an external code intelligence provider weakens that story.

## Architecture

The internal code-context engine has four layers:

1. local repository ingestion
2. extracted code mappings
3. retrieval and MCP adapter layer
4. investigation integration

## 1. Local Repository Ingestion

Repositories should be available by one of these modes:

- local mounted path
- mirrored local git clone
- internal git server clone
- uploaded repository archive for isolated environments

The engine should never require public GitHub access at runtime.

### Initial ingestion responsibilities

- detect repository metadata
- scan file tree
- identify service entrypoints
- extract route definitions
- extract likely handlers
- extract worker or queue consumers
- capture basic symbol metadata
- capture commit and changed-file metadata locally

## 2. Extracted Code Mappings

The engine should persist operationally useful mappings rather than trying to parse everything on day 1.

### Primary mappings

- `service -> repository`
- `application -> repository`
- `route -> handler`
- `span -> symbol`
- `deployment version -> commit`
- `queue/topic -> worker handler`

### Secondary mappings

- `module -> dependent modules`
- `symbol -> related symbols`
- `module -> likely owner/team`

## 3. Retrieval and MCP Adapter Layer

The investigation system should access code context through typed local tools.

Proposed tool namespace:

- `code.find_service_owner`
- `code.route_to_handler`
- `code.span_to_symbol`
- `code.find_related_symbols`
- `code.recent_changes_for_component`
- `code.find_recent_deployments`
- `code.blast_radius`
- `code.queue_to_consumers`

These tools should be backed by local indexed data and local repo metadata.

## 4. Investigation Integration

Investigation should use code context only when strong runtime hints exist.

Good triggers:

- incident includes service name
- logs include route path
- traces include span names
- deployment version is known
- queue/topic is visible in logs or traces

Then the investigation flow becomes:

1. gather runtime evidence
2. derive code lookup hints
3. query local code-context tools
4. merge runtime and code evidence
5. produce grounded RCA with likely code area

## Data Model

Add initial models in `genai/models.py`.

### RepositoryIndex

- `name`
- `local_path`
- `default_branch`
- `provider`
- `repo_identifier`
- `last_indexed_at`
- `is_active`
- `metadata`

### ServiceRepositoryBinding

- `service_name`
- `application_name`
- `repository_index`
- `team_name`
- `ownership_confidence`
- `metadata`

### RouteBinding

- `service_name`
- `repository_index`
- `http_method`
- `route_pattern`
- `handler_name`
- `handler_file_path`
- `line_start`
- `line_end`
- `confidence`
- `metadata`

### SpanBinding

- `service_name`
- `repository_index`
- `span_name`
- `symbol_name`
- `symbol_file_path`
- `line_start`
- `line_end`
- `confidence`
- `metadata`

### DeploymentBinding

- `service_name`
- `environment`
- `version`
- `repository_index`
- `commit_sha`
- `deployed_at`
- `metadata`

### CodeChangeRecord

- `repository_index`
- `commit_sha`
- `author`
- `title`
- `changed_files`
- `committed_at`
- `metadata`

### SymbolRelation

- `repository_index`
- `source_symbol`
- `target_symbol`
- `relation_type`
- `confidence`
- `metadata`

## Extraction Strategy

Start narrow and language-aware.

### Phase 1 extraction

Support the frameworks and languages we actually operate against first.

Examples:

- Python web routes
- Django views
- Flask or FastAPI routes
- worker/task registration patterns
- common OpenTelemetry span naming patterns

If the platform later needs broader coverage, add extractors incrementally.

### Extraction methods

Use a mix of:

- framework-aware regex or AST extraction
- lightweight parser-based extraction where justified
- repository conventions
- configuration files and manifests
- deployment metadata

Do not over-invest in a universal parser before the joins prove useful.

## Local Indexing Workflow

1. register repository path
2. scan repository tree
3. extract service metadata
4. extract routes and handlers
5. extract symbols and worker entrypoints
6. capture recent commits and changed files
7. build searchable bindings
8. mark index freshness timestamp

This can run:

- manually
- on schedule
- after deployment sync
- after repository mirror refresh

## Investigation Evidence Contract

The code-context engine should return compact evidence objects.

### Example output for route lookup

- `repository`
- `service_name`
- `route`
- `handler_name`
- `handler_file_path`
- `confidence`
- `supporting_context`

### Example output for span lookup

- `repository`
- `span_name`
- `symbol_name`
- `symbol_file_path`
- `confidence`
- `matched_by`

### Example output for recent changes

- `repository`
- `module_or_file`
- `recent_commits`
- `authors`
- `change_summary`
- `risk_signal`

## UI Changes

## Incident View

Add code context block:

- likely repository
- team owner
- likely handler
- likely symbol
- recent deployment version
- recent changes

## Investigation View

Show code evidence next to runtime evidence:

- service
- route
- handler
- symbol
- recent commits
- likely blast radius

## Dashboard Visibility

Add operational visibility for:

- indexed repositories
- stale repository indexes
- code lookup hit rate
- top repositories implicated by incidents

## Failure Model

The system must degrade cleanly.

If code indexing is unavailable or stale:

- incidents still investigate using runtime evidence
- code evidence is omitted or marked stale
- no execution flow should fail because code context is missing

## Security Model

This design assumes local control of source code.

Requirements:

- repository paths or mirrors must be explicitly registered
- only approved repos are indexed
- code lookups are audited
- tenant separation must apply to repository indexing and retrieval

## Rollout Plan

## Phase 1: Repository and Ownership Foundation

Deliverables:

- repository registration model
- service-to-repo binding
- local repo scanner scaffold
- admin pages for repo bindings

Outcome:

- incidents can identify likely owning repository

## Phase 2: Route and Span Mapping

Deliverables:

- route extraction
- handler mapping
- span-to-symbol mapping
- first three MCP tools:
  - `code.find_service_owner`
  - `code.route_to_handler`
  - `code.span_to_symbol`

Outcome:

- investigations can identify likely source entrypoints

## Phase 3: Change Correlation

Deliverables:

- local git change ingestion
- deployment-to-commit mapping
- `code.recent_changes_for_component`
- `code.find_recent_deployments`

Outcome:

- incidents can be linked to recent changes and release windows

## Phase 4: Dependency and Blast Radius

Deliverables:

- symbol relationships
- module relationship extraction
- `code.find_related_symbols`
- `code.blast_radius`

Outcome:

- better impact analysis and safer remediation decisions

## Phase 5: Investigation and Learning Integration

Deliverables:

- investigation prompt enrichment with code context
- dashboard visibility
- operator feedback on code relevance
- ranking and replay use code-context confidence

Outcome:

- code-aware incident RCA becomes part of normal system behavior

## Implementation Tasks In This Repo

### New files

- `genai/code_context_types.py`
- `genai/code_context_services.py`
- `genai/code_context_ingestion.py`
- `genai/code_context_extractors.py`

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

## Optional Mode: GitNexus Adapter

GitNexus should remain an optional secondary mode.

If enabled:

- the same `code.*` contracts remain stable
- the backend provider can be GitNexus instead of the internal index
- AIOps still owns runtime bindings and investigation orchestration

This allows:

- internal deployments to stay fully self-contained
- advanced deployments to use GitNexus when appropriate

## Recommendation

Primary product path:

- build the internal code-context engine

Optional deployment mode:

- support GitNexus as a backend provider behind the same `code.*` contracts

This keeps the architecture consistent with the air-gapped product story while preserving flexibility.
