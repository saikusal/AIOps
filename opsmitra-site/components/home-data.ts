export const uspTriad = [
  {
    badge: "Air-Gapped",
    color: "blue",
    headline: "Zero bytes leave your network. Ever.",
    copy: "Every inference call — RCA, blast radius analysis, remediation planning, post-mortem generation — runs on your own GPU via a local vLLM instance. No cloud API keys. No telemetry egress. Your incident data never touches a third-party server.",
    proof: ["Local vLLM inference on your GPU", "No internet required at runtime", "GDPR · PCI-DSS · HIPAA compatible"],
  },
  {
    badge: "Self-Hosted",
    color: "violet",
    headline: "Your infra. Your models. Your control plane.",
    copy: "Bring your own LLM, your own observability stack, your own code repositories, and your own agents. OpsMitra deploys inside your network perimeter — on-prem, private cloud, or air-gapped data center — with full operator control over every component.",
    proof: ["Docker Compose or Kubernetes Helm chart", "BYOL — any vLLM-compatible model", "Full Helm chart with migration jobs"],
  },
  {
    badge: "Code-Aware",
    color: "mint",
    headline: "From service symptom to the exact handler.",
    copy: "Every other AIOps tool stops at the service boundary. OpsMitra traces the incident path into your repositories: matching the failing route to the handler function, the span to the module, the error to the recent commit that introduced it, and the blast radius into downstream owners.",
    proof: ["Repo · Route · Handler · Span graph", "Recent change and deployment correlation", "Blast radius mapped into source ownership"],
  },
];

export const comparison = [
  { capability: "Air-gapped / no data egress",        opsmitra: true,      datadog: false,      newrelic: false,     grafana: "partial", pagerduty: false },
  { capability: "Fully self-hosted deployment",        opsmitra: true,      datadog: false,      newrelic: false,     grafana: true,      pagerduty: false },
  { capability: "Code-aware RCA (handler/route/span)", opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "Incident to source commit tracing",   opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "Multi-step streaming investigations", opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "AI-generated runbooks",               opsmitra: true,      datadog: "partial",  newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "Policy-gated governed remediation",   opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: "partial" },
  { capability: "Local LLM inference (no cloud AI)",   opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "Fleet / agent management",            opsmitra: true,      datadog: "partial",  newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "Change blast radius analysis",        opsmitra: true,      datadog: "partial",  newrelic: "partial", grafana: false,     pagerduty: false },
  { capability: "Alert noise suppression rules",       opsmitra: true,      datadog: true,       newrelic: "partial", grafana: "partial", pagerduty: "partial" },
  { capability: "Data lifecycle / retention governance", opsmitra: true,    datadog: "partial",  newrelic: "partial", grafana: false,     pagerduty: false },
  { capability: "BYOL — bring your own model",         opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: false },
  { capability: "Industrial OT / IIoT support",        opsmitra: true,      datadog: false,      newrelic: false,     grafana: false,     pagerduty: false },
];

export const industries = [
  {
    tier: "industrial",
    name: "Manufacturing & Industrial OT",
    reason: "CNC machines, PLCs, and SCADA networks. Air-gapped AI reasoning for environments where downtime costs thousands per minute and cloud telemetry egress is prohibited.",
    protocols: ["OPC-UA", "MTConnect", "Modbus TCP"],
  },
  {
    tier: "it",
    name: "SaaS & Fintech",
    reason: "Full-stack observability correlation across Kubernetes and microservices. Data residency requirements and PCI-DSS mandate on-prem AI for payment-adjacent telemetry.",
    protocols: ["Prometheus", "Datadog", "Jaeger"],
  },
  {
    tier: "domain",
    name: "Pharma & Healthcare",
    reason: "CFR Part 11 compliant audit trails with sovereign data control. HIPAA limits where patient-adjacent telemetry can travel — OpsMitra never sends it anywhere.",
    protocols: ["InfluxDB", "OSIsoft PI", "HL7"],
  },
  {
    tier: "domain",
    name: "Defence & Public Sector",
    reason: "Air-gapped networks prohibit cloud tooling entirely. Sovereign data requirements block SaaS AIOps. OpsMitra runs fully inside the classified boundary.",
    protocols: ["Splunk", "Custom REST", "MIL-STD"],
  },
  {
    tier: "it",
    name: "Telco & Critical Infrastructure",
    reason: "Network failures cascade in seconds. OpsMitra correlates across topology, config, code, and real-time spans to pinpoint the fault path before impact spreads.",
    protocols: ["SNMP", "gRPC", "OpenTelemetry"],
  },
  {
    tier: "domain",
    name: "Energy & Utilities",
    reason: "Grid operations and smart meters generate OT + IT telemetry. OpsMitra unifies them inside your air-gapped control boundary with full audit trails.",
    protocols: ["DNP3", "IEC 61850", "MQTT"],
  },
];

