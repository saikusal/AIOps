import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, type AdminUser } from "../../lib/api";

const ROLE_CHOICES = ["viewer", "responder", "operator", "admin", "owner", "auditor"];

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: adminApi.listUsers });
  const tenantsQuery = useQuery({ queryKey: ["admin", "tenants"], queryFn: adminApi.listTenants });
  const [form, setForm] = useState({ username: "", email: "", password: "", is_superuser: false });
  const [assignFor, setAssignFor] = useState<AdminUser | null>(null);
  const [assignTenantId, setAssignTenantId] = useState("");
  const [assignRole, setAssignRole] = useState("viewer");

  const createMutation = useMutation({
    mutationFn: () => adminApi.createUser(form),
    onSuccess: () => {
      setForm({ username: "", email: "", password: "", is_superuser: false });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Parameters<typeof adminApi.updateUser>[1] }) => adminApi.updateUser(id, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  const assignMutation = useMutation({
    mutationFn: () => adminApi.createMembership({ tenant_id: assignTenantId, user_id: assignFor!.id, role: assignRole }),
    onSuccess: () => {
      setAssignFor(null); setAssignTenantId(""); setAssignRole("viewer");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });

  return (
    <>
      <article className="page-card" style={{ marginBottom: "1rem" }}>
        <div className="eyebrow">Create</div>
        <h3 style={{ marginTop: 0 }}>New User</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto auto", gap: "0.6rem", alignItems: "end" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Username <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Email <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
            Password (min 8) <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", paddingBottom: "0.5rem" }}>
            <input type="checkbox" checked={form.is_superuser} onChange={(e) => setForm({ ...form, is_superuser: e.target.checked })} />
            Platform admin
          </label>
          <button
            className="assistant-button"
            disabled={!form.username.trim() || form.password.length < 8 || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? "Creating…" : "Create"}
          </button>
        </div>
        {createMutation.isError ? (
          <p style={{ color: "var(--color-status-down, #ef4444)", fontSize: "0.8rem", marginTop: "0.6rem" }}>
            {createMutation.error instanceof Error ? createMutation.error.message : "Create failed"}
          </p>
        ) : null}
      </article>

      <article className="page-card">
        <div className="eyebrow">All Users</div>
        <h3 style={{ marginTop: 0 }}>{usersQuery.data?.count ?? 0} users</h3>
        {usersQuery.isLoading ? <p>Loading…</p> : null}
        {usersQuery.data ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>User</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Email</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Tenants</th>
                <th style={{ textAlign: "center", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Admin</th>
                <th style={{ textAlign: "center", padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>Active</th>
                <th style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}></th>
              </tr>
            </thead>
            <tbody>
              {usersQuery.data.results.map((u) => (
                <tr key={u.id}>
                  <td style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)" }}>{u.username}</td>
                  <td style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)" }}>{u.email || "—"}</td>
                  <td style={{ padding: "0.5rem 0.4rem", borderBottom: "1px solid var(--color-border,#1f2937)", color: "var(--color-muted,#9ca3af)" }}>
                    {u.memberships.length === 0 ? "—" : u.memberships.map((m) => `${m.tenant_name} (${m.role})`).join(", ")}
                  </td>
                  <td style={{ padding: "0.5rem 0.4rem", textAlign: "center", borderBottom: "1px solid var(--color-border,#1f2937)" }}>
                    <input
                      type="checkbox"
                      checked={u.is_superuser}
                      onChange={(e) => updateMutation.mutate({ id: u.id, patch: { is_superuser: e.target.checked } })}
                    />
                  </td>
                  <td style={{ padding: "0.5rem 0.4rem", textAlign: "center", borderBottom: "1px solid var(--color-border,#1f2937)" }}>
                    <input
                      type="checkbox"
                      checked={u.is_active}
                      onChange={(e) => updateMutation.mutate({ id: u.id, patch: { is_active: e.target.checked } })}
                    />
                  </td>
                  <td style={{ padding: "0.5rem 0.4rem", textAlign: "right", borderBottom: "1px solid var(--color-border,#1f2937)" }}>
                    <button className="shell__link shell__link--small" onClick={() => setAssignFor(u)}>
                      Assign tenant
                    </button>
                    <button
                      className="shell__link shell__link--small"
                      onClick={() => {
                        const pw = prompt(`New password for ${u.username} (min 8 chars):`);
                        if (pw && pw.length >= 8) updateMutation.mutate({ id: u.id, patch: { password: pw } });
                      }}
                    >
                      Reset password
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </article>

      {assignFor ? (
        <article className="page-card" style={{ marginTop: "1rem" }}>
          <div className="eyebrow">Assign tenant</div>
          <h3 style={{ marginTop: 0 }}>Add {assignFor.username} to a tenant</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: "0.6rem", alignItems: "end" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
              Tenant
              <select value={assignTenantId} onChange={(e) => setAssignTenantId(e.target.value)}>
                <option value="">Select a tenant…</option>
                {(tenantsQuery.data?.results || []).map((t) => (
                  <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>
                ))}
              </select>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.78rem" }}>
              Role
              <select value={assignRole} onChange={(e) => setAssignRole(e.target.value)}>
                {ROLE_CHOICES.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </label>
            <button
              className="assistant-button"
              disabled={!assignTenantId || assignMutation.isPending}
              onClick={() => assignMutation.mutate()}
            >
              {assignMutation.isPending ? "Assigning…" : "Assign"}
            </button>
            <button className="shell__link shell__link--small" onClick={() => setAssignFor(null)}>Cancel</button>
          </div>
          {assignMutation.isError ? (
            <p style={{ color: "var(--color-status-down, #ef4444)", fontSize: "0.8rem", marginTop: "0.6rem" }}>
              {assignMutation.error instanceof Error ? assignMutation.error.message : "Assign failed"}
            </p>
          ) : null}
        </article>
      ) : null}
    </>
  );
}
