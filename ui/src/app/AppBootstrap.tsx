/**
 * Bootstraps the dynamic plugin system at runtime.
 *
 * Mount inside the QueryClientProvider (so `useUIManifest` has a
 * client) and around the RouterProvider. On every successful manifest
 * fetch the union of capability flags is published to the plugin
 * registry; AppShell + CapabilityGuard re-render reactively.
 *
 * On a fetch error (e.g. 401 from a missing token) the registry is
 * cleared so plugin nav items disappear gracefully — better than a
 * stale "you can see Audit Log" sidebar.
 */
import { useEffect, type ReactNode } from "react";

import { registry } from "@/plugins/registry";
import { useUIManifest } from "@/plugins/useManifest";

interface AppBootstrapProps {
  children: ReactNode;
}

export function AppBootstrap({ children }: AppBootstrapProps) {
  const { data, error } = useUIManifest();

  useEffect(() => {
    if (data) {
      const flags = data.plugins.flatMap((p) => p.capabilities ?? []);
      registry.setActiveCapabilities(flags);
    }
  }, [data]);

  useEffect(() => {
    if (error) {
      registry.setActiveCapabilities([]);
    }
  }, [error]);

  return <>{children}</>;
}
