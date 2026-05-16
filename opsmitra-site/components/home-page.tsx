"use client";

import { useState, useEffect, useRef } from "react";
import {
  SiPrometheus,
  SiVictoriametrics,
  SiDatadog,
  SiJaeger,
  SiOpensearch,
  SiSplunk,
  SiDynatrace,
  SiGrafana,
  SiInfluxdb,
  SiGooglecloud,
  SiMqtt,
  SiJira,
  SiGithub,
  SiGitlab,
  SiBitbucket,
  SiJenkins,
  SiArgo,
  SiKubernetes,
} from "@icons-pack/react-simple-icons";
import {
  Activity,
  Binary,
  Cloud,
  LineChart,
  Network,
  Cpu,
  Server,
  Bell,
  GitBranch,
  MessageSquare,
  Users,
} from "lucide-react";
import {
  comparison,
  differentiators,
  featureGrid,
  modules,
  pillars,
  productShots,
  stats,
  uspTriad,
  workflow,
  industries,
  integrationCatalog,
  egapSteps,
  protocolStack,
  mcpToolGroups,
  fleetCapabilities,
  orbitalNodes,
} from "./home-data";

/* ── Scroll Reveal hook ─────────────────────────────────────── */
function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { el.classList.add("visible"); obs.disconnect(); } },
      { threshold: 0.12 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return ref;
}

/* ── Count-up hook ──────────────────────────────────────────── */
function useCountUp(target: number, duration = 1400) {
  const [value, setValue] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        obs.disconnect();
        const start = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - start) / duration, 1);
          setValue(Math.round(p * target));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      },
      { threshold: 0.5 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [target, duration]);
  return { ref, value };
}

/* ── Helpers ────────────────────────────────────────────────── */
function IntegrationIcon({ name, iconName }: { name: string; iconName: string }) {
  const n = name.toLowerCase();
  if (n.includes("prometheus"))       return <SiPrometheus size={26} color="#e6522c" />;
  if (n.includes("victoriametrics"))  return <SiVictoriametrics size={26} color="#621cff" />;
  if (n.includes("datadog"))          return <SiDatadog size={26} color="#632ca6" />;
  if (n.includes("jaeger"))           return <SiJaeger size={26} color="#60d0e4" />;
  if (n.includes("opensearch"))       return <SiOpensearch size={26} color="#005eb8" />;
  if (n.includes("splunk"))           return <SiSplunk size={26} color="#333" />;
  if (n.includes("dynatrace"))        return <SiDynatrace size={26} color="#1496ff" />;
  if (n.includes("grafana"))          return <SiGrafana size={26} color="#f46800" />;
  if (n.includes("influx"))           return <SiInfluxdb size={26} color="#22adf6" />;
  if (n.includes("cloudwatch"))       return <Cloud size={26} color="#ff9900" />;
  if (n.includes("azure"))            return <Server size={26} color="#0089d6" />;
  if (n.includes("gcp") || n.includes("google")) return <SiGooglecloud size={26} color="#4285f4" />;
  if (n.includes("mqtt"))             return <SiMqtt size={26} color="#9b59b6" />;
  if (n.includes("servicenow"))       return <Activity size={26} color="#62d84e" />;
  if (n.includes("jira"))             return <SiJira size={26} color="#0052cc" />;
  if (n.includes("slack"))            return <MessageSquare size={26} color="#e01e5a" />;
  if (n.includes("teams"))            return <Users size={26} color="#6264a7" />;
  if (n.includes("github"))           return <SiGithub size={26} color="#24292e" />;
  if (n.includes("gitlab"))           return <SiGitlab size={26} color="#fc6d26" />;
  if (n.includes("bitbucket"))        return <SiBitbucket size={26} color="#0052cc" />;
  if (n.includes("jenkins"))          return <SiJenkins size={26} color="#d33833" />;
  if (n.includes("argo"))             return <SiArgo size={26} color="#ef7b4d" />;
  if (n.includes("flux"))             return <GitBranch size={26} color="#5468ff" />;
  if (n.includes("kubernetes"))       return <SiKubernetes size={26} color="#326ce5" />;
  if (n.includes("nagios"))           return <Bell size={26} color="#7b9fff" />;
  switch (iconName) {
    case "metrics":    return <LineChart size={26} color="#7b9fff" />;
    case "logs":       return <Binary size={26} color="#7b9fff" />;
    case "traces":     return <Network size={26} color="#7b9fff" />;
    case "industrial": return <Cpu size={26} color="#16c7d8" />;
    case "cloud":      return <Cloud size={26} color="#b89dff" />;
    case "itsm":       return <Activity size={26} color="#d97706" />;
    case "notify":     return <Bell size={26} color="#059669" />;
    case "devops":     return <GitBranch size={26} color="#2563eb" />;
    default:           return <Activity size={26} color="#8494b0" />;
  }
}

