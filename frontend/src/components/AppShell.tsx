import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useRefreshInterval } from "../lib/refresh";

<<<<<<< Updated upstream
const navItems = [
  { to: "/domain-onboarding", label: "Domain Onboarding",        meta: "Infra · Network · Cloud" },
  { to: "/ingestion",         label: "Unified Data Ingestion",   meta: "Agents · Kafka · Enrichment" },
  { to: "/intelligence",      label: "AI/ML Intelligence",       meta: "Anomaly · RCA · Prediction" },
  { to: "/alerts",            label: "Alerts",                   meta: "Signal Feed · Anomaly Explainer" },
  { to: "/incidents",         label: "Incidents",                meta: "SLA · War Room · PIR" },
  { to: "/investigations",    label: "Investigations",           meta: "Live RCA · Tool Trace · Stages" },
  { to: "/integrations",      label: "Integrations",             meta: "Connectors · External Sources" },
  { to: "/topology",          label: "Topology & CMDB",          meta: "Service Graph · Blast Radius" },
  { to: "/code-context",      label: "Code Context",             meta: "Repo Graph · Runtime To Code" },
  { to: "/genai",             label: "Assistant",                meta: "RCA · AI Chat" },
  { to: "/change-risk",       label: "Change Risk",              meta: "Deploy Risk · Maintenance Window" },
  { to: "/automation",        label: "Knowledge Base",           meta: "Runbooks · Auto-Remediation" },
  { to: "/analytics",         label: "Analytics & Reporting",    meta: "SLO · MTTR · Exec Views" },
=======
type NavIconName = "radar" | "database" | "topology" | "incident" | "automation" | "admin";

type NavItem = {
  to: string;
  label: string;
  meta: string;
  icon: NavIconName;
  matches: readonly string[];
  permission?: string;
};

const navItems: readonly NavItem[] = [
  {
    to: "/operations",
    label: "Operations Overview",
    meta: "Posture · MTTR · SLO · Risk",
    icon: "radar",
    matches: ["/operations", "/analytics", "/intelligence", "/predictions", "/cache"],
  },
  {
    to: "/onboarding",
    label: "Onboarding & Data",
    meta: "Targets · Agents · Kafka · Tools",
    icon: "database",
    matches: ["/onboarding", "/domain-onboarding", "/enroll", "/ingestion", "/fleet", "/profiles", "/integrations"],
  },
  {
    to: "/topology",
    label: "Service Topology",
    meta: "CMDB · Blast Radius · Code",
    icon: "topology",
    matches: ["/topology", "/applications", "/code-context", "/graph"],
  },
  {
    to: "/incidents-rca",
    label: "Incidents & RCA",
    meta: "Alerts · Incidents · AI RCA",
    icon: "incident",
    matches: ["/incidents-rca", "/alerts", "/incidents", "/investigations", "/genai", "/assistant"],
  },
  {
    to: "/automation",
    label: "Automation & Change Risk",
    meta: "Runbooks · Approvals · Rollback",
    icon: "automation",
    matches: ["/automation", "/change-risk", "/documents"],
  },
  {
    to: "/administration",
    label: "Administration",
    meta: "Tenants · RBAC · Settings",
    icon: "admin",
    permission: "tenant.manage",
    matches: ["/administration", "/settings"],
  },
>>>>>>> Stashed changes
];

function NavIcon({ name }: { name: NavIconName }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  switch (name) {
    case "radar":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
          <path d="M12 12l5.5-5.5" />
          <path d="M4 12h2" />
          <path d="M18 12h2" />
        </svg>
      );
    case "database":
      return (
        <svg {...common}>
          <ellipse cx="12" cy="6" rx="7" ry="3" />
          <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" />
          <path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
        </svg>
      );
    case "topology":
      return (
        <svg {...common}>
          <rect x="3" y="4" width="6" height="6" rx="2" />
          <rect x="15" y="4" width="6" height="6" rx="2" />
          <rect x="9" y="15" width="6" height="6" rx="2" />
          <path d="M9 7h6" />
          <path d="M12 10v5" />
        </svg>
      );
    case "incident":
      return (
        <svg {...common}>
          <path d="M12 3l9 16H3L12 3z" />
          <path d="M12 9v4" />
          <path d="M12 17h.01" />
        </svg>
      );
    case "automation":
      return (
        <svg {...common}>
          <path d="M12 3v3" />
          <path d="M12 18v3" />
          <path d="M3 12h3" />
          <path d="M18 12h3" />
          <circle cx="12" cy="12" r="5" />
          <path d="M15.5 8.5l-7 7" />
        </svg>
      );
    case "admin":
      return (
        <svg {...common}>
          <circle cx="12" cy="8" r="4" />
          <path d="M5 21a7 7 0 0 1 14 0" />
          <path d="M18.5 5.5l1 1" />
          <path d="M19.5 6.5l1-1" />
        </svg>
      );
  }
}

