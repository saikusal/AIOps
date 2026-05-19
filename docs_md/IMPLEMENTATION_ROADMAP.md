# OpsMitra Implementation Roadmap

This roadmap turns the current design set into a practical delivery sequence.

It is meant to answer:

- what should be built first
- what can wait
- which dependencies block other work
- how to get to a marketable product without trying to finish everything at once

Related design tracks:

- `Track 1`: [AGENT_POLICY_AND_RUNTIME_DESIGN.md](./AGENT_POLICY_AND_RUNTIME_DESIGN.md)
- `Track 2`: [AUTONOMOUS_CONTROL_PLANE_DESIGN.md](./AUTONOMOUS_CONTROL_PLANE_DESIGN.md)
- `Track 3`: [DATA_MEMORY_LIFECYCLE_DESIGN.md](./DATA_MEMORY_LIFECYCLE_DESIGN.md)
- `Track 4`: [INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md](./INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md)

Supporting assessments:

- [CODE_CONTEXT_GAP_ASSESSMENT.md](./CODE_CONTEXT_GAP_ASSESSMENT.md)
- [DYNATRACE_SPLUNK_COMPARISON_FOR_OPSMITRA.md](./DYNATRACE_SPLUNK_COMPARISON_FOR_OPSMITRA.md)

## Executive Summary

Do not try to implement all four tracks in parallel.

The correct order is:

1. `Track 1 first`
   This is the foundation for safe automation and centralized log ingestion.
2. `Track 2 next`
   This turns the control plane into a stronger multi-step investigation system.
3. `Track 3 after that`
   This makes the resulting system operationally durable.
4. `Track 4 in staged slices`
   Start with the framework and a few high-value connectors, not every connector at once.

## Delivery Philosophy

The goal is not “finish all architecture before shipping.”

The goal is:

- make the platform safer
- make it more useful
- make it easier to sell
- avoid architectural debt that blocks future autonomy

That means each phase should produce something demonstrably better and marketable.

## Phase Overview

### Phase 1: Foundation Hardening

Primary tracks:

- `Track 1`
- small enabling parts of `Track 2`

Outcome:

- target runtime knowledge becomes first-class
- target policy becomes first-class
- centralized log ingestion path becomes properly modeled
- onboarding starts capturing the right information

Estimated effort:

- `1.5 to 3 weeks`

### Phase 2: Investigation Engine Maturity

Primary tracks:

- `Track 2`
- code-context improvements needed for Track 2 quality

Outcome:

- the control plane reasons in multiple steps
- investigation stages become explicit
- evidence gaps and contradictions are first-class
- diagnostics and verification are more reliable

Estimated effort:

- `2 to 4 weeks`

### Phase 3: Operational Durability

Primary tracks:

- `Track 3`

Outcome:

- evidence and memory are retained intentionally
- lifecycle and retention become manageable
- replay and learning become more sustainable

Estimated effort:

- `1 to 2 weeks`

### Phase 4: External Platform Connectivity

Primary tracks:

- `Track 4`

Outcome:

- OpsMitra can sit on top of existing customer telemetry platforms
- adoption becomes much easier

Estimated effort:

- `2 to 6+ weeks`, depending on how many connectors are attempted

## Recommended Sequencing

## Phase 1: Track 1 Core Foundation

This is the correct implementation starting point.

### ~~1.1 Backend data model~~

~~Implement:~~

- ~~`TargetPolicyProfile`~~
- ~~`TargetPolicyAssignment`~~
- ~~`TargetRuntimeProfile`~~
- ~~`TargetServiceBinding`~~
- ~~`TargetLogSource`~~
- ~~`TargetLogIngestionProfile`~~

~~Deliverables:~~

- ~~Django models~~
- ~~migrations~~
- ~~admin registration~~
- ~~serializers/helpers~~

Why first:

- everything else depends on knowing what a target actually is

### ~~1.2 Seed default policy profiles~~

~~Seed at least:~~

