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
import { useSettings } from "@/lib/settings";

export interface UIManifestEntry {
  id: string;
  /** Plugin version, used for skew warnings. Defaults to "0.0.0". */
  version: string;
  /** Capability flags; the registry treats an empty list as "plugin opted out". */
  capabilities: string[];
  display_name?: string;
  npm_package?: string | null;
  min_ui_version?: string | null;
}

export interface UIManifestResponse {
  plugins: UIManifestEntry[];
}

export const UI_MANIFEST_QUERY_KEY = ["ui-manifest"] as const;

export function useUIManifest() {
  // Manifest requires auth; firing it without a token returns 401 and
  // the global onUnauthorized hook would yank the user away from
  // public pages (signup, login). Gate the query on token presence —
  // when the user logs in, the LoginPage invalidates this query key
  // and the manifest fetches as expected.
  const apiToken = useSettings((s) => s.apiToken);
  return useQuery<UIManifestResponse>({
    queryKey: UI_MANIFEST_QUERY_KEY,
    queryFn: () => apiFetch<UIManifestResponse>("/api/v1/ui/manifest"),
    staleTime: 60_000,
    retry: 1,
    enabled: !!apiToken,
  });
}
