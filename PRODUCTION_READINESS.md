# OpsMitra Production Readiness

Last updated: 2026-05-14

This file tracks what has already been implemented and what still needs to be completed before taking OpsMitra into production.

## Current Position

OpsMitra is now beyond demo-only state. It has the core shape of a self-hosted AIOps control plane:

- Alert ingestion, incident creation, incident numbering, incident archive/delete.
- One alert lifecycle maps to one incident; repeated events in the same lifecycle update the same incident.
- Grouped Alertmanager payloads preserve per-alert incident tracking instead of collapsing sibling alerts into one ticket.
- Local vLLM-based investigation, deep-dive generation, diagnostic planning, and remediation recommendation.
- React operator UI for alerts, incidents, investigations, integrations, fleet, analytics, and tenant access control.
- Controlled execution path with typed actions, policy evaluation, approval gates, dry-run handling, rollback metadata, break-glass controls, and post-action verification.
- Multi-tenancy and RBAC across critical backend endpoints and React navigation.
- Integration framework for observability, ITSM, notification, cloud, DevOps, and code/change providers.
- Docker Compose deployment and Helm/Kubernetes deployment assets.

The platform is suitable for controlled internal production trials after environment-specific configuration, security review, and operational runbooks are completed. It should still be positioned as an AI incident control plane that works beside existing observability/ITSM systems, not as a full day-one replacement for Datadog, Dynatrace, PagerDuty, BigPanda, Splunk, or Grafana.

## Implemented

### Incident Lifecycle

- Unique incident numbers were added.
- Incident archive/delete exists on the backend and React incidents page.
- Repeated alert notifications update the same incident only when they are part of the same alert lifecycle.
- New alert lifecycle creates a new incident.
- Alertmanager grouped sibling alerts create separate incidents for separate alert identities.
- Incident timeline, graph, linked investigations, generated runbooks, SLA acknowledgement, and narrative generation are tenant-scoped.

### Alert Noise And Correlation

- Alert dedupe is conservative to preserve per-alert tracking.
- Alert suppression rules and maintenance windows exist.
- Correlation links are created for related incidents without preventing new per-alert incident creation.
- Alert noise stats endpoint exists.
- Topology/correlation support exists as related incident links rather than automatic incident merging.

### Deep Dive And LLM Output

- New incidents can trigger deep dive automatically.
- Cached incident data no longer overwrites fresh LLM remediation/command output.
- Frontend preserves backend-provided diagnostic command, remediation command, post-command analysis, and remediation output.
- Policy-blocked commands do not rewrite or hide the command recommended by the LLM; policy decision is surfaced separately.
- Investigation streams and live step projections exist for React investigation detail views.

### Remediation Safety

- Typed action inference exists for diagnostics and remediations.
- Execution policy evaluation exists through EGAP/policy engine.
- Approval token flow exists for commands requiring approval.
- Approval requires approver identity and approval reason.
- React safety panel supports approval, break-glass, rollback initiation, and verification.
- Approved remediation now continues through the actual execution path instead of stopping at approval.
- Break-glass is enforced server-side and requires a reason when policy requires it.
- Policy packs support environment-aware controls.
- Pre-execution blast radius estimation can force approval.
- Dry-run responses avoid agent dispatch.
- Database-change rollback snapshot capture exists for supported SQL mutations.
- Rollback endpoint creates rollback intents and attempts to derive rollback commands.
- Post-action verification can keep remediation status in `verification_pending`.
- Remediation outcomes and replay evaluations are recorded.
- Execution intents are tenant-owned.

### RBAC And Multi-Tenancy

- Tenant, membership, invitation, and tenant audit event models exist.
- Operational models are tenant-owned; nullable tenant foreign keys were closed by migration `0029_alter_alertevent_tenant_and_more`.
- Tenant query scoping excludes cross-tenant records.
- Backend permissions now cover tenant, incident, alert, investigation, integration, fleet, execution, cache, lifecycle, code-context, and operations surfaces.
- React tenant provider, tenant switcher, and permission-aware navigation exist.
- Admin member management UI exists at `/settings/members`.
- Tenant audit events are append-only at the Django model/signal layer.

