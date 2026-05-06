# Track 4: Integrations And Telemetry Adapters Design

This is Track 4 of the OpsMitra autonomy and operations architecture plan.

Related tracks:

- `Track 1`: [AGENT_POLICY_AND_RUNTIME_DESIGN.md](./AGENT_POLICY_AND_RUNTIME_DESIGN.md)
- `Track 2`: [AUTONOMOUS_CONTROL_PLANE_DESIGN.md](./AUTONOMOUS_CONTROL_PLANE_DESIGN.md)
- `Track 3`: [DATA_MEMORY_LIFECYCLE_DESIGN.md](./DATA_MEMORY_LIFECYCLE_DESIGN.md)

This document defines how OpsMitra should connect to existing observability and telemetry platforms instead of requiring every customer to replace their current stack.

## Why Track 4 Is Needed

Most customers already have:

- metrics systems
- log platforms
- tracing backends
- dashboards
- alert sources

If OpsMitra requires every customer to migrate everything into a fully native stack before it becomes useful, adoption will be much harder.

OpsMitra should therefore support both:

1. `Native mode`
   Customers use OpsMitra’s own ingestion path and target-side components.
2. `Connected mode`
   OpsMitra connects to existing external telemetry systems and uses them as evidence sources.

This allows the product to position itself as:

- the incident operations and remediation control plane
- not necessarily a mandatory replacement for all observability tooling

## Design Goals

Track 4 should allow OpsMitra to:

- connect to external telemetry systems
- authenticate securely
- normalize heterogeneous telemetry responses
- query metrics, logs, traces, alerts, and topology signals through a unified internal interface
- merge external telemetry with native runtime knowledge and code-context evidence
- choose source priority and fallback behavior
- present integration status and health in the UI

## Core Principles

1. OpsMitra should not require customers to replace their existing observability stack.
2. External integrations should feed the same investigation and remediation workflow as native telemetry.
3. The autonomy loop should use normalized evidence, not vendor-specific response formats.
4. Integrations must be secure, testable, observable, and configurable.
5. Native and external sources must coexist cleanly.

## Product Positioning Impact

Track 4 is strategically important because it allows OpsMitra to say:

- “Use our native stack if you want.”
- “Or connect us to what you already have.”

That is a much stronger sales motion than:

- “replace your existing telemetry stack first.”

## Supported Source Categories

Track 4 should cover these source classes:

### Metrics

- Prometheus
- VictoriaMetrics
- Grafana-compatible PromQL endpoints
- later commercial metrics APIs

### Logs

- OpenSearch
- Elasticsearch
- Loki
- later Splunk
- later commercial log APIs

### Traces

- Jaeger
- Tempo
- later Dynatrace / Datadog / New Relic trace APIs if needed

### Alerts

- Alertmanager-compatible sources
- external alert webhooks
- later vendor-specific alert APIs

### Topology / Inventory

- native OpsMitra inventory
- Kubernetes cluster state
- later cloud APIs
- later CMDB or service catalog systems if needed

### Cloud Control Planes

- AWS APIs
- Azure APIs
- GCP APIs

These are needed for managed-service context, cloud metadata, and non-host telemetry enrichment.

## Priority Connector Set

Track 4 should distinguish between:

- connectors needed for market credibility
- connectors that should actually be built first

### Tier 1: Build First

These are the highest-priority commercial connectors for broad enterprise relevance:

- `Splunk`
- `Dynatrace`
- `Datadog`

Why:

- Splunk is a major log and operational search source
- Dynatrace is a major APM and topology source
- Datadog is widely used across metrics, traces, logs, and monitors

### Tier 2: Build Next

- `New Relic`

Why:

- widely used
- valuable for metrics, traces, logs, and alert context
- slightly lower priority than the Tier 1 set for the current roadmap

### Tier 3: Alert-Source-First

- `Nagios`

Why:

- still important in many environments
- often more useful as an alert/check source than as a rich modern telemetry backend

For Nagios, the initial design should focus on:

- alert ingestion
- check state ingestion
- incident correlation input

not:

- deep traces/logs/topology parity with modern observability platforms

## What Track 4 Is Not

Track 4 is not meant to turn OpsMitra into:

- a general-purpose iPaaS platform
- a huge connector marketplace from day one
- a replacement for every customer’s existing observability backend

The goal is narrower:

- ingest and normalize enough evidence from external systems to make OpsMitra useful for investigation and remediation

## Integration Modes

### 1. Native-Only Mode

All evidence comes from:

- target-side shippers/collectors
- native metrics/logs/traces
- native runtime inventory

### 2. External-Only Mode

A customer uses:

- external metrics
- external logs
- external traces

OpsMitra still adds:

- runtime knowledge
- code context
- workflow orchestration
- remediation policy

