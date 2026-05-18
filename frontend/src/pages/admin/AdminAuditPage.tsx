import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

export function AdminAuditPage() {
  const [tenantId, setTenantId] = useState("");
  const [action, setAction] = useState("");
  const [limit, setLimit] = useState(100);

  const tenantsQuery = useQuery({ queryKey: ["admin", "tenants"], queryFn: adminApi.listTenants });
  const auditQuery = useQuery({
    queryKey: ["admin", "audit", tenantId, action, limit],
    queryFn: () => adminApi.auditLog({ tenant_id: tenantId || undefined, action: action || undefined, limit }),
  });

  return (
    <>
      <article className="page-card" style={{ marginBottom: "1rem" }}>
        <div className="eyebrow">Filters</div>
        <h3 style={{ marginTop: 0 }}>Global Audit</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.6rem", alignItems: "end" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Tenant
            <select value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
              <option value="">All tenants</option>
              {(tenantsQuery.data?.results || []).map((t) => (
                <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Action contains
            <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="e.g. tenant.member or alerts.closed" />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Limit
            <select value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))}>
              {[50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
      </article>

      <article className="page-card">
        <div className="eyebrow">Events</div>
        <h3 style={{ marginTop: 0 }}>{auditQuery.data?.count ?? 0} events</h3>
        {auditQuery.isLoading ? <p>Loading…</p> : null}
        {auditQuery.data ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>When</th>
                <th style={{ textAlign: "left", padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Tenant</th>
                <th style={{ textAlign: "left", padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Actor</th>
                <th style={{ textAlign: "left", padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Action</th>
                <th style={{ textAlign: "left", padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Object</th>
                <th style={{ textAlign: "left", padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Metadata</th>
              </tr>
            </thead>
            <tbody>
              {auditQuery.data.results.map((event) => (
                <tr key={event.event_id}>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)", whiteSpace: "nowrap" }}>
                    {event.created_at ? new Date(event.created_at).toLocaleString() : "—"}
                  </td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>{event.tenant_name || "—"}</td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>{event.actor || "—"}</td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}><code>{event.action}</code></td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)" }}>
                    {event.object_type ? `${event.object_type}:${event.object_id}` : "—"}
                  </td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)" }}>
                    <code style={{ fontSize: "0.7rem" }}>{Object.keys(event.metadata).length ? JSON.stringify(event.metadata) : "—"}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </article>
    </>
  );
}