export const integrationCatalog = [
  // IT Observability
  { name: "Prometheus",        category: "it",   desc: "Metrics",              icon: "metrics"    },
  { name: "VictoriaMetrics",   category: "it",   desc: "Metrics",              icon: "metrics"    },
  { name: "Grafana",           category: "it",   desc: "Dashboards",           icon: "metrics"    },
  { name: "Splunk",            category: "it",   desc: "Logs",                 icon: "logs"       },
  { name: "Elasticsearch",     category: "it",   desc: "Logs",                 icon: "logs"       },
  { name: "OpenSearch",        category: "it",   desc: "Logs",                 icon: "logs"       },
  { name: "Loki",              category: "it",   desc: "Log Aggregation",      icon: "logs"       },
  { name: "Datadog",           category: "it",   desc: "Mixed Observability",  icon: "mixed"      },
  { name: "Dynatrace",         category: "it",   desc: "Traces / Topology",    icon: "traces"     },
  { name: "New Relic",         category: "it",   desc: "APM / Observability",  icon: "traces"     },
  { name: "Jaeger",            category: "it",   desc: "Distributed Traces",   icon: "traces"     },
  { name: "Tempo",             category: "it",   desc: "Distributed Traces",   icon: "traces"     },
  { name: "InfluxDB",          category: "it",   desc: "Time-series DB",       icon: "metrics"    },
  { name: "PagerDuty",         category: "it",   desc: "Alerting",             icon: "mixed"      },
  { name: "OpsGenie",          category: "it",   desc: "Alerting",             icon: "mixed"      },
  { name: "Alertmanager",      category: "it",   desc: "Alert Routing",        icon: "mixed"      },
  // ITSM & Notification
  { name: "ServiceNow",        category: "itsm", desc: "ITSM / Ticketing",     icon: "itsm"       },
  { name: "Jira",              category: "itsm", desc: "Issue Tracking",       icon: "itsm"       },
  { name: "Slack",             category: "itsm", desc: "Notifications",        icon: "notify"     },
  { name: "Microsoft Teams",   category: "itsm", desc: "Notifications",        icon: "notify"     },
  { name: "GitHub",            category: "itsm", desc: "Source Control",       icon: "devops"     },
  { name: "GitLab",            category: "itsm", desc: "Source Control",       icon: "devops"     },
  { name: "Bitbucket",         category: "itsm", desc: "Source Control",       icon: "devops"     },
  { name: "Jenkins",           category: "itsm", desc: "CI/CD",                icon: "devops"     },
  { name: "Argo CD",           category: "itsm", desc: "GitOps",               icon: "devops"     },
  { name: "Flux CD",           category: "itsm", desc: "GitOps",               icon: "devops"     },
  { name: "Kubernetes",        category: "itsm", desc: "Container Orchestration", icon: "devops" },
  { name: "Nagios",            category: "itsm", desc: "Infrastructure Monitoring", icon: "mixed" },
  // OT
  { name: "OPC-UA",            category: "ot",   desc: "Universal OT Standard", icon: "industrial" },
  { name: "MTConnect",         category: "ot",   desc: "CNC Telemetry",        icon: "industrial" },
  { name: "Modbus TCP",        category: "ot",   desc: "Legacy PLCs",          icon: "industrial" },
  { name: "MQTT",              category: "ot",   desc: "IIoT Sensors",         icon: "industrial" },
  { name: "OSIsoft PI",        category: "ot",   desc: "Process Historian",    icon: "industrial" },
  { name: "PROFINET",          category: "ot",   desc: "Industrial Ethernet",  icon: "industrial" },
  { name: "DNP3",              category: "ot",   desc: "SCADA / Utilities",    icon: "industrial" },
  { name: "EtherNet/IP",       category: "ot",   desc: "PLC Networking",       icon: "industrial" },
  // Cloud
  { name: "AWS CloudWatch",    category: "cloud", desc: "Cloud Metrics",       icon: "cloud"      },
  { name: "Azure Monitor",     category: "cloud", desc: "Cloud Metrics",       icon: "cloud"      },
  { name: "GCP Operations",    category: "cloud", desc: "Cloud Metrics",       icon: "cloud"      },
  { name: "AWS X-Ray",         category: "cloud", desc: "Distributed Tracing", icon: "cloud"      },
  { name: "Azure Sentinel",    category: "cloud", desc: "SIEM",                icon: "cloud"      },
  { name: "GCP BigQuery",      category: "cloud", desc: "Analytics",           icon: "cloud"      },
  { name: "AWS OpenSearch",    category: "cloud", desc: "Managed Search",      icon: "cloud"      },
  { name: "Azure Log Analytics", category: "cloud", desc: "Log Management",    icon: "cloud"      },
];