- ~~`linux-readonly`~~
- ~~`linux-app-systemd`~~
- ~~`linux-app-docker`~~
- ~~`linux-db-readonly`~~
- ~~`prod-restricted`~~

~~Deliverables:~~

- ~~seed command or startup seeding~~
- ~~clear defaults for new targets~~

### ~~1.3 Onboarding model extension~~

~~Extend onboarding flows to capture:~~

- ~~role~~
- ~~environment~~
- ~~runtime type~~
- ~~primary service/container~~
- ~~log source type~~
- ~~log source details~~
- ~~policy profile~~

~~Deliverables:~~

- ~~backend request handling~~
- ~~persistence~~
- ~~validation~~

### ~~1.4 Onboarding UI upgrade~~

~~Add steps for:~~

- ~~runtime detection review~~
- ~~target classification~~
- ~~service mapping~~
- ~~log source selection~~
- ~~execution policy selection~~

~~Deliverables:~~

- ~~updated onboarding forms~~
- ~~review screen~~
- ~~install summary~~

### ~~1.5 Target configuration page~~

~~Add post-onboarding edit surface for:~~

- ~~role~~
- ~~service bindings~~
- ~~log sources~~
- ~~policy profile~~
- ~~approval-related toggles~~

~~Deliverables:~~

- ~~detail page or configuration page~~
- ~~save/update flows~~

### ~~1.6 Generated target config~~

~~Add a generated config representation for the Linux target bundle.~~

~~Deliverables:~~

- ~~backend config endpoint or payload generator~~
- ~~config versioning fields~~
- ~~config status tracking~~

### ~~1.7 Centralized logging setup modeling~~

~~Decide and model:~~

- ~~Fluent Bit as target-side shipper~~
- ~~OpenSearch stream families~~
- ~~required log metadata fields~~
- ~~generated shipper config from target models~~

~~Deliverables:~~

- ~~stream family design in code/config~~
- ~~generated per-target Fluent Bit config~~
- ~~no per-host or per-app index explosion~~

### ~~1.8 Agent refresh flow~~

~~Do not reinstall on role changes.~~

~~Deliverables:~~

- ~~config refresh path~~
- ~~applied version tracking~~
- ~~last apply status~~

### Phase 1 exit criteria

Phase 1 is done when:

- target runtime knowledge is persisted
- target policy is persisted
- centralized log-ingestion config is modeled
- onboarding captures the needed details
- target configuration can be updated later
- agent behavior can be changed without reinstall

## Phase 2: Track 2 Investigation Engine

Once Track 1 is stable enough, strengthen the control plane loop.

### ~~2.1 Investigation state machine~~

~~Add explicit investigation states such as:~~

- ~~`queued`~~
- ~~`scoping`~~
- ~~`collecting_evidence`~~
- ~~`assessing_evidence`~~
- ~~`planning_next_step`~~
- ~~`awaiting_approval`~~
- ~~`executing`~~
- ~~`verifying`~~
- ~~`resolved`~~
- ~~`failed`~~

### ~~2.2 Planner schema~~

~~Persist structured outputs for:~~

- ~~current goal~~
- ~~current target scope~~
- ~~candidate hypotheses~~
- ~~missing evidence~~
- ~~next planned tool calls~~

### ~~2.3 Evidence bundle normalization~~

~~Normalize evidence into one internal structure:~~

- ~~metrics~~
- ~~logs~~
- ~~traces~~
- ~~runtime profile~~
- ~~code context~~
- ~~dependency graph~~
- ~~recent changes~~
- ~~runbooks~~

### ~~2.4 Multi-iteration next-step selection~~

~~Implement bounded internal loop behavior:~~

- ~~choose next evidence tool~~
- ~~collect~~
- ~~reassess~~
- ~~continue or stop~~

### ~~2.5 Contradiction and confidence handling~~

~~Make these explicit in data and UI:~~

- ~~contradicting evidence~~
- ~~confidence score~~
- ~~unresolved evidence gaps~~

### ~~2.6 Verification loop~~

~~After execution:~~

