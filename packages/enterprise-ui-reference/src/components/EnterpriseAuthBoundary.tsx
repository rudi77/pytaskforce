/**
 * Auth boundary that supplies real RBAC claims to the host's
 * `<RequireRole>` guard.
 *
 * Without this wrapper the host's `<RequireRole>` guard would find no
 * `<UserRolesProvider>` and fall back to permissive rendering — fine
 * for dev, NOT fine for an enterprise admin panel. Every route this
 * package contributes is wrapped in `EnterpriseAuthBoundary` so
 * production deployments enforce admin/auditor/approver roles.
 *
 * Roles come from `GET /api/v1/admin/me`, which is owned by the
 * enterprise backend plugin. While that request is in-flight the
 * provider exposes `loading: true` so guards render nothing rather
 * than briefly flashing forbidden content.
 */
import { useQuery } from "@tanstack/react-query";
import {
  ApiError,
  apiFetch,
  Skeleton,
  UserRolesProvider,
} from "@taskforce/ui-shell";
import type { ReactNode } from "react";

interface AdminMeResponse {
  id: string;
  email: string;
  roles: string[];
}

async function fetchAdminMe(): Promise<{ roles: string[] }> {
  try {
    const me = await apiFetch<AdminMeResponse>("/api/v1/admin/me");
    return { roles: me.roles ?? [] };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      // Unauthenticated / forbidden → no roles, the guard will reject.
      return { roles: [] };
    }
    if (error instanceof ApiError && (error.status === 404 || error.status === 501)) {
      // /admin/me not yet deployed → degrade to "no roles" so guards
      // visibly forbid rather than silently allow.
      return { roles: [] };
    }
    throw error;
  }
}

interface EnterpriseAuthBoundaryProps {
  children: ReactNode;
}

export function EnterpriseAuthBoundary({ children }: EnterpriseAuthBoundaryProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["enterprise", "me"],
    queryFn: fetchAdminMe,
    staleTime: 60_000,
    retry: 0,
  });

  if (error && !(error instanceof ApiError)) {
    // Network error — surface it; we do NOT default to permissive.
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-6 text-sm text-destructive">
        <p className="font-medium">Could not load auth context.</p>
        <p className="mt-1 text-xs">
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      </div>
    );
  }

  return (
    <UserRolesProvider value={{ roles: data?.roles ?? [], loading: isLoading }}>
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-9 w-1/3" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : (
        children
      )}
    </UserRolesProvider>
  );
}
