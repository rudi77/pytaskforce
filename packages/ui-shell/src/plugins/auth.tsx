/**
 * RBAC context shared between the host shell and any UI plugin.
 *
 * Plugins that bundle their own auth (e.g. `@taskforce/enterprise-ui`)
 * mount a `<UserRolesProvider value={...}>` around their routes; the
 * host's `<RequireRole>` reads from this context via `useUserRoles()`.
 *
 * Living in `@taskforce/ui-shell` (not the host) ensures the React
 * context object identity matches across the host bundle and every
 * plugin chunk — without it, the host's `RequireRole` would read a
 * different context than the plugin's `UserRolesProvider` writes,
 * silently breaking RBAC.
 */
import { createContext, useContext, type ReactNode } from "react";

export interface UserRolesContextValue {
  /**
   * Roles the current user holds, e.g. `["admin"]`. Empty array means
   * "user is authenticated but has no roles" — RBAC guards treat
   * this as forbidden when `requireRoles` is non-empty.
   */
  roles: string[];
  /**
   * Whether the auth state is still loading. Guards render nothing
   * while loading to avoid a flash of forbidden content.
   */
  loading?: boolean;
}

/**
 * `null` is the "no auth provider mounted" signal. Guards treat it
 * as permissive so routes still render in MVP / dev setups.
 */
export const UserRolesContext = createContext<UserRolesContextValue | null>(null);

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
