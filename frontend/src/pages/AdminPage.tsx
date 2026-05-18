import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { AdminTenantsPage } from "./admin/AdminTenantsPage";
import { AdminUsersPage } from "./admin/AdminUsersPage";
import { AdminPermissionsPage } from "./admin/AdminPermissionsPage";
import { AdminAuditPage } from "./admin/AdminAuditPage";

function AdminOverview() {
  const cards = [
    { title: "Tenants", desc: "List, create, and manage all tenants in the system.", to: "/admin/tenants" },
    { title: "Users", desc: "Create users, toggle the platform-admin flag, reset passwords, assign to tenants.", to: "/admin/users" },
    { title: "Permissions", desc: "Grant per-page permissions to a user beyond their tenant role.", to: "/admin/permissions" },
    { title: "Global audit", desc: "Cross-tenant view of all tenant audit events.", to: "/admin/audit" },
  ];
  return (
    <section
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        gap: "1rem",
        marginTop: "1rem",
      }}
    >
      {cards.map((card) => (
        <NavLink
          key={card.to}
          to={card.to}
          className="page-card"
          style={{ display: "flex", flexDirection: "column", gap: "0.45rem", textDecoration: "none" }}
        >
          <h3 style={{ margin: 0 }}>{card.title}</h3>
          <p style={{ fontSize: "0.85rem", color: "var(--color-muted, #9ca3af)", margin: 0 }}>{card.desc}</p>
        </NavLink>
      ))}
    </section>
  );
}

export function AdminPage() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_superuser) return <Navigate to="/" replace />;

  return (
    <>
      <section className="hero-card">
        <div className="eyebrow">Platform Admin</div>
        <h2>Super-Admin Console</h2>
        <p>
          Cross-tenant management. Visible only to users with platform-admin (<code>is_superuser</code>) privileges.
        </p>
      </section>

      <nav
        style={{
          display: "flex",
          gap: "0.5rem",
          padding: "0.5rem 0.6rem",
          margin: "1rem 0 0.75rem",
          background: "var(--color-surface, #111827)",
          border: "1px solid var(--color-border, #1f2937)",
          borderRadius: "0.45rem",
          flexWrap: "wrap",
        }}
      >
        {[
          { to: "/admin", label: "Overview", end: true },
          { to: "/admin/tenants", label: "Tenants" },
          { to: "/admin/users", label: "Users" },
          { to: "/admin/permissions", label: "Permissions" },
          { to: "/admin/audit", label: "Global Audit" },
        ].map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            style={({ isActive }) => ({
              padding: "0.4rem 0.85rem",
              borderRadius: "0.3rem",
              fontSize: "0.82rem",
              fontWeight: 500,
              textDecoration: "none",
              color: isActive ? "#fff" : "var(--color-muted, #9ca3af)",
              background: isActive ? "var(--color-accent, #2563eb)" : "transparent",
            })}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <Routes>
        <Route index element={<AdminOverview />} />
        <Route path="tenants" element={<AdminTenantsPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="permissions" element={<AdminPermissionsPage />} />
        <Route path="audit" element={<AdminAuditPage />} />
      </Routes>
    </>
  );
}