### Audit Trail

- Tenant audit events are written for privileged tenant, integration, cache, alert-rule, execution, fleet, runbook, SLA, narrative, and operator-feedback actions.
- Incident timelines record diagnostic execution, remediation execution, policy blocks, approval, rollback initiation, and generated artifacts.
- ExecutionIntent stores policy decision, typed action, approval metadata, break-glass metadata, rollback metadata, blast-radius estimate, verification result, and response payload.

### Integrations

- Integration model, credentials, bindings, health checks, and writeback tickets exist.
- Observability/cloud/vendor adapters exist for Prometheus/VictoriaMetrics, OpenSearch, Splunk, Datadog, Dynatrace, AWS, Jaeger/Tempo-style traces, and miscellaneous sources.
- ITSM/notification/devops adapters exist for ServiceNow, Jira, PagerDuty/Opsgenie-style alerting, Slack, Teams, GitHub, GitLab, Bitbucket, Jenkins, Argo CD, Flux CD, Kubernetes, and custom providers.
- Incident writeback is conditional: only configured/enabled integrations should be used. If only ServiceNow is configured, it should not try to create PagerDuty/Jira/etc. tickets.
- Integration health checking command exists.
- React integration catalog includes observability, cloud, ITSM, notification, DevOps, CI/CD, and code providers.

### Deployment

- Docker Compose startup runs migrations automatically through `entrypoint.sh`.
- Predictor also uses the same startup migration path defensively.
- Helm chart includes migration job assets for Kubernetes upgrades.
- Helm assets exist for web, frontend, predictor, integration health cron, and cluster-agent related deployment.
- Kubernetes monitored-cluster onboarding/install assets exist.

### Signal Analytics

- Signal Heatmap: services × time-bucket alert density matrix, DB-aggregated via `TruncHour/TruncDay/TruncMinute`, color-encoded by count and peak severity, responsive D3 canvas with time-range picker (1h / 6h / 24h / 7d) and hover tooltips.
- Correlated Timeline: unified event stream across alerts, incidents, and execution intents on a shared time axis with swim lanes, quadratic Bézier correlation connectors linking events by `incident_key`, D3 brush zoom, and break-glass highlighting.
- Both views are tenant-scoped, DB-aggregated (no Python loops over large querysets), capped against runaway queries, and auto-refresh every 30 seconds via React Query.
- Heatmap queries `IncidentAlert` (full per-firing history) rather than `AlertEvent` (upsert model, only latest state per alert identity) so density reflects actual alert volume over time.
- Cross-linking: clicking a heatmap cell filters the timeline to that service; clicking a timeline event surfaces an "Open Incident" action strip.

### Predictor / Intelligence

- Prediction/intelligence pages and backend prediction models exist.
- Predictor deployment configuration exists in Compose and Helm.
- Predictor startup/migration handling was aligned with the rest of the stack.

## Recently Fixed During Review

- Approval-required remediation no longer gets stuck after approval; second request with approval token executes the original intent.
- Break-glass now requires a reason server-side when policy requires it.
- Break-glass respects policy packs that disable break-glass.
- Execution intents created by the execute endpoint now use the active request tenant.
- React safety panel now feeds approval back into the execute flow instead of only marking the intent approved.
- Tenant audit events cannot be modified or deleted through normal Django model operations.

## Remaining Work Before Production

### P0 - Must Complete Before Live Production

- Run a full end-to-end test in Docker Compose with Postgres, Redis, vLLM, frontend, web, predictor, and at least one agent.
- Run a full Kubernetes install/upgrade test using the Helm chart and migration job.
- Validate ServiceNow/Jira/PagerDuty/Slack/Teams writeback behavior with real tokens in a staging environment.
- Validate that integration writeback only calls configured integrations and degrades cleanly when others are absent.
- Add a lightweight unauthenticated health endpoint for Kubernetes probes.
- Add liveness/readiness/startup probes for web, frontend, predictor, Redis, Postgres, OTel collector, VictoriaMetrics, Jaeger, and cluster agent.
- Add production secret handling using Kubernetes Secret references or ExternalSecrets.
- Configure secure cookie, CSRF, allowed hosts, TLS, and ingress settings for the production domain.
- Add backup and restore process for Postgres.
- Decide whether Redis/Valkey is cache-only or durable operational state; configure persistence or external managed Redis accordingly.
- Add production resource requests/limits.
- Remove or gate any demo-only data seeding in production mode.
- Run load tests for alert ingestion, incident list, investigation streaming, and concurrent remediation execution.
- Review command allowlists and Kubernetes agent RBAC before enabling write actions.

