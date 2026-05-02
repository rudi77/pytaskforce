# ADR-021: UI Plugin System for the Management UI

**Status:** Accepted
**Date:** 2026-05-02

## Context

Until now the React management UI (`ui/src/app/AppShell.tsx`,
`ui/src/app/router.tsx`) wired its sidebar entries and routes
statically. The backend already supported optional plugins via the
entry-point system (`PluginProtocol`, `taskforce.plugins`,
`taskforce.routers`, `is_enterprise_available()`), but those plugins
could only contribute REST routes — there was no mechanism to expose
new UI surfaces.

This blocked features like `taskforce-enterprise` (Tenants, Users &
Roles, Audit Log, Agent Catalog, Approvals) from shipping a
management UI alongside their REST API. Either the host UI would have
to know about every plugin at build time (tight coupling) or a custom
fork of the host would be needed (no longer "open source core +
optional enterprise plugin"). Both were unacceptable.

We needed a contract that:

* lets external packages contribute nav items and pages with no host
  source-code change,
* keeps those contributions **invisible** when the matching backend
  plugin is not loaded (so installing only the npm package without
  the Python package shows nothing),
* preserves a **single design system** so plugin pages are visually
  indistinguishable from host pages,
* keeps a clean clean-architecture boundary (no host code reaching
  into plugin internals or vice versa),
* is **build-time** rather than runtime, so we avoid Module
  Federation, CSP relaxations, and double-React bugs.

## Decision

Introduce a three-layer system:

1. **Backend contract** (this repo): `PluginProtocol` gains an
   optional `get_ui_manifest()` returning a `UIManifest` TypedDict
   (`id`, `version`, `display_name`, `capabilities`, `npm_package`,
   `min_ui_version`). A new endpoint `GET /api/v1/ui/manifest`
   aggregates the manifest of every loaded plugin and returns it
   with the server version.

2. **Frontend plugin SDK** (`packages/ui-shell/`,
   `@taskforce/ui-shell`): a published npm package that owns
   - the shadcn-derived primitives (`Button`, `Card`, `Tabs`,
     `Dialog`, `Input`, `Label`, `Badge`, `Skeleton`, `Textarea`,
     `Toast`),
   - a Tailwind preset (`@taskforce/ui-shell/tailwind.preset`) so
     host and plugins share tokens,
   - a configurable `apiFetch` / `sseStream` / `ApiError` (the host
     calls `configureApiClient(...)` at startup; plugins just
     import `apiFetch`),
   - the canonical plugin contract types (`UIPlugin`, `PluginNavItem`,
     `PluginRoute`, `PluginRegistry`).

3. **Host integration** (`ui/src/plugins/`): a Zustand-backed
   `PluginRegistry`, an `<AppBootstrap>` that fetches the manifest
   and publishes the union of capability flags into the registry,
   and `<CapabilityGuard>` / `<RequireRole>` guards used by the
   router factory. `AppShell` merges built-in nav items with the
   registered plugins' nav items, splitting them into a `main` and
   an `admin` section.

Plugins are loaded via dynamic `import()` from
`ui/src/plugins/loader.ts`. Vite is taught (via
`vite.config.ts → rollupOptions.external`) to externalize any
optional plugin package that is not present in `node_modules` so the
build never breaks when a package is missing. When the package IS
installed, Rollup bundles its code as separate lazy chunks because
the plugin's pages use `lazy(() => import(...))`.

## Consequences

### Positive

* **Operators opt in per package**: installing
  `pip install taskforce-enterprise` enables the backend; adding
  `@taskforce/enterprise-ui` to `optionalDependencies` in
  `ui/package.json` and rebuilding pulls in the matching UI.
* **No design drift**: plugins can only render shell-provided
  primitives + Tailwind classes from the shared preset, so spacing,
  colors, typography, and dark-mode behavior are identical to the
  host.
* **Two-layer gating**: capability flags hide entire features when
  the backend plugin is disabled at runtime; per-route RBAC roles
  hide individual pages when the user lacks the required claim.
* **Same-origin, single bundle**: no CSP relaxations, no
  cross-origin script loads, no double-React bugs.
* **Backwards compatible**: existing plugins without
  `get_ui_manifest()` still work — the loader uses
  `getattr(instance, "get_ui_manifest", None)`.

### Negative / risks

* **Version skew** between host and plugin: mitigated by
  `min_ui_version` in each manifest entry plus a console warning
  emitted by the host's skew detector (`ui/src/plugins/skew.ts`)
  when the host is out of range.
* **Operator must rebuild** the UI bundle to pick up a newly
  installed plugin (build-time integration). Acceptable trade-off
  vs. the complexity of runtime Module Federation.
* **Tailwind purge gotcha**: the host's `tailwind.config.ts`
  `content` glob must include
  `node_modules/@taskforce/<plugin>-ui/dist/**` or the plugin's
  utility classes get purged. Documented in the plugin README.
* **Type-only ambient declaration** (`ui/src/types/optional-plugins.d.ts`)
  needed so TypeScript can still typecheck the dynamic import even
  when the optional package is uninstalled.

### Alternatives considered

* **Vite Module Federation (runtime loading)**: rejected. Adds CSP
  surface, exposes a hosting requirement for federated chunks the
  pytaskforce backend does not provide, and risks double React copies
  via shared-module mismatches.
* **Host-Context primitive injection**: rejected. Forces every plugin
  component to consume context for trivial primitives, breaks
  tree-shaking, and only solves part of the Tailwind-purge problem
  (layout classes still come from plugin source).
* **Vendor enterprise UI inside `pytaskforce/ui/`**: rejected. Couples
  release cycles, violates the "lean core + optional enterprise"
  separation, and forces the host repo to track every plugin.

## Implementation references

| Concern | File |
|---|---|
| Plugin contract (Python) | `src/taskforce/application/plugin_loader.py` (`UIManifest`, `PluginProtocol.get_ui_manifest`, `collect_ui_manifests`) |
| Manifest endpoint | `src/taskforce/api/routes/ui.py`, schema in `src/taskforce/api/schemas/ui_manifest.py` |
| Host registry | `ui/src/plugins/registry.ts` |
| Manifest hook | `ui/src/plugins/useManifest.ts` |
| Loader | `ui/src/plugins/loader.ts` |
| Capability + RBAC guards | `ui/src/plugins/CapabilityGuard.tsx`, `ui/src/plugins/RequireRole.tsx` |
| Skew detector | `ui/src/plugins/skew.ts` |
| Bootstrap | `ui/src/app/AppBootstrap.tsx` |
| Sidebar merge | `ui/src/app/AppShell.tsx` |
| Router factory | `ui/src/app/router.tsx` |
| Shared design system | `packages/ui-shell/` (`@taskforce/ui-shell`) |
| Reference plugin | `packages/enterprise-ui-reference/` (`@taskforce/enterprise-ui`) |

## Tests

* `tests/unit/api/routes/test_ui_manifest.py` — unit + integration
  test of `collect_ui_manifests()` and the manifest endpoint, with a
  monkeypatched plugin registry simulating loaded plugins.
* `ui/src/plugins/registry.test.ts` — registry behavior incl.
  capability gating semantics.
* `ui/src/plugins/skew.test.ts` — semver-range parsing + skew
  detection.

## Documentation

* User-facing docs: [`docs/features/ui-plugins.md`](../features/ui-plugins.md)
* Reference plugin guide: `packages/enterprise-ui-reference/README.md`
