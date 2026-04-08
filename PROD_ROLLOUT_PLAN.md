# Production Rollout Plan

## Goal
Turn the current AIOps platform into a productized control plane that clients can deploy and use to onboard real infrastructure without removing the existing demo applications.

The demo applications remain in the repository and in demo deployments for:
- showcase flows
- internal testing
- chaos validation
- UI and RCA demos

They are not part of the production onboarding story for client infrastructure.

## Product Direction
The platform should ship as a **control plane** plus **environment-specific onboarding packages**.

### Control Plane
The control plane is the existing AIOps platform, extended with:
- authentication and tenant management
- target onboarding and fleet management
- configuration profiles for Linux, Windows, Kubernetes, Docker hosts, and cloud
- discovered service inventory
- topology generation and graph rendering
- telemetry health and agent health
- incident, RCA, remediation, and audit workflows

### Managed Agent Layer
Clients should not install multiple unrelated components manually. The product should provide a single managed installer path per environment.

Recommended packaging:
- **AIOps Supervisor Agent** for Linux and Windows
- **Helm chart / Operator-based onboarding** for Kubernetes
- optional host-level discovery add-ons for Docker and cloud VMs

The supervisor/managed install should handle:
- OpenTelemetry Collector
- host metrics exporter (`node_exporter` on Linux, `windows_exporter` on Windows)
- log collection
- service/process/container discovery
- enrollment token registration
- config refresh and heartbeat

## Current Platform vs Productized Platform
### What already exists
The current control plane already has:
- central UI
- incidents
- assistant workflows
- predictions
- graphs
- telemetry integrations
- command execution and remediation workflows

### What needs to be added for production rollout
The major missing product area is a new **Fleet / Config / Onboarding** section.

This should be the main new product window, not a full platform rewrite.

## New Product Area: Fleet / Config
Add a new primary navigation section such as:
- `Fleet`
- `Infrastructure`
- or `Targets`

Recommended initial screens:

### 1. Fleet Overview
Purpose:
- show all onboarded targets
- show health and enrollment status
- show discovered services and environment counts

Should include:
- target name
- environment type
- status
- last heartbeat
- installed profile
- discovered services count
- collector/exporter versions
- agent version

### 2. Enroll Target
Purpose:
- onboard a new target into the platform

User flow:
1. Choose target type
2. Choose telemetry profile
3. Generate enrollment token
4. Generate installation instructions
5. Install on client target
6. Wait for target to connect back

Target types:
- Linux server
- Windows server
- Kubernetes cluster
- Docker host
- Cloud VM

### 3. Telemetry Profiles
Purpose:
- define what gets installed and collected

Example profiles:
- Infra only
- Infra + logs
- Infra + logs + traces
- Full application observability
- Custom profile

### 4. Target Detail
Purpose:
- manage one enrolled target

Should include:
- target metadata
- OS / environment type
- installed components
- collector/exporter health
- discovered services
- logs, metrics, traces availability
- config profile
- recent errors
- upgrade status

### 5. Generated Install Artifacts
Purpose:
- give the client the correct installation command or package

Examples:
- Linux install shell script
- Windows PowerShell bootstrap
- Kubernetes Helm command and values
- Docker host bootstrap

## Onboarding Model by Environment
The platform must be independent of deployment style, but the onboarding mechanism cannot be identical for every target.

### Linux standalone server
Recommended onboarding model:
- client runs one generated shell command
- command downloads or installs the AIOps Supervisor Agent
- supervisor installs and manages required components

Linux bundle should include or manage:
- OpenTelemetry Collector
- node exporter
- log shipper
- discovery helper
- enrollment client

Linux flow:
1. User selects `Linux server`
2. User chooses telemetry profile
3. Platform generates tenant-scoped token
4. Platform generates install command
5. Client runs command on target server
6. Supervisor enrolls back into control plane
7. Target appears in Fleet
8. Discovered services begin populating the platform

### Windows standalone server
Recommended onboarding model:
- PowerShell bootstrap or signed installer package

Windows bundle should include or manage:
- OpenTelemetry Collector for Windows
- windows exporter
- Windows event log collection
- enrollment client

### Kubernetes cluster
Recommended onboarding model:
- Helm chart with tenant-specific values
- optionally OpenTelemetry Operator where appropriate

Kubernetes install should provide:
- collector deployment/daemonset/gateway pattern
- cluster metadata collection
- service/pod discovery
- traces and metrics routing
- enrollment token and tenant config

### Docker host
Recommended onboarding model:
- host-level supervisor with Docker discovery
- not per-container manual installs

### Cloud
Treat cloud as:
- Linux/Windows VM onboarding for hosts
- Kubernetes onboarding for managed clusters
- API integrations later for managed services

## Discovery and Application Population
### What should happen after onboarding
When a target is onboarded, the platform should automatically begin showing:
- the target/host itself
- discovered services/processes/containers
- metrics health
- traces if available
- logs if configured
- incidents and predictions mapped to those services

### Do we need automatic topology and graphs?
Yes.

For production use, the topology should not depend on static demo JSON alone.

