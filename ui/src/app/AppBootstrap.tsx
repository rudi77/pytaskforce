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
import { useEffect, useRef, type ReactNode } from "react";

import { registry } from "@/plugins/registry";
import { checkSkew, logSkewIssue } from "@/plugins/skew";
import { useUIManifest, type UIManifestEntry } from "@/plugins/useManifest";

interface AppBootstrapProps {
  children: ReactNode;
}

function manifestSignature(entries: readonly UIManifestEntry[]): string {
  // Deterministic, stable across refetches with identical content.
  return entries
    .map((p) => `${p.id}@${p.version}:${[...p.capabilities].sort().join(",")}`)
    .sort()
    .join("|");
}

export function AppBootstrap({ children }: AppBootstrapProps) {
  const { data, error } = useUIManifest();

  // TanStack Query returns a fresh `data` object on every refetch.
  // Skip the registry write + skew warning when the *content* is
  // unchanged so AppShell doesn't rerender every 60 s and the skew
  // warning doesn't repeat.
  const lastSignature = useRef<string | null>(null);
  const skewWarned = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!data) return;

    const sig = manifestSignature(data.plugins);
    if (sig === lastSignature.current) return;
    lastSignature.current = sig;

    const flags = data.plugins.flatMap((p) => p.capabilities ?? []);
    registry.setActiveCapabilities(flags);

    const hostVersion =
      typeof __TASKFORCE_UI_VERSION__ === "string" ? __TASKFORCE_UI_VERSION__ : "0.0.0";

    for (const plugin of data.plugins) {
      const issue = checkSkew({
        pluginId: plugin.id,
        hostVersion,
        // Empty string ("") and null both fall back to "0.0.0".
        pluginVersion: plugin.version || "0.0.0",
        constraint: plugin.min_ui_version,
      });
      if (!issue) continue;
      const warnKey = `${plugin.id}@${plugin.version}|${plugin.min_ui_version}`;
      if (skewWarned.current.has(warnKey)) continue;
      skewWarned.current.add(warnKey);
      logSkewIssue(issue);
    }
  }, [data]);

  useEffect(() => {
    if (error) {
      registry.setActiveCapabilities([]);
      lastSignature.current = "";
    }
  }, [error]);

  return <>{children}</>;
}