function SectionHeader({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return (
    <div className="section-header">
      <div className="section-header__eyebrow">{eyebrow}</div>
      <h2 dangerouslySetInnerHTML={{ __html: title }} />
      <p>{copy}</p>
    </div>
  );
}

function CompareCell({ value }: { value: boolean | string }) {
  if (value === true)  return <span className="cmp-yes">✓</span>;
  if (value === false) return <span className="cmp-no">✕</span>;
  return <span className="cmp-partial">~</span>;
}

/* ── Orbital Diagram ────────────────────────────────────────── */
function OrbitalDiagram() {
  const size = 340;
  const cx = size / 2;
  const R = 140;
  return (
    <div className="orbital-canvas">
      <div className="orbital-wrapper" style={{ width: size, height: size }}>
        {/* Dashed orbit rings */}
        <div className="orbital-ring" />
        <div className="orbital-ring orbital-ring--inner" />

        {/* SVG spoke lines from center to each node */}
        <svg
          viewBox={`0 0 ${size} ${size}`}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 0, pointerEvents: "none" }}
        >
          {orbitalNodes.map(({ label, angle }) => {
            const rad = (angle * Math.PI) / 180;
            const x2 = cx + R * Math.cos(rad);
            const y2 = cx + R * Math.sin(rad);
            return (
              <line
                key={label}
                x1={cx} y1={cx} x2={x2} y2={y2}
                stroke="rgba(37,99,235,0.18)"
                strokeWidth={1}
                strokeDasharray="5 4"
              />
            );
          })}
        </svg>

        {/* Center brand block */}
        <div
          className="orbital-center"
          style={{ width: 80, height: 80, borderRadius: 16, flexDirection: "column", gap: 2, zIndex: 2 }}
        >
          <span style={{ fontSize: 9, letterSpacing: ".10em", opacity: 0.7, textTransform: "uppercase" }}>AI Engine</span>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: ".02em" }}>OpsMitra</span>
        </div>

        {/* Orbit nodes */}
        {orbitalNodes.map(({ label, angle }) => {
          const rad = (angle * Math.PI) / 180;
          const x = cx + R * Math.cos(rad);
          const y = cx + R * Math.sin(rad);
          return (
            <div
              key={label}
              style={{ position: "absolute", left: x, top: y, transform: "translate(-50%,-50%)", zIndex: 1 }}
            >
              <div className="orbital-node-chip">{label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Network Growth Cards ───────────────────────────────────── */
function NetworkCard({
  step,
  title,
  italicWord,
  desc,
  svgContent,
}: {
  step: string;
  title: string;
  italicWord?: string;
  desc: string;
  svgContent: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setAnimated(true); obs.disconnect(); } },
      { threshold: 0.3 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return (
    <div className="network-card" ref={ref}>
      <div className="network-card__step">{step}</div>
      <h4>
        {italicWord ? (
          <>{title.replace(italicWord, "")}<em>{italicWord}</em></>
        ) : title}
      </h4>
      <p>{desc}</p>
      <div className={`network-card__svg${animated ? " animate" : ""}`}>
        {svgContent}
      </div>
    </div>
  );
}

/* ── Marquee Strip ──────────────────────────────────────────── */
const marqueeItems = [
  "Prometheus", "VictoriaMetrics", "Datadog", "Splunk", "Jaeger", "OpenSearch",
  "ServiceNow", "Jira", "PagerDuty", "Slack", "GitHub", "GitLab",
  "Kubernetes", "Argo CD", "Jenkins", "Flux CD", "OPC-UA", "Modbus TCP",
  "AWS CloudWatch", "Azure Monitor", "GCP Operations", "InfluxDB", "Dynatrace", "New Relic",
];

function MarqueeStrip() {
  const doubled = [...marqueeItems, ...marqueeItems];
  return (
    <div className="marquee-wrap">
      <div className="marquee-inner">
        {doubled.map((item, i) => (
          <span key={i} className="marquee-item">
            <span className="marquee-dot" />
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ── Architecture Diagram ───────────────────────────────────── */
function ArchitectureDiagram() {
  return (
    <div className="architecture-diagram" aria-label="OpsMitra architecture overview">
      <div className="architecture-diagram__lane">
        <div className="architecture-node architecture-node--signal">
          <span>Signals</span>
          <strong>Logs · Metrics · Traces · Alerts · OT</strong>
        </div>
        <div className="architecture-link">→</div>
        <div className="architecture-node architecture-node--runtime">
          <span>Runtime Context</span>
          <strong>Topology · Incidents · Blast Radius</strong>
        </div>
      </div>
      <div className="architecture-diagram__lane">
        <div className="architecture-node architecture-node--code">
          <span>Code Context</span>
          <strong>Repos · Routes · Spans · Modules · Commits</strong>
        </div>
        <div className="architecture-link">→</div>
        <div className="architecture-node architecture-node--brain">
          <span>OpsMitra Reasoning</span>
          <strong>RCA · Risk · Runbooks · Action Planning</strong>
        </div>
      </div>
      <div className="architecture-diagram__lane">
        <div className="architecture-node architecture-node--governance">
          <span>Governance</span>
          <strong>Policies · Approvals · Audit · Rollback</strong>
        </div>
        <div className="architecture-link">→</div>
        <div className="architecture-node architecture-node--action">
          <span>Outcome</span>
          <strong>Safe Remediation · Verification · Fleet</strong>
        </div>
      </div>
    </div>
  );
}

/* ── Product Preview ────────────────────────────────────────── */
function ProductPreview({ mode }: { mode: (typeof productShots)[number]["mode"] }) {
  if (mode === "incident") {
    return (
      <div className="preview-window">
        <div className="preview-window__bar">
          <span /><span /><span />
          <strong>OpsMitra — Live Investigation</strong>
        </div>
        <div className="preview-window__body preview-window__body--incident">
          <div className="rca-service-pill">app-orders · CrashLoopBackOff (restart: 5)</div>
          <div className="preview-card preview-card--primary">
            <div className="preview-card__eyebrow">Root Cause · Confidence 94%</div>
            <h4>Redis memory limit reached, cascading into orders initialization failure.</h4>
            <p>Key eviction triggered session-service latency spike, causing app-orders startup to fail on token validation in <code>views.py:health()</code>.</p>
          </div>
          <div className="rca-conditions">
            <div className="rca-conditions__label">Evidence Collected</div>
            <div className="rca-bullet"><span>·</span>redis-cluster memory at 97.8%; eviction policy active</div>
            <div className="rca-bullet"><span>·</span>session-service p99 latency up 6× over baseline</div>
            <div className="rca-bullet"><span>·</span>Commit a3f92c1 raised max_connections 3 days ago</div>
          </div>
          <div className="rca-actions-list">
            <div className="rca-conditions__label">Recommended Actions</div>
            <div className="rca-action-row"><span className="rca-action-badge rca-action-badge--high">HIGH</span>Scale redis-cluster memory 2 GB → 4 GB immediately</div>
            <div className="rca-action-row"><span className="rca-action-badge rca-action-badge--med">MED</span>Add memory pressure alert at 80% threshold</div>
          </div>
        </div>
      </div>
    );
  }
  if (mode === "code") {
    return (
      <div className="preview-window">
        <div className="preview-window__bar">
          <span /><span /><span />
          <strong>Code Context Graph</strong>
        </div>
        <div className="preview-window__body preview-window__body--code">
          <div className="graph-node graph-node--application">customer-portal</div>
          <div className="graph-node graph-node--repository">customer-portal-demo</div>
          <div className="graph-node graph-node--service">app-orders</div>
          <div className="graph-node graph-node--route">GET /health</div>
          <div className="graph-node graph-node--file">views.py · line 142</div>
          <div className="graph-connector graph-connector--a" />
          <div className="graph-connector graph-connector--b" />
          <div className="graph-connector graph-connector--c" />
          <div className="graph-connector graph-connector--d" />
        </div>
      </div>
    );
  }
  return (
    <div className="preview-window">
      <div className="preview-window__bar">
        <span /><span /><span />
        <strong>Governed Remediation</strong>
      </div>
      <div className="preview-window__body preview-window__body--remediation">
        <div className="approval-flow">
          <div className="approval-step approval-step--signal">AI Plan</div>
          <div className="approval-arrow">→</div>
          <div className="approval-step approval-step--policy">Policy Check</div>
          <div className="approval-arrow">→</div>
          <div className="approval-step approval-step--approval">Approval</div>
          <div className="approval-arrow">→</div>
          <div className="approval-step approval-step--verify">Verify</div>
        </div>
        <div className="preview-command">
          <span>Rollback snapshot captured · Blast radius: 2 services</span>
          <strong>kubectl scale deployment redis-cluster --replicas=3</strong>
        </div>
      </div>
    </div>
  );
}

/* ── Main Page ──────────────────────────────────────────────── */
export function HomePage() {
  const [activeIntegrationTab, setActiveIntegrationTab] = useState("it");

  const filteredIntegrations = integrationCatalog.filter(
    (item) => item.category === activeIntegrationTab
  );

  const revealUsp       = useReveal();
  const revealOrbital   = useReveal();
  const revealEgap      = useReveal();
  const revealProtocols = useReveal();
  const revealFleet     = useReveal();
  const revealMcp       = useReveal();
  const revealFeatures  = useReveal();
  const revealWorkflow  = useReveal();
  const revealCompare   = useReveal();

  return (
    <main id="top" className="site-shell">

      {/* NAV */}
      <header className="topbar">
        <div className="brand">
          <div className="brand__mark">OM</div>
          <div>
            <strong>OpsMitra</strong>
            <span>AI Incident Control Plane</span>
          </div>
        </div>
        <nav className="topnav">
          <a href="#usp">Why OpsMitra</a>
          <a href="#protocols">Protocols</a>
          <a href="#egap">EGAP</a>
          <a href="#fleet">Fleet</a>
          <a href="#features">Capabilities</a>
          <a href="#compare">Compare</a>
          <a href="#contact">Contact</a>
        </nav>
        <a className="button button--primary" href="#contact" style={{ flexShrink: 0 }}>Book A Demo</a>
      </header>

      {/* HERO */}
      <section className="band band--hero">
        <div className="band__inner">
          <div className="hero-outer">
            <div className="hero-side-text hero-side-text--left">Air-Gapped · Self-Hosted · Code-Aware</div>
            <div className="hero-side-text hero-side-text--right">AI Incident Control Plane</div>

            <div className="hero-eyebrow">
              <span>Self-Hosted AIOps</span>
            </div>

            <h1 className="hero-headline">
              <span className="line animate">The AI incident</span>
              <span className="line animate">control plane that runs</span>
              <span className="line animate"><em>entirely inside your network.</em></span>
            </h1>

            <p className="hero-sub">
              OpsMitra traces live incidents from runtime telemetry all the way into your source
              code — handler, route, span, and recent commit — then executes governed remediation
              entirely inside your own infrastructure. No cloud AI. No data egress. Ever.
            </p>

            <div className="hero__actions">
              <a className="button button--primary" href="#contact">Book A Demo</a>
              <a className="button button--secondary" href="#features">See All Capabilities</a>
            </div>

            <p className="hero-tagline">
              Designed for <strong>manufacturing floors, finance, defence, and healthcare</strong> where SaaS AIOps is simply not an option.
              Powered by <a href="#protocols">EGAP · MCP · AIP · CCG</a>.
            </p>

            <div className="stats-band">
              {stats.map((item) => (
                <div key={item.label} className="stat-chip">
                  <div className="stat-chip__label">{item.label}</div>
                  <div className="stat-chip__value">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* MARQUEE */}
      <MarqueeStrip />

      {/* USP TRIFECTA */}
      <section id="usp" className="band band--usp">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealUsp}>
              <SectionHeader
                eyebrow="Why OpsMitra"
                title="Three capabilities<br/>no one else combines."
                copy="The market has observability tools. It has code tools. It has AIOps tools. None of them connect all three inside an air-gapped, self-hosted environment with governed execution. That is the gap OpsMitra fills."
              />
              <div className="usp-grid">
                {uspTriad.map((item) => (
                  <article key={item.badge} className={`usp-card usp-card--${item.color}`}>
                    <div className="usp-card__badge">{item.badge}</div>
                    <h3>{item.headline}</h3>
                    <p>{item.copy}</p>
                    <ul className="usp-card__proof">
                      {item.proof.map((p) => (
                        <li key={p}><span className="usp-check">✓</span>{p}</li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ORBITAL — how OpsMitra unifies signals */}
      <section className="band band--orbital">
        <div className="band__inner">
          <div className="reveal" ref={revealOrbital}>
            <div className="orbital-section">
              <div className="orbital-copy">
                <div className="eyebrow">Signal Unification</div>
                <h2>Every signal, one<br/><em>reasoning engine.</em></h2>
                <p>
                  OpsMitra ingests alerts, metrics, logs, traces, fleet events, code changes, and topology
                  into one unified context layer. The AI engine reasons across all of them simultaneously
                  — not in silos.
                </p>
                <p>
                  No manual correlation. No tab-switching. No data leaving your network boundary.
                  Every source stays inside your infrastructure and feeds structured context to the
                  local LLM reasoning engine via the Model Context Protocol.
                </p>
                <a className="text-link" href="#protocols">Learn about MCP →</a>
              </div>
              <OrbitalDiagram />
            </div>
          </div>
        </div>
      </section>

      {/* PROTOCOL STACK — EGAP / MCP / AIP / CCG */}
      <section id="protocols" className="band band--protocols">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealProtocols}>
              <SectionHeader
                eyebrow="Core Protocols"
                title="Four protocols that make<br/>OpsMitra different."
                copy="EGAP, MCP, AIP, and CCG are the architectural primitives that give OpsMitra its safety, context richness, and code-aware reasoning. No other platform ships all four."
              />
              <div className="protocol-grid">
                {protocolStack.map((p) => (
                  <article key={p.name} className={`protocol-card protocol-card--${p.color}`}>
                    <div className="protocol-card__header">
                      <div className="protocol-card__abbr">{p.name}</div>
                      <div className="protocol-card__full">{p.full}</div>
                    </div>
                    <p>{p.desc}</p>
                    <div className="protocol-card__tags">
                      {p.tags.map((tag) => (
                        <span key={tag} className="protocol-tag">{tag}</span>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* EGAP PIPELINE */}
      <section id="egap" className="band band--egap">
        <div className="band__inner">
          <div className="reveal" ref={revealEgap}>
            <div className="egap-split">
              <div className="egap-copy">
                <div className="eyebrow">EGAP Protocol</div>
                <h2>Six gates between<br/>intent and <em>execution.</em></h2>
                <p>
                  Every remediation action — whether recommended by the AI or initiated by an operator —
                  passes through the Execution &amp; Governance Action Protocol. Six typed checkpoints
                  ensure no command runs without context, policy clearance, risk assessment, and a
                  rollback snapshot.
                </p>
                <p>
                  The LLM recommends. EGAP decides.
                </p>
              </div>
              <div className="egap-pipeline">
                {egapSteps.map((s) => (
                  <div key={s.step} className="egap-step">
                    <div className="egap-step__connector" />
                    <div className="egap-step__num">{s.step}</div>
                    <div className="egap-step__body">
                      <div className="egap-step__name">{s.name}</div>
                      <div className="egap-step__desc">{s.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FLEET */}
      <section id="fleet" className="band band--fleet">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealFleet}>
              <SectionHeader
                eyebrow="Fleet Management"
                title="One control plane.<br/>Every managed node."
                copy="Enroll Linux servers, Kubernetes clusters, and industrial OT machines in the same fleet dashboard. Push policies, dispatch diagnostics, and maintain real-time heartbeat visibility across every target — all governed by the same EGAP execution pipeline."
              />
              <div className="fleet-grid">
                {fleetCapabilities.map((cap) => (
                  <article key={cap.title} className="fleet-card">
                    <div className="fleet-card__icon">{cap.icon}</div>
                    <h3>{cap.title}</h3>
                    <p>{cap.desc}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* MCP TOOLS */}
      <section className="band band--mcp">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealMcp}>
              <SectionHeader
                eyebrow="Model Context Protocol"
                title="18 structured tools.<br/>Zero hallucination retrieval."
                copy="The OpsMitra MCP server gives the AI reasoning engine real-time, typed access to incidents, topology, metrics, logs, traces, code ownership, deployments, and blast radius — across five context groups."
              />
              <div className="mcp-grid">
                {mcpToolGroups.map((group) => (
                  <div key={group.group} className={`mcp-group mcp-group--${group.color}`}>
                    <div className="mcp-group__label">{group.group}</div>
                    {group.tools.map((tool) => (
                      <div key={tool} className="mcp-tool">{tool}</div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS — Network Growth Cards */}
      <section className="band band--features" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="How It Works"
              title="From raw signal to verified,<br/>audited action."
              copy="Five stages. One closed loop. Every step is designed to move operators from uncertainty to a verified, audited decision — with the minimum unsafe automation surface."
            />
            <div className="network-grid">
              <NetworkCard
                step="01 — Ingest"
                title="Normalize"
                italicWord="Normalize"
                desc="40+ connectors pull metrics, logs, traces, alerts, topology, change events, and OT telemetry into a unified signal store."
                svgContent={
                  <svg width="120" height="70" fill="none">
                    <circle cx="20" cy="35" r="7" fill="var(--blue-lt)" stroke="var(--blue)" strokeWidth="1.5"/>
                    <circle cx="60" cy="15" r="7" fill="var(--teal-lt)" stroke="var(--teal)" strokeWidth="1.5"/>
                    <circle cx="60" cy="55" r="7" fill="var(--violet-lt)" stroke="var(--violet)" strokeWidth="1.5"/>
                    <circle cx="100" cy="35" r="7" fill="var(--blue-lt)" stroke="var(--blue)" strokeWidth="1.5"/>
                    <line className="edge" x1="27" y1="35" x2="53" y2="18" stroke="var(--blue)" strokeWidth="1.5"/>
                    <line className="edge" x1="27" y1="35" x2="53" y2="52" stroke="var(--violet)" strokeWidth="1.5"/>
                    <line className="edge" x1="67" y1="18" x2="93" y2="35" stroke="var(--teal)" strokeWidth="1.5"/>
                    <line className="edge" x1="67" y1="52" x2="93" y2="35" stroke="var(--violet)" strokeWidth="1.5"/>
                  </svg>
                }
              />
              <NetworkCard
                step="02 — Diagnose"
                title="Investigate"
                italicWord="Investigate"
                desc="Multi-step streaming investigation. Evidence collected, hypotheses scored, code path traced — in real time."
                svgContent={
                  <svg width="120" height="70" fill="none">
                    <rect x="10" y="25" width="28" height="20" rx="4" fill="var(--amber-lt)" stroke="var(--amber)" strokeWidth="1.5"/>
                    <rect x="82" y="25" width="28" height="20" rx="4" fill="var(--green-lt)" stroke="var(--green)" strokeWidth="1.5"/>
                    <circle cx="60" cy="35" r="10" fill="var(--blue-lt)" stroke="var(--blue)" strokeWidth="1.5"/>
                    <line className="edge" x1="38" y1="35" x2="50" y2="35" stroke="var(--amber)" strokeWidth="1.5"/>
                    <line className="edge" x1="70" y1="35" x2="82" y2="35" stroke="var(--green)" strokeWidth="1.5"/>
                    <text x="57" y="39" fontSize="9" fill="var(--blue)" fontWeight="700">AI</text>
                  </svg>
                }
              />
              <NetworkCard
                step="03 — Correlate"
                title="Connect"
                italicWord="Connect"
                desc="Signal analytics surface alert density heatmaps. Correlation links join alerts, incidents, and executions by shared incident key."
                svgContent={
                  <svg width="120" height="70" fill="none">
                    <circle cx="20" cy="20" r="6" fill="var(--orange-lt)" stroke="var(--orange)" strokeWidth="1.5"/>
                    <circle cx="60" cy="35" r="6" fill="var(--blue-lt)" stroke="var(--blue)" strokeWidth="1.5"/>
                    <circle cx="100" cy="20" r="6" fill="var(--orange-lt)" stroke="var(--orange)" strokeWidth="1.5"/>
                    <circle cx="20" cy="55" r="6" fill="var(--violet-lt)" stroke="var(--violet)" strokeWidth="1.5"/>
                    <circle cx="100" cy="55" r="6" fill="var(--violet-lt)" stroke="var(--violet)" strokeWidth="1.5"/>
                    <line className="edge" x1="26" y1="23" x2="54" y2="32" stroke="var(--orange)" strokeWidth="1.5"/>
                    <line className="edge" x1="94" y1="23" x2="66" y2="32" stroke="var(--orange)" strokeWidth="1.5"/>
                    <line className="edge" x1="26" y1="52" x2="54" y2="38" stroke="var(--violet)" strokeWidth="1.5"/>
                    <line className="edge" x1="94" y1="52" x2="66" y2="38" stroke="var(--violet)" strokeWidth="1.5"/>
                  </svg>
                }
              />
              <NetworkCard
                step="04 — Explain"
                title="Reason"
                italicWord="Reason"
                desc="Plain-language RCA grounded in handler code, spans, commits, and blast radius. AI-generated runbooks and incident narratives on demand."
                svgContent={
                  <svg width="120" height="70" fill="none">
                    <rect x="5" y="10" width="50" height="50" rx="6" fill="var(--bg-alt)" stroke="var(--border-md)" strokeWidth="1.5"/>
                    <line className="edge" x1="14" y1="24" x2="46" y2="24" stroke="var(--ink-soft)" strokeWidth="1.2"/>
                    <line className="edge" x1="14" y1="32" x2="40" y2="32" stroke="var(--ink-soft)" strokeWidth="1.2"/>
                    <line className="edge" x1="14" y1="40" x2="44" y2="40" stroke="var(--ink-soft)" strokeWidth="1.2"/>
                    <circle cx="90" cy="35" r="16" fill="var(--violet-lt)" stroke="var(--violet)" strokeWidth="1.5"/>
                    <line className="edge" x1="56" y1="35" x2="74" y2="35" stroke="var(--violet)" strokeWidth="1.5"/>
                    <text x="84" y="39" fontSize="8" fill="var(--violet)" fontWeight="700">RCA</text>
                  </svg>
                }
              />
              <NetworkCard
                step="05 — Remediate"
                title="Execute safely"
                italicWord="safely"
                desc="Policy-checked, approval-gated, blast-radius-estimated, rollback-snapshotted, and audit-logged. EGAP governs every action."
                svgContent={
                  <svg width="120" height="70" fill="none">
                    <rect x="5" y="27" width="22" height="16" rx="3" fill="var(--blue-lt)" stroke="var(--blue)" strokeWidth="1.5"/>
                    <rect x="35" y="27" width="22" height="16" rx="3" fill="var(--amber-lt)" stroke="var(--amber)" strokeWidth="1.5"/>
                    <rect x="65" y="27" width="22" height="16" rx="3" fill="var(--violet-lt)" stroke="var(--violet)" strokeWidth="1.5"/>
                    <rect x="95" y="27" width="22" height="16" rx="3" fill="var(--green-lt)" stroke="var(--green)" strokeWidth="1.5"/>
                    <line className="edge" x1="27" y1="35" x2="35" y2="35" stroke="var(--blue)" strokeWidth="1.5"/>
                    <line className="edge" x1="57" y1="35" x2="65" y2="35" stroke="var(--amber)" strokeWidth="1.5"/>
                    <line className="edge" x1="87" y1="35" x2="95" y2="35" stroke="var(--violet)" strokeWidth="1.5"/>
                  </svg>
                }
              />
            </div>
          </div>
        </div>
      </section>

      {/* FEATURE GRID */}
      <section id="features" className="band band--architecture">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealFeatures}>
              <SectionHeader
                eyebrow="Capabilities"
                title="Everything built in.<br/>Nothing bolted on."
                copy="OpsMitra ships as a complete incident intelligence platform — not a collection of loosely coupled tools. Every capability is designed to work together inside your own network boundary."
              />
              <div className="feature-grid">
                {featureGrid.map((item) => (
                  <article key={item.title} className="feature-card">
                    <div className="feature-card__icon">{item.icon}</div>
                    <h3>{item.title}</h3>
                    <p>{item.copy}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ARCHITECTURE */}
      <section className="band band--features" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="Architecture"
              title="Signal to safe action.<br/>Entirely inside your boundary."
              copy="Every layer — signal ingestion, code context, AI reasoning, governance, and execution — runs on your infrastructure. The control plane never phones home."
            />
            <ArchitectureDiagram />
          </div>
        </div>
      </section>

      {/* INDUSTRIES */}
      <section id="industries" className="band band--industries">
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="Coverage"
              title="Built for every<br/>critical network."
              copy="From Kubernetes clusters in the cloud to air-gapped CNC machines on the manufacturing floor. If it generates telemetry, OpsMitra can investigate it."
            />
            <div className="bento-grid">
              {industries.map((ind) => {
                const isLarge = ind.tier === "industrial";
                return (
                  <div key={ind.name} className={`bento-card ${isLarge ? "bento-card--large" : ""}`}>
                    <div className={`bento-card__badge bento-card__badge--${ind.tier}`}>
                      {ind.tier === "industrial" ? "Industrial & OT" : ind.tier === "it" ? "Cloud & IT" : "Regulated"}
                    </div>
                    <h3>{ind.name}</h3>
                    <p>{ind.reason}</p>
                    {isLarge && (
                      <div className="bento-card__visual">
                        <div className="ot-diagram">
                          <div className="ot-node">
                            <Cpu size={24} color="#0891b2" />
                            <span>PLC / SCADA</span>
                          </div>
                          <div className="ot-connector">
                            <span /><span /><span /><span />
                          </div>
                          <div className="ot-node ot-node--edge">
                            <Network size={24} color="#0891b2" />
                            <span>OpsMitra Edge</span>
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="bento-card__protocols">
                      {ind.protocols.map((p) => <span key={p}>{p}</span>)}
                    </div>
                    {isLarge && <div className="hover-glow" />}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* INTEGRATIONS */}
      <section id="integrations" className="band band--integrations">
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="Integrations"
              title="40+ connectors.<br/>Everything already in your stack."
              copy="Seamlessly ingest metrics, logs, traces, and machine alarms from your existing infrastructure — and write incidents back to your ITSM, notify your team, and trigger DevOps workflows."
            />
            <div className="segmented-control-wrap">
              <div className="segmented-control">
                <button className={activeIntegrationTab === "it"   ? "is-active" : ""} onClick={() => setActiveIntegrationTab("it")}>IT &amp; Observability</button>
                <button className={activeIntegrationTab === "itsm" ? "is-active" : ""} onClick={() => setActiveIntegrationTab("itsm")}>ITSM, DevOps &amp; Notify</button>
                <button className={activeIntegrationTab === "ot"   ? "is-active" : ""} onClick={() => setActiveIntegrationTab("ot")}>Industrial / OT</button>
                <button className={activeIntegrationTab === "cloud"? "is-active" : ""} onClick={() => setActiveIntegrationTab("cloud")}>Cloud Providers</button>
              </div>
            </div>
            <div className="integrations-grid">
              {filteredIntegrations.map((item) => (
                <div key={item.name} className="integration-card">
                  <div className="integration-card__icon">
                    <IntegrationIcon name={item.name} iconName={item.icon || "mixed"} />
                  </div>
                  <h4>{item.name}</h4>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* PLATFORM PILLARS */}
      <section id="platform" className="band band--platform">
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="Platform"
              title="Built for teams that need<br/>more than observability."
              copy="OpsMitra combines observability, code intelligence, incident reasoning, fleet management, and safe execution into one operating system for modern engineering teams."
            />
            <div className="pillars-grid">
              {pillars.map((item) => (
                <article key={item.title} className="pillar-card">
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* WORKFLOW */}
      <section id="workflow" className="band band--workflow">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealWorkflow}>
              <SectionHeader
                eyebrow="Workflow"
                title="A closed-loop<br/>incident intelligence workflow."
                copy="Each step is designed to move operators from uncertainty to a verified, audited decision with the minimum unsafe automation surface."
              />
              <div className="workflow-grid">
                {workflow.map((item) => (
                  <article key={item.step} className="workflow-card">
                    <span>{item.step}</span>
                    <h3>{item.title}</h3>
                    <p>{item.copy}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* MODULES */}
      <section className="band band--modules">
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="Modules"
              title="One control plane.<br/>Twelve operational surfaces."
              copy="OpsMitra ships onboarding, ingestion, alert intelligence, incident command, streaming investigations, code context, change risk, signal analytics, predictions, remediation, fleet management, and audit lifecycle as a unified platform."
            />
            <div className="modules-grid">
              {modules.map((item) => (
                <div key={item} className="module-pill">{item}</div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* MARKET COMPARISON */}
      <section id="compare" className="band band--compare">
        <div className="band__inner">
          <div className="section-frame">
            <div className="reveal" ref={revealCompare}>
              <SectionHeader
                eyebrow="Market Comparison"
                title="What the rest of the market<br/>cannot do."
                copy="We benchmarked the core capabilities that matter for regulated, sovereign, and air-gapped environments. The result speaks for itself."
              />
              <div className="compare-table-wrap">
                <table className="compare-table">
                  <thead>
                    <tr>
                      <th>Capability</th>
                      <th className="compare-table__us">OpsMitra</th>
                      <th>Datadog</th>
                      <th>New Relic</th>
                      <th>Grafana</th>
                      <th>PagerDuty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.map((row) => (
                      <tr key={row.capability}>
                        <td>{row.capability}</td>
                        <td className="compare-table__us"><CompareCell value={row.opsmitra} /></td>
                        <td><CompareCell value={row.datadog} /></td>
                        <td><CompareCell value={row.newrelic} /></td>
                        <td><CompareCell value={row.grafana} /></td>
                        <td><CompareCell value={row.pagerduty} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="compare-legend">
                <span><span className="cmp-yes">✓</span> Supported</span>
                <span><span className="cmp-partial">~</span> Partial</span>
                <span><span className="cmp-no">✕</span> Not available</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* DIFFERENTIATORS */}
      <section className="band band--differentiators">
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="The Difference"
              title="This is not just AIOps."
              copy="The platform spans incident intelligence, code-aware reasoning, governed execution, fleet management, and sovereign deployment. Six capabilities the market treats as separate products."
            />
            <div className="differentiators-grid">
              {differentiators.map((item) => (
                <article key={item.title} className="differentiator-card">
                  <div className="differentiator-card__eyebrow">{item.eyebrow}</div>
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* PRODUCT SHOTS */}
      <section className="band band--screenshots">
        <div className="band__inner">
          <div className="section-frame">
            <SectionHeader
              eyebrow="Product Views"
              title="What operators see<br/>during a live incident."
              copy="Streaming investigations, code-path graph exploration, and governed remediation workflows — all running inside your own network."
            />
            <div className="product-shots-grid">
              {productShots.map((shot) => (
                <article key={shot.title} className="product-shot">
                  <ProductPreview mode={shot.mode} />
                  <div className="product-shot__copy">
                    <h3>{shot.title}</h3>
                    <p>{shot.copy}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* DEPLOYMENT */}
      <section id="deployment" className="band band--deployment">
        <div className="band__inner">
          <div className="section-frame">
            <div className="deployment-panel">
              <div>
                <div className="section-header__eyebrow">Deployment</div>
                <h2>Sovereign deployment is part of the product, not an afterthought.</h2>
                <p>
                  Docker Compose for single-node trials. Helm chart for Kubernetes production with
                  migration jobs, persistent volumes, ingress, and a cluster agent for managed fleet nodes.
                  Bring your own LLM, your own observability stack, and your own code repositories.
                </p>
              </div>
              <ul className="deployment-list">
                <li>Docker Compose or Kubernetes Helm chart</li>
                <li>Automated DB migrations at startup</li>
                <li>Kubernetes cluster agent for fleet management</li>
                <li>Policy-gated remediation workflows (EGAP)</li>
                <li>18-tool MCP server for AI context</li>
                <li>RBAC with 6 roles and multi-tenant support</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* CONTACT */}
      <section id="contact" className="band band--contact">
        <div className="band__inner">
          <div className="section-frame">
            <div className="contact-panel">
              <div>
                <div className="section-header__eyebrow">Get In Touch</div>
                <h2>If your environment cannot phone home, OpsMitra is ready for it.</h2>
                <p>
                  We work with teams in finance, defence, healthcare, manufacturing, and regulated enterprise
                  where SaaS AIOps is simply not viable. Let us talk about your environment.
                </p>
              </div>
              <div className="contact-actions">
                <a className="button button--primary" href="mailto:hello@opsmitra.ai">hello@opsmitra.ai</a>
                <a className="button button--ghost" href="#top">Back To Top</a>
              </div>
            </div>
          </div>
        </div>
      </section>

    </main>
  );
}
