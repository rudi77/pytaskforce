import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/api/client";

interface AdminMeResponse {
  roles?: string[];
  permissions?: string[];
  user_id?: string;
  tenant_id?: string;
  email?: string;
}

interface CurrentPermissions {
  enforced: boolean;
  permissions: Set<string>;
  userId: string | null;
  tenantId: string | null;
  email: string | null;
}

async function fetchCurrentPermissions(): Promise<CurrentPermissions> {
  try {
    const me = await apiFetch<AdminMeResponse>("/api/v1/admin/me");
    return {
      enforced: true,
      permissions: new Set(me.permissions ?? []),
      userId: me.user_id ?? null,
      tenantId: me.tenant_id ?? null,
      email: me.email ?? null,
    };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 501)) {
      return {
        enforced: false,
        permissions: new Set(),
        userId: null,
        tenantId: null,
        email: null,
      };
    }
    throw error;
  }
}

export function useCurrentPermissions() {
  const query = useQuery({
    queryKey: ["enterprise", "me", "permissions"],
    queryFn: fetchCurrentPermissions,
    retry: 0,
    staleTime: 60_000,
  });

  const can = (permission: string): boolean => {
    if (!query.data) return false;
    if (!query.data.enforced) return true;
    return query.data.permissions.has(permission);
  };

  return {
    ...query,
    can,
    enforced: query.data?.enforced ?? true,
  };
}
