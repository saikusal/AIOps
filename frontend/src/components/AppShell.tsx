import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useRefreshInterval } from "../lib/refresh";
import { useTenant } from "../lib/tenant";

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
  { to: "/settings/members",  label: "Access Control",           meta: "Tenants · RBAC", permission: "tenant.manage" },
];

function navGlyph(label: string): string {
  return label
    .split(/[^\w]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { refreshMs, setRefreshMs, options } = useRefreshInterval();
  const { current, tenants, switchTenant, switchPending, hasPermission } = useTenant();
  const { user, logout } = useAuth();
  const navItemsForUser = [
    ...navItems,
    ...(user?.is_superuser ? [{ to: "/admin", label: "Platform Admin", meta: "Tenants · Users · Permissions" }] : []),
  ];
  const currentNav = navItemsForUser.find((item) => location.pathname.startsWith(item.to));
  const pageTitle = currentNav?.label ?? "Operational Intelligence";

  const handleSignOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };
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
          <svg className="shell__brand-logo" width="36" height="36" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logo-grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#00f0ff" />
                <stop offset="100%" stopColor="#8a2be2" />
              </linearGradient>
              <linearGradient id="logo-grad2" x1="100%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#ff00ff" />
                <stop offset="100%" stopColor="#00f0ff" />
              </linearGradient>
            </defs>
            <path d="M16 2 L28 8 L28 24 L16 30 L4 24 L4 8 Z" stroke="url(#logo-grad1)" strokeWidth="3" strokeLinejoin="round"/>
            <circle cx="16" cy="16" r="6" fill="url(#logo-grad2)" />
          </svg>
          <div>
            <strong>OpsMitra</strong>
            <div>Observability Control Plane</div>
          </div>
        </div>

        <nav className="shell__nav">
          {navItemsForUser.filter((item) => !("permission" in item && item.permission) || hasPermission((item as { permission: string }).permission)).map((item) => (
            <NavLink
              key={item.to}
              className={({ isActive }) => `shell__nav-link${isActive ? " is-active" : ""}`}
              to={item.to}
            >
              <span className="shell__nav-glyph" aria-hidden="true">
                {navGlyph(item.label)}
              </span>
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
            {current ? (
              <label className="shell__tenant">
                <span>Workspace</span>
                <select
                  value={current.tenant_id}
                  onChange={(event) => switchTenant(event.target.value)}
                  disabled={switchPending || tenants.length <= 1}
                >
                  {tenants.map((tenant) => (
                    <option key={tenant.tenant_id} value={tenant.tenant_id}>
                      {tenant.name} · {tenant.role}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
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
            {user ? (
              <div className="shell__user" style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.78rem", color: "var(--color-muted, #9ca3af)" }}>
                <span>
                  {user.username}
                  {user.is_superuser ? " · admin" : ""}
                </span>
              </div>
            ) : null}
            <button
              type="button"
              className="shell__link"
              onClick={handleSignOut}
              style={{ background: "none", border: "none", cursor: "pointer", padding: 0, font: "inherit" }}
            >
              Sign Out
            </button>
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