### P1 - Strongly Recommended For Controlled Production

- Complete rollback execution UX: rollback intent creation exists, but the operator flow to approve and execute rollback should be tightened end-to-end.
- Add incident restore UI for archived incidents.
- Add incident merge/split actions for operators.
- Add saved filters and better incident search by incident number, service, owner, team, environment, and status.
- Add audit export per incident.
- Add integration health dashboard in React.
- Add credential rotation workflow for integrations.
- Add tenant invitation email delivery and SSO/password onboarding for newly created users.
- Add application/team/environment/target-level access scoping on top of tenant-level RBAC.
- Add alert storm backpressure controls.
- Add worker queue separation for expensive LLM investigations.
- Add production values profiles: `values-small.yaml`, `values-prod.yaml`, `values-ha.yaml`.
- Add NetworkPolicies.
- Add disaster recovery runbook.
- Add upgrade/rollback checklist for migrations.

### P2 - Enterprise Readiness

- HA profile for web/frontend/predictor and external managed Postgres/Redis.
- Topology-aware optional incident correlation mode.
- Formal golden incident scenario suite.
- RCA quality scoring and regression tracking by model/prompt/behavior version.
- Hallucination or unsupported-claim detection for LLM answers.
- Tamper-evident evidence bundle hashes.
- Legal hold workflow.
- Compliance documentation for regulated customers.
- Advanced event rules: suppress, route, enrich, dedupe, escalate.
- Full integration marketplace/health center.
- Formal release notes and migration notes per version.

## Production Deployment Checklist

Before going live:

- Set `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, public base URL, and TLS/ingress values.
- Set strong values for `SECRET_KEY`, `AGENT_SECRET_TOKEN`, `MCP_INTERNAL_TOKEN`, and `AIOPS_INTENT_SIGNING_SECRET`.
- Use managed Postgres or production-grade in-cluster Postgres with backups.
- Use managed Redis/Valkey or configure persistence/HA.
- Configure vLLM endpoint and model availability.
- Configure only the integrations actually used by the environment.
- Disable demo-only test data and sample credentials.
- Apply migrations through the Helm migration job or startup migration path.
- Verify tenant/admin user bootstrap.
- Verify RBAC with viewer, responder/operator, admin, and owner accounts.
- Verify incident creation from a real alert payload.
- Verify deep dive, diagnostic command, approval-required remediation, break-glass blocked/allowed cases, rollback initiation, and post-action verification.
- Verify integration ticket creation with one enabled ITSM system and absent optional systems.
- Verify audit events and incident timeline entries for all privileged actions.

## Known Risks

- Rollback support is partially implemented. It creates rollback intents and can generate rollback commands, including snapshot-based SQL rollback for supported cases, but rollback execution UX needs a dedicated final pass.
- High-volume behavior is not proven until load testing is completed.
- Production Kubernetes HA behavior is not proven until multi-replica and failover tests are completed.
- Integration behavior depends on real provider API contracts and tokens; each provider needs staging validation.
- Tenant-level RBAC exists, but fine-grained app/team/environment/target scoping is still pending.
- Evidence retention, legal hold, and compliance exports are not complete.

## Positioning

Credible production positioning:

> OpsMitra is a self-hosted AI incident control plane that works beside existing observability and ITSM tools, turns alerts into evidence-grounded investigations, maps failures back to runtime and code context, and executes remediations only through explicit policy, approval, audit, and rollback boundaries.

Avoid positioning it as a full replacement for enterprise observability suites on day one. The strongest initial wedge is regulated or privacy-sensitive teams that want local AI-assisted incident investigation and controlled remediation without sending telemetry, logs, traces, code context, or remediation decisions to an external SaaS copilot.
