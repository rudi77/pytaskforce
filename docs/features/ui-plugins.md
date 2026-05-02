# UI Plugin System

The Taskforce management UI supports optional **UI plugins** —
external npm packages that contribute sidebar entries and pages to
the React shell. UI plugins pair with a backend Python plugin (the
ones loaded via the `taskforce.plugins` entry-point group) and are
gated at runtime by the backend's manifest, so an installed UI
plugin stays invisible until the matching backend plugin is loaded.

This system is what makes
[`taskforce-enterprise`](https://github.com/rudi77/taskforce-enterprise)
ship its admin pages (Tenants, Users & Roles, Audit Log, Agent
Catalog, Approvals) without modifying the open-source core.

For the architectural rationale see
[ADR-021](../adr/adr-021-ui-plugin-system.md).

---

## For operators: how to enable an enterprise UI plugin

An operator who wants the enterprise admin pages does this once:

1. **Install the backend plugin** (Python):

   ```bash
   pip install taskforce-enterprise   # or: uv pip install ...
   ```

   At Taskforce API startup the entry-point group `taskforce.plugins`
   discovers the package automatically. Confirm it loaded:

   ```bash
   curl http://localhost:8070/api/v1/ui/manifest
   ```

   The response should include `{"id": "enterprise", ...}`. The
   manifest endpoint is intentionally unauthenticated (the same level
   of disclosure as the React shell would already make at first
   render) but deliberately omits the server version to limit
   fingerprinting — use `GET /health` if you need a version probe.

2. **Install the matching UI plugin** (npm) and rebuild the host UI:

   ```jsonc
   // ui/package.json
   {
     "optionalDependencies": {
       "@taskforce/enterprise-ui": "^0.1.0"
     }
   }
   ```

   ```bash
   cd ui && npm install && npm run build
   ```

   Vite detects the package and bundles the enterprise pages as
   separate lazy chunks. Operators who don't want the enterprise UI
   simply omit step 2 — the build skips the package without errors.

3. **Reload the management UI in the browser.** The "Admin" section
   appears in the sidebar with the entries the backend manifest
   declared.

### Disabling individual capabilities

The backend plugin can filter which capabilities it advertises. For
example, in your plugin config:

```yaml
enterprise:
  ui:
    enabled_capabilities: [admin.users, admin.audit]
```

Pages whose capability is not listed disappear from the sidebar.
Existing browser sessions catch up within ~60 s (the manifest
refetch interval).

### Tailwind purge

If you maintain a custom Tailwind configuration, make sure the
plugin's compiled output is in your `content` glob, otherwise the
plugin's utility classes get purged at build time:

```ts
// ui/tailwind.config.ts
import preset from "@taskforce/ui-shell/tailwind.preset";

export default {
  presets: [preset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "./node_modules/@taskforce/enterprise-ui/dist/**/*.{js,mjs}",
  ],
};
```

---

## For plugin authors: how to ship a UI plugin

Most authors will want to start by copying the reference
implementation:

```bash
cp -r packages/enterprise-ui-reference  taskforce-<plugin>/web
```

The minimum a UI plugin needs:

```ts
// src/index.ts
import type { PluginRegistry, UIPlugin } from "@taskforce/ui-shell";
import { lazy } from "react";
import { Building2 } from "lucide-react";

const plugin: UIPlugin = {
  id: "<plugin-id>",                   // matches backend get_ui_manifest()["id"]
  displayName: "...",
  version: "0.1.0",
  capabilities: ["<plugin-id>.feature_a", "<plugin-id>.feature_b"],
  navItems: [
    {
      to: "/<plugin-id>/feature_a",
      label: "Feature A",
      icon: Building2,
      section: "admin",
      requires: ["<plugin-id>.feature_a"],
      order: 10,
    },
  ],
  routes: [
    {
      path: "<plugin-id>/feature_a",
      element: lazy(() => import("./pages/FeatureA")),
      requires: ["<plugin-id>.feature_a"],
      requireRoles: ["admin"],          // optional RBAC gate
    },
  ],
};

export function register(registry: PluginRegistry): void {
  registry.register(plugin);
}
```

The package's `package.json` should peer-depend on
`@taskforce/ui-shell`, `react`, `react-dom`, `react-router-dom`,
`@tanstack/react-query`, and `lucide-react` so the host bundle
provides exactly one copy of each.

### Backend manifest

In your plugin's Python class, return a `UIManifest` (a `TypedDict`
exported from `taskforce.application.plugin_loader`):

```python
def get_ui_manifest(self) -> UIManifest:
    return {
        "id": "<plugin-id>",
        "version": __version__,
        "display_name": "My Plugin",
        "capabilities": ["<plugin-id>.feature_a", "<plugin-id>.feature_b"],
        "npm_package": "@taskforce/<plugin>-ui",
        "min_ui_version": ">=0.1.0,<1.0.0",
    }
```