export const pillars = [
  {
    title: "See The Full Runtime Story",
    copy: "Unify telemetry, topology, incidents, predictions, and signal analytics into one operating view so teams stop context-switching during active failures.",
  },
  {
    title: "Trace Incidents Into Code",
    copy: "Map live failures to repositories, handlers, spans, modules, and recent commits so RCA stops at the exact code path instead of the service boundary.",
  },
  {
    title: "Recommend Safe Actions",
    copy: "Governed, policy-aware remediation plans with approval controls, break-glass boundaries, rollback snapshots, and post-execution verification before any action is taken.",
  },
  {
    title: "Manage The Fleet",
    copy: "Enroll Linux servers, Kubernetes clusters, and OT targets from one control plane. Push policies, run diagnostics, and maintain heartbeat visibility across every managed node.",
  },
];

export const workflow = [
  { step: "01", title: "Ingest",    copy: "OpsMitra normalizes alerts, logs, traces, metrics, topology, change events, and OT telemetry from 40+ sources into a unified signal store." },
  { step: "02", title: "Diagnose",  copy: "A multi-step investigation engine collects evidence, scores hypotheses, adapts the plan in real time, and streams progress to the operator — not a static post-hoc report." },
  { step: "03", title: "Correlate", copy: "Signal analytics surface alert density patterns. Correlation links connect alerts, incidents, and executions across services by shared incident key and timeline position." },
  { step: "04", title: "Explain",   copy: "Operators receive plain-language reasoning grounded in handler code, span data, recent commits, and blast radius — with AI-generated runbooks and incident narratives on demand." },
  { step: "05", title: "Remediate", copy: "Ranked remediation plans are policy-checked, approval-gated where required, executed through governed agents, verified post-action, and fully recorded in the audit trail." },
];

export const modules = [
  "Domain Onboarding",
  "Unified Ingestion",
  "Alert Intelligence",
  "Incident Command",
  "Streaming Investigations",
  "Code Context Graph",
  "Change Risk Analysis",
  "Signal Analytics",
  "Prediction Engine",
  "Safe Remediation",
  "Fleet Management",
  "Audit & Data Lifecycle",
];

export const differentiators = [
  {
    eyebrow: "Code-Aware RCA",
    title: "From service symptom to module-level explanation",
    copy: "OpsMitra does not stop at logs and metrics. It follows the path into handlers, spans, repository ownership, and recent code changes — with blast radius mapped to downstream service owners.",
  },
  {
    eyebrow: "Sovereign By Design",
    title: "Built for air-gapped and self-hosted environments",
    copy: "Run your own models, your own observability stack, and your own code indexing. No telemetry egress, no cloud API keys, no vendor dependency on your incident data.",
  },
  {
    eyebrow: "Governed Automation",
    title: "Agentic workflows with hard safety boundaries",
    copy: "Every action is policy-evaluated, approval-gated, blast-radius-checked, rollback-snapshotted, and audit-logged. The LLM recommends. The platform decides.",
  },
  {
    eyebrow: "Fleet Intelligence",
    title: "One control plane for every managed node",
    copy: "Enroll Kubernetes clusters, Linux servers, and OT machines. Push policies, run remote diagnostics, and maintain real-time heartbeat visibility across the entire managed fleet.",
  },
  {
    eyebrow: "Living Investigations",
    title: "Multi-step streaming RCA, not static reports",
    copy: "Investigations run as adaptive multi-step workflows — collecting evidence, scoring confidence, and streaming progress in real time so operators see the reasoning unfold, not a final summary after the fact.",
  },
  {
    eyebrow: "Signal Analytics",
    title: "Alert density heatmaps and correlated timelines",
    copy: "Service × time-bucket heatmaps surface alert density patterns. A correlated timeline merges alerts, incidents, and executions on one axis with connectors linking events to the incident they caused.",
  },
];

export const stats = [
  { value: "40+",          label: "Integration connectors" },
  { value: "Zero Egress",  label: "No data leaves your network" },
  { value: "Code-Path RCA", label: "Down to handler, route, and commit" },
  { value: "IT + OT",      label: "K8s clusters to PLC machines" },
];

