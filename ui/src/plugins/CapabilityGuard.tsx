/**
 * Route-level guard that hides plugin pages whose capability flags are
 * not (or no longer) reported as active by the backend manifest.
 *
 * Renders `NotFoundPage` instead of the wrapped children when any of
 * the required flags is missing. Used by the router factory to wrap
 * each plugin route — the AppShell does the equivalent filtering for
 * sidebar nav items inline.
 */
import type { ReactNode } from "react";

import NotFoundPage from "@/pages/NotFoundPage";

import { capabilitiesSatisfied, usePluginRegistry } from "./registry";

interface CapabilityGuardProps {
  /** Capability flags that ALL must be active. Empty array = always render. */
  requires: readonly string[];
  children: ReactNode;
}

export function CapabilityGuard({ requires, children }: CapabilityGuardProps) {
  const { activeCapabilities } = usePluginRegistry();
  if (!capabilitiesSatisfied(requires, activeCapabilities)) return <NotFoundPage />;
  return <>{children}</>;
}