### 3. Hybrid Mode

Most realistic enterprise mode:

- some telemetry is native
- some telemetry is external
- control plane merges them into one investigation flow

## Cloud And Kubernetes Connector Model

Cloud environments should be treated as a combination of:

1. `Compute onboarding`
2. `Cluster onboarding`
3. `Cloud control-plane connectors`

Track 4 should explicitly support all three.

### Compute Onboarding

Use this for:

- AWS EC2
- Azure VMs
- GCP Compute Engine VMs

These should be treated like Linux targets:

- install target-side agent bundle
- install centralized log shipper
- install command agent
- ship telemetry back to the control plane

### Cluster Onboarding

Use this for:

- EKS
- AKS
- GKE

These should use:

- in-cluster `k8s-cluster-agent`
- RBAC-scoped access
- cluster-local workload discovery
- Kubernetes-native diagnostic and remediation path

Track 4 should not model EKS, AKS, or GKE as “SSH into worker nodes first.” The primary connected-mode model should remain:

- cluster agent inside the cluster
- cloud API connector outside the cluster when cloud metadata is needed

### Cloud Control-Plane Connectors

Use these for:

- managed services with no host agent
- cloud-native metadata
- account, subscription, or project inventory
- cloud alerts
- managed database context
- cluster metadata enrichment

Examples:

- AWS: EC2 metadata, EKS metadata, RDS, CloudWatch-derived context
- Azure: VM metadata, AKS metadata, Azure Monitor-derived context
- GCP: GCE metadata, GKE metadata, Cloud Monitoring / Cloud Logging-derived context

This means cloud connectivity is not “just install an agent on a server.”

## Cloud Provider Scope

Track 4 should support cloud platforms in layers:

### AWS

- `EC2`: compute agent path
- `EKS`: cluster-agent path
- managed AWS services: AWS connector/API path

### Azure

- `Azure VMs`: compute agent path
- `AKS`: cluster-agent path
- managed Azure services: Azure connector/API path

### GCP

- `GCE`: compute agent path
- `GKE`: cluster-agent path
- managed GCP services: GCP connector/API path

## Adapter Architecture

Track 4 should introduce a normalized adapter layer.

The control plane should not ask:

- “call Jaeger”
- “call Loki”
- “call Splunk”

Instead it should ask:

- `fetch_metrics(...)`
- `fetch_logs(...)`
- `fetch_traces(...)`
- `fetch_alert_state(...)`
- `fetch_topology_context(...)`

Then the adapter layer resolves which backend to use.

## Proposed Service Layer

Suggested modules:

- `genai/integrations/base.py`
- `genai/integrations/metrics.py`
- `genai/integrations/logs.py`
- `genai/integrations/traces.py`
- `genai/integrations/alerts.py`
- `genai/integrations/registry.py`
- `genai/integrations/health.py`

Suggested vendor adapters:

- `genai/integrations/vendors/prometheus.py`
- `genai/integrations/vendors/victoriametrics.py`
- `genai/integrations/vendors/opensearch.py`
- `genai/integrations/vendors/elasticsearch.py`
- `genai/integrations/vendors/loki.py`
- `genai/integrations/vendors/jaeger.py`
- `genai/integrations/vendors/tempo.py`

Later:

- `splunk.py`
- `dynatrace.py`
- `datadog.py`
- `newrelic.py`
- `nagios.py`

## Normalized Result Shapes

Every integration should map vendor responses into internal normalized shapes.

Examples:

- `NormalizedMetricResult`
- `NormalizedLogResult`
- `NormalizedTraceResult`
- `NormalizedAlertResult`
- `NormalizedTopologyResult`

This is necessary so Track 2 can reason over:

- one consistent evidence model

instead of:

- many vendor-specific payload formats

## Proposed Data Model

Track 4 likely needs new models such as:

### 1. `Integration`

Suggested fields:

- `name`
- `integration_type`
- `category`
- `endpoint_url`
- `auth_mode`
- `enabled`
- `metadata_json`
- `health_status`
- `last_health_check_at`

### 2. `IntegrationCredential`

Suggested fields:

- `integration`
- `secret_ref`
- `credential_metadata`
- `rotation_status`

### 3. `IntegrationBinding`

Maps integrations to environments, applications, or targets.

Suggested fields:

- `integration`
- `environment`
- `application_name`
- `target`
- `priority`
- `enabled`

### 4. `IntegrationHealthCheck`

Suggested fields:

- `integration`
- `status`
- `checked_at`
- `latency_ms`
- `message`
- `details_json`

### 5. `CloudAccountBinding`

Maps a cloud integration to an account, subscription, or project scope.

Suggested fields:

