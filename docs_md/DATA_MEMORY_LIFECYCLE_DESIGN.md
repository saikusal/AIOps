# Track 3: Data, Memory, And Lifecycle Design

This is Track 3 of the OpsMitra autonomy and operations architecture plan.

Related tracks:

- `Track 1`: [AGENT_POLICY_AND_RUNTIME_DESIGN.md](./AGENT_POLICY_AND_RUNTIME_DESIGN.md)
- `Track 2`: [AUTONOMOUS_CONTROL_PLANE_DESIGN.md](./AUTONOMOUS_CONTROL_PLANE_DESIGN.md)
- `Track 4`: [INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md](./INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md)

This document defines how OpsMitra should manage:

- operational data classes
- investigation memory
- evidence retention
- long-term learning artifacts
- archival and cleanup

Track 3 is necessary because a more autonomous control plane produces much more state than a simple dashboard or chatbot.

## Design Goals

OpsMitra should:

- separate data classes by purpose and retention
- use the right storage system for each class
- preserve investigation evidence that matters
- keep enough memory for future learning and replay
- avoid treating Elasticsearch as the system of record
- support purge, retention, archive, and compliance controls

## Why This Track Is Needed

A mature AIOps platform accumulates:

- alerts
- incidents
- tool invocations
- investigation plans
- evidence bundles
- execution intents
- verification records
- replay evaluations
- runbooks
- code-context indexes
- agent inventory and runtime snapshots

Without a lifecycle design, the system becomes:

- expensive to operate
- hard to govern
- difficult to replay
- difficult to audit
- difficult to clean safely

## Core Principles

1. Postgres should be the system of record for control-plane state.
2. OpenSearch should not be the authoritative long-term store for all evidence.
3. Tempo should be the long-term trace backend direction, with object storage underneath it.
4. Vector retrieval should be logically separated from relational state, even if early deployments start with `pgvector`.
5. Large or immutable artifacts should move to object storage.
6. Hot operational data and cold historical data should be separated.
7. Memory used for learning should be deliberate, not accidental cache buildup.
8. Retention and lifecycle rules should be explicit and configurable.

## Data Categories

OpsMitra data should be divided into categories.

### 1. Hot Telemetry

Short-horizon, rapidly changing operational data:

- logs
- traces
- metrics
- cluster or host heartbeat snapshots

Primary use:

- active investigation
- near-real-time validation

Track 3 does not define how logs are collected. That belongs to Track 1. Track 3 defines how centrally ingested logs are retained, aged out, archived, and governed after they arrive.

### 2. Operational State

Structured product state:

- incidents
- alerts
- investigation runs
- execution intents
- outcomes
- onboarding records
- target inventory

Primary use:

- day-to-day product workflows

### 3. Runtime Knowledge

Target-specific configuration and discovered runtime context:

- target runtime profile
- service bindings
- log sources
- policy assignments
- discovered services and workloads

Primary use:

- safe automation
- correct evidence gathering

### 4. Evidence Memory

Structured evidence snapshots used by the autonomy loop:

- metrics snapshots
- log excerpts
- trace excerpts
- code-context evidence
- dependency context
- contradiction records

Primary use:

- replay
- RCA traceability
- planner learning

### 5. Learning Memory

Data used to improve future decisions:

- replay evaluations
- operator feedback
- ranking outcomes
- verification success/failure
- common incident patterns

Primary use:

- ranking
- planner heuristics
- quality improvement

### 6. Immutable Artifacts

Large or archival objects:

- evidence bundles
- exported postmortems
- investigation transcripts
- archived reports
- uploaded documents and runbooks

Primary use:

- audit
- compliance
- long-term storage

## Storage Strategy

Use different stores for different data classes.

### Postgres

Use as the primary system of record for:

- incidents
- investigation runs
- tool invocations
- execution intents
- target policy/runtime models
- replay and operator feedback metadata

### Redis

Use for:

- short-lived caches
- queued command state
- in-flight coordination
- transient retries

Redis should not be treated as durable memory.

### OpenSearch

Use for:

- searchable recent logs
- active operational debugging