export const productShots = [
  {
    title: "Streaming Investigation",
    copy: "Multi-step AI investigation streams evidence collection, hypothesis scoring, and code-path tracing in real time — operators watch the reasoning unfold, not a static report.",
    mode: "incident",
  },
  {
    title: "Code Context Graph",
    copy: "Trace a runtime issue into repositories, handlers, spans, modules, and recent commits instead of stopping at the service boundary.",
    mode: "code",
  },
  {
    title: "Governed Remediation",
    copy: "Every action is policy-evaluated, approval-gated, blast-radius-checked, and verified after execution so automation stays inside operational guardrails.",
    mode: "remediation",
  },
] as const;

export const egapSteps = [
  { step: "01", name: "Intent",       color: "blue",   desc: "Operator or AI recommends an action. OpsMitra creates a typed ExecutionIntent with action type, target service, environment, and command preview." },
  { step: "02", name: "Policy",       color: "violet", desc: "EGAP evaluates the intent against active PolicyPacks. Environment-aware rules decide: auto-approve, require human approval, or block entirely." },
  { step: "03", name: "Blast Radius", color: "orange", desc: "Pre-execution blast radius estimation maps downstream services and owners at risk. High-impact actions force a mandatory approval gate." },
  { step: "04", name: "Approval",     color: "amber",  desc: "Paused intents require an approver identity and written reason. Break-glass overrides are server-enforced, reason-required, and audit-logged." },
  { step: "05", name: "Execute",      color: "green",  desc: "Approved intents dispatch through the governed fleet agent. Rollback snapshots capture system state before any mutation is applied." },
  { step: "06", name: "Verify",       color: "teal",   desc: "Post-action verification confirms the outcome matches expectations. Failed verifications hold the intent in verification_pending for operator review." },
];

export const protocolStack = [
  {
    name: "EGAP",
    full: "Execution & Governance Action Protocol",
    color: "violet",
    desc: "The policy-gated execution layer. Every remediation action passes through typed intent inference, PolicyPack evaluation, blast radius assessment, approval gate, governed agent dispatch, and post-execution verification. The LLM recommends. EGAP decides.",
    tags: ["ExecutionIntent", "PolicyPack", "BlastRadius", "ApprovalToken", "BreakGlass", "RollbackSnapshot", "PostVerification"],
  },
  {
    name: "MCP",
    full: "Model Context Protocol",
    color: "blue",
    desc: "18 structured context providers give the AI reasoning engine real-time, typed access to incidents, topology, metrics, logs, traces, code ownership, recent deployments, and blast radius data — without free-form retrieval hallucination.",
    tags: ["IncidentSummary", "TopologyGraph", "ServiceMetrics", "LogSearch", "TraceSearch", "RouteHandler", "SpanSymbol", "RecentChanges", "BlastRadius"],
  },
  {
    name: "AIP",
    full: "Alert Ingest Pipeline",
    color: "mint",
    desc: "Normalizes Alertmanager payloads into IncidentAlert records, evaluates suppression rules and maintenance windows, correlates alerts to incidents via lifecycle key, and deduplicates repeated firings without losing per-alert incident tracking.",
    tags: ["IncidentAlert", "LifecycleKey", "AlertSuppression", "MaintenanceWindow", "IncidentCorrelation", "AlertDedup"],
  },
  {
    name: "CCG",
    full: "Code Context Graph",
    color: "orange",
    desc: "Maps runtime services to source repositories, API routes to handler functions, distributed trace spans to source symbols, and deployments to recent commits. Enables code-path RCA that stops at the exact line, not the service boundary.",
    tags: ["RepositoryIndex", "RouteBinding", "SpanBinding", "DeploymentBinding", "CodeChangeRecord", "SymbolRelation", "BlastRadiusIntoSource"],
  },
];

export const mcpToolGroups = [
  { group: "Incidents",     color: "amber",  tools: ["Incident Summary", "Incident Timeline"] },
  { group: "Applications",  color: "blue",   tools: ["App Overview", "Topology Graph", "Component Detail"] },
  { group: "Observability", color: "teal",   tools: ["Service Metrics", "Metrics Query", "Log Search", "Trace Search"] },
  { group: "Code Context",  color: "violet", tools: ["Service Owner", "Route Handler", "Span Symbol", "Recent Changes", "Recent Deployments", "Related Symbols", "Blast Radius", "Search Context", "Read Snippet"] },
  { group: "Knowledge",     color: "green",  tools: ["Runbook Search"] },
];

