import { createContext, useContext, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCurrentTenant, selectTenant, type TenantContextPayload, type TenantMembership } from "./api";
import { useAuth } from "./auth";

type TenantContextValue = {
  current?: TenantMembership;
  tenants: TenantMembership[];
  isLoading: boolean;
  hasPermission: (permission: string) => boolean;
  switchTenant: (tenantId: string) => void;
  switchPending: boolean;
};

const TenantContext = createContext<TenantContextValue>({
  tenants: [],
  isLoading: true,
  hasPermission: () => false,
  switchTenant: () => undefined,
  switchPending: false,
});

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const tenantQuery = useQuery<TenantContextPayload>({
    queryKey: ["tenant-context"],
    queryFn: fetchCurrentTenant,
    retry: false,
    enabled: !!user,
  });
  const switchMutation = useMutation({
    mutationFn: selectTenant,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
  });

  const permissions = useMemo(() => new Set(tenantQuery.data?.current.permissions || []), [tenantQuery.data?.current.permissions]);

  return (
    <TenantContext.Provider
      value={{
        current: tenantQuery.data?.current,
        tenants: tenantQuery.data?.tenants || [],
        isLoading: tenantQuery.isLoading,
        hasPermission: (permission) => permissions.has(permission),
        switchTenant: (tenantId) => switchMutation.mutate(tenantId),
        switchPending: switchMutation.isPending,
      }}
    >
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  return useContext(TenantContext);
}
