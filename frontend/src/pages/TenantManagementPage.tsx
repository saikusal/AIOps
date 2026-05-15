import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTenantMember,
  disableTenantMember,
  fetchTenantMembers,
  updateTenantMember,
  type TenantMembership,
} from "../lib/api";
import { useTenant } from "../lib/tenant";

const roleOptions = ["viewer", "operator", "admin", "owner"];

function MemberRow({ member }: { member: TenantMembership }) {
  const queryClient = useQueryClient();
  const [role, setRole] = useState(member.role);
  const updateMutation = useMutation({
    mutationFn: () => updateTenantMember(member.membership_id, { role, is_active: member.is_active !== false }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tenant-members"] }),
        queryClient.invalidateQueries({ queryKey: ["tenant-context"] }),
      ]);
    },
  });
  const disableMutation = useMutation({
    mutationFn: () => disableTenantMember(member.membership_id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tenant-members"] }),
        queryClient.invalidateQueries({ queryKey: ["tenant-context"] }),
      ]);
    },
  });

  const userLabel = member.user?.username || member.user?.email || "User";
  const hasChanged = role !== member.role;
  const isInactive = member.is_active === false;

  return (
    <tr>
      <td>
        <strong>{userLabel}</strong>
        <span>{member.user?.email || "No email set"}</span>
      </td>
      <td>
        <select value={role} onChange={(event) => setRole(event.target.value)} disabled={isInactive}>
          {roleOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </td>
      <td>
        <span className={`tenant-status ${isInactive ? "tenant-status--inactive" : ""}`}>
          {isInactive ? "Disabled" : "Active"}
        </span>
      </td>
      <td>
        <div className="tenant-member-actions">
          <button
            className="action-button action-button--secondary"
            type="button"
            disabled={!hasChanged || isInactive || updateMutation.isPending}
            onClick={() => updateMutation.mutate()}
          >
            Update
          </button>
          <button
            className="action-button action-button--danger"
            type="button"
            disabled={isInactive || disableMutation.isPending}
            onClick={() => disableMutation.mutate()}
          >
            Disable
          </button>
        </div>
        {(updateMutation.error || disableMutation.error) && (
          <p className="inline-error">
            {updateMutation.error instanceof Error
              ? updateMutation.error.message
              : disableMutation.error instanceof Error
                ? disableMutation.error.message
                : "Member update failed."}
          </p>
        )}
      </td>
    </tr>
  );
}

export function TenantManagementPage() {
  const queryClient = useQueryClient();
  const { current, hasPermission } = useTenant();
  const canManage = hasPermission("tenant.manage");
  const [form, setForm] = useState({ username: "", email: "", role: "viewer" });
  const membersQuery = useQuery({
    queryKey: ["tenant-members"],
    queryFn: fetchTenantMembers,
    enabled: canManage,
  });
  const createMutation = useMutation({
    mutationFn: () =>
      createTenantMember({
        username: form.username.trim() || undefined,
        email: form.email.trim() || undefined,
        role: form.role,
      }),
    onSuccess: async () => {
      setForm({ username: "", email: "", role: "viewer" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tenant-members"] }),
        queryClient.invalidateQueries({ queryKey: ["tenant-context"] }),
      ]);
    },
  });

  const activeCount = useMemo(
    () => (membersQuery.data || []).filter((member) => member.is_active !== false).length,
    [membersQuery.data],
  );

  if (!canManage) {
    return (
      <div className="page-card tenant-management">
        <div className="eyebrow">Access Control</div>
        <h2>Tenant Members</h2>
        <p>You need tenant administrator access to manage workspace members.</p>
      </div>
    );
  }

  return (
    <div className="page-card tenant-management">
      <header className="tenant-management__header">
        <div>
          <div className="eyebrow">Access Control</div>
          <h2>Tenant Members</h2>
          <p>{current?.name || "Current workspace"} member access and role assignments.</p>
        </div>
        <div className="tenant-management__stats">
          <span>Active</span>
          <strong>{activeCount}</strong>
        </div>
      </header>

      <form
        className="tenant-member-form"
        onSubmit={(event) => {
          event.preventDefault();
          createMutation.mutate();
        }}
      >
        <label className="form-field">
          <span>Username</span>
          <input
            value={form.username}
            onChange={(event) => setForm((currentForm) => ({ ...currentForm, username: event.target.value }))}
            placeholder="ops-admin"
          />
        </label>
        <label className="form-field">
          <span>Email</span>
          <input
            type="email"
            value={form.email}
            onChange={(event) => setForm((currentForm) => ({ ...currentForm, email: event.target.value }))}
            placeholder="user@example.com"
          />
        </label>
        <label className="form-field">
          <span>Role</span>
          <select value={form.role} onChange={(event) => setForm((currentForm) => ({ ...currentForm, role: event.target.value }))}>
            {roleOptions.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <button className="action-button" type="submit" disabled={createMutation.isPending || (!form.username.trim() && !form.email.trim())}>
          Add Member
        </button>
      </form>
      {createMutation.error && <p className="inline-error">{createMutation.error instanceof Error ? createMutation.error.message : "Member create failed."}</p>}

      {membersQuery.isLoading && <p className="tenant-management__message">Loading members...</p>}
      {membersQuery.error && <p className="inline-error">{membersQuery.error instanceof Error ? membersQuery.error.message : "Unable to load members."}</p>}

      <div className="tenant-member-table-wrap">
        <table className="tenant-member-table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Role</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {(membersQuery.data || []).map((member) => (
              <MemberRow key={member.membership_id} member={member} />
            ))}
          </tbody>
        </table>
        {!membersQuery.isLoading && (membersQuery.data || []).length === 0 && (
          <p className="tenant-management__message">No members are assigned to this tenant.</p>
        )}
      </div>
    </div>
  );
}