Recommended topology strategy:
1. Use traces to infer service-to-service edges where available
2. Use discovery metadata to identify nodes
3. Use metrics to attach health, latency, and risk overlays
4. Use static/manual configuration only as fallback or override

Topology inputs should include:
- service names from traces
- process/service discovery
- container metadata where present
- host metadata
- explicit operator overrides where necessary

This allows onboarded infrastructure to appear in the existing:
- Applications view
- Graph view
- Incidents view
- Predictions view

## Storage Plan
This is one of the most important product decisions.

### Control plane state
Use:
- PostgreSQL

Store:
- tenants
- users and roles
- targets
- enrollment tokens
- fleet metadata
- telemetry profiles
- incidents
- command history
- chat history
- audit logs metadata
- topology metadata and overrides

### Cache and queueing
Use:
- Redis

Use it for:
- cache
- session acceleration
- task queue support
- ephemeral state

### Metrics storage
Current Prometheus is acceptable for existing development/demo workflows.

For production and multi-tenant scale, move toward a remote metrics backend with durable retention.

### Traces storage
Current Jaeger is acceptable for current development/demo workflows.

For production, traces should use a more durable backend with long retention support.

### Logs storage
The platform should use a centralized logs backend with tenant-aware retention and query support.

### Object storage
Plan for S3-compatible object storage for:
- long retention telemetry blocks
- archives
- exported reports
- installer artifacts
- backups

### Recommended long-term storage split
- PostgreSQL for control plane metadata
- Redis for cache/queue/session acceleration
- dedicated metrics backend for production metrics retention
- dedicated traces backend for production traces retention
- centralized logs backend
- object storage for long-term retention and artifacts

## Security and Enrollment
The onboarding workflow must be designed for client trust and auditability.

### Required controls
- tenant-scoped enrollment tokens
- TLS for all control and telemetry paths
- RBAC for onboarding and fleet actions
- audit logs for installs, config changes, commands, and remediation
- short-lived or revocable enrollment credentials
- no requirement to permanently store customer root passwords in the platform

### Recommended install model
Prefer:
- generated install command that the client runs on their target

Avoid as the default:
- platform-held SSH credentials that directly push into customer infrastructure

This is safer and easier to operate for SaaS and enterprise deployments.

## Product Packaging
### What should be bundled for clients
The product should package:
- control plane images/charts
- Linux supervisor installer path
- Windows installer path
- Kubernetes Helm chart/operator path
- config and onboarding UI

### What should not be bundled into production rollout
Do not bundle the demo custom applications as required production components.

Keep them in the repo and in demo mode for:
- showcase
- validation
- chaos testing
- development

## Recommended Rollout Phases
### Phase 1: Linux standalone onboarding
Deliver first:
- Fleet / Config UI
- Linux target enrollment flow
- telemetry profile selection
- generated install command
- supervisor enroll + heartbeat
- discovered services appear in control plane
- topology derived from discovery + traces where present

This is the best first productionizable slice.

### Phase 2: Windows onboarding
Deliver:
- PowerShell bootstrap or installer
- Windows exporter and event log support
- same fleet status and enrollment model

### Phase 3: Kubernetes onboarding
Deliver:
- Helm-based onboarding
- cluster telemetry profile
- namespace and cluster discovery
- cluster-level topology population

### Phase 4: Docker host onboarding
Deliver:
- host-level supervisor install
- container discovery
- container/service mapping into topology

### Phase 5: Cloud integrations
Deliver:
- cloud VM onboarding paths
- managed cluster paths
- later managed service inventory integrations

## Concrete UI Plan
### New navigation item
Add one new top-level item:
- `Fleet`

### Fleet subpages
- Fleet Overview
- Enroll Target
- Profiles
- Target Detail
- Install Artifacts
- Audit / Activity

### Existing pages stay in place
Keep and extend:
- Applications
- Assistant
- Alerts
- Incidents
- Predictions
- Documents
- Graphs

Onboarded infrastructure should flow into those existing pages automatically.

## Proposed Data Flow
1. Client deploys control plane
2. Operator opens Fleet > Enroll Target
3. Operator chooses Linux / Windows / Kubernetes
4. Platform generates token and install instructions
5. Client installs supervisor/collector/exporters on target
6. Target enrolls back to control plane
7. Telemetry begins flowing to central backends
8. Discovery identifies services and metadata
9. Graph/topology is built from traces + discovery
10. Applications, incidents, predictions, and assistant flows use the onboarded data

## Key Product Principle
The platform should feel like:
- one central AIOps control plane
- one new Fleet / Config onboarding area
- one managed install path per environment

Not:
- a bundle of unrelated exporters that clients assemble manually

## Immediate Next Build Recommendation
Build next in this order:
1. `Fleet` navigation and page scaffolding
2. Linux target onboarding flow
3. telemetry profile model
4. enrollment token model
5. generated Linux install command
6. target heartbeat / fleet status model
7. discovered service inventory
8. topology generation from traces + discovery

That gives the cleanest path from the current demo platform to a client-ready control plane.