function HumanOperatorIllustration() {
  return (
    <svg className="shell__human-illustration" viewBox="0 0 148 118" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path className="shell__human-screen" d="M67 18h58a8 8 0 0 1 8 8v43a8 8 0 0 1-8 8H67a8 8 0 0 1-8-8V26a8 8 0 0 1 8-8z" />
      <path className="shell__human-line" d="M73 35h18M73 49h34M73 63h22" />
      <circle className="shell__human-dot" cx="117" cy="35" r="5" />
      <path className="shell__human-skin" d="M46 42c9.5 0 17-7.5 17-17S55.5 8 46 8 29 15.5 29 25s7.5 17 17 17z" />
      <path className="shell__human-hair" d="M30 27c0-14 9-21 20-20 8 1 13 7 14 14-9-4-18-3-26 3-2 1.5-5 2.5-8 3z" />
      <path className="shell__human-shirt" d="M17 107V76c0-14 12-25 28-25h3c16 0 28 11 28 25v31H17z" />
      <path className="shell__human-accent" d="M37 53l9 15 9-15" />
      <path className="shell__human-arm" d="M75 81c16-8 28-10 40-7" />
      <path className="shell__human-arm" d="M17 82c-5 5-7 12-7 23" />
      <path className="shell__human-base" d="M25 108h93" />
    </svg>
  );
}

export function AppShell() {
  const location = useLocation();
  const { refreshMs, setRefreshMs, options } = useRefreshInterval();
<<<<<<< Updated upstream
  const currentNav = navItems.find((item) => location.pathname.startsWith(item.to));
=======
  const { current, tenants, switchTenant, switchPending, hasPermission } = useTenant();
  const currentNav = navItems.find((item) => item.matches.some((path) => location.pathname === path || location.pathname.startsWith(`${path}/`)));
>>>>>>> Stashed changes
  const pageTitle = currentNav?.label ?? "Operational Intelligence";
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("aiops-sidebar-collapsed") === "true";
  });
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem("aiops-theme");
    return stored === "light" ? "light" : "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("aiops-theme", theme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem("aiops-sidebar-collapsed", String(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  return (
    <div className={`shell${isSidebarCollapsed ? " shell--sidebar-collapsed" : ""}`}>
      <aside className="shell__sidebar">
        <div className="shell__brand">
          <svg className="shell__brand-logo" width="36" height="36" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logo-grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="100%" stopColor="#2EB6AE" />
              </linearGradient>
              <linearGradient id="logo-grad2" x1="100%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#2EB6AE" />
                <stop offset="100%" stopColor="#ffffff" />
              </linearGradient>
            </defs>
            <path d="M16 2 L28 8 L28 24 L16 30 L4 24 L4 8 Z" stroke="url(#logo-grad1)" strokeWidth="3" strokeLinejoin="round"/>
            <circle cx="16" cy="16" r="6" fill="url(#logo-grad2)" />
          </svg>
          <div className="shell__brand-copy">
            <strong>AIOps Platform</strong>
            <div>Observability Control Plane</div>
          </div>
          <button
            className="shell__sidebar-toggle"
            type="button"
            aria-label={isSidebarCollapsed ? "Expand left menu" : "Minimize left menu"}
            aria-expanded={!isSidebarCollapsed}
            title={isSidebarCollapsed ? "Expand menu" : "Minimize menu"}
            onClick={() => setIsSidebarCollapsed((collapsed) => !collapsed)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d={isSidebarCollapsed ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <nav className="shell__nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              className={() => {
                const isActive = item.matches.some((path) => location.pathname === path || location.pathname.startsWith(`${path}/`));
                return `shell__nav-link${isActive ? " is-active" : ""}`;
              }}
              to={item.to}
              title={isSidebarCollapsed ? `${item.label} - ${item.meta}` : undefined}
              aria-label={isSidebarCollapsed ? item.label : undefined}
            >
              <span className="shell__nav-glyph" aria-hidden="true">
                <NavIcon name={item.icon} />
              </span>
              <span className="shell__nav-copy">
                <strong>{item.label}</strong>
                <span>{item.meta}</span>
              </span>
            </NavLink>
          ))}
        </nav>
        <div className="shell__sidebar-footer">
          <div className="shell__human-card">
            <HumanOperatorIllustration />
            <div>
              <span>Human in the loop</span>
              <strong>Operator guided automation</strong>
            </div>
          </div>
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