Do not use as the sole long-term evidence archive.

### Metrics Backend

Use VictoriaMetrics or Prometheus for:

- metrics retention
- windowed queries
- trend and verification checks

### Trace Backend

Use `Tempo` as the target long-term trace backend for:

- recent trace investigation
- service call-path evidence
- trace search and long-horizon retention through object storage

`Jaeger` should be treated as transitional compatibility, not the final storage direction.

### Vector Backend

Use a dedicated vector retrieval abstraction for:

- code-context embeddings
- runbook and document retrieval
- historical RCA memory search
- long-term semantic incident knowledge

Recommended direction:

- keep `Postgres` as the canonical metadata store
- allow `pgvector` as an early implementation
- preserve a clean migration path to a separate vector engine such as `Weaviate` if semantic retrieval becomes a core product capability

Do not tightly couple vector search persistence to the core control-plane relational schema.

### Object Storage

Use S3-compatible object storage for:

- archived evidence bundles
- long transcripts
- exported reports
- retained snapshots too large for Postgres

## Logical Architecture vs Deployment Implementation

OpsMitra should use one logical storage architecture with different deployment implementations.

### Docker / Single-Node Implementation

Default implementation:

- `Postgres` on Docker volume
- `Redis` on Docker volume or ephemeral storage
- `VictoriaMetrics` on Docker volume
- `OpenSearch` on Docker volume
- `Tempo` in monolithic mode with local disk or bundled object-store-compatible backing
- local object storage via MinIO when S3-compatible behavior is needed

This tier should optimize for:

- simple install
- local persistence
- minimal operator burden

### Kubernetes / Standard Implementation

Default implementation:

- `Postgres` on PVC
- `Redis` on PVC or managed service
- `VictoriaMetrics` on PVC
- `OpenSearch` on PVC
- `Tempo` backed by object storage
- evidence archives in external or in-cluster S3-compatible object storage

This tier should optimize for:

- storage-class portability
- safer retention at scale
- easier backup and restore

### Kubernetes / Enterprise Implementation

Supported implementation:

- managed or hardened external `Postgres`
- managed or hardened external `OpenSearch`
- `Tempo` backed by external object storage
- customer-provided CSI / storage platform
- optional customer-owned distributed storage such as `Ceph/Rook`

`Ceph/Rook` should be supported if the customer already uses it, but it should not be a mandatory baseline dependency for OpsMitra.

## Retention Model

Each data category needs explicit retention guidance.

Suggested starting point:

- hot logs in OpenSearch: `7-30 days`
- hot traces: `3-14 days`
- metrics raw: `30-90 days`
- metrics rollups: `90-400 days`
- incidents: `1-7 years`
- execution intents and outcomes: `1-7 years`
- investigation run metadata: `1-3 years`
- evidence snapshots: `90-365 days`
- replay and learning metadata: `1-3 years`
- archived evidence bundles for major incidents: `1-7 years`

These should later become policy-driven rather than hardcoded.

If the logging backend naming or implementation evolves later, the retention model should remain attached to data categories and stream classes rather than one backend-specific index naming convention.

Vector retention should be tied to the source object lifecycle:

- code embeddings follow repository index lifecycle
- runbook/document embeddings follow document lifecycle
- incident-memory embeddings follow evidence or archive lifecycle

## Investigation Memory Model

The autonomous loop should maintain layered memory.

### 1. Working Memory

Short-lived memory for the current investigation:

- current plan
- current evidence bundle
- current hypotheses
- current iteration state

This can live in Postgres-backed run state plus short-lived cache support.

### 2. Incident Memory

Structured state for the lifetime of the incident:

- all iterations
- evidence snapshots
- tool outputs
- verification records
- final RCA

### 3. Historical Memory

Cross-incident memory:

- prior similar incidents
- outcome patterns
- common successful remediations
- operator feedback

### 4. Archived Memory

Cold retained memory:

- exported investigation package
- long-term compliance evidence

## Evidence Bundle Design

Evidence bundles should become first-class objects.

Each bundle should capture:

