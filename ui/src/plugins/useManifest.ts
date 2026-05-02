/**
 * TanStack-Query hook that fetches the backend's UI manifest.
 *
 * The manifest tells the shell which optional backend plugins are
 * loaded and which capability flags they contribute. The hook is
 * consumed by `<AppBootstrap>` which relays the flags into the plugin
 * registry. Refetching is gentle (60 s stale time) so a server-side
 * plugin disabling is picked up within a minute without hammering the
 * endpoint.
 */
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export interface UIManifestEntry {
  id: string;
  version?: string;
  display_name?: string;
  capabilities: string[];
  npm_package?: string | null;
  min_ui_version?: string | null;
}

export interface UIManifestResponse {
  plugins: UIManifestEntry[];
  server_version: string;
}

export const UI_MANIFEST_QUERY_KEY = ["ui-manifest"] as const;

export function useUIManifest() {
  return useQuery<UIManifestResponse>({
    queryKey: UI_MANIFEST_QUERY_KEY,
    queryFn: () => apiFetch<UIManifestResponse>("/api/v1/ui/manifest"),
    staleTime: 60_000,
    retry: 1,
  });
}
