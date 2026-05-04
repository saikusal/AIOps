import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useRefreshInterval } from "../lib/refresh";

const navItems = [
  { to: "/domain-onboarding", label: "Domain Onboarding",        meta: "Infra · Network · Cloud" },
  { to: "/ingestion",         label: "Unified Data Ingestion",   meta: "Agents · Kafka · Enrichment" },
  { to: "/intelligence",      label: "AI/ML Intelligence",       meta: "Anomaly · RCA · Prediction" },
  { to: "/alerts",            label: "Alerts",                   meta: "Signal Feed · Anomaly Explainer" },
  { to: "/incidents",         label: "Incidents",                meta: "SLA · War Room · PIR" },
  { to: "/topology",          label: "Topology & CMDB",          meta: "Service Graph · Blast Radius" },
  { to: "/code-context",      label: "Code Context",             meta: "Repo Graph · Runtime To Code" },
  { to: "/genai",             label: "Assistant",                meta: "RCA · AI Chat" },
  { to: "/change-risk",       label: "Change Risk",              meta: "Deploy Risk · Maintenance Window" },
  { to: "/automation",        label: "Knowledge Base",           meta: "Runbooks · Auto-Remediation" },
  { to: "/analytics",         label: "Analytics & Reporting",    meta: "SLO · MTTR · Exec Views" },
];

export function AppShell() {
  const location = useLocation();
  const { refreshMs, setRefreshMs, options } = useRefreshInterval();
  const currentNav = navItems.find((item) => location.pathname.startsWith(item.to));
  const pageTitle = currentNav?.label ?? "Operational Intelligence";
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem("aiops-theme");
    return stored === "light" ? "light" : "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("aiops-theme", theme);
  }, [theme]);

  return (
    <div className="shell">
      <aside className="shell__sidebar">
        <div className="shell__brand">
          <span className="shell__brand-mark">A</span>
          <div>
            <strong>AIOps</strong>
            <div>Observability Control Plane</div>
          </div>
        </div>
        <div className="shell__sidebar-section">
          <div className="shell__sidebar-label">Workspace</div>
          <div className="shell__sidebar-blurb">
            Unified operations across Domain Onboarding, Data Ingestion, AI/ML Intelligence, Event & Incident Management, Topology, GenAI, Automation, and Analytics.
          </div>
        </div>
        <nav className="shell__nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              className={({ isActive }) => `shell__nav-link${isActive ? " is-active" : ""}`}
              to={item.to}
            >
              <span className="shell__nav-copy">
                <strong>{item.label}</strong>
                <span>{item.meta}</span>
              </span>
            </NavLink>
          ))}
        </nav>
        <div className="shell__sidebar-footer">
          <div className="shell__sidebar-stat">
            <span>Mode</span>
            <strong>Live</strong>
          </div>
          <div className="shell__sidebar-stat">
            <span>Stack</span>
            <strong>AIOps SaaS</strong>
          </div>
        </div>
      </aside>
      <div className="shell__content">
        <header className="shell__topbar">
          <label className="shell__search">
            <span>Search</span>
            <input
              type="text"
              value=""
              readOnly
              placeholder="Applications, services, incidents, alerts"
              aria-label="Search"
            />
          </label>
          <div className="shell__actions">
            <div className="shell__badge">Telemetry Live</div>
            <div className="shell__badge shell__badge--muted">AI Guided</div>
            <button
              className="shell__theme-toggle"
              type="button"
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? "Light Mode" : "Dark Mode"}
            </button>
            <label className="shell__refresh">
              <span>Refresh</span>
              <select
                value={refreshMs === false ? "false" : String(refreshMs)}
                onChange={(event) => {
                  const value = event.target.value;
                  setRefreshMs(value === "false" ? false : Number(value));
                }}
              >
                {options.map((option) => (
                  <option key={String(option.value)} value={option.value === false ? "false" : String(option.value)}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <a className="shell__link" href="/genai/logout/">
              Sign Out
            </a>
          </div>
        </header>
        <header className="shell__header">
          <div>
            <div className="eyebrow">Observability Workspace</div>
            <h1 className="shell__title">{pageTitle}</h1>
          </div>
          <div className="shell__header-metrics">
            <div className="shell__header-metric">
              <span>Surface</span>
              <strong>Live</strong>
            </div>
            <div className="shell__header-metric">
              <span>Modules</span>
              <strong>M1–M8</strong>
            </div>
            <div className="shell__header-metric">
              <span>Mode</span>
              <strong>Streaming</strong>
            </div>
          </div>
        </header>
        <main className="shell__main">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname + location.search}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