- `integration`
- `provider`
- `account_id`
- `subscription_id`
- `project_id`
- `scope_name`
- `environment`
- `enabled`
- `metadata_json`

## Query Resolution Model

The control plane needs a source selection strategy.

For example:

- logs for `orders-api` in `prod`
- metrics for `payments-gateway`
- traces for `checkout-service`

Track 4 should decide:

1. which integrations are eligible
2. which source has highest priority
3. whether multiple sources should be queried
4. how results are merged or deduplicated

## Source Priority Rules

OpsMitra should support configurable priority rules such as:

- prefer native logs over external logs
- prefer external traces over native traces
- query both native and external metrics and merge carefully

The exact rules should be configurable by:

- environment
- source class
- customer preference

## UI Requirements

Track 4 requires a real integration management UI.

The UI should support:

- create integration
- set endpoint and auth
- test connection
- view health status
- bind integration to environments/apps/targets
- enable or disable
- configure source priority

Useful UI views:

- integrations list
- integration detail page
- connection test results
- binding summary
- integration health panel

The UI should also distinguish:

- compute onboarding
- cluster onboarding
- cloud account, subscription, or project connectors

## Security Requirements

Integration credentials must be handled carefully.

Track 4 should support:

- secret references rather than raw plain-text sprawl
- minimal credential scope
- connectivity testing without exposing secrets
- auditability of who changed what

This connects strongly to future secret-backend work.

## Interaction With Track 2

Track 2 should consume telemetry through Track 4 adapters.

That means the autonomous loop should not care whether traces came from:

- native Jaeger
- external Tempo
- later a vendor API

The control plane should reason over normalized evidence only.

## Interaction With Track 1

Track 1 provides:

- target runtime knowledge
- target identity
- service bindings
- log-source metadata

Track 4 uses that information to ask external sources the right questions.

For example:

- map target `orders-prod-01` to service `orders-api`
- query external logs for `service_name=orders-api`
- query external traces for `service.name=orders-api`

## Interaction With Track 3

Track 3 defines:

- how normalized external evidence is retained
- how much raw integration output is stored
- lifecycle of fetched evidence snapshots

Track 4 does not define retention. It defines acquisition and normalization.

## Rollout Plan

### Phase 1: Metrics Adapters

Start with:

- Prometheus
- VictoriaMetrics
- Grafana-compatible PromQL endpoints

These are high value and relatively straightforward.

### Phase 2: Trace Adapters

Start with:

- Jaeger
- Tempo

### Phase 3: Log Adapters

Start with:

- OpenSearch
- Elasticsearch
- Loki

### Phase 4: Integration UI And Health

- add CRUD for integrations
- add connection tests
- add binding and priority model

### Phase 5: Commercial Platform Adapters

Only after open/self-hosted adapters are stable:

- Splunk
- Dynatrace
- Datadog

### Phase 6: Additional Commercial And Legacy Connectors

- New Relic
- Nagios

Nagios should begin as:

- alert-source ingestion
- incident enrichment

rather than:

- full rich telemetry parity with more modern observability platforms

### Phase 7: Cloud Provider Connectors

Build:

- AWS connector foundation
- Azure connector foundation
- GCP connector foundation

These should focus first on:

- account or project connectivity
- metadata and inventory enrichment
- cluster metadata enrichment
- managed-service context

### Phase 8: Cloud-Specific Managed Service Enrichment

Expand cloud connectors to support:

- managed database context
- cloud-native alerts
- cluster-specific cloud metadata
- service-to-cloud-resource correlation

## Recommended Build Order

Implement in this order:

1. integration registry model
2. normalized metrics adapter interface
3. normalized trace adapter interface
4. normalized log adapter interface
5. integration UI and health checks
6. source priority and merge behavior
7. Tier 1 commercial adapters: Splunk, Dynatrace, Datadog
8. Tier 2 and legacy adapters: New Relic, Nagios
9. cloud provider connector foundation: AWS, Azure, GCP
10. cloud managed-service enrichment

## Go-To-Market Implication

Track 4 should allow OpsMitra to say:

- “We are designed to sit on top of your existing observability stack.”
- “Initial connector priority includes Splunk, Dynatrace, Datadog, and New Relic.”
- “Nagios support is planned as an alert-source integration for legacy estates.”

That is a stronger and more honest position than claiming broad parity with every platform on day one.

## Expected Outcome

With Track 4 implemented, OpsMitra becomes much easier to adopt because it can:

- sit on top of existing observability systems
- use external telemetry for investigation
- preserve its differentiation in code context, autonomy, and safe execution

This is one of the most important go-to-market enablers for the platform.

## Bottom Line

Track 4 lets OpsMitra become:

- a native observability stack when needed
- a telemetry-aware incident control plane on top of existing tools when needed

That flexibility is strategically important in a competitive market.