- ~~re-check telemetry~~
- ~~compare before and after~~
- ~~record verification result~~
- ~~continue only if needed~~

### ~~2.7 Code-context quality improvement~~

~~Track 2 depends on code evidence quality.~~

~~At minimum:~~

- ~~improve service-to-repo confidence visibility~~
- ~~show stale index conditions~~
- ~~avoid overclaiming code root cause when context is weak~~

### ~~2.8 Live investigation UI~~

~~Expose the autonomous loop to operators in the frontend.~~

~~At minimum:~~

- ~~recent investigation runs page~~
- ~~investigation detail page with live or replayable stages~~
- ~~tool-call trace visibility~~
- ~~evidence gaps, contradictions, and confidence visibility~~
- ~~incident-to-investigation navigation~~

### Phase 2 exit criteria

Phase 2 is done when:

- investigations visibly run in multiple stages
- operators can see those stages live or in replay
- evidence gaps are explicit
- stop conditions exist
- verification is formalized
- the control plane is more than a single-pass summarizer

## Phase 3: Track 3 Durability And Memory

This phase prevents the platform from becoming operationally messy.

### ~~3.1 Data classification~~

~~Classify:~~

- ~~hot telemetry~~
- ~~operational state~~
- ~~runtime knowledge~~
- ~~evidence memory~~
- ~~learning memory~~
- ~~archived artifacts~~

~~Include explicit store ownership for:~~

- ~~`Postgres` as control-plane system of record~~
- ~~`OpenSearch` for centralized logs~~
- ~~`VictoriaMetrics` for metrics~~
- ~~`Tempo` as long-term trace backend direction~~
- ~~object storage for archives and large artifacts~~
- ~~vector backend behind an abstraction boundary~~

### ~~3.2 Evidence snapshot model~~

~~Add first-class:~~

- ~~evidence snapshots~~
- ~~investigation transcript records~~
- ~~evidence bundle references~~

### ~~3.3 Retention policy model~~

~~Add policy records for:~~

- ~~logs~~
- ~~traces~~
- ~~metrics~~
- ~~investigation evidence~~
- ~~execution history~~
- ~~learning artifacts~~

~~Also define:~~

- ~~Docker single-node storage defaults~~
- ~~Kubernetes standard storage defaults~~
- ~~Kubernetes enterprise storage options~~
- ~~object-storage requirements~~
- ~~vector-store lifecycle rules~~

### ~~3.4 Lifecycle jobs~~

~~Implement:~~

- ~~pruning~~
- ~~compaction~~
- ~~archive preparation~~
- ~~stale snapshot cleanup~~

### ~~3.5 Archive path~~

~~Prepare:~~

- ~~evidence bundle export~~
- ~~object-storage ready archive model~~

### ~~3.6 Trace backend transition plan~~

~~Plan and implement:~~

- ~~`Jaeger` compatibility during transition~~
- ~~`Tempo` as the target trace backend~~
- ~~object-storage-backed trace retention~~
- ~~control-plane query abstraction so trace backend choice is not hardcoded everywhere~~

### ~~3.7 Vector backend abstraction~~

~~Plan and implement:~~

- ~~vector retrieval interface~~
- ~~`pgvector` as acceptable early implementation~~
- ~~clean migration path to a separate engine such as `Weaviate`~~
- ~~separation between relational source-of-truth data and vector index/storage~~

### Phase 3 exit criteria

Phase 3 is done when:

- memory growth is intentional
- evidence is retainable and reviewable
- cleanup does not require manual guesswork
- trace storage direction is explicit
- vector storage direction is explicit
- Docker and Kubernetes storage implementations are both documented and supportable

## Phase 4: Track 4 Integrations

Do this in slices, not all vendors at once.

### 4.1 Integration registry framework

Build:

- `Integration`
- `IntegrationCredential`
- `IntegrationBinding`
- `IntegrationHealthCheck`

### 4.2 Adapter interfaces

Implement normalized interfaces for:

- metrics
- traces
- logs
- alerts