export const fleetCapabilities = [
  { icon: "🖥️", title: "Linux Server Enrollment",   desc: "One-command agent install via generated shell script. Automatic service discovery, log source binding, and policy application on first heartbeat." },
  { icon: "☸️", title: "Kubernetes Cluster Agent",   desc: "Full namespace, node, deployment, statefulset, daemonset, and ingress discovery. Pod-level metrics collection. Command polling and execution." },
  { icon: "📋", title: "Policy Push",                desc: "Apply TargetPolicyProfiles to enrolled nodes. Control collection intervals, log sources, allowed commands, and execution permissions per target." },
  { icon: "🔧", title: "Remote Diagnostics",         desc: "Dispatch diagnostic commands through the fleet agent. Stream results back to the control plane. Full audit trail on every dispatched command." },
  { icon: "💓", title: "Heartbeat Monitoring",       desc: "Every enrolled node reports health at configurable intervals. Missing heartbeats surface immediately in the fleet dashboard with last-seen timestamps." },
  { icon: "🏭", title: "OT Machine Support",         desc: "Enroll industrial targets running OPC-UA, Modbus, or MTConnect alongside IT fleet nodes in the same control plane with the same governance model." },
];

export const orbitalNodes = [
  { label: "Alerts",    angle: 0   },
  { label: "Metrics",   angle: 45  },
  { label: "Logs",      angle: 90  },
  { label: "Traces",    angle: 135 },
  { label: "Code",      angle: 180 },
  { label: "Fleet",     angle: 225 },
  { label: "Changes",   angle: 270 },
  { label: "Topology",  angle: 315 },
];

export const featureGrid = [
  {
    icon: "🔍",
    title: "Multi-Step Streaming Investigations",
    copy: "Adaptive investigation workflows collect evidence, score hypotheses, and stream progress via SSE. Each run produces a full evidence bundle, confidence scores, and a downloadable narrative.",
  },
  {
    icon: "📋",
    title: "AI Runbook Generation",
    copy: "OpsMitra generates actionable runbooks directly from live incident context — handler paths, evidence, blast radius, and recommended steps — ready to share or archive.",
  },
  {
    icon: "🗺️",
    title: "Signal Heatmap & Timeline",
    copy: "A service × time-bucket alert density heatmap and a correlated multi-lane timeline merge alerts, incidents, and remediations so operators see causality, not isolated events.",
  },
  {
    icon: "⚡",
    title: "Change Risk & Blast Radius",
    copy: "Before and after any deployment, OpsMitra estimates blast radius into downstream services, maps affected code owners, and surfaces recent change history correlated with live incidents.",
  },
  {
    icon: "🤖",
    title: "Fleet Management & Agents",
    copy: "Enroll Linux servers and Kubernetes clusters with one command. Push policy profiles, run remote diagnostics, stream command results, and monitor heartbeat for every managed node.",
  },
  {
    icon: "🔮",
    title: "Anomaly Prediction Engine",
    copy: "The predictor service forecasts SLO degradation and anomaly onset before thresholds breach, giving operators a window to act preventively.",
  },
  {
    icon: "🔇",
    title: "Alert Intelligence",
    copy: "User-defined noise suppression rules and maintenance windows filter alert storms. Anomaly explanation turns raw spikes into human-readable context before they reach the incident queue.",
  },
  {
    icon: "🔐",
    title: "RBAC With 6 Roles + SSO",
    copy: "Owner, Admin, Operator, Responder, Viewer, and Auditor roles with tenant isolation, workspace switching, invitation-based onboarding, and SSO support.",
  },
  {
    icon: "🗃️",
    title: "Data Lifecycle Governance",
    copy: "Configurable retention policies per data class, automated archival to object storage, lifecycle job execution logs, and retention holds for legal and compliance requirements.",
  },
  {
    icon: "🔗",
    title: "18 MCP Context Providers",
    copy: "Model Context Protocol tools give the AI engine structured access to incidents, metrics, logs, traces, topology, code ownership, recent changes, deployments, and blast radius data.",
  },
  {
    icon: "↩️",
    title: "Rollback & Verification",
    copy: "Execution intents capture rollback snapshots before acting. Post-action verification confirms success. Rollback intents reverse the change through the same governed path.",
  },
  {
    icon: "📑",
    title: "Audit Trail",
    copy: "Append-only tenant audit events record every privileged action — integration config, execution, approval, break-glass, cache purge, fleet enrollment, and SLA acknowledgement.",
  },
];
