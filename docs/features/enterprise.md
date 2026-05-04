# Enterprise Integration Surface (Core Repository)

This page documents what **remains in `pytaskforce`** after enterprise product
features were moved to a separate repository.

## Current state

- Enterprise product modules (RBAC admin APIs, tenant/user lifecycle, compliance
  bundles, etc.) are **not implemented in this repo**.
- The open-source core intentionally provides extension points so those features
  can be attached from external packages/plugins without modifying core runtime
  behavior.

## Core contracts available in `pytaskforce`

1. **Interface/stub layer (hexagonal ports)**
   - `src/taskforce/core/interfaces/` contains protocol contracts used by the
     domain/application layers.
2. **Plugin integration hooks**
   - Plugin discovery and registration can add routes, tools, middleware, and
     UI capabilities at startup.
3. **Host/embedding surface**
   - `taskforce.host` exposes supported APIs for third-party embedding
     (standalone service, embedded FastAPI routes, or in-process library usage).
4. **Management UI capability negotiation**
   - `GET /api/v1/ui/manifest` exposes plugin-contributed UI manifests so the
     management UI can render optional feature modules dynamically.

## Why this split

This boundary keeps `pytaskforce` slim while preserving a stable, testable,
maintainable hexagonal core. Enterprise functionality can evolve independently
without coupling core release cadence to private/commercial modules.

## Related docs

- [Architecture Overview](../architecture.md)
- [Integration Guide](../integration-guide.md)
- [UI Plugin System](ui-plugins.md)