### 4.3 Open/self-hosted adapters first

Build first:

- Prometheus / VictoriaMetrics
- Tempo
- OpenSearch

### 4.4 Integration UI

Add:

- create integration
- test connection
- bind to environment/app/target
- set priority

### 4.5 Tier 1 commercial adapters

Build next:

- Splunk
- Dynatrace
- Datadog

### 4.6 Tier 2 and legacy adapters

Build after that:

- New Relic
- Nagios

Nagios should start as:

- alert/check-state source

not as:

- first-class deep telemetry parity target

### 4.7 Cloud provider connector foundation

Build after the core adapter framework is stable:

- AWS connector foundation
- Azure connector foundation
- GCP connector foundation

These connectors should initially focus on:

- account, subscription, or project connectivity
- inventory and metadata enrichment
- managed-service context
- cluster metadata enrichment

They should not be treated as a substitute for:

- Linux target onboarding on cloud VMs
- cluster-agent onboarding for EKS, AKS, and GKE

### 4.8 Cloud-specific managed-service enrichment

After cloud connector foundation exists, expand into:

- managed database context
- cloud-native alert context
- cloud service metadata correlation
- service-to-cloud-resource mapping

### Phase 4 exit criteria

Phase 4 is done when:

- OpsMitra can operate in native mode
- OpsMitra can operate in connected mode
- core investigations work on top of external telemetry

## What Not To Do

Avoid these mistakes:

- building all four tracks at once
- adding Kafka or Flink before the ingestion path needs them
- building all connectors before the adapter framework exists
- overinvesting in code-context breadth before Track 1 target knowledge is solid
- trying to replace every observability tool instead of integrating with them

## Suggested Engineering Milestones

### ~~Milestone A~~

- ~~Track 1 data models~~
- ~~seeded profiles~~
- ~~onboarding form changes~~

### ~~Milestone B~~

- ~~target configuration page~~
- ~~generated config~~
- ~~config refresh~~
- ~~centralized log-ingestion model~~

### ~~Milestone C~~

- ~~investigation state machine~~
- ~~evidence bundle normalization~~
- ~~multi-step planner~~

### ~~Milestone D~~

- ~~verification loop~~
- ~~confidence and contradiction model~~
- ~~code-context maturity controls~~
- ~~live investigation frontend~~

### ~~Milestone E~~

- ~~retention model~~
- ~~evidence snapshots~~
- ~~lifecycle jobs~~
- ~~Tempo transition plan~~
- ~~vector backend abstraction plan~~

### Milestone F

- integration registry
- Prometheus / Tempo / OpenSearch adapters

### Milestone G

- Splunk / Dynatrace / Datadog connectors

### Milestone H

- AWS / Azure / GCP connector foundation
- cluster metadata enrichment for EKS / AKS / GKE

### Milestone I

- managed-service cloud enrichment

## Suggested Timeline

This is a realistic single-team estimate, not a promise.

### Short version

- Phase 1: `1.5 to 3 weeks`
- Phase 2: `2 to 4 weeks`
- Phase 3: `1 to 2 weeks`
- Phase 4 framework + first adapters: `2 to 4 weeks`
- Phase 4 commercial connectors beyond that: additional time
- Cloud connector foundation: additional time after the framework is stable

### Honest total

For a strong first version across all tracks:

- `6 to 10+ weeks`

depending on:

- number of connectors
- UI polish level
- testing depth
- deployment hardening

## Recommended Immediate Next Step

Start with `Milestone A` and `Milestone B` from Phase 1.

That means:

1. add Track 1 backend models
2. seed default policy profiles
3. extend onboarding data capture
4. add target configuration editing
5. add generated config versioning

Only after that should implementation move deeper into autonomy or broad integrations.

## Bottom Line

The correct path is:

- build target/runtime/policy foundation first
- then improve the control plane reasoning loop
- then harden memory and lifecycle
- then broaden integrations

That gives OpsMitra the best chance of becoming:

- technically solid
- operationally safe
- marketable in a crowded space
