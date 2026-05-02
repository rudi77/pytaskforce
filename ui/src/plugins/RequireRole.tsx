/**
 * Lightweight RBAC guard for plugin pages.
 *
 * The host shell does not own user identity — pytaskforce core has no
 * built-in auth — so this guard reads from a `UserRolesContext` that
 * the plugin (or a future host-side provider) populates. When no
 * provider is mounted, the guard is permissive: routes render
 * normally. This keeps the dev experience friendly for setups without
 * RBAC while still letting enterprise (or any other plugin) plug in a
 * provider around its routes that returns real role claims.
 *
 * When a provider IS mounted but the current user lacks all required
 * roles, the guard renders a forbidden page (403-style). Returning a
 * "forbidden" rather than "not found" is intentional: the user can see
 * the feature exists and may request access, vs. silently hiding it.
 */
import { createContext, useContext, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

interface UserRolesContextValue {
  /**
   * Roles the current user holds, e.g. `["admin"]`. Empty array means
   * "user is authenticated but has no roles" — the guard treats this
   * as forbidden when `requireRoles` is non-empty.
   */
  roles: string[];
  /**
   * Whether the auth state is still loading. The guard renders nothing
   * while loading to avoid a flash of forbidden content.
   */
  loading?: boolean;
}

/**
 * `null` is the "no auth provider mounted" signal. The guard treats it
 * as permissive so routes still render in MVP / dev setups.
 */
const UserRolesContext = createContext<UserRolesContextValue | null>(null);

interface UserRolesProviderProps {
  value: UserRolesContextValue;
  children: ReactNode;
}

export function UserRolesProvider({ value, children }: UserRolesProviderProps) {
  return (
    <UserRolesContext.Provider value={value}>{children}</UserRolesContext.Provider>
  );
}

/** Read the user's role claims. Returns `null` when no provider is mounted. */
export function useUserRoles(): UserRolesContextValue | null {
  return useContext(UserRolesContext);
}

interface RequireRoleProps {
  /** ANY of these roles satisfies the guard. Empty array = always render. */
  roles: readonly string[];
  children: ReactNode;
}

function ForbiddenPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <h2 className="text-2xl font-semibold tracking-tight">Forbidden</h2>
      <p className="text-sm text-muted-foreground">
        Your account does not have access to this page.
      </p>
      <Button asChild>
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}

export function RequireRole({ roles, children }: RequireRoleProps) {
  const ctx = useUserRoles();

  // No provider mounted → no auth configured → render permissively.
  if (ctx === null) return <>{children}</>;

  if (ctx.loading) return null;

  if (roles.length === 0) return <>{children}</>;

  const hasAnyRole = roles.some((role) => ctx.roles.includes(role));
  return hasAnyRole ? <>{children}</> : <ForbiddenPage />;
}
