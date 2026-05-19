# Production Readiness Gaps

This document captures the main gaps to close before positioning OpsMitra as a production-grade platform.

## Current Position

OpsMitra has a strong foundation for a self-hosted, local-AI incident control plane:

- Django control plane and React operator UI
- local vLLM-backed RCA and remediation reasoning
- incident, alert, timeline, evidence, replay, and remediation models
- controlled execution agents with policy gates
- Docker Compose deployment
- Helm charts for the control plane and Kubernetes monitored-cluster agent
- code-context and runbook grounding paths

The platform is suitable for pilots and controlled internal production trials. It is not yet at the maturity level of enterprise observability or incident-response platforms such as Datadog, Dynatrace, PagerDuty, BigPanda, New Relic, Splunk ITSI, or Grafana IRM.

The strongest product wedge remains:

> Self-hosted, local-AI incident investigation and policy-controlled remediation for regulated teams that cannot send sensitive telemetry, logs, traces, source context, or remediation decisions to an external SaaS copilot.

## Kubernetes Deployment Gaps

### 1. High Availability

Current state:

- Most workloads run as a single replica.
- Web, predictor, Postgres, Redis, Jaeger, VictoriaMetrics, and OpenTelemetry Collector are not HA.

Required changes:

- Add configurable replica counts for stateless components.
- Add `PodDisruptionBudget` for web, frontend, predictor, and agents.
- Add anti-affinity or topology spread constraints.
- Add a production values profile with at least two web replicas.
- Ensure long-running SSE/investigation streaming behavior works with multiple web pods.

### 2. Database Production Strategy

Current state:

- Helm chart deploys Postgres as a plain `Deployment`.
- No built-in backup, restore, PITR, or failover strategy.

Required changes:

- Recommend managed Postgres for production by default.
- If in-cluster Postgres remains supported, move it to `StatefulSet`.
- Add backup/restore documentation.
- Add a backup CronJob or document integration with Velero, CloudNativePG, Crunchy, or platform-native snapshots.
- Add migration safety notes for upgrades.
- Add DB connection pool sizing guidance.

### 3. Redis / Valkey Persistence

Current state:

- Compose uses persistent Redis data.
- Helm Redis deployment does not mount a PVC.

Required changes:

- Add Redis PVC support in Helm values.
- Add configurable persistence mode.
- Document whether Redis is durable state or operational cache.
- For production, consider external managed Redis or HA Valkey.

### 4. Migrations And Upgrade Safety

Current state:

- Docker Compose web and predictor both enter through `entrypoint.sh`, which waits for Postgres and runs `python3 manage.py migrate --noinput`.
- Helm includes a pre-upgrade migration Job so schema changes are applied before workload rollout on upgrades.
- Web and predictor startup remains idempotent and still runs migrations as a defensive fallback before serving traffic or running background loops.

Remaining production guidance:

- Add rollback guidance when a migration has already been applied.
- For first-time installs using the chart-managed Postgres, startup migration remains the install-time gate because the database service is created by the same release.

### 5. Probes And Health Checks

Current state:

- Web has readiness probe.
- Several services lack liveness/readiness/startup probes.

Required changes:

- Add liveness and readiness probes for:
  - web
  - frontend
  - predictor
  - Postgres
  - Redis
  - OpenTelemetry Collector
  - VictoriaMetrics
  - Jaeger
  - cluster agent
- Add a lightweight backend health endpoint that does not require login.

### 6. Resource Requests And Limits

Current state:

- Helm values expose resource blocks, but defaults are empty.

Required changes:

- Add default requests/limits for all components.
- Add values profiles:
  - `values-small.yaml`
  - `values-prod.yaml`
  - `values-ha.yaml`
- Document sizing by number of services, alerts per minute, retention, and concurrent users.

### 7. Network Policies

Current state:

- No Kubernetes `NetworkPolicy` resources.

Required changes:

- Restrict web egress to Postgres, Redis, vLLM, observability backends, and configured integrations.
- Restrict DB and Redis ingress to trusted control-plane pods.
- Restrict cluster-agent egress to control-plane API only where possible.
- Document required ports for monitored clusters.

### 8. Secret Management

Current state:

- Helm values include secret values directly.

Required changes:

- Support existing Kubernetes Secret references.
- Add ExternalSecrets support.
- Document SOPS, SealedSecrets, or cloud secret-manager workflows.
- Avoid recommending secrets in committed values files.
- Rotate guidance for:
  - `AGENT_SECRET_TOKEN`
  - `MCP_INTERNAL_TOKEN`
  - `AIOPS_INTENT_SIGNING_SECRET`
  - DB credentials
  - SSO credentials
  - vLLM API key

### 9. TLS And Ingress

Current state:

- Ingress exists but TLS/cert-manager flow is minimal.

Required changes:

- Add cert-manager examples.
- Add production ingress examples for nginx and cloud ingress controllers.
- Set secure cookie defaults when TLS is enabled.
- Document `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and public base URL.

### 10. Observability Stack Production Mode

Current state:

- Chart deploys single-instance Jaeger, OpenTelemetry Collector, and VictoriaMetrics.

Required changes:

- Document local observability stack as pilot/default mode.
- Add production mode for external observability backends.
- Support external Prometheus/VictoriaMetrics, Tempo/Jaeger, OpenSearch/Splunk.
- Add retention and storage sizing guidance.
- Add self-monitoring dashboards for OpsMitra itself.

### 11. Cluster Agent RBAC And Action Controls

Current state:

- Cluster agent has read-only discovery RBAC.
- Docs mention rollout restart remediation.

Required changes:

- Split RBAC profiles:
  - read-only discovery
  - diagnostics
  - restart remediation
  - broader admin actions
- Make write permissions opt-in.
- Add namespace scoping option.
- Add audit log for every polled command and result.
- Add policy mapping between control-plane approval and Kubernetes action permissions.

## Platform Product Gaps

### 1. Incident Lifecycle Semantics

Current state:

- Recent changes establish: one alert lifecycle maps to one incident.
- Repeated same lifecycle updates existing incident.
- Grouped Alertmanager sibling alerts create separate incidents.

Required changes:

- Document lifecycle rules clearly.
- Add configurable dedupe windows.
- Add flapping detection.
- Add maintenance window suppression.
- Add incident merge/split actions for operators.
- Add incident archive/restore views.

### 2. Alert Noise And Correlation

Current state:

- Alert grouping is now conservative to preserve per-alert tracking.

Required changes:

- Add optional correlation mode for teams that want grouped incidents.
- Add event rules:
  - suppress
  - route
  - enrich
  - dedupe
  - escalate
- Add topology-aware correlation as an optional mode.
- Add alert volume dashboards.
- Add noise-reduction reporting.

### 3. RBAC And Multi-Tenancy

Current state:

- Tenant, membership, invitation, and audit-event models exist.
- Operational records are tenant-owned and the remaining nullable tenant foreign keys are closed by migration `0029_alter_alertevent_tenant_and_more`.
- Endpoint read/write checks now cover tenant, incident, alert, investigation, integration, fleet, execution, cache, lifecycle, code-context, and operations surfaces.
- React includes tenant switching and a tenant member management page for administrators at `/settings/members`.

Remaining changes:

- Scope access by application, environment, team, or target.
- Add invitation email delivery and password/SSO onboarding workflow for newly created users.
- Add a richer role assignment workflow if approver/responder duties need to be separated beyond the current role permissions.

### 4. Remediation Safety

Current state:

- Policy engine, typed actions, approval tokens, allowlists, and controlled agents exist.

Required changes:

- Add explicit dry-run mode for every remediation where possible.
- Add rollback metadata and rollback action support.
- Add break-glass workflow.
- Add approval UI with approver identity and reason.
- Add environment-aware policy packs.
- Add remediation blast-radius estimation before execution.
- Add execution rate limits per service/environment.
- Add post-action verification requirements before marking incidents resolved.

### 5. Audit And Compliance

Current state:

- Timeline events, evidence bundles, execution intents, remediation outcomes, and tenant audit events exist.
- Privileged tenant, integration, cache, alert-rule, execution, fleet, runbook, SLA, narrative, and operator-feedback actions write audit events.

Required changes:

- Add exportable audit report per incident.
- Add evidence retention policy UI.
- Add legal hold workflow.
- Add tamper-evident hashes for evidence bundles.
- Add compliance docs for regulated customers.

### 6. Integrations

Current state:

- Integration model and vendor adapters exist.

Required changes:

- Harden and document production integrations for:
  - Prometheus / VictoriaMetrics
  - OpenSearch
  - Splunk
  - Datadog
  - Dynatrace
  - AWS CloudWatch
  - Jaeger / Tempo
  - GitHub / GitLab
  - Jira
  - ServiceNow
  - Slack
  - Microsoft Teams
  - Okta / SAML / OIDC
- Add integration health dashboards.
- Add credential rotation workflow.
- Add per-integration test and validation endpoints.

### 7. User Experience

Current state:

- React UI covers incidents, alerts, investigations, integrations, fleet, code context, predictions, and documents.

Required changes:

- Improve incident list density and filtering.
- Add saved filters.
- Add owner/team/service filters.
- Add incident number search.
- Add archive/restore view.
- Add explicit deep-dive status per incident.
- Add clear policy-block UI for commands.
- Add timeline diff between initial LLM recommendation, executed command, and post-action analysis.
- Add mobile-friendly incident response view.

### 8. Evaluation And Trust

Current state:

- Replay and evaluation models exist.

Required changes:

- Add golden incident scenarios.
- Add RCA accuracy scoring.
- Add hallucination/unsupported-claim detection.
- Add regression suite for prompts and model versions.
- Add behavior-version dashboards.
- Show why an LLM recommendation was accepted, modified, or blocked.
- Add operator feedback loop reporting.

### 9. Scalability

Current state:

- Good for pilots and local demos.
- High-volume production behavior is not proven.

Required changes:

- Load test alert ingestion.
- Load test concurrent investigations.
- Load test SSE streaming.
- Load test large incident timelines.
- Benchmark log/trace/metric retrieval latency.
- Add queueing for expensive investigation work.
- Consider worker process separation for LLM investigations.
- Add backpressure controls for alert storms.

### 10. Deployment And Operations

Required changes:

- Add production install checklist.
- Add upgrade checklist.
- Add backup/restore checklist.
- Add disaster recovery runbook.
- Add environment promotion workflow.
- Add chart CI with `helm lint` and `helm template`.
- Add smoke test Job after install.
- Add versioned release notes and migration notes.

## Recommended Production Roadmap

### Phase 1: Pilot Hardening

- Finalize incident lifecycle rules.
- Add migration Job.
- Add health endpoint and probes.
- Add resource defaults.
- Add incident archive/restore UI.
- Add Slack or Teams notifications.
- Add ServiceNow or Jira ticket creation.
- Add read-only production mode.

### Phase 2: Controlled Production

- External managed Postgres support.
- Backup/restore docs.
- NetworkPolicies.
- ExternalSecrets support.
- RBAC roles and approval UI.
- Production ingress/TLS examples.
- Alert storm backpressure.
- Investigation worker queue.

### Phase 3: Enterprise Readiness

- HA chart profile.
- Multi-team access controls.
- Compliance audit exports.
- Advanced event rules.
- Optional topology-aware correlation.
- Full integration health center.
- Formal evaluation dashboard.
- Disaster recovery certification runbook.

## Positioning Guidance

Do not position OpsMitra as a full replacement for Datadog, Dynatrace, PagerDuty, BigPanda, Splunk, or Grafana on day one.

Position it as:

> A self-hosted AI incident control plane that works beside existing observability tools, turns alerts into evidence-grounded investigations, maps failures back to code and runtime context, and executes remediations only through explicit policy and approval boundaries.

That positioning is credible and differentiated.
