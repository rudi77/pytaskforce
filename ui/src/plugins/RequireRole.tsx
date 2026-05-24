/**
 * Lightweight RBAC guard for plugin pages.
 *
 * The host shell does not own user identity — pytaskforce core has no
 * built-in auth — so this guard reads from a `UserRolesContext` that
 * the plugin (or a future host-side provider) populates.
 *
 * Default policy when **no provider** is mounted: permissive
 * (children render). This keeps the dev experience friendly for
 * setups without RBAC. To prevent shipping an open admin panel
 * accidentally, we emit a one-time `console.warn` per route the
 * first time `RequireRole` is hit with a non-empty `roles` list and
 * no provider — operators see the warning in browser devtools.
 *
 * When a provider IS mounted but the current user lacks all required
 * roles, the guard renders a forbidden page (403-style). Returning a
 * "forbidden" rather than "not found" is intentional: the user can see
 * the feature exists and may request access, vs. silently hiding it.
 *
 * Plugins that bundle their own auth (e.g. `taskforce-enterprise`)
 * MUST mount a `<UserRolesProvider>` from `@taskforce/ui-shell`
 * around their routes that supplies real claims.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useUserRoles } from "@taskforce/ui-shell";

import { Button } from "@/components/ui/button";

// Re-export the auth context surface so existing host imports
// (`@/plugins/RequireRole`) keep working unchanged.
export {
  UserRolesContext,
  UserRolesProvider,
  useUserRoles,
  type UserRolesContextValue,
} from "@taskforce/ui-shell";

interface RequireRoleProps {
  /** ANY of these roles satisfies the guard. Empty array = always render. */
  roles: readonly string[];
  children: ReactNode;
}

function ForbiddenPage() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <h2 className="text-2xl font-semibold tracking-tight">Forbidden</h2>
      <p className="text-sm text-muted-foreground">
        Your account does not have access to this page.
      </p>
      <Button onClick={() => navigate("/")}>Back to dashboard</Button>
    </div>
  );
}

/**
 * Tracks which (plugin, roles) pairs we have already warned about,
 * so the dev-mode console doesn't get one warning per render.
 */
const warnedKeys = new Set<string>();

export function RequireRole({ roles, children }: RequireRoleProps) {
  const ctx = useUserRoles();
  const requiresAuth = roles.length > 0;
  const noProvider = ctx === null;
  const warnKey = useRef<string>(roles.join("|")).current;

  useEffect(() => {
    if (requiresAuth && noProvider && !warnedKeys.has(warnKey)) {
      warnedKeys.add(warnKey);
      console.warn(
        `[ui-plugins] <RequireRole roles={${JSON.stringify(roles)}}> ` +
          "rendered without a <UserRolesProvider> mounted. The route " +
          "will render permissively — mount a provider that supplies " +
          "real role claims to enforce RBAC.",
      );
    }
  }, [requiresAuth, noProvider, warnKey, roles]);

  // No provider mounted → no auth configured → render permissively.
  if (ctx === null) return <>{children}</>;

  if (ctx.loading) return null;

  if (!requiresAuth) return <>{children}</>;

  const hasAnyRole = roles.some((role) => ctx.roles.includes(role));
  return hasAnyRole ? <>{children}</> : <ForbiddenPage />;
}

/** Test-only: clears the warned-keys set so warnings can be re-asserted. */
export function __resetWarnedKeysForTests() {
  warnedKeys.clear();
}