- incident or investigation reference
- timestamp
- evidence sources included
- summarized findings
- contradiction markers
- confidence metadata
- relevant raw excerpts

Large raw payloads should be stored out-of-line when necessary, with Postgres holding metadata and object references.

## Lifecycle Operations

The platform should support explicit lifecycle jobs.

Examples:

- prune expired caches
- age out old hot log references
- archive closed-incident evidence bundles
- compact or summarize old investigation runs
- prune raw tool responses while keeping summaries
- expire stale onboarding or enrollment tokens
- rotate agent heartbeat snapshots

## Legal Hold And Protection

Some incidents or evidence sets may need protection from deletion.

The design should support:

- legal hold or retention hold flags
- severity-based retention overrides
- manual archival protection for major incidents

This matters for enterprise and regulated environments.

## Data Model Additions

Track 3 likely requires new models or extensions such as:

- `DataRetentionPolicy`
- `EvidenceBundle`
- `EvidenceArtifact`
- `ArchiveManifest`
- `LifecycleJobRun`
- `RetentionHold`
- `InvestigationTranscript`
- `EvidenceSnapshot`

Suggested roles:

- `DataRetentionPolicy`
  retention rules per data category
- `EvidenceBundle`
  normalized archived package for an investigation
- `EvidenceArtifact`
  pointer to large raw artifacts
- `ArchiveManifest`
  records object-storage contents for a bundle
- `LifecycleJobRun`
  records pruning/archive job history
- `RetentionHold`
  prevents cleanup for protected objects
- `InvestigationTranscript`
  stores structured autonomy-loop conversation and decisions
- `EvidenceSnapshot`
  stores per-iteration evidence bundle references

## Learning Data Design

Not all memory should be kept forever.

The platform should distinguish:

- `replay metadata` worth keeping
- `raw command outputs` worth pruning
- `high-value incident outcomes` worth archiving
- `noisy transient evidence` worth expiring

Learning should focus on structured signals:

- action success rate
- contradiction frequency
- verification pass rate
- time to resolution
- operator override frequency

These are more durable than storing every raw payload indefinitely.

## UI Requirements

OpsMitra should surface lifecycle and memory state to operators and admins.

Useful UI views:

- evidence retention status
- archived bundles
- replay and learning summaries
- lifecycle job history
- target inventory recency
- incident evidence package export

Admins should be able to:

- see what is retained where
- trigger archive/export
- apply retention holds
- review lifecycle failures

## Policy Interaction

Track 3 depends on the other tracks.

Examples:

- Track 1 determines which runtime knowledge must be persisted
- Track 2 determines which investigation artifacts are produced
- Track 3 defines how long they live and where they are stored

The three tracks must be designed together, even if implemented in phases.

## Rollout Plan

### Phase 1: Data Classification

- define categories in code and docs
- identify what currently lives only in cache or ad hoc JSON
- map current models to lifecycle classes

### Phase 2: Evidence Snapshot Persistence

- add explicit evidence snapshot or bundle references
- avoid losing important investigation context after one response

### Phase 3: Retention Policies

- add policy records for major data categories
- implement cleanup jobs for short-lived data

### Phase 4: Archive Support

- add object-storage-backed archive path for evidence bundles and transcripts
- store manifests in Postgres

### Phase 5: Lifecycle UI And Job Reporting

- surface retention and archive state
- record lifecycle job outcomes

### Phase 6: Learning Memory Hardening

- preserve structured replay and outcome data
- prune low-value raw data more aggressively

## Recommended Build Order

Implement in this order:

1. data category inventory
2. evidence snapshot model
3. retention policy model
4. lifecycle job framework
5. archive/object storage support
6. lifecycle admin and UI visibility

## Expected Outcome

With Track 3 implemented, OpsMitra should:

- retain the right evidence for the right duration
- avoid bloated operational stores
- preserve enough memory for replay and learning
- support archive, export, and cleanup safely
- be operationally credible for larger customer environments

## Summary

Track 3 turns OpsMitra from a system that merely accumulates data into a system that understands the lifecycle of its own operational memory.

That is necessary if the control plane is going to become more autonomous, more stateful, and more enterprise-ready over time.
