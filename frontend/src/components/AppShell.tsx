import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useRefreshInterval } from "../lib/refresh";

const navItems = [
  { to: "/applications", label: "Applications" },
  { to: "/assistant", label: "Assistant" },
  { to: "/alerts", label: "Alerts" },
  { to: "/incidents", label: "Incidents" },
  { to: "/predictions", label: "Predictions" },
  { to: "/documents", label: "Documents" },
];

export function AppShell() {
  const location = useLocation();
  const { refreshMs, setRefreshMs, options } = useRefreshInterval();

  return (
    <div className="shell">
      <aside className="shell__sidebar">
        <div className="shell__brand">
          <span className="shell__brand-mark" />
          <div>
            <strong>AIOps</strong>
            <div>Immersive Control Plane</div>
          </div>
        </div>
        <nav className="shell__nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              className={({ isActive }) => `shell__nav-link${isActive ? " is-active" : ""}`}
              to={item.to}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="shell__content">
        <header className="shell__header">
          <div>
            <div className="eyebrow">AIOps Command Center</div>
            <h1 className="shell__title">Operational Intelligence</h1>
          </div>
          <div className="shell__actions">
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
