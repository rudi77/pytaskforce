/**
 * Host-side façade over the shared `@taskforce/ui-shell` HTTP client.
 *
 * The shell owns the actual implementation (`apiFetch`, `sseStream`,
 * `ApiError`) so the host UI and any UI plugin (e.g.
 * `@taskforce/enterprise-ui`) speak to the backend through one
 * configured client — same auth headers, same error class, same base
 * URL. The host calls {@link configureApiClient} once at startup
 * (see `src/main.tsx`) to plug in the settings-store accessors;
 * everything else just imports `apiFetch` from `@/api/client` (host)
 * or `@taskforce/ui-shell` (plugin) and they hit the same code path.
 *
 * This file used to contain a duplicate implementation. Keeping it
 * as a thin re-export preserves the established `@/api/client`
 * import paths used across the existing pages.
 */
export { apiFetch, sseStream, ApiError, configureApiClient } from "@taskforce/ui-shell";
export type { ApiClientConfig } from "@taskforce/ui-shell";