The host's `GET /api/v1/ui/manifest` aggregates manifests from all
loaded plugins. Plugins without `get_ui_manifest()` are silently
skipped (additive contract).

### Capability flags

Capability flags are arbitrary strings, but a `<plugin>.<feature>`
convention keeps them readable. Every nav item / route's `requires`
array lists the flags that must be present in the manifest for the
item to render. An empty `requires` defaults to the plugin's own
`capabilities` list.

When the user visits a route whose capability is not active, the
host's `<CapabilityGuard>` renders the standard `NotFoundPage` —
this matches the URL silently disappearing from the sidebar.

### RBAC gating

Plugins that need per-page RBAC (e.g. only admins see "Audit Log")
declare `requireRoles: ["admin", "auditor"]` on the route. The host
ships a permissive default — when no `<UserRolesProvider>` is
mounted, every role check passes. The plugin is responsible for
mounting its own provider that calls its `/api/v1/admin/me` endpoint
(or equivalent) and supplies the user's roles.

When a provider IS mounted but the user lacks all required roles,
the route renders a Forbidden page (not a 404 — the user can see
the feature exists and may request access).

### Version skew

If your manifest declares `min_ui_version`, the host's skew detector
compares the running UI bundle's version against the constraint and
emits a `console.warn` when mismatched. Supported grammar:

| Constraint | Meaning |
|---|---|
| `">=1.0.0"` | host >= 1.0.0 |
| `">=1.0.0,<2.0.0"` | 1.0.0 <= host < 2.0.0 |
| `"1.2.3"` | host exactly 1.2.3 |

The warning links the plugin id, the host's version, and the
constraint, so an operator seeing
`[ui-plugins] enterprise@1.2.0 expects host >=1.2.0,<2.0.0, but
host is 1.1.0` knows to rebuild the bundle. Skew is non-fatal — the
plugin still loads.

---

## API reference

### Backend

| Endpoint | Returns |
|---|---|
| `GET /api/v1/ui/manifest` | `{ plugins: UIManifestEntry[], server_version: string }` |

```python
class UIManifest(TypedDict, total=False):
    id: str
    version: str
    display_name: str
    capabilities: list[str]
    npm_package: str | None
    min_ui_version: str | None
```

### Frontend (`@taskforce/ui-shell`)

| Symbol | Purpose |
|---|---|
| `UIPlugin` | Plugin shape: `id`, `displayName`, `version`, `capabilities`, `navItems`, `routes` |
| `PluginRegistry` | Mutable registry: `register(plugin)`, `list()`, `setActiveCapabilities(...)`, `isCapabilityActive(...)` |
| `PluginNavItem` | Sidebar entry: `to`, `label`, `icon`, `section`, `requires`, `order` |
| `PluginRoute` | Page: `path`, `element`, `requires`, `requireRoles` |
| `apiFetch`, `sseStream`, `ApiError` | HTTP helpers using the host-configured base URL + bearer token |
| `configureApiClient(...)` | Host-side install of base URL + token providers |
| `Button`, `Card`, `Tabs`, `Dialog`, `Input`, ... | shadcn-derived primitives, single source of truth |
| `tailwind.preset` (sub-export) | Shared Tailwind preset (colors, spacing, animations, fonts) |

### Frontend (host)

| Symbol | Purpose |
|---|---|
| `bootstrapPlugins()` | Dynamically imports each optional plugin package and calls its `register(...)` |
| `<AppBootstrap>` | Fetches `/api/v1/ui/manifest`, publishes capabilities into the registry, runs skew check |
| `<CapabilityGuard requires>` | Renders `NotFoundPage` when any required flag is missing |
| `<RequireRole roles>` | Renders Forbidden when the user lacks all required roles (no-op when no provider mounted) |
| `<UserRolesProvider value>` | Plugin-mounted context that supplies the current user's roles |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Plugin nav items don't appear | Backend plugin not loaded | `is_enterprise_available()` / check `/api/v1/ui/manifest` |
| Plugin nav items appear, page renders 404 | Capability listed in manifest but `requires` references a different flag | Align flag names between backend manifest and plugin's `requires` |
| Plugin styles look wrong | Tailwind purged the plugin's classes | Add the plugin's `dist/` glob to `content` in the host's Tailwind config |
| Console: `unused '@ts-expect-error' directive` | TS now sees the package; remove the directive | Use `optional-plugins.d.ts` ambient declaration instead |
| Console: `[ui-plugins] X expects host …` | Version skew | Rebuild the host UI bundle, or pin the plugin to a compatible version |
