import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, type AdminMembership } from "../../lib/api";

export function AdminPermissionsPage() {
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: adminApi.listUsers });
  const catalogQuery = useQuery({ queryKey: ["admin", "permissions", "catalog"], queryFn: adminApi.permissionCatalog });

  const [selectedMembershipId, setSelectedMembershipId] = useState<string>("");

  const membershipQuery = useQuery({
    queryKey: ["admin", "membership", selectedMembershipId],
    queryFn: () => adminApi.fetchMembership(selectedMembershipId),
    enabled: !!selectedMembershipId,
  });

  const [draftExtras, setDraftExtras] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (membershipQuery.data) {
      setDraftExtras(new Set(membershipQuery.data.extra_permissions));
    }
  }, [membershipQuery.data]);

  const membershipOptions = useMemo(() => {
    const list: { id: string; label: string }[] = [];
    for (const user of usersQuery.data?.results || []) {
      for (const membership of user.memberships) {
        list.push({
          id: membership.membership_id,
          label: `${user.username} · ${membership.tenant_name} · ${membership.role}`,
        });
      }
    }
    return list;
  }, [usersQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      adminApi.updateMembership(selectedMembershipId, {
        extra_permissions: Array.from(draftExtras),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "membership", selectedMembershipId] });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });

  const member: AdminMembership | undefined = membershipQuery.data;
  const rolePermissions = new Set((member?.permissions || []).filter((p) => !(member?.extra_permissions || []).includes(p)));

  return (
    <>
      <article className="page-card" style={{ marginBottom: "1rem" }}>
        <div className="eyebrow">Select</div>
        <h3 style={{ marginTop: 0 }}>Which membership?</h3>
        <p style={{ fontSize: "0.8rem", color: "var(--color-muted,#9ca3af)", marginTop: 0 }}>
          Each user has one membership per tenant. Pick the membership to grant extra per-page permissions on top of the role.
        </p>
        <select
          value={selectedMembershipId}
          onChange={(e) => setSelectedMembershipId(e.target.value)}
          style={{ width: "100%", maxWidth: "560px" }}
        >
          <option value="">Select a user / tenant membership…</option>
          {membershipOptions.map((opt) => (
            <option key={opt.id} value={opt.id}>{opt.label}</option>
          ))}
        </select>
      </article>

      {selectedMembershipId && member ? (
        <article className="page-card">
          <div className="eyebrow">Permissions for {member.user.username} @ {member.name}</div>
          <h3 style={{ marginTop: 0 }}>Role: {member.role}</h3>
          <p style={{ fontSize: "0.8rem", color: "var(--color-muted,#9ca3af)", marginTop: 0 }}>
            Checked-but-greyed permissions come from the role and cannot be removed here. Toggle additional permissions below.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "0.75rem" }}>
            {Object.entries(catalogQuery.data?.grouped || {}).map(([group, perms]) => (
              <div key={group}>
                <div style={{ fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-muted,#6b7280)", marginBottom: "0.4rem" }}>
                  {group}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.4rem 0.9rem" }}>
                  {perms.map((p) => {
                    const fromRole = rolePermissions.has(p);
                    const fromExtra = draftExtras.has(p);
                    const checked = fromRole || fromExtra;
                    return (
                      <label
                        key={p}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.45rem",
                          fontSize: "0.82rem",
                          color: fromRole ? "var(--color-muted,#9ca3af)" : "var(--color-text,#e5e7eb)",
                          opacity: fromRole ? 0.7 : 1,
                          cursor: fromRole ? "not-allowed" : "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={fromRole}
                          onChange={(e) => {
                            const next = new Set(draftExtras);
                            if (e.target.checked) next.add(p);
                            else next.delete(p);
                            setDraftExtras(next);
                          }}
                        />
                        <code style={{ fontSize: "0.78rem" }}>{p}</code>
                        {fromRole ? <span style={{ fontSize: "0.65rem", opacity: 0.7 }}>(role)</span> : null}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: "0.6rem", marginTop: "1rem", alignItems: "center" }}>
            <button
              className="assistant-button"
              disabled={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending ? "Saving…" : "Save extra permissions"}
            </button>
            {saveMutation.isSuccess ? <span style={{ color: "var(--color-status-healthy,#22c55e)", fontSize: "0.8rem" }}>Saved.</span> : null}
            {saveMutation.isError ? (
              <span style={{ color: "var(--color-status-down,#ef4444)", fontSize: "0.8rem" }}>
                {saveMutation.error instanceof Error ? saveMutation.error.message : "Save failed"}
              </span>
            ) : null}
          </div>
        </article>
      ) : null}
    </>
  );
}
