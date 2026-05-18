import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

export function AdminTenantsPage() {
  const queryClient = useQueryClient();
  const tenantsQuery = useQuery({ queryKey: ["admin", "tenants"], queryFn: adminApi.listTenants });
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [domain, setDomain] = useState("");

  const createMutation = useMutation({
    mutationFn: () => adminApi.createTenant({ name: name.trim(), slug: slug.trim() || undefined, domain: domain.trim() || undefined }),
    onSuccess: () => {
      setName(""); setSlug(""); setDomain("");
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) => adminApi.updateTenant(id, { is_active: isActive }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] }),
  });

  return (
    <>
      <article className="page-card" style={{ marginBottom: "1rem" }}>
        <div className="eyebrow">Create</div>
        <h3 style={{ marginTop: 0 }}>New Tenant</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: "0.6rem", alignItems: "end" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Name <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc" />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Slug (optional) <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="acme" />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Domain (optional) <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="acme.com" />
          </label>
          <button
            className="assistant-button"
            disabled={!name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? "Creating…" : "Create Tenant"}
          </button>
        </div>
        {createMutation.isError ? (
          <p style={{ color: "var(--color-status-down, #ef4444)", fontSize: "0.8rem", marginTop: "0.6rem" }}>
            {createMutation.error instanceof Error ? createMutation.error.message : "Create failed"}
          </p>
        ) : null}
      </article>

      <article className="page-card">
        <div className="eyebrow">All Tenants</div>
        <h3 style={{ marginTop: 0 }}>{tenantsQuery.data?.count ?? 0} tenants</h3>
        {tenantsQuery.isLoading ? <p>Loading…</p> : null}
        {tenantsQuery.isError ? <p style={{ color: "var(--color-status-down, #ef4444)" }}>Failed to load.</p> : null}
        {tenantsQuery.data ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Name</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Slug</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Domain</th>
                <th style={{ textAlign: "right", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Members</th>
                <th style={{ textAlign: "center", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Status</th>
                <th style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}></th>
              </tr>
            </thead>
            <tbody>
              {tenantsQuery.data.results.map((t) => (
                <tr key={t.tenant_id}>
                  <td style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>{t.name}</td>
                  <td style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)" }}>{t.slug}</td>
                  <td style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)" }}>{t.domain || "—"}</td>
                  <td style={{ padding: "0.5rem 0.4rem", textAlign: "right", borderBottom: "1px solid var(--color-border,#1f2937)" }}>{t.member_count}</td>
                  <td style={{ padding: "0.5rem 0.4rem", textAlign: "center", borderBottom: "1px solid var(--color-border,#1f2937)" }}>
                    {t.is_active ? "Active" : "Disabled"}
                  </td>
                  <td style={{ padding: "0.5rem 0.4rem", textAlign: "right", borderBottom: "1px solid var(--color-border,#1f2937)" }}>
                    <button
                      className="shell__link shell__link--small"
                      onClick={() => updateMutation.mutate({ id: t.tenant_id, isActive: !t.is_active })}
                      disabled={updateMutation.isPending}
                    >
                      {t.is_active ? "Disable" : "Enable"}
                    </button>
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
